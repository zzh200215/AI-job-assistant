"""结构感知的输入裁剪：超预算时按段落优先级**整段**丢弃，不按字符从头硬切。

出处：`简历与面试优化.md` §4 P1.1。修之前四处各自 `text[:6000]` / `text[:4000]`，切掉的正好是文档尾部——
而中文简历尾部常放着最近的那份工作（正序排布的简历），所以硬切丢的是最值钱的一段，且用户毫不知情。

两条设计约束的出处要分清：
* 简历侧优先级表照文档那句"基本信息→工作经历→项目→技能→教育→其他"；
* 段名识别走**关键词别名表**，段名**不要求独占一行**（他 2026-10-16 拍的那档）。
  真实 PDF/DOCX 抽出来的文本里，"工作经历：2021至今…"这种段名和正文同形的排布很常见，
  只认"整行只有段名"会在真实数据上大面积识别失败。
* **JD 那张表（`JD_PRIORITY_ORDER`）是护栏带出来的，文档没写过**——文档的优先级表只针对简历。
  排序依据取自现成的下游依赖：`required_skills` 是 B2 那条 skill_gap 的权威来源、也是模拟面试出题的输入。

识别的边界条件（也是这个模块唯一可能出错的地方）：段名必须落在**一行的开头**（允许前导空白与 `【`、`#`、`|`
这类装饰），否则正文里出现"负责过项目经历梳理"这种句子会被当成段落边界，把好端端的正文切掉半截。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 保留优先级：越靠前越晚被丢。文档 §4 P1.1 原表；段名写真实简历的完整写法（"项目经历"而非"项目"）。
PRIORITY_ORDER: tuple[str, ...] = ("基本信息", "工作经历", "项目经历", "技能", "教育", "其他")

# 每段的常见别名。列表内部顺序无关，编译时统一按长度倒序进正则交替（同一起点先试长的，
# 免得 "work experience" 里的 "experience" 抢位）。
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "基本信息": ("基本信息", "个人信息", "个人资料", "基础信息", "联系方式", "求职意向", "contact", "personal info"),
    "工作经历": (
        "工作经历",
        "工作经验",
        "职业经历",
        "任职经历",
        "工作履历",
        "work experience",
        "employment",
        "experience",
    ),
    "项目经历": ("项目经历", "项目经验", "个人项目", "项目介绍", "主要项目", "project experience", "projects"),
    "技能": ("专业技能", "技能特长", "技能清单", "技术能力", "技术栈", "技能", "technical skills", "skills"),
    "教育": ("教育背景", "教育经历", "学习经历", "学历背景", "教育", "education"),
    "其他": (
        "兴趣爱好",
        "自我评价",
        "个人评价",
        "附加信息",
        "获奖情况",
        "证书",
        "其他信息",
        # 这两档是 2026-10-16 扫 13 份真简历扫出来的：id 13 用「核心优势」、id 20 用「个人优势」当段名，
        # 表里没有时它们不独立成段，正文被并进上一段（教育）一起按低优先级丢掉。
        "个人优势",
        "核心优势",
        "其他",
        "interests",
        "awards",
        "others",
    ),
}

# JD 一族。见模块 docstring 第三条——这张表文档里没有，是 JD 侧护栏要求"不许从头硬切"逼出来的。
JD_PRIORITY_ORDER: tuple[str, ...] = ("任职要求", "岗位职责", "基本信息", "其他")

JD_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "任职要求": (
        "任职要求",
        "职位要求",
        "岗位要求",
        "任职资格",
        "招聘要求",
        "能力要求",
        "qualifications",
        "requirements",
        "what you'll bring",
    ),
    "岗位职责": ("岗位职责", "工作职责", "职位职责", "工作内容", "responsibilities", "main duties", "about the role"),
    "基本信息": (
        "工作地点",
        "薪资待遇",
        "薪酬范围",
        "经验要求",
        "学历要求",
        "职位信息",
        "基本信息",
        "job location",
        "salary",
    ),
    "其他": ("公司介绍", "我们提供", "福利待遇", "加分项", "团队介绍", "benefits", "perks", "about us", "其他"),
}

# 段名允许的前导装饰：行首空白、markdown 井号、引用符、书名号、项目符号。
# 最后两档不是猜的：2026-10-16 扫库里 13 份真简历的抽取文本，50 个识别到的段里漏认的 3 个
# 全是「U+258E 左侧竖块 + 专业技能 / 项目经历 / 教育背景」这一种排版；ASCII 竖线本来就允许，
# 它的孪生全角（U+FF5C）一并放行。码位写成反斜杠 uXXXX 交给 re 解，不进源文件字面量
# ——这台机器的写入通道会改写生僻码位，踩过。
_LEAD = r"[ \t\u3000]*[#>|\-•·※【\[\u258e\uff5c]*"
# 段名之后允许紧跟的装饰（同行形的"同形"就在这里被吃掉：冒号后的正文留在本段内）。
_TRAIL = r"\s*[：:】\]｜|、,，.。]*\s*"


@dataclass(frozen=True)
class SectionMap:
    """一张段落表：优先级 + 编译好的正则 + 别名回查。"""

    priority: tuple[str, ...]
    pattern: re.Pattern
    alias_to_section: dict[str, str]
    rank: dict[str, int]


def build_section_map(priority: tuple[str, ...], aliases: dict[str, tuple[str, ...]]) -> SectionMap:
    flat: dict[str, str] = {}
    for section in priority:
        for alias in aliases.get(section, ()):
            flat[alias.lower()] = section
    ordered = sorted(flat, key=len, reverse=True)
    pattern = re.compile(
        "(?m)^" + _LEAD + "(" + "|".join(re.escape(a) for a in ordered) + ")" + _TRAIL,
        re.IGNORECASE,
    )
    return SectionMap(
        priority=priority, pattern=pattern, alias_to_section=flat, rank={n: i for i, n in enumerate(priority)}
    )


RESUME_SECTIONS = build_section_map(PRIORITY_ORDER, SECTION_ALIASES)
JD_SECTIONS = build_section_map(JD_PRIORITY_ORDER, JD_SECTION_ALIASES)


@dataclass(frozen=True)
class BudgetResult:
    text: str
    truncated: bool
    dropped_chars: int
    dropped_sections: list[str]


def _spans(text: str, sections: SectionMap) -> list[tuple[str | None, int, int]]:
    """切成 (段名, start, end)。段名是 None 的那一段是第一个段名之前的引子，永远保留。"""
    hits: list[tuple[int, str]] = []
    for m in sections.pattern.finditer(text):
        # 边界取**整个匹配的行首**（m.start()），不是别名的起点（m.start(1)）：
        # 段名前挂着装饰时，用后者会把那个装饰留在上一段的尾巴上——
        # 裁剪结果末尾多出一个孤立符号，而上一段明明是被整段丢掉的。这条是护栏抓出来的。
        hits.append((m.start(), sections.alias_to_section[m.group(1).lower()]))

    if not hits:
        return [(None, 0, len(text))]

    spans: list[tuple[str | None, int, int]] = []
    if hits[0][0] > 0:
        spans.append((None, 0, hits[0][0]))
    for i, (start, name) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        spans.append((name, start, end))
    return spans


def fit_structured_text(text: str, limit: int, sections: SectionMap = RESUME_SECTIONS) -> BudgetResult:
    """把 `text` 裁到 `limit` 字符以内，超限时按 `sections.priority` 从**最不值得留**的那段开始整段丢。

    返回的 `text` 一定是原文若干片段的拼接：不重排、不改写、不在字符中间切（Python 的 str 切片切不开字符）。
    """
    if len(text) <= limit:
        return BudgetResult(text, False, 0, [])

    spans = _spans(text, sections)
    # 同名的多段（简历里两段"工作经历"是常态）共用一个优先级，但各自是独立的可丢单元。
    droppable = [(i, s) for i, s in enumerate(spans) if s[0] is not None]
    kept = set(range(len(spans)))

    def kept_length() -> int:
        return sum(spans[i][2] - spans[i][1] for i in kept)

    dropped: list[str] = []
    # 每一轮丢"优先级最低的那段"；同优先级里丢文档中更靠后的（真实简历里后面那段通常是次要内容）。
    # **始终留一段不丢**（`len(droppable) > 1`）：整份只有一段超大内容时（一栏 20k 字符的工作经历很常见），
    # 丢到底会喂给模型一个空串——那一发解析必然失败，比硬切更糟。留住的那段交给下面的兜底硬切收进预算。
    # 认不出任何段名时 droppable 为空，直接落到兜底硬切——仍然会盖上 truncation 标记，不再静默。
    while kept_length() > limit and len(droppable) > 1:
        worst = max(
            droppable,
            key=lambda pair: (sections.rank[pair[1][0]], pair[0]),
        )
        dropped.append(worst[1][0])
        kept.discard(worst[0])
        droppable.remove(worst)

    out = "".join(text[spans[i][1] : spans[i][2]] for i in sorted(kept))

    if len(out) > limit:
        # 全丢完仍超预算（或压根认不出段落）：按字符切到 limit，这是兜底而不是常态。
        out = out[:limit]
    return BudgetResult(out, True, len(text) - len(out), dropped)
