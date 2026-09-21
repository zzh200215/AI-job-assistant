#!/usr/bin/env python
"""给 RAG 评估门装一份一次性语料：真入库链路，零外部服务。

为什么需要它：`scripts/eval_rag.py` 要量检索质量，就得有一个能查的库。CI 里没有
MySQL，干净检出的 `backend/chroma_db` 是空的，所以那道门只能以"数据库不可用"退出码 2
——明确地红，却仍然什么都没测。这里把仓库自带的 `docs/knowledge-seeds/` 走一遍
**真实入库路径**（落盘 → 解析 → 切片 → embedding → 写 Chroma → 建 knowledge_document 行），
装进一个临时 SQLite 文件和一个临时 Chroma 目录。

embedding 用 mock provider：它按文本 hash 出伪向量，可复现但没有语义。所以这份语料
能测的是词法（BM25）召回、RRF 融合、可见性裁剪这条链路，测不出语义向量质量——
后者只能在有真 embedding 的环境里量，不要用这道门假装量过。

用法（在 backend/ 下运行；env 由 CI 或调用方给出）：
    DATABASE_URL=sqlite:///./rag_ci.sqlite3 CHROMA_DIR=./rag_ci_chroma \
    EMBEDDING_PROVIDER=mock LLM_PROVIDER=mock \
      python scripts/seed_rag_corpus.py

退出码：0 成功；1 参数/环境不对（含"目标看起来是真库"）；2 有文档入库失败或语料为空。
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SEED_ROOT = _ROOT.parent / "docs" / "knowledge-seeds"


def guard_scratch_target(allow_non_scratch: bool = False) -> str:
    """只允许往临时 SQLite 里灌语料，除非显式 --force。

    这个脚本会建表并写行，误指向开发/生产 MySQL 就是往真库里塞 16 篇种子文档 + 一个
    机器人用户，而且没有对应的清理入口。
    """
    from app.core.config import settings

    url = settings.database_url
    if not url.startswith("sqlite:") and not allow_non_scratch:
        print(f"[ERROR] 目标不是临时 SQLite（协议 {url.split('://')[0]}://），拒绝写入。")
        print("        这道门要的是可复现的一次性语料；确实要写这个库请加 --force。")
        raise SystemExit(1)
    return url


def ensure_schema_and_user(username: str) -> int:
    """建表 + 准备评估用户，返回 user_id。"""
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(_type, _compiler, **_kwargs):
        # SQLite 里只有 "INTEGER PRIMARY KEY" 是 rowid 别名（会自增），BIGINT 不是。
        # 根目录 conftest.py 为测试做了同一个转换；临时库也要它，否则主键拿不到值。
        return "INTEGER"

    import app.models  # noqa: F401  注册全部模型到 Base.metadata
    from app.core.database import Base, SessionLocal, engine
    from app.core.security import hash_password
    from app.core.user_roles import CANDIDATE_ROLE
    from app.models.user import User

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            # 密码随机：这个用户只给评估当可见性口径用，不该能登录。
            user = User(
                username=username,
                email=f"{username}@example.invalid",
                password=hash_password(secrets.token_urlsafe(24)),
                role=CANDIDATE_ROLE,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[OK]   评估用户 {user.username} id={user.id} role={user.role}")
        else:
            print(f"[SKIP] 评估用户已存在 {user.username} id={user.id} role={user.role}")
        return user.id
    finally:
        db.close()


def seed_documents() -> tuple[int, int, int, int]:
    """把 docs/knowledge-seeds 灌进库。返回 (新增, 跳过, 失败, 新增切片数)。

    复用运维脚本 `import_knowledge.py` 的同一套 helper（文件枚举、标题、去重判定），
    所以这里入库的东西和手工执行 import_knowledge_seeds.py 的结果一致。
    """
    from app.core.database import SessionLocal
    from app.services import knowledge_service
    from scripts.import_knowledge import default_title, exists, iter_files
    from scripts.import_knowledge_seeds import SEED_MAPPINGS

    if not SEED_ROOT.exists():
        print(f"[ERROR] 种子目录不存在: {SEED_ROOT}")
        raise SystemExit(1)

    imported = skipped = failed = chunks = 0
    db = SessionLocal()
    try:
        for folder_name, doc_type in SEED_MAPPINGS:
            folder = SEED_ROOT / folder_name
            if not folder.exists():
                print(f"[WARN] 缺少种子目录，跳过: {folder}")
                continue
            for path in iter_files(folder, recursive=True):
                title = default_title(path)
                if exists(db, title=title, file_name=path.name, doc_type=doc_type):
                    skipped += 1
                    continue
                # user_id=None + 无 organization：文档落进租户级可见范围，
                # 评估用户（非管理员）因此能查到，而且检索真的走了一遍可见性集合的裁剪。
                doc = knowledge_service.save_and_process(
                    db,
                    path.read_bytes(),
                    path.name,
                    title,
                    doc_type,
                    user_id=None,
                )
                if doc.status == "ready":
                    imported += 1
                    chunks += doc.chunk_count or 0
                    print(f"[OK]   {folder_name}/{path.name} -> doc_id={doc.id} chunks={doc.chunk_count}")
                else:
                    failed += 1
                    print(f"[FAIL] {folder_name}/{path.name} -> {doc.error_msg}")
    finally:
        db.close()
    return imported, skipped, failed, chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a scratch knowledge corpus for the RAG eval gate")
    parser.add_argument("--username", default="rag_eval_bot", help="评估用的用户名（非管理员，见模块说明）")
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许对非 SQLite 的 DATABASE_URL 写入（默认拒绝：本机开发库是 MySQL，别把种子文档塞进去）",
    )
    args = parser.parse_args()

    print(f"[INFO] 目标库: {guard_scratch_target(args.force)}")
    from app.core.chroma_client import get_knowledge_collection, resolve_chroma_dir

    print(f"[INFO] Chroma 目录: {resolve_chroma_dir()}")

    user_id = ensure_schema_and_user(args.username)
    imported, skipped, failed, chunks = seed_documents()
    live = get_knowledge_collection().count()

    print(
        f"[DONE] imported={imported} skipped={skipped} failed={failed} "
        f"新增切片={chunks} collection.count={live} user_id={user_id}"
    )
    if failed:
        return 2
    if live == 0:
        print("[ERROR] 语料为空，评估无从进行")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
