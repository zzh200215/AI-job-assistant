"""组合分析各份测试共用的载荷。

三个项目的形状是**故意各不相同**的：领域不同、骨架不同、有的带基线有的不带、
技术栈两两有交集但没有任何一个组件三个项目都用——这样"共用栈求交集""换皮比对"
"按项目点名扣分"这三族判据才有东西可分，也不会碰巧全绿。

`DUP` 那一条的正文与 `SECOND` 逐字相同，只换项目名：它是红线 1（同一个项目换名字写两遍）
唯一的确定形状，钉的是"命中即出局"，而合法输入不可能长成那样。

内容全部是本仓库自己编的；反推件里有公司名与客户信息，PII 那条口径不许进仓。
"""

from __future__ import annotations

FIRST_DESC = """面向内部法务的合同初审流程。
项目描述：合同原文与扫描件存 MinIO，条款结构化结果落 PostgreSQL，法规片段入 Chroma。
核心职责：
用 LangGraph 把审查拆成解析、条款抽取、BM25 与向量召回、Rerank、报告生成几个节点。
证据冲突或上下文过长时重组证据包，仍不足则转人工复核。
项目成果：
常规合同扫查初稿由人工约 30 - 60 分钟缩短至 5 - 10 分钟。
基于 80 余份历史审查意见搭建样本库。"""

SECOND_DESC = """把经营日报周报从人工 Excel 统计改成系统生成。
项目描述：指标口径写在 MySQL 的规则表里，自然语言问法走 FastAPI 进编排。
核心职责：
负责取数与图表生成两段，异常归因那一层交给规则判定。
项目成果：
日报出稿从每天 2 小时压缩到 15 分钟以内。"""

THIRD_DESC = """企业知识库的问答与工具调用。
项目描述：文档切分入 Chroma，实体关系入 Neo4j，回答前按出处校验。
核心职责：
负责召回与重排两段；引用不完整时不答，标成待确认。
项目成果：
检索命中率没有前后对比，只写了覆盖 1200 余份文档。"""

FIRST = {
    "name": "合同初审助手",
    "role": "主程",
    "start": "2025.02",
    "end": "2025.10",
    "desc": FIRST_DESC,
    "tech": ["LangGraph", "Chroma", "FastAPI", "Neo4j"],
}
SECOND = {
    "name": "经营分析日报",
    "role": "参与",
    "start": "2024.06",
    "end": "2024.12",
    "desc": SECOND_DESC,
    "tech": ["FastAPI", "MySQL"],
}
THIRD = {
    "name": "知识库问答",
    "role": "算法工程",
    "desc": THIRD_DESC,
    "tech": ["Chroma", "Neo4j", "Qwen"],
}
# 第四、第五个项目只为一件事存在：**把 2~N 泛化验到 N=5**。
# 参考件是三个人的合理规模，而锁死三个会让"多项目"这个功能在两三个以上时静默画歪——
# 表格列数、叙事段数、排列那一格的 `PJ-0N` 都跟着 N 长，没有样本就没有证据。
FOURTH_DESC = """设备巡检记录的问答与看板。
项目描述：巡检工单进 MinIO，结构化记录落 PostgreSQL，指标口径写在 YAML 里。
核心职责：负责取数与看板两段，缺证据的指标一律标灰不画。
项目成果：巡检看板出稿由每天 40 分钟缩短到 5 分钟，覆盖 6 类设备。"""

FIFTH_DESC = """内部培训材料的自动生成。
项目描述：课程大纲与题库存 MySQL，生成结果过一遍逐字回查再发布。
核心职责：负责生成与回查两段，回查不过的不发布。
项目成果：一门课的讲义由 3 天缩短到半天，题目复用率约 4 成。"""

FOURTH = {
    "name": "巡检记录看板",
    "role": "主程",
    "start": "2023.09",
    "end": "2024.03",
    "desc": FOURTH_DESC,
    "tech": ["MinIO", "PostgreSQL", "Vue"],
}
FIFTH = {
    "name": "培训材料生成",
    "role": "算法工程",
    "desc": FIFTH_DESC,
    "tech": ["MySQL", "Qwen", "FastAPI"],
}

# 与 SECOND 逐字相同、只换个名字——红线 1 的形状。
DUP = {
    "name": "另一份经营分析",
    "role": "主程",
    "desc": SECOND_DESC,
    "tech": ["FastAPI", "MySQL"],
}

# 单项目分析已经跑过的那两份（组合表头「单项目均分」要从这里取）。
PROJECT_TOTALS = {0: 88, 1: 79}

