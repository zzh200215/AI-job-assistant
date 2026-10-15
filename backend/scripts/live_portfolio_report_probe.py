"""跑一份真简历的组合分析：量三发用时、复核拒了什么、换皮判据的假阳性率。

安全口径（一次没做好就是往他真库里写数据）：
* 先建同机临时库 `portfolio_report_live_probe`，`os.environ["DATABASE_URL"]` 在 **import app 之前**
  指过去，并在动手前 assert `engine.url.database` 真是那一个；
* 从 llmXM **只读**一条真简历，复制进临时库；全程不 INSERT 到 llmXM；
* 口令只在这里拼接、一次都不打印；渲染出的 HTML 落到**仓库外**目录，PII 不进树；
* 结束时 DROP 临时库（放在 `finally` 里，两条提前退出路径也删——D236 现撞过一次），
  并各用一条**新连接**读 llmXM 的表数与探针痕迹做前后对照。

这一支还额外量一件事：**换皮那条判据在真简历上的假阳性率**。
`NEAR_COPY_THRESHOLD = 0.85` 是本仓库反推待定的数，它只出证据不判出局正是因为它没在真样本上量过；
这条探针把每一对项目的相似度都打出来，量出来贴近 0.85 的合法对子多了，阈值就该抬。

跑法：
  cd backend && ./.venv/Scripts/python.exe scripts/live_portfolio_report_probe.py                     # 真 provider，会花钱
  cd backend && PROBE_PROVIDER=mock ./.venv/Scripts/python.exe scripts/live_portfolio_report_probe.py  # 零花费，只验链路
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUTSIDE = Path("D:/AI/llmXM/_live_portfolio_reports")

env = {}
with open(BACKEND / ".env", encoding="utf-8", errors="replace") as handle:
    for line in handle:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"')

HOST = env["MYSQL_HOST"]
PORT = env.get("MYSQL_PORT", "3306")
USER = env["MYSQL_USER"]
PASSWORD = env["MYSQL_PASSWORD"]
SOURCE_DB = env["MYSQL_DB"]
TEMP_DB = "portfolio_report_live_probe"

os.environ["DATABASE_URL"] = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{TEMP_DB}?charset=utf8mb4"
os.environ["APP_ENV"] = "development"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["LLM_PROVIDER"] = os.environ.get("PROBE_PROVIDER") or env.get("LLM_PROVIDER", "mock")
os.environ["EMBEDDING_PROVIDER"] = env.get("EMBEDDING_PROVIDER", "mock")
os.environ["REDIS_URL"] = ""
os.environ["RUN_SCHEDULER"] = "false"

sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

SOURCE_URL = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{SOURCE_DB}?charset=utf8mb4"
SERVER_URL = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/?charset=utf8mb4"


def source_table_count() -> int:
    eng = create_engine(SOURCE_URL)
    try:
        with eng.connect() as conn:
            return int(
                conn.execute(
                    text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:d"), {"d": SOURCE_DB}
                ).scalar()
            )
    finally:
        eng.dispose()


def probe_footprint_in_source() -> tuple[int, int]:
    """llmXM 里有没有探针留下的痕迹（用户/简历）。"""
    eng = create_engine(SOURCE_URL)
    try:
        with eng.connect() as conn:
            users = int(conn.execute(text("SELECT COUNT(*) FROM tb_user WHERE username LIKE 'live_pf_%'")).scalar())
            resumes = int(conn.execute(text("SELECT COUNT(*) FROM tb_resume WHERE file_name LIKE 'live_pf%'")).scalar())
        return users, resumes
    finally:
        eng.dispose()


def drop_temp() -> None:
    eng = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{TEMP_DB}`"))
    eng.dispose()


print("== 前置对照：llmXM ==")
before_tables = source_table_count()
before_footprint = probe_footprint_in_source()
print(f"  表数 {before_tables}  探针痕迹 {before_footprint}")

server = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
with server.connect() as conn:
    conn.execute(text(f"DROP DATABASE IF EXISTS `{TEMP_DB}`"))
    conn.execute(text(f"CREATE DATABASE `{TEMP_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
server.dispose()

import app.models  # noqa: E402, F401  —— 注册全部模型
from app.core.config import settings  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.history import Resume  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import portfolio_report_rubric as rubric  # noqa: E402
from app.services import portfolio_report_service as svc  # noqa: E402
from app.services.portfolio_report_html import render_portfolio_report_html  # noqa: E402

assert engine.url.database == TEMP_DB, (engine.url.database, TEMP_DB)
assert settings.DATABASE_URL.endswith(TEMP_DB + "?charset=utf8mb4"), settings.DATABASE_URL[-40:]
print(f"== 写侧引擎指向临时库 {engine.url.database}，provider={os.environ['LLM_PROVIDER']} ==")

Base.metadata.create_all(bind=engine)

source = create_engine(SOURCE_URL)
Session = sessionmaker(bind=engine)
db = Session()
EXIT_CODE = 0
try:
    chosen = None
    try:
        with source.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT id, name, parsed_json, file_name FROM tb_resume "
                        "WHERE parsed_json IS NOT NULL ORDER BY id DESC LIMIT 60"
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                parsed = row["parsed_json"]
                if isinstance(parsed, str):
                    try:
                        parsed = json.loads(parsed)
                    except json.JSONDecodeError:
                        continue
                projects = [p for p in ((parsed or {}).get("project_experience") or []) if isinstance(p, dict)]
                if len(projects) < 2:
                    continue
                total = sum(len(str(p.get("desc") or "")) for p in projects)
                chosen = (int(row["id"]), str(row["name"] or ""), parsed, projects, total)
                break
    finally:
        source.dispose()

    if chosen is None:
        print("近 60 条真简历里没有一条带两个以上项目的 —— 这一支验不了，需要人先传一份多项目简历")
        raise SystemExit(3)

    resume_id_src, name, parsed, projects, total_chars = chosen
    print(f"== 取用源简历 id={resume_id_src} 项目数={len(projects)} 项目正文合计={total_chars} 字 ==")
    for index, entry in enumerate(projects):
        print(f"   PJ-{index + 1:02d} {str(entry.get('name') or '')[:24]} 正文 {len(str(entry.get('desc') or ''))} 字")

    user = User(
        username="live_pf_run",
        email="live_pf_run@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.flush()
    resume = Resume(
        name=name,
        file_name="live_pf.pdf",
        file_path="uploads/live_pf.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json=parsed,
    )
    db.add(resume)
    db.commit()
    target_resume_id = resume.id
    indices = list(range(len(projects)))

    # 换皮判据的假阳性测量：真简历上每一对项目折叠后有多像。
    texts = {index: str(entry.get("desc") or "") for index, entry in enumerate(projects)}
    print("== 换皮判据在真简历上的形状（这一条是阈值要不要抬的依据）==")
    for left, right in ((a, b) for position, a in enumerate(indices) for b in indices[position + 1 :]):
        print(
            f"   PJ-{left + 1:02d} × PJ-{right + 1:02d} 相似度 {rubric.pair_similarity(texts[left], texts[right])}"
            f"  （阈值 {rubric.NEAR_COPY_THRESHOLD}）"
        )
    print(f"   完全相同的那几对：{rubric.duplicate_pairs(texts)}")

    print("== 前三节（组合档案 / 组合图解 / 使用建议，三发）==")
    t0 = time.time()
    report = svc.generate_portfolio_report(db, target_resume_id, indices, user_id=user.id)
    elapsed_report = time.time() - t0
    print(
        f"  用时 {elapsed_report:.1f}s  合计 {report.score_cell()}  评级 {report.grade}  "
        f"难度 {report.difficulty.get('level')}  项目数 {report.project_count}"
    )
    print(f"  表头单项目均分那一格：{report.average_cell()}")
    print(f"  命中红线 {[row['key'] for row in report.excluded_by]}")
    print(f"  横向对比 {len(report.compare.get('rows') or [])} 行 / 能力覆盖 {len(report.capabilities)} 行")
    stack = report.stack_reuse
    print(f"  共用栈 {stack.get('shared_count')} 只 / 交集比例 {stack.get('shared_ratio')}")
    print(f"  阶段失败 {report.stage_errors}")
    print(f"  出处 { {k: (v or {}).get('source') for k, v in report.provenance.items()} }")
    counts: dict[str, int] = {}
    for row in report.red_line_rejected + report.diagram_rejected + report.advice_rejected:
        counts[str(row.get("reason"))] = counts.get(str(row.get("reason")), 0) + 1
    print(f"  前三节被拒计数 {counts or '（零拒因）'}")

    print("== 第四节（跨项目 12 题，一发）==")
    t1 = time.time()
    questions = svc.build_questions(db.get(Resume, target_resume_id), report)
    elapsed_q = time.time() - t1
    dist = questions.get("distribution") or {}
    print(
        f"  用时 {elapsed_q:.1f}s  共 {dist.get('total')} 题（目标 {dist.get('target')}）"
        f" 可答 {dist.get('answerable')} 需补强 {dist.get('weak')} 高危 {dist.get('high_risk')}"
    )
    print(f"  题型分布 {dist.get('by_kind')}")
    qcounts: dict[str, int] = {}
    for row in report.questions_rejected:
        qcounts[str(row.get("reason"))] = qcounts.get(str(row.get("reason")), 0) + 1
    print(f"  第四节被拒计数 {qcounts or '（零拒因）'}")
    report.questions = questions

    print("== 交付前机检 ==")
    html = render_portfolio_report_html(report)
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    out = OUTSIDE / f"live_portfolio_report_{int(time.time())}.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    print(f"  过检，HTML {len(html.encode('utf-8')) / 1024:.1f} KB 写到仓库外：{out}")
except SystemExit as exc:  # 找不到数据也要把临时库删掉
    EXIT_CODE = int(exc.code or 0)
except RuntimeError as exc:
    print(f"  未过检：{exc}")
    EXIT_CODE = 4
finally:
    db.close()
    drop_temp()
    print("== 收尾对照：llmXM ==")
    after_tables = source_table_count()
    after_footprint = probe_footprint_in_source()
    print(f"  表数 {before_tables} -> {after_tables}  探针痕迹 {before_footprint} -> {after_footprint}")
    eng = create_engine(SOURCE_URL)
    try:
        with eng.connect() as conn:
            alembic = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            has_table = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema=:d AND table_name='portfolio_report_job'"
                    ),
                    {"d": SOURCE_DB},
                ).scalar()
            )
    finally:
        eng.dispose()
    print(f"  llmXM 的 alembic 版本 {alembic}（组合表在 llmXM 里：{has_table}，应为 0）")
    leftover = create_engine(SERVER_URL)
    try:
        with leftover.connect() as conn:
            n = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name LIKE '%live_probe%'")
                ).scalar()
            )
    finally:
        leftover.dispose()
    print(f"  临时库残留 {n}（应为 0）")

raise SystemExit(EXIT_CODE)
