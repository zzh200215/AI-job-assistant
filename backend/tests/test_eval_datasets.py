"""评测语料自身的门。P2 建起来之前，这一族**没有一条测试在看**。

起因：`tests/eval/resume_parse_eval.jsonl` 与 `interview_eval.jsonl` 里一共有 4 行是坏 JSON
（`input` 对象少一个闭合括号，`expected` 被吞成它的成员）。两支文件都无人读，所以没有任何一处
会红——它们在树里静默坏了不知道多久，是这次盘 P2 语料才撞见的。

所以这里的三条腿分别是：
1. **每一行都必须能解析**（把刚才那件事变成会红的东西，而不是靠人翻）；
2. 每个文件内部的**顶层键形状一致**（坏行的典型症状就是形状不齐）；
3. `parse_eval.jsonl` 必须与生成器的输出**逐字一致**——语料是数据，漂了要么改语料要么改生成器，
   不许只改一边（`recommend_eval` 那条"标签不许由被测代码回生成"的纪律在这里的对偶）。
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts.gen_parse_eval import (  # noqa: E402
    EMAIL_RE,
    FAKE_NAMES,
    NAME_RE,
    NAMED_RE,
    PHONE_RE,
    build_rows,
    fake_email,
    fake_phone,
    validate,
)

# 生成器把槽位从 0 开始编号（slot 0 ⇒ 13800138001 / resume01@example.com），这里必须跟着从 0 起。
FAKE_PHONE_SET = {fake_phone(i) for i in range(9)}
FAKE_EMAIL_SET = {fake_email(i) for i in range(9)}


def _pii_hits(label: str, text: str) -> list[str]:
    """一份文本里凡是"像真人联系方式"的 token，不在假值表里的都算命中。"""
    hits = [f"{label}: 手机号样式 {p}" for p in sorted(set(PHONE_RE.findall(text))) if p not in FAKE_PHONE_SET]
    hits += [f"{label}: 邮箱样式 {e}" for e in sorted(set(EMAIL_RE.findall(text))) if e not in FAKE_EMAIL_SET]
    named = NAMED_RE.search(text) or NAME_RE.match(text.strip().splitlines()[0] if text.strip() else "")
    if named and named.group(1) not in FAKE_NAMES:
        hits.append(f"{label}: 姓名 {named.group(1)} 不在假名表里")
    return hits


def _rows(path: pathlib.Path) -> list[tuple[int, dict]]:
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        out.append((n, json.loads(line)))
    return out


@pytest.mark.parametrize("path", sorted((BACKEND / "tests/eval").glob("*.jsonl")), ids=lambda p: p.name)
def test_every_line_of_an_eval_dataset_parses(path: pathlib.Path) -> None:
    """坏行不会自己报错——只会在某天有人来读的时候才炸。这条就是让它现在炸。"""
    broken = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            broken.append(f"第 {n} 行：{exc.msg}（col {exc.colno}）")
    assert not broken, f"{path.name} 里有 {len(broken)} 行不是合法 JSON：{broken[:3]}"


@pytest.mark.parametrize("path", sorted((BACKEND / "tests/eval").glob("*.jsonl")), ids=lambda p: p.name)
def test_key_shape_is_consistent_within_a_dataset(path: pathlib.Path) -> None:
    """同一个数据集的顶层键必须一致——`agent_eval` 与 `recommend_eval` 各是一套约定，
    但一套里不许漂。缺键通常意味着有人改了标注忘了改其余样本。"""
    rows = _rows(path)
    assert rows, f"{path.name} 是空的"
    shapes = {tuple(sorted(r)) for _, r in rows}
    assert len(shapes) == 1, f"{path.name} 里有 {len(shapes)} 种顶层键形状：{[list(s) for s in shapes]}"


def test_ids_are_unique_across_the_parse_corpus() -> None:
    path = BACKEND / "tests/eval/parse_eval.jsonl"
    ids = [r["id"] for _, r in _rows(path)]
    assert len(ids) == len(set(ids)), f"parse_eval 里有重复 id：{[i for i in ids if ids.count(i) > 1]}"


def test_parse_corpus_matches_its_generator() -> None:
    """语料由 `scripts/gen_parse_eval.py` 从画像渲染而来（gold 在前、文本在后）。
    只改文件不改生成器 = 标签来源不可审计；只改生成器不改文件 = 跑的不是仓库里那份。
    """
    rows = build_rows()
    bad = validate(rows)
    assert not bad, f"生成器产出的语料自己不合格：{bad[:3]}"
    shipped = _rows(BACKEND / "tests/eval/parse_eval.jsonl")
    assert len(shipped) == len(rows), f"仓库里 {len(shipped)} 条，生成器 {len(rows)} 条"
    for (n, got), want in zip(shipped, rows, strict=False):
        assert got == want, f"第 {n} 条与生成器不一致（id={got.get('id')}）：改语料要连生成器一起改"


def test_parse_corpus_covers_what_the_plan_promised() -> None:
    """`简历与面试优化.md` §4 P2 承诺的覆盖度：≥24 份简历、≥10 份 JD、2 份 >15000、
    中英文与应届/社招/转行齐。承诺过的东西要有门，不然下次改语料就悄悄少了。"""
    rows = [r for _, r in _rows(BACKEND / "tests/eval/parse_eval.jsonl")]
    resumes = [r for r in rows if r["kind"] == "resume"]
    assert len(resumes) >= 24, f"合成简历只有 {len(resumes)} 份"
    assert sum(1 for r in rows if r["kind"] == "jd") >= 10, "JD 样本不足 10 份"
    assert sum(1 for r in rows if r["kind"] == "real") >= 4, "真文本臂不足 4 份（这是唯一能当能力说事的一臂）"
    assert sum(1 for r in resumes if len(r["raw_text"]) > 15000) >= 2, ">15000 长简历不足 2 份，量不到截断修复"
    assert {r["language"] for r in rows} == {"zh", "en"}, "中英文覆盖不齐"
    assert {"fresh", "experienced", "switcher"} <= {r["cohort"] for r in resumes}, "应届/社招/转行三档不齐"


# ---------------------------------------------------------------------------
# 真文本臂的 PII 门（2026-10-17 加）
# ---------------------------------------------------------------------------
# 那一臂的原文是**真人简历**（带手机号、QQ 邮箱、姓名、学校）。按他拍的"脱敏后再入库"，
# 脱敏在 `scripts/gen_parse_eval.py` 的 `redact()` 里做；这条门判的是落盘结果：夹具与语料里
# 真文本那几行，只许出现假身份表里的值。**合成臂不在射程内**——那些号码本来就是编的，
# 拿假值表去卡它们只会造成假红。


def test_real_arm_fixtures_are_pseudonymised() -> None:
    real_dir = BACKEND / "tests/eval/real_resumes"
    files = sorted(real_dir.glob("*.txt"))
    assert files, "真文本臂夹具目录是空的，这条门失去意义"
    offenders: list[str] = []
    for path in files:
        offenders += _pii_hits(path.name, path.read_text(encoding="utf-8"))
    assert not offenders, f"真文本夹具里残留真人联系方式：{offenders[:6]}"


def test_real_arm_rows_in_the_corpus_are_pseudonymised() -> None:
    rows = [r for _, r in _rows(BACKEND / "tests/eval/parse_eval.jsonl") if r["kind"] == "real"]
    offenders: list[str] = []
    for row in rows:
        offenders += _pii_hits(row["id"], row["raw_text"])
        for key in ("name", "phone", "email"):
            value = row["gold"].get(key, "")
            if not value:
                continue
            allowed = (
                value in FAKE_NAMES
                if key == "name"
                else value in FAKE_PHONE_SET
                if key == "phone"
                else value in FAKE_EMAIL_SET
            )
            if not allowed:
                offenders.append(f"{row['id']}: gold.{key} 不在假身份表里")
    assert not offenders, f"语料里真文本那几行残留真人联系方式：{offenders[:6]}"


def test_real_arm_keeps_the_identity_grouping_honest() -> None:
    """3 份排版属于同一个人，这一点不能因为脱敏而变成 3 个人：同一个假手机号必须对应同一个假姓名。

    数 gold 里的不同姓名 = 报"覆盖了几个人"，脱敏若按**文件序号**发假身份，就会把一个人拆成三个，
    末行那句统计跟着说谎。所以这里钉的是 phone→name 的函数性。
    """
    rows = [r for _, r in _rows(BACKEND / "tests/eval/parse_eval.jsonl") if r["kind"] == "real"]
    by_phone: dict[str, set[str]] = {}
    for row in rows:
        phone, name = row["gold"].get("phone", ""), row["gold"].get("name", "")
        if phone and name:
            by_phone.setdefault(phone, set()).add(name)
    split = {phone: names for phone, names in by_phone.items() if len(names) > 1}
    assert not split, f"同一个手机号被拆成了多个姓名（脱敏按文件序号发了假身份）：{split}"


def test_pii_gate_flags_a_real_looking_identity() -> None:
    """反向证据：把这张尺对着一个明显像真人的样张必须响，否则上面三条是空转。

    样张用的是编造的号段与常见邮箱域，不是库里那位真人的值——把真值写进测试等于换个地方泄露。
    """
    dirty = "姓名：郭建成\n电话：13912345678  邮箱：guojc@gmail.com\n"
    hits = _pii_hits("sample", dirty)
    assert len(hits) == 3, f"PII 门漏掉了东西，只报出 {hits}"
    assert not _pii_hits("clean", "姓名：周思远\n电话：13800138001  邮箱：resume01@example.com\n"), "假身份被判成违规"


def test_interview_dynamic_cases_shape() -> None:
    """P3.2 对比用例的形状：三档齐全、必考技能非空、题面里**不许**预置必考技能名。

    最后一条是这套对比的测量前提：静态臂的覆盖必须是 0，增益才说明"追问把必考项带进来了"；
    题面里如果本来就念了 JD 词表，静态臂的覆盖会跟着上去，那个 +100pp 就成了假的。
    """
    import json

    path = BACKEND / "tests/eval/interview_dynamic_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    skills = cases["jd"]["required_skills"]
    assert len(skills) >= 3, f"必考技能太少，覆盖率的粒度不够：{skills}"
    assert {"good", "mid", "weak"} <= set(cases["candidates"]), "三档考生不全"
    assert all(item.get("question") and item.get("ref_answer") for item in cases["questions"]), "题面或参考答案缺项"
    leaked = [
        f"{item['question']} ⇒ {skill}" for item in cases["questions"] for skill in skills if skill in item["question"]
    ]
    assert not leaked, f"题面里预置了必考技能名，静态臂的覆盖会假高：{leaked[:3]}"
