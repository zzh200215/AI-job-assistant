"""单个项目的六维尺 —— `docs/project-report-spec.md` §2 的唯一权威。

这把尺和整份简历那把七维尺（`resume_report_rubric`）**不是同一把**：
一张量项目成色（项目本身 95 分 + 它在简历里排第几 5 分），一张量整份简历。
两处同名不同义的维度（指标责任、深度、可迁移、面试承载）各算各的，
所以这一族的评级用**词**（标杆级 / 优秀 / …）而不是 A/B/C/D——
两份报告同时写着"B 档"却指两件事，是 §5 那条"口径自洽"最先崩的地方。

表原文反推自《如何评估是不是一个好项目》（六维量表 + 六条红线 + 位次机制）。
**标了「反推待定」的是本仓库自定的口径，成品里没有那个数**，改动要在台账里点名。

本模块不做任何模型调用：给维度表、把模型返回的分读成可信的数、算位次那一维、
求和、落档。红线里能逐字核的那几条在这里给**判据函数**，不下结论——结论由服务端
拿真原文算，模型只能提名。
"""

from __future__ import annotations

import re
from typing import Any

from app.services.resume_report_rubric import score_or_none

# (键, 对外标签, 满分, 是否由模型判, 判分口径一句话)
# D6 不由模型判：它是排位的函数，写死在 RANK_SCORES 里。
DIMENSIONS: tuple[tuple[str, str, int, bool, str], ...] = (
    (
        "d1_role_signal",
        "D1 岗位信号强度",
        24,
        True,
        "技术选型是不是这个岗位的主流栈、场景是不是这个岗位真实在做的业务、"
        "干的事与 JD 里的动词重不重合、有没有一条对得上的能力主线；"
        "面试官在这一维不是在评好坏，是在找同类。",
    ),
    (
        "d2_depth",
        "D2 深度与真实感",
        24,
        True,
        "数据是真的吗（多少量、从哪来、什么分布）、有攻坚痕迹吗、有取舍过程吗（为什么选 A 不选 B）、"
        "有可验证证据吗（上线了吗、跑了多久）；凡是能靠模板编出来的东西，这一维一分都拿不到。",
    ),
    (
        "d3_metric",
        "D3 指标责任与达成",
        19,
        True,
        "有没有量化结果（不能只有形容词）、有没有基线（从多少到多少）、"
        "数字和本人动作对不对得上、达成闭环里有没有「怎么测的」；每个数字都要挂着一个自己的动作。",
    ),
    (
        "d4_transfer",
        "D4 技术可迁移性",
        14,
        True,
        "抽掉业务背景这条技术轴还立不立得住、是方法论还是照搬了公司的表结构、"
        "换一家能不能复用、有没有沉淀出可复用的规范或参数。",
    ),
    (
        "d5_interview",
        "D5 面试承载力",
        14,
        True,
        "每个数字讲不讲清怎么测、每个选型讲不讲清为什么、每个细节能不能讲到第三层、"
        "整条链路前后自不自洽；写一句答不上来的话比不写更糟。",
    ),
    (
        "d6_rank",
        "D6 简历位次",
        5,
        False,
        "只看这个项目排在简历里第几个：第 1 个 5 分、第 2 个 3 分、第 3 个及以后 1 分。"
        "同一项目放第一位比放第四位多 4 分，而排序是零成本改动。",
    ),
)

DIMENSION_KEYS: tuple[str, ...] = tuple(row[0] for row in DIMENSIONS)
MODEL_JUDGED_KEYS: tuple[str, ...] = tuple(row[0] for row in DIMENSIONS if row[3])
TOTAL_FULL: int = sum(row[2] for row in DIMENSIONS)

# 前五维算项目本体、第六维算排列——这一句是成品思路篇里的原话，报告要能对上。
BODY_FULL: int = sum(row[2] for row in DIMENSIONS if row[3])

# 位次得分（反推待定：思路篇给的是"第 1 个 5 / 第 2 个 3 / 第 3 个 1 / 第 4 个及以后 1"，
# 这一族沿用它，不自己改档）。索引从 0 起。
RANK_SCORES: tuple[int, ...] = (5, 3, 1)
RANK_COEFFICIENTS: tuple[int, ...] = (5, 3, 1)