PARSED = {"project_experience": [FIRST, SECOND, THIRD]}
PARSED_WITH_DUP = {"project_experience": [FIRST, SECOND, DUP]}
PARSED_FIVE = {"project_experience": [FIRST, SECOND, THIRD, FOURTH, FIFTH]}
ENTRIES_BY_INDEX = {0: FIRST, 1: SECOND, 2: THIRD, 3: FOURTH, 4: FIFTH}

ALL_TECH = ["LangGraph", "Chroma", "FastAPI", "Neo4j", "MySQL", "Qwen"]


# ---------------------------------------------------------------- 过复核的"干净载荷"工厂
# 三份测试（service / html / job）都要一份**能被真复核整条吃下**的载荷：
# 放在这个非 `test_` 模块里而不是让测试互相 import——pytest 的 prepend 导入模式
# 能让它侥幸跑通，但那是运气不是约定。
def quote_of(entry: dict) -> str:
    """取这一条项目原文里的第一行正文，当作"逐字引用"用。"""
    for line in entry["desc"].splitlines():
        text = line.strip()
        if len(text) >= 8:
            return text
    return entry["name"]


def dimensions_payload(indices: list[int] | None = None) -> dict:
    anchors = [
        quote_of(entry) for entry in ([FIRST, SECOND, THIRD] if not indices else [ENTRIES_BY_INDEX[i] for i in indices])
    ]

    def note(position: int) -> str:
        return f"「{anchors[position % len(anchors)]}」这一条是原文里能逐字找到的说法"

    return {
        "d1_role_signal": {"score": 20, "note": note(0)},
        "d2_combo_distinct": {"score": 16, "note": note(1)},
        "d3_metric": {"score": 14, "note": note(2)},
        "d4_growth_line": {"score": 11, "note": note(0)},
        "d5_interview": {"score": 10, "note": note(1)},
    }


def profile_payload(indices: list[int] | None = None, **overrides: object) -> dict:
    picked = indices or [0, 1, 2]
    anchor = quote_of(FIRST)
    payload = {
        "summary": {
            "projects_line": "三个项目叠在一起看",
            "common_skeleton": "多路召回取依据、在依据上判断、不足时转人工",
            "difference_line": "一个重可追溯、一个重确定性、一个重数据质量",
        },
        "dimensions": dimensions_payload(picked),
        "red_lines": [],
        "difficulty": {"level": "L3", "reason": "这一组叠了检索与编排两类范式，留有口径但没有微调那一层"},
        "compare": [
            {
                "row": key,
                "cells": [{"project_index": index, "text": f"这一行的说法，取自「{anchor}」"} for index in picked],
            }
            for key in (
                "domain",
                "skeleton",
                "orchestration",
                "retrieval",
                "highlight",
                "metric",
                "transferable",
            )
        ],
        "capabilities": [
            {
                "capability": key,
                "cells": [
                    {"project_index": index, "cell": "重点覆盖" if position == 0 else "部分覆盖"}
                    for position, index in enumerate(picked)
                ],
            }
            for key in ("hybrid_retrieval", "knowledge_graph", "agent_orchestration", "refusal", "llmops")
        ],
        "shared_stack": ["FastAPI", "Chroma"],
        "risks": [
            {"point": "骨架相同", "detail": "追问差异时只能重说技术栈", "fix": "每个项目各补一条别的没有的决策"},
            {
                "point": "归因未拆",
                "detail": "几项改动一起上，各自贡献说不清",
                "fix": "固定其他变量、每次只改一处跑对照",
            },
            {"point": "业务效果薄", "detail": "没有复核通过率与退回率口径", "fix": "补一次使用埋点统计"},
        ],
    }
    payload.update(overrides)
    return payload


def diagram_payload(indices: list[int] | None = None) -> dict:
    picked = indices or [0, 1, 2]
    return {
        "narrative": {
            "title": "把这几个项目讲成一条从找得到到判得准的成长线",
            "stages": [
                {
                    "project_index": index,
                    "stage_name": f"阶段 {position + 1}",
                    "points": [
                        f"要点写的是「{quote_of(ENTRIES_BY_INDEX[index])}」这一段的原文",
                        "把依据与判断分开，依据不足时不硬下结论",
                        "留下了自己的口径与一次对照",
                        "边界：没写上线多久、谁在用",
                    ],
                    "core_question": "这一阶段要回答的核心问题是依据从哪来",
                    "keywords": "检索、依据、复核",
                }
                for position, index in enumerate(picked)
            ],
            "one_line": "先解决依据从哪来，再解决判断能不能复现——不是同一件事做几遍",
        },
        "rounds": [
            {"key": key, "text": "这一轮面试官问的是差异、取舍与投入分配，要拿出能讲两层的说法"}
            for key in ("single_deep_dive", "selection_reason", "cross_compare", "authenticity", "next_step")
        ],
        "reuse_read": "共用的那几只组件说明这套选型是稳定的，不是每个项目现学",
        "unique_read": "只在一个项目里出现的那几只，说明选型跟着场景走",
        "sameness_answer": "回答是不是换皮分两层：先说共用栈证明熟练，再说差异栈证明不是照搬",
        "strategy": "每一轮备一段一分钟的口述稿，第三与第四轮是组合层的胜负手",
        "usage": "讲组合时先看横向对比，再用叙事主线串成递进，陪练重点过后两轮",
    }


