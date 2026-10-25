"""P2 `parse_eval`：简历/JD 解析质量的第四轨评测（`简历与面试优化.md` §4 P2）。

**三臂**，因为他 2026-10-16 拍的是"链路进 CI、质量手动"：

* 确定性臂（不碰 provider，CI 可门）：拿语料原文过一遍 P1.1 的截断器，量
  截断发生率、丢段分布、**段尾那份最新经历有没有保住**、以及"判卷器本身可用"（gold 喂回
  判卷器必须满分——仪器不自检，数字就没意义）。
* 抽取臂（不碰 provider，CI 可门，2026-10-24 补）：`raw_text` 必须是文件里拆出来的那份。
  一路是清单夹具（TXT、临时生成的 DOCX 往返、坏 PDF 的**用户可见报错**），另一路是语料里
  带 `source_file` 的真文本行（4 份），抽取产物与 `raw_text` 归一化后必须逐字相同。
* 语义臂（要 provider，真跑才出门数）：走产品那条路（`guarded_parse`：预算内取文本 →
  单发解析 → 结构校验 → 一次自纠），量字段级 P/R/F1 与**首发一次通过率**。真文本臂的
  skills/经历/项目 gold 在 `tests/eval/human_gold_TO_FILL.json`，只并入 `_状态=done` 的行；
  工作按公司+职位、项目按项目名做集合比对。

三条纪律是抄既有三轨的，不是新规矩：
1. mock 下给语义臂设门槛**直接判红**（`eval_rag.py:405-411` 那条），因为 mock 的 `chat_json`
   对任何输入都回同一份 `_MOCK_RESUME`，"准确率"是常数对常数；成文原话在 `README.md:260`。
2. 门槛必须赢得过**空模型基线**：电话/邮箱/姓名这三个客观字段有正则直取这条免费基线
   （`regex_baseline()`），LLM 赢不过它，这道门分不出好坏（同 `agent_eval` 的 trivial baseline）。
3. 标签不许由被测代码回生成（`recommend_eval.jsonl` 头注释）：语料由 `gen_parse_eval.py`
   从画像渲染而来，画像在前、文本在后；真文本臂的标签是**正则从原文**取的，正则不属于被测系统。

跑法：
    python scripts/eval_parse.py                                  # 默认 mock，只跑确定性与抽取臂
    python scripts/eval_parse.py --allow-real --min-field-f1 0.75  # 真 provider，出门数（花钱）
    python scripts/eval_parse.py --sample 4 --allow-real --human-gold tests/eval/human_gold_TO_FILL.json --min-field-f1 0.75
    python scripts/eval_parse.py --output reports/parse_eval_latest.json

退出码：0 通过 / 3 门槛红 / 2 被 provider 闸拦下或评估身份定不下来。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.prompts.jd_parse import JD_PARSE_PROMPT  # noqa: E402
from app.prompts.rendering import render_prompt  # noqa: E402
from app.prompts.resume_parse import RESUME_PARSE_PROMPT  # noqa: E402
from app.schemas.jd import JDParsedSchema  # noqa: E402
from app.schemas.resume import ResumeParsedSchema  # noqa: E402
from app.services.parse_guard import PARSE_INPUT_BUDGET, validation_errors  # noqa: E402
from app.utils.file_parser import parse_resume  # noqa: E402
from app.utils.text_budget import fit_structured_text  # noqa: E402
from scripts.provider_guard import require_mock  # noqa: E402

# 这几项逐条报告召回与正则基线，但 `--min-field-f1` 只门列表字段：
# 正则直取在 name/phone/email 上就是 1.0，LLM 再准也只能打平，拿它当门分不出好坏（2026-10-23 拍）。
GATED_FIELDS = ("name", "phone", "email")
REPORT_ONLY_FIELDS = ("current_title", "current_company", "years_exp")
LIST_FIELDS = ("skills", "required_skills")
ENTITY_LIST_FIELDS = ("work_experience", "project_experience")
ALL_LIST_FIELDS = (*LIST_FIELDS, *ENTITY_LIST_FIELDS)
HUMAN_GOLD_LIST_FIELDS = ("skills", *ENTITY_LIST_FIELDS)
DEFAULT_HUMAN_GOLD = "tests/eval/human_gold_TO_FILL.json"
DEFAULT_EXTRACTION_MANIFEST = "tests/eval/resume_files/manifest.json"

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


def _norm_skill(value: Any) -> str:
    # 技能名里的空格是排版差异（`Agent 编排` vs `Agent编排`），集合语义应忽略；
    # 标点不归一——`C/C++` 与 `C++` 仍是两个不同写法，不能混成一个。
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def score_list(field: str, got: Any, want: Any) -> tuple[int, int, int]:
    """返回 (交集, 模型给出数, gold 数)。技能是集合语义，不做措辞匹配。"""
    g = {_norm_skill(x) for x in (got or []) if str(x).strip()}
    w = {_norm_skill(x) for x in (want or []) if str(x).strip()}
    return len(g & w), len(g), len(w)


def _norm_entity(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip().lower())
    return re.sub(r"[·•|/\\,，。;；:：()（）\[\]【】\-_]+", "", text)


def _work_key(item: Any) -> str:
    if not isinstance(item, dict):
        return _norm_entity(item)
    company = _norm_entity(item.get("company"))
    title = _norm_entity(item.get("title"))
    if company or title:
        return f"{company}|{title}"
    return _norm_entity(item.get("desc"))[:40]


def _project_key(item: Any) -> str:
    if not isinstance(item, dict):
        return _norm_entity(item)
    name = _norm_entity(item.get("name"))
    if name:
        return name
    role = _norm_entity(item.get("role"))
    desc = _norm_entity(item.get("desc"))
    return f"{role}|{desc[:40]}" if (role or desc) else ""


def score_entities(field: str, got: Any, want: Any) -> tuple[int, int, int]:
    """工作/项目按实体键做集合比对：工作=公司+职位，项目=项目名（缺失才退回角色/描述）。"""
    key_fn = _work_key if field == "work_experience" else _project_key
    g = {key_fn(item) for item in (got or []) if key_fn(item)}
    w = {key_fn(item) for item in (want or []) if key_fn(item)}
    return len(g & w), len(g), len(w)


def load_human_gold(path: pathlib.Path) -> dict[str, Any]:
    """读人工 gold；只把 `_状态=done` 且至少有一个列表字段的行视为可用。"""
    result: dict[str, Any] = {"rows": {}, "total": 0, "done": 0, "path": str(path)}
    if not path.exists():
        result["error"] = "missing"
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result["error"] = type(exc).__name__
        return result
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        result["error"] = "rows_missing"
        return result
    result["total"] = len(rows)
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("_状态") != "done":
            continue
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            continue
        lists = {field: row.get(field) or [] for field in HUMAN_GOLD_LIST_FIELDS}
        if not any(lists.values()):
            continue
        mapping[row_id] = lists
    result["rows"] = mapping
    result["done"] = len(mapping)
    return result


def merge_human_gold(rows: list[dict], human_gold: dict[str, Any]) -> int:
    """把已标行的列表字段并进对应语料行；不覆盖原有标量 gold。"""
    mapping = human_gold.get("rows") or {}
    merged = 0
    for row in rows:
        extra = mapping.get(str(row.get("id") or ""))
        if not extra:
            continue
        gold = dict(row.get("gold") or {})
        gold.update(extra)
        row["gold"] = gold
        merged += 1
    return merged


def _norm_extracted(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _write_minimal_pdf(text: str, target: pathlib.Path) -> None:
    """写一个只含一页 ASCII 文本的合法 PDF，给抽取臂覆盖 pdfplumber 的成功路径。

    真实中文版式的证据在 `reports/file_extraction_measure.json`（10/11）；这里只验
    "PDF 能打开、文本能回来"这条接线，所以不引入 PDF 写库。
    """
    if any(ord(char) > 127 for char in text):
        raise ValueError("minimal PDF fixture is ASCII-only")
    lines = text.splitlines() or [""]
    content = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            content.append("0 -18 Td")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content.append(f"({escaped}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    target.write_bytes(bytes(output))


def _extraction_detail(case: dict, case_id: str, source: str, tmp_dir: str, base_dir: pathlib.Path) -> dict:
    detail = {
        "id": case_id,
        "source": source,
        "file": str(case.get("file") or ""),
        "file_type": str(case.get("file_type") or ""),
        "expect": str(case.get("expect") or "text"),
        "ok": False,
        "chars": 0,
        "exact": False,
        "normalized": False,
        "error": "",
    }
    source_path = base_dir / str(case.get("file") or "")
    if not case.get("file") or not source_path.exists():
        detail["error"] = "源文件不存在"
        return detail

    path = source_path
    if case.get("generate") == "pdf":
        path = pathlib.Path(tmp_dir) / f"{case_id}.pdf"
        _write_minimal_pdf(source_path.read_text(encoding="utf-8"), path)
    elif case.get("generate") == "docx":
        from docx import Document

        path = pathlib.Path(tmp_dir) / f"{case_id}.docx"
        document = Document()
        for line in source_path.read_text(encoding="utf-8").splitlines():
            document.add_paragraph(line)
        document.save(str(path))

    try:
        text = parse_resume(str(path), str(case.get("file_type") or ""))
    except Exception as exc:  # 期望抛错的条目，异常本身就是读数
        if detail["expect"] == "error":
            marker = str(case.get("error_contains") or "")
            matched = isinstance(exc, ValueError) and bool(marker) and marker in str(exc)
            detail.update({"ok": matched, "normalized": matched, "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
            if not matched:
                detail["error"] += f"｜未命中期望文案 {marker!r}"
            return detail
        detail["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return detail

    if detail["expect"] == "error":
        detail["error"] = "期望解析抛错，实际成功返回"
        return detail

    expect_text = base_dir / str(case.get("expect_text") or "")
    if not expect_text.exists():
        detail["error"] = "expect_text 不存在"
        return detail
    expected = expect_text.read_text(encoding="utf-8")
    detail.update(
        {
            "chars": len(text),
            "exact": text.strip() == expected.strip(),
            "normalized": _norm_extracted(text) == _norm_extracted(expected),
        }
    )
    detail["ok"] = detail["normalized"]
    if not detail["ok"]:
        detail["error"] = (
            f"抽取文本与期望不一致（{len(_norm_extracted(text))} vs {len(_norm_extracted(expected))} 字符）"
        )
    return detail


def extraction_arm(rows: list[dict], manifest_path: pathlib.Path, eval_set_path: pathlib.Path) -> dict:
    """不碰 provider 的抽取臂：`raw_text` 必须就是文件抽取出来的那份文本。

    两路输入：① 清单里的夹具（TXT / 运行时生成的 DOCX / 坏 PDF 的报错文案）；
    ② 语料里带 `source_file` 的真文本行——这一路钉的是"eval 的输入不是人抄的，是文件拆出来的"。
    """
    details: list[dict] = []
    errors: list[str] = []

    if not manifest_path.exists():
        errors.append(f"清单不存在：{manifest_path}")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = manifest.get("cases") or []
        with tempfile.TemporaryDirectory() as tmp_dir:
            for case in cases:
                if not isinstance(case, dict):
                    continue
                case_id = str(case.get("id") or f"case{len(details) + 1}")
                detail = _extraction_detail(case, case_id, "fixture", tmp_dir, manifest_path.parent)
                details.append(detail)
                if not detail["ok"]:
                    errors.append(f"{case_id}: {detail['error'] or '抽取结果不一致'}")

    for row in rows:
        source_file = str(row.get("source_file") or "").strip()
        if not source_file or not isinstance(row.get("raw_text"), str):
            continue
        candidates = (
            eval_set_path.parent / "real_resumes" / source_file,
            eval_set_path.parent / source_file,
        )
        source_path = next((path for path in candidates if path.exists()), None)
        case_id = f"real:{row.get('id')}"
        if source_path is None:
            errors.append(f"{case_id}: 源文件不存在 {source_file}")
            details.append(
                {
                    "id": case_id,
                    "source": "real",
                    "file": source_file,
                    "file_type": pathlib.Path(source_file).suffix.lstrip("."),
                    "expect": "text",
                    "ok": False,
                    "chars": 0,
                    "exact": False,
                    "normalized": False,
                    "error": "源文件不存在",
                }
            )
            continue
        # 真文本行的期望不是另一份文件，而是语料自己的 raw_text：两臂本来就吃它。
        file_type = source_path.suffix.lstrip(".").lower()
        detail = {
            "id": case_id,
            "source": "real",
            "file": source_file,
            "file_type": file_type,
            "expect": "text",
            "ok": False,
            "chars": 0,
            "exact": False,
            "normalized": False,
            "error": "",
        }
        try:
            text = parse_resume(str(source_path), file_type)
        except Exception as exc:
            detail["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        else:
            raw = str(row.get("raw_text") or "")
            detail.update(
                {
                    "chars": len(text),
                    "exact": text.strip() == raw.strip(),
                    "normalized": _norm_extracted(text) == _norm_extracted(raw),
                }
            )
            detail["ok"] = detail["normalized"]
            if not detail["ok"]:
                detail["error"] = (
                    f"抽取文本与语料 raw_text 不一致（{len(_norm_extracted(text))} vs {len(_norm_extracted(raw))} 字符）"
                )
        details.append(detail)
        if not detail["ok"]:
            errors.append(f"{case_id}: {detail['error'] or '抽取结果不一致'}")

    matched = sum(1 for detail in details if detail["ok"])
    return {
        "manifest": str(manifest_path),
        "cases": len(details),
        "matched": matched,
        "match_rate": round(matched / len(details), 4) if details else None,
        "errors": errors,
        "details": details,
    }


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
        for f in ALL_LIST_FIELDS:
            if not gold.get(f):
                continue
            scorer = score_entities if f in ENTITY_LIST_FIELDS else score_list
            inter, got_n, want_n = scorer(f, gold[f], gold[f])
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
    list_stats = {f: [0, 0, 0] for f in ALL_LIST_FIELDS}
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
        for f in ALL_LIST_FIELDS:
            if gold.get(f):
                scorer = score_entities if f in ENTITY_LIST_FIELDS else score_list
                inter, got_n, want_n = scorer(f, payload.get(f), gold[f])
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
        "lists": {f: list_pr(f) for f in ALL_LIST_FIELDS if list_stats[f][2]},
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
    extraction: dict | None = None,
    min_extract_match: float | None = None,
) -> list[str]:
    bad: list[str] = []
    if len(det["errors"]) > max_errors:
        bad.append(f"确定性臂异常 {len(det['errors'])} > {max_errors}：{det['errors'][:3]}")
    if min_tail_keep is not None:
        if det["tail_keep_rate"] is None:
            bad.append("--min-tail-keep 设了但语料里没有可判的段尾样本")
        elif det["tail_keep_rate"] < min_tail_keep:
            bad.append(f"段尾保全率 {det['tail_keep_rate']} < 门槛 {min_tail_keep}")
    if extraction is not None:
        if len(extraction.get("errors") or []) > max_errors:
            bad.append(f"抽取臂不符 {len(extraction['errors'])} > {max_errors}：{extraction['errors'][:3]}")
        if min_extract_match is not None:
            if extraction.get("match_rate") is None:
                bad.append("--min-extract-match 设了但抽取臂没有可判样本")
            elif extraction["match_rate"] < min_extract_match:
                bad.append(f"抽取一致率 {extraction['match_rate']} < 门槛 {min_extract_match}")
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
            # 标量（name/phone/email）不设门：正则直取在这三项上就是 1.0，LLM 最好也只能打平；
            # 把“平手”判红会让任何门槛值必然红三条。它们仍逐条出现在报告里，供人看。
            for f, st in sem["lists"].items():
                if st["f1"] is not None and st["f1"] < min_field_f1:
                    bad.append(f"列表字段 {f} F1 {st['f1']} < 门槛 {min_field_f1}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--eval-set", default="tests/eval/parse_eval.jsonl")
    ap.add_argument("--sample", type=int, default=0, help="只跑前 N 条（0 = 全跑）")
    ap.add_argument("--output", default=None)
    ap.add_argument("--max-errors", type=int, default=0)
    ap.add_argument("--min-tail-keep", type=float, default=None, help="确定性臂：段尾保全率门槛（CI 可门）")
    ap.add_argument("--min-structure-rate", type=float, default=None, help="语义臂：首发通过结构校验的比例")
    ap.add_argument(
        "--min-field-f1", type=float, default=None, help="语义臂：列表字段 F1 门槛（标量只报数，不参与比较）"
    )
    ap.add_argument("--human-gold", default=DEFAULT_HUMAN_GOLD, help="真文本臂的人工 gold（只并入 _状态=done 的行）")
    ap.add_argument(
        "--extraction-manifest",
        default=DEFAULT_EXTRACTION_MANIFEST,
        help="抽取臂夹具清单（TXT/DOCX 往返/坏 PDF 报错）",
    )
    ap.add_argument(
        "--min-extract-match",
        type=float,
        default=1.0,
        help="抽取臂一致率门槛。默认 1.0 是接线不变量，不是质量门槛：夹具是确定的，文件读出来必须就是 eval 的输入",
    )
    ap.add_argument("--allow-real", action="store_true", help="允许真 provider 跑语义臂（花钱）")
    args = ap.parse_args()

    require_mock("eval_parse.py", allow_real=args.allow_real)

    from app.core.config import settings

    mock = (settings.LLM_PROVIDER or "mock").lower() == "mock"

    rows = load_eval_set(pathlib.Path(args.eval_set))
    if args.sample:
        rows = rows[: args.sample]
    human_gold = load_human_gold(pathlib.Path(args.human_gold))
    merged_human_gold = merge_human_gold(rows, human_gold)
    human_gold["merged"] = merged_human_gold
    resumes = [r for r in rows if r["kind"] in ("resume", "real")]
    jds = [r for r in rows if r["kind"] == "jd"]

    self_check = instrument_self_check(rows)
    det = deterministic_arm(rows)
    ext = extraction_arm(rows, pathlib.Path(args.extraction_manifest), pathlib.Path(args.eval_set))
    print("=" * 70)
    print(f"parse_eval：{len(rows)} 条（简历+真臂 {len(resumes)}｜JD {len(jds)}）｜provider={settings.LLM_PROVIDER}")
    print(f"判卷器自检：{'通过' if self_check['passed'] else '不通过 ' + str(self_check['misses'][:5])}")
    human_note = f"{human_gold['done']}/{human_gold['total']} 行已标，{merged_human_gold} 行并入"
    if human_gold.get("error"):
        human_note += f"（{human_gold['error']}）"
    print(f"人工 gold：{human_note}（{args.human_gold}）")
    print(
        f"确定性臂：截断 {det['truncated_count']} 条（率 {det['truncated_rate']}）"
        f"｜段尾保全 {det['tail_kept']}/{det['tail_total']} = {det['tail_keep_rate']}"
        f"｜丢段分布 {det['dropped_sections']}"
    )
    print(f"抽取臂：{ext['matched']}/{ext['cases']} 一致 = {ext['match_rate']}（{args.extraction_manifest}）")
    for line in ext["errors"][:5]:
        print("  -", line)
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
        extraction=ext,
        min_extract_match=args.min_extract_match,
    )

    if args.output:
        from datetime import datetime, timezone

        thresholds = {
            "max_errors": args.max_errors,
            "min_tail_keep": args.min_tail_keep,
            "min_structure_rate": args.min_structure_rate,
            "min_field_f1": args.min_field_f1,
            "min_extract_match": args.min_extract_match,
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
                "human_gold": {
                    "path": args.human_gold,
                    "total": human_gold["total"],
                    "done": human_gold["done"],
                    "merged": merged_human_gold,
                    "error": human_gold.get("error"),
                },
            },
            "instrument_self_check": self_check,
            "deterministic": det,
            "extraction": ext,
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
