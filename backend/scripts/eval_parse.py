"""P2 `parse_eval`：简历/JD 解析质量的第四轨评测（`简历与面试优化.md` §4 P2）。

**两臂**，因为他 2026-10-16 拍的是"链路进 CI、质量手动"：

* 确定性臂（不碰 provider，CI 可门）：拿语料原文过一遍 P1.1 的截断器，量
  截断发生率、丢段分布、**段尾那份最新经历有没有保住**、以及"判卷器本身可用"（gold 喂回
  判卷器必须满分——仪器不自检，数字就没意义）。
* 语义臂（要 provider，真跑才出门数）：走产品那条路（`guarded_parse`：预算内取文本 →
  单发解析 → 结构校验 → 一次自纠），量字段级 P/R/F1 与**首发一次通过率**。

三条纪律是抄既有三轨的，不是新规矩：
1. mock 下给语义臂设门槛**直接判红**（`eval_rag.py:405-411` 那条），因为 mock 的 `chat_json`
   对任何输入都回同一份 `_MOCK_RESUME`，"准确率"是常数对常数；成文原话在 `README.md:260`。
2. 门槛必须赢得过**空模型基线**：电话/邮箱/姓名这三个客观字段有正则直取这条免费基线
   （`regex_baseline()`），LLM 赢不过它，这道门分不出好坏（同 `agent_eval` 的 trivial baseline）。
3. 标签不许由被测代码回生成（`recommend_eval.jsonl` 头注释）：语料由 `gen_parse_eval.py`
   从画像渲染而来，画像在前、文本在后；真文本臂的标签是**正则从原文**取的，正则不属于被测系统。

跑法：
    python scripts/eval_parse.py                                  # 默认 mock，只跑确定性臂
    python scripts/eval_parse.py --allow-real --min-field-f1 0.8  # 真 provider，出门数（花钱）
    python scripts/eval_parse.py --output reports/parse_eval_latest.json

退出码：0 通过 / 3 门槛红 / 2 被 provider 闸拦下或评估身份定不下来。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.prompts.jd_parse import JD_PARSE_PROMPT  # noqa: E402
from app.prompts.rendering import render_prompt  # noqa: E402
from app.prompts.resume_parse import RESUME_PARSE_PROMPT  # noqa: E402
from app.schemas.jd import JDParsedSchema  # noqa: E402
from app.schemas.resume import ResumeParsedSchema  # noqa: E402
from app.services.parse_guard import PARSE_INPUT_BUDGET, validation_errors  # noqa: E402
from app.utils.text_budget import fit_structured_text  # noqa: E402
from scripts.provider_guard import require_mock  # noqa: E402

# 只这几项进门；主观项（经历摘要、title 的措辞）只进报告——§6 风险 5 那条。
GATED_FIELDS = ("name", "phone", "email")
REPORT_ONLY_FIELDS = ("current_title", "current_company", "years_exp")
LIST_FIELDS = ("skills", "required_skills")

PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NAMED_RE = re.compile(r"姓\s*名[:：]\s*([一-龥]{2,4})")
NAME_LINE_RE = re.compile(r"^([一-龥]{2,4})\s*$", re.M)


def load_eval_set(path: pathlib.Path) -> list[dict[str, Any]]:
    """JSONL，跳过空行与 `#`（与三轨同一形状）。"""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _norm_email(v: Any) -> str:
    return str(v or "").strip().lower()


def _norm_name(v: Any) -> str:
    return re.sub(r"\s+", "", str(v or ""))


def regex_baseline(raw_text: str) -> dict[str, str]:
    """不用模型的那条基线：电话/邮箱/姓名直接正则取。语义臂的门必须赢得过它。"""
    name = NAMED_RE.search(raw_text) or NAME_LINE_RE.match(raw_text.strip().splitlines()[0] if raw_text.strip() else "")
    return {
        "name": _norm_name(name.group(1)) if name else "",
        "phone": PHONE_RE.search(raw_text).group(0) if PHONE_RE.search(raw_text) else "",
        "email": _norm_email(EMAIL_RE.search(raw_text).group(0)) if EMAIL_RE.search(raw_text) else "",
    }


def score_scalar(field: str, got: Any, want: Any) -> bool:
    if field == "email":
        return _norm_email(got) == _norm_email(want) and bool(_norm_email(want))
    if field == "name":
        return _norm_name(got) == _norm_name(want) and bool(_norm_name(want))
    return str(got or "").strip() == str(want or "").strip() and bool(str(want or "").strip())


def score_list(field: str, got: Any, want: Any) -> tuple[int, int, int]:
    """返回 (交集, 模型给出数, gold 数)。技能是集合语义，不做措辞匹配。"""
    g = {str(x).strip().lower() for x in (got or []) if str(x).strip()}
    w = {str(x).strip().lower() for x in (want or []) if str(x).strip()}
    return len(g & w), len(g), len(w)


def deterministic_arm(rows: list[dict]) -> dict:
    """不碰 provider 的那一臂：P1.1 的截断器在语料上的行为。"""
    truncated = 0
    tail_kept = 0
    tail_total = 0
    dropped_sections: dict[str, int] = {}
    errors: list[str] = []
    for r in rows:
        try:
            fit = fit_structured_text(r["raw_text"], PARSE_INPUT_BUDGET)
        except Exception as exc:  # 不吞：仪器抛异常必须成为红，不是少一项
            errors.append(f"{r['id']}: fit_structured_text 抛 {type(exc).__name__}")
            continue
        if fit.truncated:
            truncated += 1
            for s in fit.dropped_sections:
                dropped_sections[s] = dropped_sections.get(s, 0) + 1
        needle = r.get("tail_line") or _tail_needle(r)
        # **只数"段尾确实在原文里"的样本**。没这句就会把"渲染时压根没写这一段"的样本算成丢尾，
        # 报出一个像截断退化的数（第一版就是 25/28=0.8929，查下去 3 条全是 fresh 档，
        # 那批模板没有工作经历段，needle 从来没在原文里出现过）。
        if needle and needle in r["raw_text"]:
            tail_total += 1
            if needle in fit.text:
                tail_kept += 1
            else:
                errors.append(f"{r['id']}: 段尾 {needle[:16]}… 被裁掉了（丢了 {fit.dropped_sections}）")
    return {
        "samples": len(rows),
        "truncated_count": truncated,
        "truncated_rate": round(truncated / len(rows), 4) if rows else None,
        "dropped_sections": dropped_sections,
        "tail_kept": tail_kept,
        "tail_total": tail_total,
        "tail_keep_rate": round(tail_kept / tail_total, 4) if tail_total else None,
        "errors": errors,
    }


def _tail_needle(row: dict) -> str:
    gold = row.get("gold") or {}
    for job in reversed(gold.get("work_experience") or []):
        title = str(job.get("title") or "").strip()
        if title:
            return title
    return ""


def instrument_self_check(rows: list[dict]) -> dict:
    """判卷器自检：把 gold 原样喂回打分函数，必须满分。
    这条不过，后面所有 F1 数字都是空的——仪器没对准，量到的偏差是仪器自己的。
    """
    misses: list[str] = []
    for r in rows:
        gold = r.get("gold") or {}
        for f in GATED_FIELDS:
            if gold.get(f) and not score_scalar(f, gold[f], gold[f]):
                misses.append(f"{r['id']}.{f}")
        for f in LIST_FIELDS:
            if gold.get(f):
                inter, got_n, want_n = score_list(f, gold[f], gold[f])
                if not (inter == got_n == want_n):
                    misses.append(f"{r['id']}.{f}")
    return {"passed": not misses, "misses": misses[:20]}


def semantic_arm(rows: list[dict], chat: Any) -> dict:
    """走产品那条路的语义臂。`chat` 由调用方注入（mock 或真 provider），
    注入而不是自己 import，是为了能记下"这一发到底调了几次模型"。"""
    calls = {"n": 0}

    def counting(prompt: str) -> Any:
        calls["n"] += 1
        return chat(prompt)

    hits = {f: 0 for f in GATED_FIELDS}
    wants = {f: 0 for f in GATED_FIELDS}
    base_hits = {f: 0 for f in GATED_FIELDS}
    list_stats = {f: [0, 0, 0] for f in LIST_FIELDS}
    report_only = {f: 0 for f in REPORT_ONLY_FIELDS}
    report_only_total = {f: 0 for f in REPORT_ONLY_FIELDS}
    first_pass = 0
    scored = 0
    errors: list[str] = []
    per_sample = []

    for r in rows:
        schema = JDParsedSchema if r["kind"] == "jd" else ResumeParsedSchema
        template = JD_PARSE_PROMPT if r["kind"] == "jd" else RESUME_PARSE_PROMPT
        key = "jd_text" if r["kind"] == "jd" else "resume_text"
        try:
            fit = fit_structured_text(r["raw_text"], PARSE_INPUT_BUDGET)
            prompt = render_prompt(template, **{key: fit.text})
            first = counting(prompt)
            first_ok = not validation_errors(schema, first)
            payload = first if isinstance(first, dict) else {}
            if not first_ok:
                payload = counting(prompt + "\n\n【上一次输出未通过结构校验】\n- 见上一轮") or payload
        except Exception as exc:
            errors.append(f"{r['id']}: {type(exc).__name__}")
            continue

        scored += 1
        first_pass += int(first_ok)
        gold = r.get("gold") or {}
        baseline = regex_baseline(r["raw_text"])
        row_hit = {}
        for f in GATED_FIELDS:
            if not gold.get(f):
                continue
            wants[f] += 1
            ok = score_scalar(f, payload.get(f), gold[f])
            hits[f] += int(ok)
            row_hit[f] = ok
            if f in baseline and baseline[f] and score_scalar(f, baseline[f], gold[f]):
                base_hits[f] += 1
        for f in LIST_FIELDS:
            if gold.get(f):
                inter, got_n, want_n = score_list(f, payload.get(f), gold[f])
                acc = list_stats[f]
                acc[0] += inter
                acc[1] += got_n
                acc[2] += want_n
        for f in REPORT_ONLY_FIELDS:
            if gold.get(f) != "" and gold.get(f) is not None:
                report_only_total[f] += 1
                report_only[f] += int(_loose_contains(payload.get(f), gold.get(f)))
        per_sample.append({"id": r["id"], "first_pass": first_ok, "fields": row_hit})

    def pr(field: str) -> dict:
        w = wants[field]
        return {
            "want": w,
            "hit": hits[field],
            "recall": round(hits[field] / w, 4) if w else None,
            "regex_baseline_recall": round(base_hits[field] / w, 4) if w else None,
        }

    def list_pr(field: str) -> dict:
        inter, got_n, want_n = list_stats[field]
        p = inter / got_n if got_n else 0.0
        rc = inter / want_n if want_n else 0.0
        f1 = (2 * p * rc / (p + rc)) if (p + rc) else 0.0
        return {"precision": round(p, 4), "recall": round(rc, 4), "f1": round(f1, 4), "want": want_n}

    return {
        "llm_calls": calls["n"],
        "scored": scored,
        "errors": errors,
        "first_pass_rate": round(first_pass / scored, 4) if scored else None,
        "scalar": {f: pr(f) for f in GATED_FIELDS},
        "lists": {f: list_pr(f) for f in LIST_FIELDS if list_stats[f][2]},
        "report_only": {
            f: (round(report_only[f] / report_only_total[f], 4) if report_only_total[f] else None)
            for f in REPORT_ONLY_FIELDS
        },
        "per_sample": per_sample,
    }


def _loose_contains(got: Any, want: Any) -> bool:
    g, w = str(got or "").strip().lower(), str(want or "").strip().lower()
    return bool(w) and (w in g or g in w)


def check_thresholds(
    det: dict,
    sem: dict | None,
    *,
    mock: bool,
    max_errors: int,
    min_tail_keep: float | None,
    min_structure_rate: float | None,
    min_field_f1: float | None,
) -> list[str]:
    bad: list[str] = []
    if len(det["errors"]) > max_errors:
        bad.append(f"确定性臂异常 {len(det['errors'])} > {max_errors}：{det['errors'][:3]}")
    if min_tail_keep is not None:
        if det["tail_keep_rate"] is None:
            bad.append("--min-tail-keep 设了但语料里没有可判的段尾样本")
        elif det["tail_keep_rate"] < min_tail_keep:
            bad.append(f"段尾保全率 {det['tail_keep_rate']} < 门槛 {min_tail_keep}")
    if mock and (min_field_f1 is not None):
        bad.append("mock 环境下给语义臂设字段门槛是假门：mock 的 chat_json 对任何输入回同一份常量")
    if sem is not None:
        if len(sem["errors"]) > max_errors:
            bad.append(f"语义臂异常 {len(sem['errors'])} > {max_errors}：{sem['errors'][:3]}")
        if min_structure_rate is not None:
            if sem["first_pass_rate"] is None:
                bad.append("--min-structure-rate 设了但一条都没跑出来")
            elif sem["first_pass_rate"] < min_structure_rate:
                bad.append(f"结构一次通过率 {sem['first_pass_rate']} < 门槛 {min_structure_rate}")
        if min_field_f1 is not None:
            for f, st in sem["scalar"].items():
                if not st["want"]:
                    continue
                if st["recall"] is not None and st["recall"] < min_field_f1:
                    bad.append(f"字段 {f} 召回 {st['recall']} < 门槛 {min_field_f1}")
                base = st["regex_baseline_recall"]
                if base is not None and st["recall"] is not None and st["recall"] <= base:
                    bad.append(f"字段 {f} 召回 {st['recall']} 赢不过正则直取的基线 {base}——这道门分不出好坏")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--eval-set", default="tests/eval/parse_eval.jsonl")
    ap.add_argument("--sample", type=int, default=0, help="只跑前 N 条（0 = 全跑）")
    ap.add_argument("--output", default=None)
    ap.add_argument("--max-errors", type=int, default=0)
    ap.add_argument("--min-tail-keep", type=float, default=None, help="确定性臂：段尾保全率门槛（CI 可门）")
    ap.add_argument("--min-structure-rate", type=float, default=None, help="语义臂：首发通过结构校验的比例")
    ap.add_argument("--min-field-f1", type=float, default=None, help="语义臂：客观字段召回，且必须赢过正则基线")
    ap.add_argument("--allow-real", action="store_true", help="允许真 provider 跑语义臂（花钱）")
    args = ap.parse_args()

    require_mock("eval_parse.py", allow_real=args.allow_real)

    from app.core.config import settings

    mock = (settings.LLM_PROVIDER or "mock").lower() == "mock"

    rows = load_eval_set(pathlib.Path(args.eval_set))
    if args.sample:
        rows = rows[: args.sample]
    resumes = [r for r in rows if r["kind"] in ("resume", "real")]
    jds = [r for r in rows if r["kind"] == "jd"]

    self_check = instrument_self_check(rows)
    det = deterministic_arm(rows)
    print("=" * 70)
    print(f"parse_eval：{len(rows)} 条（简历+真臂 {len(resumes)}｜JD {len(jds)}）｜provider={settings.LLM_PROVIDER}")
    print(f"判卷器自检：{'通过' if self_check['passed'] else '不通过 ' + str(self_check['misses'][:5])}")
    print(
        f"确定性臂：截断 {det['truncated_count']} 条（率 {det['truncated_rate']}）"
        f"｜段尾保全 {det['tail_kept']}/{det['tail_total']} = {det['tail_keep_rate']}"
        f"｜丢段分布 {det['dropped_sections']}"
    )
    if not self_check["passed"]:
        print("[FAIL] 判卷器自检没过，语义臂的数字不作数——先修打分函数")
        return 3

    sem = None
    if not mock or args.allow_real:
        from app.services.llm_service import chat_json

        sem = semantic_arm(rows, chat_json)
        print(
            f"语义臂：LLM 调用 {sem['llm_calls']} 次｜首发通过校验 {sem['first_pass_rate']}"
            f"｜客观字段 {json.dumps(sem['scalar'], ensure_ascii=False)}"
        )
        print(f"      列表字段 {json.dumps(sem['lists'], ensure_ascii=False)}")
        print(f"      只报不门 {json.dumps(sem['report_only'], ensure_ascii=False)}")
    else:
        print("语义臂：mock 下跳过（常数对常数的准确率没有意义），加 --allow-real 才出门数")

    bad = check_thresholds(
        det,
        sem,
        mock=mock,
        max_errors=args.max_errors,
        min_tail_keep=args.min_tail_keep,
        min_structure_rate=args.min_structure_rate,
        min_field_f1=args.min_field_f1,
    )

    if args.output:
        from datetime import datetime, timezone

        thresholds = {
            "max_errors": args.max_errors,
            "min_tail_keep": args.min_tail_keep,
            "min_structure_rate": args.min_structure_rate,
            "min_field_f1": args.min_field_f1,
        }
        report = {
            "report_type": "parse",
            "run_meta": {
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "eval_set": args.eval_set,
                "sample": args.sample,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                # 读端从 run_meta 里取 thresholds/generated_at（别的轨就这么放），
                # 顶层那份是给 CI 日志看的同一份数。
                "thresholds": thresholds,
                "budget": PARSE_INPUT_BUDGET,
            },
            "instrument_self_check": self_check,
            "deterministic": det,
            "semantic": sem,
            "thresholds": thresholds,
            "failures": bad,
        }
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print(f"报告写出 {out}")

    if bad:
        print("[FAIL] 门槛未过：")
        for line in bad:
            print("  -", line)
        return 3
    print("[ok] 已设的门槛全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