def advice_payload(indices: list[int] | None = None) -> dict:
    picked = indices or [0, 1, 2]
    reverse = list(reversed(picked))
    return {
        "arrangements": [
            {
                "project_indices": picked,
                "scenario": "目标岗位偏编排与可追溯",
                "pros": "最亮的那一条排在前面抓眼球",
                "cons": "第二份的分更高时会被问为什么不放前面",
            },
            {
                "project_indices": reverse,
                "scenario": "目标岗位偏数据质量与知识库",
                "pros": "先立量化与清洗那一条",
                "cons": "协议化那条最容易体现架构能力却被放到最后",
            },
            {
                "project_indices": [picked[2], picked[0], picked[1]] if len(picked) == 3 else picked,
                "scenario": "目标岗位偏工程化与知识库建设",
                "pros": "先展示最量化的再展示清洗",
                "cons": "最体现架构能力的那一条被放到最后容易被忽略",
            },
        ],
        "default_choice": 0,
        "default_reason": "默认按简历顺序，因为它正好形成一条递进",
        "asked_before": [
            {
                "asked": "这几个项目有什么本质不同",
                "answer": "骨架相同但解决的核心问题不一样，一个重依据、一个重复现、一个重生长",
            },
            {
                "asked": "为什么技术栈重叠这么多",
                "answer": "重叠的那几只是这一类系统的基础组件，差异的那几只是跟着场景选的",
            },
            {
                "asked": "跨度这么大你一个人怎么做",
                "answer": "先说参与边界：每个项目负责的模块不同，领域判断标准是和业务方一起定的",
            },
        ],
        "strengthen": [
            {
                "gap": "归因都合在一起测",
                "action": "固定其他变量、每次只改一处跑对照",
                "expected": "D3 指标责任这一维站得住",
            },
            {"gap": "业务效果普遍偏薄", "action": "每个项目补一到两个业务口径", "expected": "D2 区分度与真实感更稳"},
            {
                "gap": "叙事顺序没有设计",
                "action": "按递进重排并各写一句核心问题",
                "expected": "位次与叙事这一维不靠运气",
            },
        ],
        "citation": {
            "borrow": "值得学的是组织方式：每个项目抓一个最独特的点，项目之间形成递进",
            "adapt": "不能照搬领域词与指标口径，换方向要写自己真做过的那一处",
            "breaks": "一抄就穿的是都写成主导、都套同一套口径、把跨度讲得理所当然",
        },
    }


def questions_payload(indices: list[int] | None = None, count: int = 12) -> dict:
    kinds = ("差异与取舍", "选型与理由", "真实与边界", "评测与归因", "整合与演进", "沉淀与成长")
    anchor = quote_of(FIRST)
    body = (
        f"「{anchor}」这一条是我负责的段落。把这几个项目放在一起看，骨架确实是同一套："
        "非结构化内容进库、多路召回取依据、在依据上判断、不确定的部分交给人复核。"
        "但每个项目要解决的核心问题不一样，所以组合出来的方案也不一样——"
        "一个重依据可追溯，一个重判断能复现，一个重知识库能不能长。"
        "如果重来一次，我会把每一项改动的贡献单独测一遍，而不是几项一起上，"
        "因为归因不清楚，后面要优化就不知道该往哪使劲。"
    )
    items = []
    for position in range(count):
        status = "需补强" if position == 10 else "可答"
        items.append(
            {
                "question": f"跨项目追问（{kinds[position % len(kinds)]}这一类）：面试官真会问出口的那一句",
                "kind": kinds[position % len(kinds)],
                "answer": body,
                "followups": [
                    {"kind": "为什么", "text": "追问一：这一条为什么这么定"},
                    {"kind": "数据", "text": "追问二：口径怎么测、样本量多少"},
                ],
                "status": status,
                "missing": ["缺一个分项差值"] if status != "可答" else [],
                "risk_ref": None,
            }
        )
    return {"questions": items}
