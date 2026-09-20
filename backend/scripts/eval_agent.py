"""Agent 匹配质量评估脚本

用法（在 backend/ 目录下运行，需要启动 DB）：
    python scripts/eval_agent.py                          # 默认加载 tests/eval/agent_eval.jsonl
    python scripts/eval_agent.py --sample 5               # 只跑前 5 条
    python scripts/eval_agent.py --output report.json     # 输出 JSON 报告

输出指标：
  - mae            : Mean Absolute Error（预测分数 vs 人工标注）
  - spearman_rho   : Spearman 等级相关系数（排序一致性）
  - score_dist     : 分数偏差分布（偏高/偏低/命中）
  - per_pair_detail: 每对详情

评估逻辑：
  将每条 eval record 的 resume_profile / jd_profile 直接喂给 match_agent，
  对比输出的 match_score 与 expected_match_score。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval_agent")


def load_eval_set(path: str) -> list[dict]:
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


def compute_mae(predicted: list[float], actual: list[float]) -> float:
    n = len(predicted)
    if n == 0:
        return 0.0
    return sum(abs(p - a) for p, a in zip(predicted, actual, strict=False)) / n


def compute_spearman(predicted: list[float], actual: list[float]) -> float:
    """Spearman 等级相关系数（简化实现，无需 scipy）。"""
    n = len(predicted)
    if n < 2:
        return 0.0

    def rank(vals: list[float]) -> list[float]:
        indexed = sorted(enumerate(vals), key=lambda x: x[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
                j += 1
            avg_rank = sum(i2 + 1 for i2 in range(i, j + 1)) / (j - i + 1)
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    r_pred = rank(predicted)
    r_actual = rank(actual)

    d_sq_sum = sum((rp - ra) ** 2 for rp, ra in zip(r_pred, r_actual, strict=False))
    return 1 - (6 * d_sq_sum) / (n * (n**2 - 1))


def run_eval(eval_set: list[dict]) -> dict:
    """逐条用 match_agent 的 prompt 直接获取分数，与人工标注对比。"""
    from app.prompts.match_agent import MATCH_AGENT_PROMPT
    from app.services.llm_service import chat_json
    from app.services.match_score_calibration import apply_match_score_cap

    predicted_scores = []
    actual_scores = []
    details = []
    errors: list[tuple[str, str]] = []

    for idx, item in enumerate(eval_set):
        pair_id = item.get("id", f"pair_{idx}")
        resume_profile = item["resume_profile"]
        jd_profile = item["jd_profile"]
        expected_score = item["expected_match_score"]

        # MATCH_AGENT_PROMPT 用 {resume_report}/{job_report}/{rag_context} 占位
        error = None
        predicted = None
        try:
            prompt = MATCH_AGENT_PROMPT.format(
                resume_report=json.dumps({"summary": resume_profile}, ensure_ascii=False),
                job_report=json.dumps({"summary": jd_profile}, ensure_ascii=False),
                rag_context="（本次评估不注入 RAG 上下文）",
            )
            result = chat_json(prompt)
            apply_match_score_cap(result, resume_profile, jd_profile)
            predicted = int(result.get("match_score", 0))
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
            errors.append((pair_id, error))
            logger.warning("pair=%s 评估失败: %s", pair_id, exc)

        if error is None:
            predicted_scores.append(float(predicted))
            actual_scores.append(float(expected_score))
            diff = predicted - expected_score
            details.append(
                {
                    "id": pair_id,
                    "error": None,
                    "predicted": predicted,
                    "expected": expected_score,
                    "diff": diff,
                    "label": "hit" if abs(diff) <= 10 else ("over" if diff > 0 else "under"),
                }
            )
        else:
            # 失败的那条不进 MAE/Spearman：以前写 predicted=0，等于把"没测出来"
            # 当成"模型给了 0 分"，误差与秩相关都被污染
            details.append(
                {
                    "id": pair_id,
                    "error": error,
                    "predicted": None,
                    "expected": expected_score,
                    "diff": None,
                    "label": "errored",
                }
            )

        if (idx + 1) % 5 == 0:
            logger.info("已评估 %d/%d ...", idx + 1, len(eval_set))

    scored = len(predicted_scores)
    mae = compute_mae(predicted_scores, actual_scores) if scored else None
    # 秩相关至少要有两个点，否则 compute_spearman 只会返回它自己的 0.0 占位值
    rho = compute_spearman(predicted_scores, actual_scores) if scored >= 2 else None

    over = sum(1 for d in details if d["label"] == "over")
    under = sum(1 for d in details if d["label"] == "under")
    hit = sum(1 for d in details if d["label"] == "hit")

    report = {
        "total": len(eval_set),
        "scored": scored,
        "eval_errors": len(errors),
        "error_samples": [f"{pid}: {e}" for pid, e in errors][:3],
        "mae": round(mae, 2) if mae is not None else None,
        "spearman_rho": round(rho, 3) if rho is not None else None,
        "score_dist": {"hit_tol10": hit, "over": over, "under": under, "errored": len(errors)},
        "details": details,
    }
    return report


def check_thresholds(
    report: dict,
    *,
    max_mae: float | None = None,
    min_spearman: float | None = None,
    min_hit_tol10: int | None = None,
    max_errors: int | None = 0,
) -> list[str]:
    """Return human-readable failure reasons for a completed Agent report.

    `max_errors` 默认 0：有 pair 根本没跑出分数时，MAE/ρ 是残缺样本上的数字，
    先把这条报出来再谈阈值。
    """
    failed = []
    errors = report.get("eval_errors", 0)
    if max_errors is not None and errors > max_errors:
        samples = "; ".join(report.get("error_samples", []))
        failed.append(
            f"eval_errors {errors} > {max_errors}（{report['total']} 条里 {errors} 条没跑出预测分，"
            f"指标是在残缺样本上算的。样例：{samples or '无'}）"
        )

    scored = report.get("scored", report["total"])
    for key, floor, above_is_bad in (("mae", max_mae, True), ("spearman_rho", min_spearman, False)):
        if floor is None:
            continue
        value = report.get(key)
        if value is None:
            need = "至少 2 条" if key == "spearman_rho" else "至少 1 条"
            failed.append(f"{key} 未测出（跑出预测分的 pair 只有 {scored} 条，{need}）门槛 {floor} 无从比较")
        elif (value > floor) if above_is_bad else (value < floor):
            unit = ">" if above_is_bad else "<"
            failed.append(f"{key} {value} {unit} {floor}")

    hit_tol10 = report["score_dist"]["hit_tol10"]
    if min_hit_tol10 is not None and hit_tol10 < min_hit_tol10:
        failed.append(f"hit_tol10 {hit_tol10} < {min_hit_tol10}")
    return failed


def main():
    parser = argparse.ArgumentParser(description="Agent 匹配质量评估")
    parser.add_argument(
        "--eval-set", default=str(_PROJECT_ROOT / "tests" / "eval" / "agent_eval.jsonl"), help="评估集 JSONL 路径"
    )
    parser.add_argument("--sample", type=int, default=None, help="只跑前 N 条")
    parser.add_argument("--output", default=None, help="输出 JSON 报告路径")
    parser.add_argument("--max-mae", type=float, default=None, help="Fail if MAE is above this threshold")
    parser.add_argument("--min-spearman", type=float, default=None, help="Fail if Spearman rho is below this threshold")
    parser.add_argument(
        "--min-hit-tol10", type=int, default=None, help="Fail if hit count within +/-10 is below this threshold"
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=0,
        help="允许多少条 pair 没跑出预测分（默认 0：一条都不允许，否则指标是残缺样本）",
    )
    args = parser.parse_args()

    eval_set = load_eval_set(args.eval_set)
    logger.info("加载评估集 %d 条 from %s", len(eval_set), args.eval_set)

    if args.sample:
        eval_set = eval_set[: args.sample]
        logger.info("截取前 %d 条", args.sample)

    report = run_eval(eval_set)
    report["report_type"] = "agent"
    report["run_meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_set": str(Path(args.eval_set).resolve()),
        "sample": args.sample,
        "thresholds": {
            "max_mae": args.max_mae,
            "min_spearman": args.min_spearman,
            "min_hit_tol10": args.min_hit_tol10,
            "max_errors": args.max_errors,
        },
    }

    print("\n" + "=" * 50)
    print(
        f"Agent 匹配评估报告  (共 {report['total']} 条，实际打分 {report['scored']} 条，未跑出 {report['eval_errors']} 条)"
    )
    print("=" * 50)
    print(f"  MAE (平均绝对误差) : {report['mae']}")
    print(f"  Spearman ρ         : {report['spearman_rho']}")
    print(
        f"  分数偏差分布       : 命中(±10)={report['score_dist']['hit_tol10']}  "
        f"偏高={report['score_dist']['over']}  偏低={report['score_dist']['under']}"
    )
    print()
    for d in report["details"]:
        if d["error"] is not None:
            print(f"  {d['id']:10s}  未跑出预测分：{d['error']}")
            continue
        sign = "+" if d["diff"] > 0 else ""
        print(
            f"  {d['id']:10s}  预测={d['predicted']:3d}  期望={d['expected']:3d}  "
            f"偏差={sign}{d['diff']:d}  [{d['label']}]"
        )
    print("=" * 50)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("报告已写入 %s", out_path)

    failed = check_thresholds(
        report,
        max_mae=args.max_mae,
        min_spearman=args.min_spearman,
        min_hit_tol10=args.min_hit_tol10,
        max_errors=args.max_errors,
    )

    if failed:
        print("[FAIL] Agent eval 未通过：")
        for item in failed:
            print(f"  - {item}")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
