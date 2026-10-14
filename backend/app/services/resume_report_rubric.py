"""七维评分口径的可执行版本 —— `docs/resume-report-spec.md` §2 的唯一权威。

Prompt、服务端校验、报告渲染、前端条形图都从这里取维度表，不在任何一侧另写一份：
一张表写两处，迟早会有一处被改掉而另一处仍然"看起来是对的"。

本模块**不做任何模型调用**，只做三件事：给出维度表、把模型返回的分数读成可信的数
（越界/非数字/缺失一律判"未知"，不当 0 分）、由七维之和算总分与等级。
总分与等级是规则算的，所以它们不挂 AI 名头（A3 那条口径，见
`tests/test_rule_output_not_labelled_ai.py`）。
"""

from __future__ import annotations

from typing import Any

# (键, 对外标签, 满分, 是否带 ★, 判分口径一句话)
DIMENSIONS: tuple[tuple[str, str, int, bool, str], ...] = (
    (
        "metric_ownership",
        "指标责任与达成（C）★",
        20,
        True,
        "只算候选人自己负责并达成/优化出来的指标，团队成果与来源不明的数字不计入；"
        "看责任归属是否清楚、指标是否带口径（判定标准/样本量/标注方式）、"
        "有没有「优化前 → 优化后」，只有绝对值或全篇没有工程指标的压在这一档。",
    ),
    (
        "interview_hooks",
        "面试钩子设计（E）★",
        10,
        True,
        "简历里能递给面试官的钩子数量、四类覆盖（数字/权衡/边界/踩坑）、在各项目上的分布、"
        "有没有会把人带进坑里的钩子；钩子停在「为什么做」而代价没有数的扣分在这里。",
    ),
    (
        "role_fit",
        "岗位契合度（赛道定位）",
        20,
        False,
        "方向标签能否 5 秒判出、求职意向与优势段是否指向同一方向、该方向词表覆盖度；"
        "技能区写了名词但项目里没有对应实践的只提示、不扣分。",
    ),
    (
        "transferability",
        "技术可迁移性",
        15,
        False,
        "按 L0 会用 / L1 懂原理 / L2 能做主给占比，多数条目要能看出选型依据与边界；" "跨垂类要留下一层能带走的判断。",
    ),
    (
        "project_depth",
        "项目深度与真实感",
        20,
        False,
        "像不像真做过：细节密度（样本量、标注规模、语料条数）、约束与代价有没有写、"
        "有没有一处踩坑、切片与解析这类参数写得够不够。",
    ),
    (
        "expression_structure",
        "表达与结构",
        10,
        False,
        "句式（动词开头、无空泛形容词、无无佐证的「熟练掌握」）、人称一致、错别字与时间线连续、"
        "同一个数字在全文前后是否一致。",
    ),
    (
        "advantage_section",
        "个人优势介绍",
        5,
        False,
        "有独立优势节、讲的是差异化而不是「精通 XX」、给能力配了证据、与项目一一呼应、" "有一条站得住的方法论标签。",
    ),
)

DIMENSION_KEYS: tuple[str, ...] = tuple(row[0] for row in DIMENSIONS)
TOTAL_FULL: int = sum(row[2] for row in DIMENSIONS)

# 等级由总分映射（规则，不是模型）。
GRADE_BANDS: tuple[tuple[str, int, int, str], ...] = (
    ("A", 85, 100, "稀缺档，七维没有明显短板"),
    ("B", 75, 84, "质量过关，可直接投"),
    ("C", 65, 74, "项目描述需要重构后再投"),
    ("D", 0, 64, "先补齐再谈投递"),
)

# 低于这个总分，模块五不出题、换成"暂缓生成"版（`docs/resume-report-spec.md` §6）。
# 65 是本仓库自己定的（反推待定），不是从成品里抄来的。
INTERVIEW_MIN_TOTAL: int = 65

_LABELS: dict[str, str] = {row[0]: row[1] for row in DIMENSIONS}
_FULLS: dict[str, int] = {row[0]: row[2] for row in DIMENSIONS}