# 评级用词不用字母（理由见模块头）。区间是本仓库自定的：
# 成品二十多份样本里同一个分数落到不同措辞（85→"良好"、89→"标杆级"、84→"优秀级"），
# 反推不出稳定映射，所以按分数带切一刀并写明是「反推待定」。
GRADE_BANDS: tuple[tuple[str, int, int, str], ...] = (
    ("标杆级", 90, 100, "档案、图解、面试准备都拿得出原文出处，可直接当主打项目上考场"),
    ("优秀", 85, 89, "五维里四维在优档，能撑一场中等强度的深挖"),
    ("良好", 75, 84, "链路完整，扣分集中在指标口径与基线"),
    ("需重构", 60, 74, "写得出来但撑不住追问，先按补强路径改一版"),
    ("暂不可投", 0, 59, "这一份在项目上还没有可核验的产出"),
)

# 难度分级 L1–L5（反推待定：思路篇没有给档位定义，成品只给了每份的一句话理由，
# 所以这里的判据是"链路里叠了几类范式"这一条从成品理由里归纳出来的共同轴）。
DIFFICULTY_BANDS: tuple[tuple[str, str, str], ...] = (
    (
        "L1",
        "教程复现",
        "照着教程把一条链路搭起来，选型与参数都是别人定的，说不出为什么这么选。",
    ),
    (
        "L2",
        "单链路跑通",
        "一条链路自己走通了（解析→入库→问答或一套 CRUD），有结果但没有对照，没有优化过程。",
    ),
    (
        "L3",
        "链路上有优化与评测",
        "在链路上做过选型对比、重排/召回调优，并留下自己的指标口径。",
    ),
    (
        "L4",
        "编排加工程化的完整体",
        "有条件分支/状态编排、结构化输出约束、部署与观测，但不涉及多智能体协作或模型训练。",
    ),
    (
        "L5",
        "多范式叠加",
        "两类以上高难范式同时压在同一条链路上（多智能体协作、领域微调、图谱多跳、多模态、私有化推理）。",
    ),
)

# 六条红线。判法两档：
#   "code"  = 本模块给可逐字核的判据函数，服务端自己算，不问模型；
#   "model" = 只能由模型提名，但**必须给出逐字落在项目原文里的证据**，服务端校验证据命中，
#             命不中就整条作废（模型只能提出，不能自证）。
RED_LINES: tuple[tuple[str, str, str, str], ...] = (
    (
        "unexplainable_number",
        "性能数字无法解释",
        "model",
        "报了个数但说不清怎么来的——追问「响应优化 60%」发现是换了台机器。",
    ),
    (
        "no_baseline",
        "无基线的提升",
        "code",
        "只写「提升了 / 明显改善」，不写从多少到多少。基线缺失 = 这一条数字作废。",
    ),
    (
        "broken_stack",
        "技术链路自相矛盾",
        "code",
        "前后描述对不上：技术栈列了某个组件，职责与成果里一个字不提它干什么。",
    ),
    (
        "others_work",
        "整体搬运他人成果",
        "model",
        "项目不是自己主导的，却整段写成自己的——同行一问分工就露。",
    ),
    (
        "template_smell",
        "疑似课程作业抄写",
        "model",
        "模板痕迹重、无个人判断，一眼看出是跟着教程做的。",
    ),
    (
        "not_reproducible",
        "无法复现",
        "model",
        "问细节答不上来：写下的东西自己要能讲三分钟。讲不出来就等于没做过。",
    ),
)

RED_LINE_KEYS: tuple[str, ...] = tuple(row[0] for row in RED_LINES)
_CODE_JUDGED_RED_LINES: tuple[str, ...] = tuple(row[0] for row in RED_LINES if row[2] == "code")

_LABELS: dict[str, str] = {row[0]: row[1] for row in DIMENSIONS}
_FULLS: dict[str, int] = {row[0]: row[2] for row in DIMENSIONS}

