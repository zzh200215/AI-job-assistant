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


def run_eval(eval_set: list[dict], top_k: int = 5) -> dict:
    """逐条评估并汇总指标。

    返回:
        {
          "total": int,
          "recall@K": float,
          "mrr": float,
          "keyword_hit_rate": float,
          "per_doc_type_recall": {doc_type: float},
          "details": [...]
        }
    """
    # 延迟 import，避免在无 DB/Chroma 环境崩溃
    from app.services.multi_recall import multi_recall

    recalls = []
    rrs = []
    khits = []
    type_hit_counts: dict[str, int] = {}
    type_total_counts: dict[str, int] = {}
    details = []

    for idx, item in enumerate(eval_set):
        query = item["query"]
        expected_types = item.get("expected_doc_types", [])
        expected_keywords = item.get("expected_keywords", [])

        try:
            results = multi_recall(query, top_k=top_k)
        except Exception as exc:
            logger.warning("query=%r 检索失败: %s", query, exc)
            results = []

        retrieved_types = list(dict.fromkeys(r.get("doc_type", "") for r in results if r.get("doc_type")))
        texts = [r.get("text", "") for r in results]

        r = recall_at_k(retrieved_types, expected_types)
        rr = reciprocal_rank(retrieved_types, expected_types)
        kh = keyword_hit_rate(texts, expected_keywords)

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
                "recall": round(r, 3),
                "rr": round(rr, 3),
                "keyword_hit": round(kh, 3),
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

    report = {
        "total": len(eval_set),
        f"recall@{top_k}": round(sum(recalls) / len(recalls), 3) if recalls else 0,
        "mrr": round(sum(rrs) / len(rrs), 3) if rrs else 0,
        "keyword_hit_rate": round(sum(khits) / len(khits), 3) if khits else 0,
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
) -> list[str]:
    """Return human-readable threshold failures for a completed RAG report."""
    failed = []
    recall_key = f"recall@{top_k}"
    recall_value = report[recall_key]
    if min_recall is not None and recall_value < min_recall:
        failed.append(f"{recall_key} {recall_value} < {min_recall}")
    if min_mrr is not None and report["mrr"] < min_mrr:
        failed.append(f"mrr {report['mrr']} < {min_mrr}")
    if min_keyword_hit is not None and report["keyword_hit_rate"] < min_keyword_hit:
        failed.append(f"keyword_hit_rate {report['keyword_hit_rate']} < {min_keyword_hit}")
    return failed


# ===================== CLI =====================


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
    args = parser.parse_args()

    eval_set = load_eval_set(args.eval_set)
    logger.info("加载评估集 %d 条 from %s", len(eval_set), args.eval_set)

    if args.sample:
        eval_set = eval_set[: args.sample]
        logger.info("截取前 %d 条", args.sample)

    report = run_eval(eval_set, top_k=args.top_k)
    report["report_type"] = "rag"
    report["run_meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_set": str(Path(args.eval_set).resolve()),
        "top_k": args.top_k,
        "sample": args.sample,
        "thresholds": {
            "min_recall": args.min_recall,
            "min_mrr": args.min_mrr,
            "min_keyword_hit": args.min_keyword_hit,
        },
    }

    # 打印摘要
    print("\n" + "=" * 50)
    print(f"RAG 评估报告  (共 {report['total']} 条, recall@{args.top_k})")
    print("=" * 50)
    print(f"  Recall@{args.top_k}        : {report[f'recall@{args.top_k}']}")
    print(f"  MRR              : {report['mrr']}")
    print(f"  Keyword Hit Rate : {report['keyword_hit_rate']}")
    print()
    print("  Per Doc-Type Recall:")
    for t, v in report["per_doc_type_recall"].items():
        print(f"    {t:20s} : {v}")
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
    )

    if failed:
        print("[FAIL] RAG eval thresholds not met:")
        for item in failed:
            print(f"  - {item}")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