def dimension_label(key: str) -> str:
    return _LABELS.get(key, key)


def dimension_full(key: str) -> int:
    return _FULLS.get(key, 0)


def rubric_prompt_block() -> str:
    """把维度表渲染成 prompt 里的那段口径说明。

    由表生成而不是手抄进 prompt：手抄那一份改了，服务端校验还按旧表判。
    """
    lines = []
    for key, label, full, _star, rubric in DIMENSIONS:
        lines.append(f"- {key}（{label}，满分 {full}）：{rubric}")
    lines.append(f"七维满分之和 = {TOTAL_FULL}。")
    return "\n".join(lines)


def score_or_none(value: Any, full: int) -> int | None:
    """把一个模型给的分数读成 0..full 的整数，读不出就 None。

    布尔不是分数（`True` 是 int 的子类，不能只靠 isinstance 放行）；越界不是分数
    ——把 120 夹到 100 会让一个没数过的维度看起来是满分维度。

    七维与六维那张项目尺（`project_report_rubric`）共用这一条读法："越界不当 0 分"
    是一个量的定义，两张表各写一份，迟早一份被放宽。
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number < 0 or number > full:
        return None
    return int(round(number))


def read_dimensions(raw: Any) -> list[dict[str, Any]]:
    """把模型返回的七维读成固定顺序、每维可信的报告行。

    缺维度 = 未知，不是 0 分；多出来的未知键忽略（模型爱加维度，加一条判"未知"的
    行反而让总分更难解释）。
    """
    source = raw if isinstance(raw, dict) else {}
    rows: list[dict[str, Any]] = []
    for key, label, full, star, _rubric in DIMENSIONS:
        value = source.get(key)
        note = ""
        missing: list[str] = []
        if isinstance(value, dict):
            score = score_or_none(value.get("score"), full)
            # 只收字符串：`str({...})` 会把 Python 表示法印进候选人看到的表格里。
            note = value["note"].strip() if isinstance(value.get("note"), str) else ""
            missing = [
                item.strip() for item in value.get("missing_keywords") or [] if isinstance(item, str) and item.strip()
            ]
        else:
            score = score_or_none(value, full)
        rows.append({"key": key, "label": label, "full": full, "star": star, "score": score, "note": note})
        if missing:
            rows[-1]["missing_keywords"] = missing
    return rows


def total_of(rows: list[dict[str, Any]]) -> int | None:
    """七维之和；任一维未知则总分为未知。"""
    scores = [row["score"] for row in rows]
    if any(score is None for score in scores) or len(scores) != len(DIMENSIONS):
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
    """模块一结尾那一行等级说明（分数含义 + 不夸能力上限）。

    四档全列：总分落在 64 以下时报告仍要给一句"这是什么等级"，
    只列三档会让它显示一个没有解释的 D。
    """
    return " / ".join(f"{name} {low}–{high}（{desc}）" for name, low, high, desc in GRADE_BANDS)


def missing_keywords_of(rows: list[dict[str, Any]]) -> list[str]:
    """把各维带的缺失关键词收成一个有序去重列表（词表覆盖住在 role_fit 那一档）。"""
    seen: list[str] = []
    for row in rows:
        for word in row.get("missing_keywords") or []:
            if word not in seen:
                seen.append(word)
    return seen


def interview_allowed(total: int | None) -> bool:
    """总分是否够出面试预演。总分未知时**不出**——一句"还没算出来"比一套没有依据的口述稿诚实。"""
    return total is not None and total >= INTERVIEW_MIN_TOTAL


__all__ = [
    "DIMENSIONS",
    "DIMENSION_KEYS",
    "GRADE_BANDS",
    "INTERVIEW_MIN_TOTAL",
    "TOTAL_FULL",
    "dimension_full",
    "dimension_label",
    "grade_desc_of",
    "grade_of",
    "grade_scale_block",
    "interview_allowed",
    "missing_keywords_of",
    "read_dimensions",
    "rubric_prompt_block",
    "score_or_none",
    "total_of",
]