# 「提升类」措辞：出现这些词的那一条职责/成果，按 §2 D3 与红线 2 的定义必须带基线。
_GAIN_WORDS: tuple[str, ...] = (
    "提升",
    "提高",
    "优化",
    "降低",
    "减少",
    "改善",
    "加快",
    "加速",
    "缩短",
    "下降",
    "压缩",
    "增强",
    "精简",
)
# 基线形态：同一句里出现**两个值**，且两个值之间有前后关系。
# 不写"数字紧邻至/到"那种正则——成品里那句"由人工约 30 - 60 分钟缩短至 5 - 10 分钟"
# 的动词"缩短"夹在两个数字中间，紧邻式正则会把它判成"无基线"，而它是基线写得最好的一句。
_TODO = re.compile(r"【待补[^】]*】")
_PAIR_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_CONNECTOR = re.compile(r"(到|至|降|升|提|缩|减|增|倍|→|->|为|剩|只用|仅需)")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|ms|毫秒|秒|分钟|小时|天|周|月|人日|倍|k|K|w|万|亿|qps|QPS|token|元)?")


def dimension_label(key: str) -> str:
    return _LABELS.get(key, key)


def dimension_full(key: str) -> int:
    return _FULLS.get(key, 0)


def rubric_prompt_block() -> str:
    """把六维表渲染成 prompt 里的那段口径说明（同七维那张表的生成方式，不手抄）。"""
    lines = []
    for key, label, full, judged, rubric in DIMENSIONS:
        tail = "" if judged else "（这一维由服务端按位次算，不要打分）"
        lines.append(f"- {key}（{label}，满分 {full}）：{rubric}{tail}")
    lines.append(f"六维满分之和 = {TOTAL_FULL}，其中前五维是项目本体（{BODY_FULL} 分），第六维是排列（5 分）。")
    return "\n".join(lines)


def red_line_prompt_block() -> str:
    """红线表里**要模型判**的那几条：模型提名必须带逐字证据，否则服务端整条作废。"""
    lines = []
    for key, label, judged, rubric in RED_LINES:
        if judged != "model":
            continue
        lines.append(f"- {key}（{label}）：{rubric}")
    return "\n".join(lines)


def rank_index(project_index: int) -> int:
    """把"这份简历里的第几个项目"归一到 0..3+（第 4 个及以后同分）。"""
    return max(0, int(project_index))


def rank_score(project_index: int) -> int:
    index = rank_index(project_index)
    if index < len(RANK_SCORES):
        return RANK_SCORES[index]
    return RANK_SCORES[-1]


def rank_coefficient(project_index: int) -> int:
    """加权用的系数。思路篇里 D6 的分与"说服力"的系数是同一组数（5/3/1）。"""
    index = rank_index(project_index)
    if index < len(RANK_COEFFICIENTS):
        return RANK_COEFFICIENTS[index]
    return RANK_COEFFICIENTS[-1]


def rank_note(project_index: int) -> str:
    return f"排在简历第 {rank_index(project_index) + 1} 位；越靠前，这一项给得越高。"


def read_dimensions(raw: Any, project_index: int) -> list[dict[str, Any]]:
    """把模型返回的五维 + 服务端算的位次读成固定六行的表。

    位次那一行**不接受模型给的分**：它是排位的函数，模型给多少都不算。
    """
    source = raw if isinstance(raw, dict) else {}
    rows: list[dict[str, Any]] = []
    for key, label, full, judged, _rubric in DIMENSIONS:
        if not judged:
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "full": full,
                    "score": rank_score(project_index),
                    "note": rank_note(project_index),
                    "positional": True,
                }
            )
            continue
        value = source.get(key)
        note = ""
        if isinstance(value, dict):
            score = score_or_none(value.get("score"), full)
            note = value["note"].strip() if isinstance(value.get("note"), str) else ""
        else:
            score = score_or_none(value, full)
        rows.append(
            {
                "key": key,
                "label": label,
                "full": full,
                "score": score,
                "note": note,
                "positional": False,
            }
        )
    return rows


