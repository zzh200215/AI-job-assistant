"""RAG 检索质量评估脚本

用法（在 backend/ 目录下运行）：
    python scripts/eval_rag.py                     # 默认加载 tests/eval/rag_eval.jsonl
    python scripts/eval_rag.py --top-k 5           # 指定 recall@K 的 K
    python scripts/eval_rag.py --sample 10          # 只跑前 10 条
    python scripts/eval_rag.py --output report.json # 输出 JSON 报告

输出指标：
  - recall@K   : 期望 doc_type 在 top-K 结果中出现的比例
  - mrr        : Mean Reciprocal Rank（期望 doc_type 首次出现的倒数排名均值）
  - keyword_hit: 期望关键词在检索结果文本中命中的比例
  - per_doc_type_recall : 每个 doc_type 的独立召回率
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根目录在 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval_rag")


# ===================== 加载评估集 =====================


def load_eval_set(path: str) -> list[dict]:
    """加载 JSONL 格式的评估集。"""
    items = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("跳过无效行 %d: %s", line_no, e)
    return items


# ===================== 指标计算 =====================


def recall_at_k(retrieved_types: list[str], expected_types: list[str]) -> float:
    """期望 doc_type 在检索结果中出现的比例。"""
    if not expected_types:
        return 1.0
    hit = sum(1 for t in expected_types if t in retrieved_types)
    return hit / len(expected_types)


def reciprocal_rank(retrieved_types: list[str], expected_types: list[str]) -> float:
    """期望 doc_type 在检索结果中首次出现的倒数排名。"""
    for i, t in enumerate(retrieved_types):
        if t in expected_types:
            return 1.0 / (i + 1)
    return 0.0


def keyword_hit_rate(texts: list[str], expected_keywords: list[str]) -> float:
    """期望关键词在检索结果文本中命中的比例。"""
    if not expected_keywords:
        return 1.0
    combined = " ".join(texts).lower()
    hit = sum(1 for kw in expected_keywords if kw.lower() in combined)
    return hit / len(expected_keywords)


# ===================== 主评估循环 =====================


def run_eval(eval_set: list[dict], top_k: int = 5, *, db=None, user_id: int | None = None) -> dict:
    """逐条评估并汇总指标。

    `db` 必传：`multi_recall` 在没有会话时会 fail-closed 直接返回空
    （没有会话就没法做租户/用户可见性过滤）。以前这个脚本不带 db 就调它，于是
    每一条都拿到空结果、recall 恒为 0.0——这道门从来没有量过检索质量。

    检索抛异常的 query **不参与指标计算**，单独计数：以前它们被记成"召回 0"，
    于是"库连不上/没权限"和"检索到了但不相关"在报告里长得一模一样。
    全部 query 都异常时指标是 None（没测出）而不是 0.0（测了，很差）。

    返回:
        {
          "total": int,
          "retrieved": int,             # 真正拿到检索结果的条数
          "retrieval_errors": int,      # 抛异常的条数
          "empty_results": int,         # 没抛异常但一条都没召回
          "error_samples": [str],
          "recall@K": float | None,
          "mrr": float | None,
          "keyword_hit_rate": float | None,
          "per_doc_type_recall": {doc_type: float},
          "details": [...]
        }
    """
    # 延迟 import，避免在无 DB/Chroma 环境崩溃
    from app.services.multi_recall import multi_recall

    recalls = []
    rrs = []
    khits = []
    errors: list[tuple[str, str]] = []
    empty_results = 0
    type_hit_counts: dict[str, int] = {}
    type_total_counts: dict[str, int] = {}
    details = []

    for idx, item in enumerate(eval_set):
        query = item["query"]
        expected_types = item.get("expected_doc_types", [])
        expected_keywords = item.get("expected_keywords", [])

        error = None
        try:
            results = multi_recall(query, db=db, user_id=user_id, top_k=top_k)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
            errors.append((query, error))
            logger.warning("query=%r 检索失败: %s", query, exc)
            results = []

        retrieved_types = list(dict.fromkeys(r.get("doc_type", "") for r in results if r.get("doc_type")))
        texts = [r.get("text", "") for r in results]

        if error is None and not results:
            empty_results += 1

        r = recall_at_k(retrieved_types, expected_types)
        rr = reciprocal_rank(retrieved_types, expected_types)
        kh = keyword_hit_rate(texts, expected_keywords)

        if error is None:
            recalls.append(r)
            rrs.append(rr)
            khits.append(kh)

            for t in expected_types:
                type_total_counts[t] = type_total_counts.get(t, 0) + 1
                if t in retrieved_types:
                    type_hit_counts[t] = type_hit_counts.get(t, 0) + 1

        details.append(
            {
                "query": query,
                "error": error,
                "recall": round(r, 3) if error is None else None,
                "rr": round(rr, 3) if error is None else None,
                "keyword_hit": round(kh, 3) if error is None else None,
                "retrieved_types": retrieved_types,
                "expected_types": expected_types,
            }
        )

        if (idx + 1) % 10 == 0:
            logger.info("已评估 %d/%d ...", idx + 1, len(eval_set))

    # per doc_type recall
    per_type = {}
    for t in sorted(type_total_counts):
        per_type[t] = round(type_hit_counts.get(t, 0) / type_total_counts[t], 3)

    scored = len(recalls)
    report = {
        "total": len(eval_set),
        "retrieved": scored,
        "retrieval_errors": len(errors),
        "empty_results": empty_results,
        "error_samples": [f"{query}: {error}" for query, error in errors][:3],
        f"recall@{top_k}": round(sum(recalls) / scored, 3) if scored else None,
        "mrr": round(sum(rrs) / scored, 3) if scored else None,
        "keyword_hit_rate": round(sum(khits) / scored, 3) if scored else None,
        "per_doc_type_recall": per_type,
        "details": details,
    }
    return report


def check_thresholds(
    report: dict,
    *,
    top_k: int,
    min_recall: float | None = None,
    min_mrr: float | None = None,
    min_keyword_hit: float | None = None,
    max_retrieval_errors: int | None = 0,
) -> list[str]:
    """Return human-readable failure reasons for a completed RAG report.

    `max_retrieval_errors` 默认 0：只要有任何一条 query 是"检索直接抛异常"，
    这份报告就不能算测过——先报这条，再谈阈值。
    """
    failed = []
    errors = report.get("retrieval_errors", 0)
    if max_retrieval_errors is not None and errors > max_retrieval_errors:
        samples = "; ".join(report.get("error_samples", []))
        failed.append(
            f"retrieval_errors {errors} > {max_retrieval_errors}（{report['total']} 条里 {errors} 条检索直接抛异常，"
            f"指标不算测出。样例：{samples or '无'}）"
        )

    recall_key = f"recall@{top_k}"
    for key, floor in ((recall_key, min_recall), ("mrr", min_mrr), ("keyword_hit_rate", min_keyword_hit)):
        if floor is None:
            continue
        value = report.get(key)
        if value is None:
            failed.append(f"{key} 未测出（没有一条 query 拿到可用检索结果），门槛 {floor} 无从比较")
        elif value < floor:
            failed.append(f"{key} {value} < {floor}")
    return failed


# ===================== CLI =====================


def resolve_eval_user(db, requested: int | None) -> tuple[int | None, str]:
    """评估按哪个身份的可见范围检索；返回 (user_id, 说明)。

    找不到身份就返回 (None, 原因)——绝不能退回"不带 db 调用"，那条路会被
    `multi_recall` fail-closed 成空结果，看起来像 recall=0 的质量问题。
    管理员优先（全量可见）；没有管理员时挑一个真的看得到知识文档的用户，并把这个
    口径写进报告，免得"评估用的是谁的权限"变成隐变量。
    """
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.config import settings
    from app.core.user_roles import ADMIN_ROLE
    from app.models.user import User
    from app.utils.knowledge_access import get_visible_knowledge_doc_ids

    def describe(user, visible) -> str:
        scope = "全量可见" if visible is None else f"可见 {len(visible)} 篇知识文档"
        return f"{user.username}(id={user.id}) 的可见范围：{scope}"

    try:
        if requested is not None:
            user = db.get(User, requested)
            if user is None:
                return None, f"--user-id {requested} 在库里不存在"
            visible = get_visible_knowledge_doc_ids(db, user_id=user.id)
            if visible is not None and not visible:
                return None, f"{user.username}(id={user.id}) 看不到任何知识文档，评估会恒为 0"
            return user.id, describe(user, visible)

        candidates = []
        for username in settings.admin_usernames_list:
            user = db.query(User).filter(User.username == username).first()
            if user is not None:
                candidates.append(user)
        candidates.extend(
            db.query(User).filter(User.role == ADMIN_ROLE, User.id.notin_([u.id for u in candidates])).all()
        )
        # 没有管理员就退而求其次：按 id 顺序找一个看得到文档的普通用户
        candidates.extend(db.query(User).order_by(User.id).limit(20).all())

        seen: set[int] = set()
        ordered: list[User] = []
        for user in candidates:
            if user.id not in seen:
                seen.add(user.id)
                ordered.append(user)

        for user in ordered:
            visible = get_visible_knowledge_doc_ids(db, user_id=user.id)
            if visible is None or visible:
                return user.id, describe(user, visible)
        return None, f"查了 {len(ordered)} 个用户，没有一个能看到知识文档（知识库为空？），评估无法进行"
    except SQLAlchemyError as exc:
        return None, f"读取用户失败（数据库不可用？）：{type(exc).__name__}: {str(exc)[:160]}"


def main():
    parser = argparse.ArgumentParser(description="RAG 检索质量评估")
    parser.add_argument(
        "--eval-set", default=str(_PROJECT_ROOT / "tests" / "eval" / "rag_eval.jsonl"), help="评估集 JSONL 路径"
    )
    parser.add_argument("--top-k", type=int, default=5, help="recall@K 的 K 值")
    parser.add_argument("--sample", type=int, default=None, help="只跑前 N 条")
    parser.add_argument("--output", default=None, help="输出 JSON 报告路径")
    parser.add_argument("--min-recall", type=float, default=None, help="Fail if recall@K is below this threshold")
    parser.add_argument("--min-mrr", type=float, default=None, help="Fail if MRR is below this threshold")
    parser.add_argument(
        "--min-keyword-hit", type=float, default=None, help="Fail if keyword hit rate is below this threshold"
    )
    parser.add_argument(
        "--max-retrieval-errors",
        type=int,
        default=0,
        help="允许多少条 query 在检索阶段直接抛异常（默认 0：一条都不允许，指标才算测出）",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="以哪个用户的可见范围检索；默认取 ADMIN_USERNAMES 里的管理员（全量可见）",
    )
    args = parser.parse_args()

    eval_set = load_eval_set(args.eval_set)
    logger.info("加载评估集 %d 条 from %s", len(eval_set), args.eval_set)

    if args.sample:
        eval_set = eval_set[: args.sample]
        logger.info("截取前 %d 条", args.sample)

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        user_id, identity = resolve_eval_user(db, args.user_id)
        if user_id is None:
            print(f"[FAIL] 无法确定评估身份：{identity}")
            return 2
        logger.info("检索可见范围按 %s (user_id=%s)", identity, user_id)
        report = run_eval(eval_set, top_k=args.top_k, db=db, user_id=user_id)
    finally:
        db.close()

    report["report_type"] = "rag"
    report["run_meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_set": str(Path(args.eval_set).resolve()),
        "top_k": args.top_k,
        "sample": args.sample,
        "retrieval_identity": identity,
        "thresholds": {
            "min_recall": args.min_recall,
            "min_mrr": args.min_mrr,
            "min_keyword_hit": args.min_keyword_hit,
            "max_retrieval_errors": args.max_retrieval_errors,
        },
    }

    # 打印摘要
    print("\n" + "=" * 50)
    print(f"RAG 评估报告  (共 {report['total']} 条, recall@{args.top_k}, 口径 {identity})")
    print("=" * 50)
    print(
        f"  检索成功        : {report['retrieved']} 条"
        f"（异常 {report['retrieval_errors']} 条，空结果 {report['empty_results']} 条）"
    )
    print(f"  Recall@{args.top_k}        : {report[f'recall@{args.top_k}']}")
    print(f"  MRR              : {report['mrr']}")
    print(f"  Keyword Hit Rate : {report['keyword_hit_rate']}")
    print()
    print("  Per Doc-Type Recall:")
    for t, v in report["per_doc_type_recall"].items():
        print(f"    {t:20s} : {v}")
    if report["error_samples"]:
        print("  检索异常样例:")
        for sample in report["error_samples"]:
            print(f"    {sample}")
    print("=" * 50)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("报告已写入 %s", out_path)

    failed = check_thresholds(
        report,
        top_k=args.top_k,
        min_recall=args.min_recall,
        min_mrr=args.min_mrr,
        min_keyword_hit=args.min_keyword_hit,
        max_retrieval_errors=args.max_retrieval_errors,
    )

    if failed:
        print("[FAIL] RAG eval 未通过：")
        for item in failed:
            print(f"  - {item}")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