def total_of(rows: list[dict[str, Any]]) -> int | None:
    """六维之和；任一维未知则总分为未知（缺维度不等于 0 分，沿用七维那一条口径）。"""
    scores = [row["score"] for row in rows]
    if len(scores) != len(DIMENSIONS) or any(score is None for score in scores):
        return None
    return sum(scores)  # type: ignore[arg-type]


def grade_of(total: int | None) -> str | None:
    if total is None:
        return None
    for grade, low, high, _desc in GRADE_BANDS:
        if low <= total <= high:
            return grade
    return GRADE_BANDS[-1][0]


def grade_desc_of(total: int | None) -> str:
    grade = grade_of(total)
    for name, _low, _high, desc in GRADE_BANDS:
        if name == grade:
            return desc
    return ""


def grade_scale_block() -> str:
    return " / ".join(f"{name} {low}–{high}（{desc}）" for name, low, high, desc in GRADE_BANDS)


def difficulty_prompt_block() -> str:
    return "\n".join(f"- {level}（{name}）：{what}" for level, name, what in DIFFICULTY_BANDS)


def is_known_difficulty(level: Any) -> bool:
    return isinstance(level, str) and level.strip() in {row[0] for row in DIFFICULTY_BANDS}


# "补齐后预计"那一列要点名维度。两种写法都认：编号（D3）与标签里的词（指标责任）。
_DIMENSION_HINTS: tuple[str, ...] = ("岗位信号", "深度", "指标责任", "可迁移", "面试承载", "位次")


def mentions_dimension(text: str) -> bool:
    body = text or ""
    if re.search(r"[Dd][1-6]", body):
        return True
    return any(hint in body for hint in _DIMENSION_HINTS)


# ------------------------------------------------------- 代码能逐字核的两条：只出证据，不下结论
def split_clauses(text: str) -> list[str]:
    """把一段项目原文切成条目：按行、按分号、按句号切。

    条目而不是整段——"没有基线的提升"是按**一条**说的：一条里写"误报率下降 90%"却给不出
    从多少到多少，那一条可疑；同一项目里另一条带了基线，救不了这一条。
    """
    parts: list[str] = []
    for line in (text or "").splitlines():
        for chunk in re.split(r"[；;。\n]", line):
            item = chunk.strip(" \t-•*0123456789.、）)（")
            if len(item) >= 4:
                parts.append(item)
    return parts


def has_paired_value(clause: str) -> bool:
    """这一条里是否给了**前后两个值**，且两个值之间有前后关系的词。

    先剥掉 `【待补：…】`——那是规范给"该有个数但还没实测"留的合法出口，
    它写在那里就是"我知道这里缺一个基线"，不该再被算成缺基线的证据。
    """
    cleaned = _TODO.sub("", clause)
    numbers = _PAIR_NUMBER.findall(cleaned)
    if len(numbers) < 2:
        return False
    return bool(_CONNECTOR.search(cleaned))


def metric_gap_clauses(text: str) -> list[dict[str, str]]:
    """写了提升类措辞、但这一条自己没闭合的条目。

    三种形状分开记，因为它们的严重性不一样：
    * `no_number`：只有形容词（"大幅提升审查效率"）——红线 2 最纯的形状；
    * `single_number`：有数但只有一个方向（"误报率下降 90%"，没写原来多少）；
    * 两个值且有前后关系词的那一条**不计**（"30 - 60 分钟缩短至 5 - 10 分钟"是合规写法）。

    这一族是**证据收集器，不是判决**：判据在成品那份 85 分的项目原文上验过，
    按"命中即出局"会让成品自己出局，所以它只喂 1.6 风险提示与对内计数。
    """
    rows: list[dict[str, str]] = []
    for clause in split_clauses(text):
        if not any(word in clause for word in _GAIN_WORDS):
            continue
        if _TODO.search(clause):
            # 这一条自己写了"这里欠一个实测值"。它是承认缺口，不是藏着缺口——
            # 再把它算成"无基线的提升"，等于罚那句诚实的话。
            continue
        numbers = _NUMBER.findall(clause)
        if not numbers:
            rows.append({"clause": clause, "kind": "no_number"})
        elif not has_paired_value(clause):
            rows.append({"clause": clause, "kind": "single_number"})
    return rows


def stack_footprint(tech: list[str], project_text: str) -> dict[str, Any]:
    """技术栈落点核对：列了但整条项目原文一次都没落点的组件。

    同样**不判出局**：成品 85 分那一份 18 个组件里有 3 个（Redis、FastAPI、Python）
    在项目正文里没有落点，而它们只该出现在 1.6 的"哪里一问就穿"，不该让这份项目出局。
    返回 `{"total","missing","ratio"}`，缺落点比例进风险提示，是否算红线交模型点名。
    """
    folded = (project_text or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    total = 0
    missing: list[str] = []
    for item in tech or []:
        name = str(item or "").strip()
        if len(name) < 2:
            continue
        total += 1
        # 斜杠并列写法（"Milvus / Chroma"、"Qwen API / vLLM"）拆开各自核一遍，
        # 整串去原文里找必然找不到——那会把每一个用并列写法的技术栈都判成无落点。
        atoms = [a.strip() for a in re.split(r"[/／|｜、,，]+", name) if len(str(a).strip()) >= 2] or [name]
        if all(atom.lower().replace("-", "").replace("_", "").replace(" ", "") not in folded for atom in atoms):
            missing.append(name)
    return {"total": total, "missing": missing, "ratio": round(len(missing) / total, 3) if total else None}


def judged_red_line_keys() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(代码只出证据的两条键, 模型只能提名但必须逐字命中原文的键)——分界写一处，别在调用侧再列。"""
    model_judged = tuple(row[0] for row in RED_LINES if row[2] == "model")
    return _CODE_JUDGED_RED_LINES, model_judged


def red_line_prompt_for(key: str) -> str:
    for row in RED_LINES:
        if row[0] == key:
            return row[3]
    return ""


def red_line_label(key: str) -> str:
    for row in RED_LINES:
        if row[0] == key:
            return row[1]
    return key


def persuasion_index(totals: list[tuple[int, int]]) -> float | None:
    """思路篇那把"说服力"尺：Σ(项目分 × 位次系数) ÷ 10。

    `totals` 是 [(项目分, 系数), ...]；任何一项分数未知就不算——
    一份缺了某个项目的加权平均数比"没算出来"更坏，它会让人以为排序没问题。
    """
    if not totals:
        return None
    acc = 0
    for score, coefficient in totals:
        if score is None:
            return None
        acc += int(score) * int(coefficient)
    return round(acc / 10, 1)


def share_of(total: int | None, coefficient: int, peers: list[tuple[int | None, int]]) -> float | None:
    """本项目占这份简历加权值的百分比（成品表头那句"占这份简历 31.5%"）。

    同简历其它项目的分数没读全 ⇒ 返回 None，报告写"算不出来"，不猜一个数。
    """
    if total is None:
        return None
    values = [(total, coefficient)] + list(peers)
    if any(score is None for score, _ in values):
        return None
    acc = sum(int(score) * int(coeff) for score, coeff in values)
    if acc <= 0:
        return None
    return round(int(total) * int(coefficient) / acc * 100, 1)


__all__ = [
    "BODY_FULL",
    "DIFFICULTY_BANDS",
    "DIMENSIONS",
    "DIMENSION_KEYS",
    "GRADE_BANDS",
    "MODEL_JUDGED_KEYS",
    "RANK_COEFFICIENTS",
    "RANK_SCORES",
    "RED_LINES",
    "RED_LINE_KEYS",
    "TOTAL_FULL",
    "difficulty_prompt_block",
    "dimension_full",
    "dimension_label",
    "grade_desc_of",
    "grade_of",
    "metric_gap_clauses",
    "mentions_dimension",
    "grade_scale_block",
    "has_paired_value",
    "is_known_difficulty",
    "judged_red_line_keys",
    "persuasion_index",
    "rank_coefficient",
    "rank_note",
    "rank_score",
    "read_dimensions",
    "red_line_label",
    "red_line_prompt_block",
    "red_line_prompt_for",
    "rubric_prompt_block",
    "share_of",
    "split_clauses",
    "stack_footprint",
    "total_of",
]
