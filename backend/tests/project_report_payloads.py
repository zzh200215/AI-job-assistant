"""单项目分析各份测试共用的载荷。

放在一个非 `test_` 开头的模块里而不是让测试互相 import：pytest 的 prepend 导入模式
能让它侥幸跑通，但那是运气不是约定。

`ENTRY.desc` 的句式取自反推件里那些真实形状（分栏标题 + 条目 + 带基线的成果），
内容是本仓库自己编的——原文里有公司名与客户信息，PII 那条口径不许进仓。
"""

from app.services import project_report_service as svc
from app.services.project_report_schema import raw_entry_text

PROJ = """面向内部法务的合同初审流程，先在高频风险初筛场景里试用。
项目描述：合同原文与扫描件存 MinIO，条款结构化结果落 PostgreSQL，法规片段入 Chroma，风险关系入 Neo4j。
核心职责：
基于 LangGraph 将审查拆成解析、条款抽取、BM25 与向量召回、Rerank、图谱查询、风险分级、报告生成节点。
针对证据冲突与上下文过长触发 reset 重组证据包或转人工复核。
使用 Qwen 7B 做 LoRA 适配验证，PEFT 管理 Adapter。
项目成果：
常规合同扫查初稿由人工约 30 - 60 分钟缩短至 5 - 10 分钟。
基于 80 余份合同模板与历史审查意见搭建样本库。
输出统一落到 6 段式审查底稿。"""

ENTRY = {
    "name": "合同初审风险过滤",
    "role": "主程",
    "start": "2025.02",
    "end": "2025.10",
    "desc": PROJ,
    "tech": ["LangGraph", "Neo4j", "Chroma", "Redis", "FastAPI"],
}
PEER = {
    "name": "经营分析助手",
    "role": "参与",
    "desc": "把日报周报从手动 Excel 统计改为系统生成。",
    "tech": ["FastAPI"],
}
PARSED = {"project_experience": [ENTRY, PEER]}

BODY = raw_entry_text(ENTRY)
PEERS = svc.peer_projects(PARSED, 0)


def profile_payload():
    return {
        "portrait": {
            "domain": "法律",
            "scene": "合同初审的前置风险过滤",
            "main_line": "图谱多跳 + 混合检索 + Agent 编排",
            "components": "Neo4j、LangGraph、Chroma、Qwen",
        },
        "dimensions": {
            "d1_role_signal": {
                "score": 22,
                "note": "技能带踩中图谱检索与编排：「基于 LangGraph 将审查拆成解析」这一条一屏就认得出是同行。",
            },
            "d2_depth": {"score": 20, "note": "有攻坚痕迹（「触发 reset 重组证据包」），但样本量只有一句规模描述。"},
            "d3_metric": {"score": 15, "note": "耗时那一条给了前后两值，其余跟踪项缺优化前的值。"},
            "d4_transfer": {"score": 12, "note": "「图谱查询」那一条抽掉法律业务照样成立。"},
            "d5_interview": {"score": 11, "note": "图谱节点这一条能撑三轮，项目成果那一条撑不到第二轮。"},
        },
        "red_lines": [],
        "difficulty": {"level": "L5", "reason": "图谱多跳、编排与模型适配三类范式叠加。"},
        "highlights": [
            {
                "metric": "扫查初稿耗时",
                "value": "人工 30 - 60 分钟 → 5 - 10 分钟",
                "basis": "前置初筛环节，含人工二次加工前",
            },
            {"metric": "样本库规模", "value": "80 余份", "basis": "模板、条款样例、法规片段与历史意见四类语料"},
        ],
        "hooks": [
            "为什么把风险关系做成图谱而不是全进向量库",
            "常规解释与复杂风险的分流判定怎么定",
            "证据冲突时重置证据包的具体逻辑",
        ],
        "risks": [
            {"point": "评测只有跟踪值", "detail": "追问从多少提到多少给不出差值", "fix": "同批样例跑一次适配前后对照"},
            {
                "point": "适配验证停留在测试环境",
                "detail": "追问实际部署规模与并发时会空白",
                "fix": "【待补：按单卡压测路径跑一遍得到并发上限实测值】",
            },
        ],
        "peer_dimensions": [
            {
                "project_index": 1,
                "dimensions": {
                    "d1_role_signal": 20,
                    "d2_depth": 18,
                    "d3_metric": 12,
                    "d4_transfer": 10,
                    "d5_interview": 9,
                },
            }
        ],
    }


def answer(extra: str = "") -> str:
    base = (
        "这条链路我按一次判断只做一件事来切：先把合同变成可检索的文本与段落坐标，再切成带类型的条款单元，"
        "召回负责取回证据，图谱负责把条款到义务到风险到法规那条链拉出来，最后由规则表定等级、模板渲染出底稿。"
        "切完之后每一环都能单独测，出错定位很快，改哪一段也不会牵到别处。"
    )
    return base + extra


def question(**override):
    row = {
        "question": "这个项目当初解决的是什么问题？",
        "kind": "背景与定位",
        "answer": answer(),
        "followups": [
            {"kind": "为什么", "text": "追问一：为什么定位成初筛而不是自动定稿"},
            {"kind": "边界", "text": "追问二：定稿责任在谁，出了错怎么追"},
        ],
        "status": "可答",
        "missing": [],
        "risk_ref": None,
    }
    row.update(override)
    return row


def question_diagram():
    return {
        "title": "三层链路：下层没做好会在上层暴露",
        "cards": [
            {"title": "数据底座", "lines": ["原文、条款、法规、风险关系各归其位"]},
            {"title": "编排", "lines": ["决定什么时候去查"]},
            {"title": "分流", "lines": ["决定用哪条路查"]},
        ],
        "note": "排查问题从底往上看。",
        "how_to_draw": (
            "先画最底下那条三层底座横条，再往上画编排那一层，最上面画分流；边画边说这三层是递进的而不是并列的三块，"
            "收尾一定要补那一句：排查问题从底往上看，下层没做好一定在上层暴露。"
        ),
    }


def questions_payload(rows=None):
    if rows is None:
        rows = [
            question(),
            question(question="整体链路是怎么走的？", kind="链路与选型", diagram=question_diagram()),
            question(question="有没有试过但放弃的方案？", kind="权衡与代价"),
            question(
                question="效果是怎么跟踪的？",
                kind="数据与评测",
                status="需补强",
                missing=["条款识别准确率的前后两值", "【待补：样例集规模】"],
            ),
            question(question="哪一处最难？", kind="权衡与代价", status="高危", missing=["冲突判定阈值"], risk_ref=1),
        ]
    return {"questions": rows}


def diagrams_payload():
    return {
        "background": "这是一套给法务做合同初审的系统，原来一份常规合同要人工逐条读再翻法规库。",
        "needs": {
            "items": [
                {"title": "条款遗漏风险高", "detail": "长合同人工逐条读，附件里的条款容易看漏，要求全量覆盖扫一遍。"},
                {"title": "法规依据查找慢", "detail": "同一类条款反复查同一批法规，要求把依据结构化留存。"},
                {"title": "审查口径不一致", "detail": "风险等级依赖个人经验，要求统一成分段底稿。"},
            ],
            "roles": "法务主责判断与定稿，采购与商务协同提交。",
            "delivery": "上传合同后走解析、抽取、召回、图谱、分级与出稿，输出分段审查底稿。",
            "constraints": "合同原文不得外发；每条风险都要能解释来自哪段合同。",
        },
        "function_arch": {
            "layers": [
                {"name": "使用角色", "mine": False, "cells": [{"title": "法务", "lines": ["初筛复核与定稿"]}]},
                {"name": "业务入口", "mine": False, "cells": [{"title": "合同上传", "lines": ["原文与扫描件"]}]},
                {"name": "AI 能力层", "mine": True, "cells": [{"title": "混合召回", "lines": ["关键词与向量"]}]},
                {"name": "依托组件", "mine": False, "cells": [{"title": "Neo4j", "lines": ["图库"]}]},
            ],
            "boundary": "★ 我负责：链路分层、分流编排、检索与出稿；Neo4j 与 Chroma 是开源组件，本人负责选型与接入。",
            "deep_dive": [
                {
                    "where": "我负责的边界怎么答",
                    "point": "哪几块是本人设计实现，哪几块是选型接入",
                    "source": "职责第 2 条",
                },
                {
                    "where": "为什么分四层存",
                    "point": "读取方式不同决定了放哪一层",
                    "source": "「条款结构化结果落 PostgreSQL」",
                },
            ],
        },
        "core_flow": {
            "input": {"title": "输入", "lines": ["法务上传合同原文并选问题类型"]},
            "nodes": [
                {"no": 7, "title": "合同解析", "lines": ["版面解析还原段落与表格边界", "识别不出标待人工，绝不猜内容"]},
                {"no": 8, "title": "条款抽取与召回", "lines": ["按编号规则切条款", "关键词与向量混合召回后重排"]},
                {"no": 9, "title": "图谱多跳", "lines": ["按路径模板查关系", "模型不参与查询构造"]},
                {"no": 10, "title": "风险分级与出稿", "lines": ["模型判类别，规则表定等级", "分段底稿由模板渲染"]},
            ],
            "exit": {"title": "出口", "lines": ["系统只出初筛底稿，法务二次加工定稿"]},
            "fallbacks": ["证据对不上或上下文过长 → 重置证据包重检", "等级不确定 → 不硬判，转人工复核"],
            "state": "共享状态：每个节点只写自己产出的字段，下游只读自己需要的。",
            "deep_dive": [
                {"where": "为什么拆成四个节点", "point": "一次判断只做一件事，出错好定位", "source": "职责第 3 条"},
                {"where": "回退为什么分两档", "point": "能不能确定是唯一判据", "source": "「触发 reset 重组证据包」"},
            ],
        },
        "system_arch": {
            "layers": [
                {
                    "name": "编排层",
                    "components": [
                        {"title": "入口分流", "line": "按问题类型决定走哪条"},
                        {"title": "状态图", "line": "节点串起来"},
                    ],
                },
                {
                    "name": "能力层",
                    "components": [
                        {"title": "混合召回", "line": "关键词与向量"},
                        {"title": "图谱查询", "line": "路径模板"},
                    ],
                },
                {
                    "name": "存储层",
                    "components": [{"title": "对象存储", "line": "合同原件"}, {"title": "图库", "line": "风险关系"}],
                    "principle": "同一份内容放哪层，取决于它是被精确读取、被语义匹配，还是被跨实体串联。",
                },
            ],
            "deep_dive": [
                {"where": "分层存储的一致性", "point": "统一主键与更新入口", "source": "职责第 1 条"},
                {
                    "where": "图谱为什么半自动维护",
                    "point": "关系错了会藏在多跳路径里",
                    "source": "项目中自建图谱那一段",
                },
            ],
        },
        "sequence": {
            "lanes": ["法务", "入口分流", "解析", "召回", "图谱", "出稿"],
            "messages": [
                {"from": "法务", "to": "入口分流", "text": "上传合同并选问题类型"},
                {"from": "入口分流", "to": "解析", "text": "显式规则分流后交给解析"},
                {"from": "解析", "to": "召回", "text": "条款列表进入混合召回"},
                {"from": "召回", "to": "图谱", "text": "条款单元按路径模板多跳"},
                {"from": "图谱", "to": "出稿", "text": "分级结果与证据一起出底稿"},
            ],
            "branches": ["证据对不上 → 重置证据包重检", "等级不确定 → 转人工复核"],
            "artifacts": {
                "task": "合同编号与问题类型",
                "process": "条款列表、证据列表、图谱路径",
                "control": "检索轮次、待确认项",
            },
            "deep_dive": [
                {"where": "最危险的异常", "point": "引用缺失意味着没依据就下了结论", "source": "成果第 3 条"},
                {"where": "解析错了怎么办", "point": "标待人工，绝不用模型补", "source": "职责第 4 条"},
            ],
        },
        "reading_note": "教学先看背景与需求两张，面试先看功能架构那张的高亮层。",
    }


def advice_payload():
    return {
        "teaching": {
            "suitable": "图谱建模粒度 / 混合检索分流 / 多跳查询 / 结构化输出约束",
            "steps": "第一步用纯检索跑通条款解释；第二步补图谱只管复杂风险；第三步加多路径分流；第四步引入适配并做前后对照",
            "entry": "先拿一批合同与一份风险清单，把条款—风险—依据三层关系画出来，只做两跳查询",
            "stage": "适合放在检索与编排之后的进阶环节",
        },
        "reuse": {
            "structure": "先写业务定位，再写分层数据链路，最后写多路径推理",
            "expression": "「原文—证据—图谱」分层这种说法可以搬",
            "replace": "行业口径、语料规模、全部耗时数字都要换成自己的",
            "counterexample": "照搬耗时那段会被追问前置环节的边界与语料来源",
        },
        "practice": {
            "method": "先自己口述一遍录音，再对照口述稿改结论句与口径",
            "rehearsal": "追问预演到第三层才算过关",
            "timing": "主答案控制在两分钟内，每轮追问一分钟内",
        },
        "strengthen": [
            {
                "gap": "评测只有跟踪值",
                "action": "同批样例跑一次适配前后对照，记录差值",
                "expected": "D3 指标责任 良 → 优",
            },
            {
                "gap": "图谱命中率没有结果值",
                "action": "抽一批复杂风险样本对比走与不走图谱",
                "expected": "D5 面试承载力更稳",
            },
        ],
        "citation": {
            "borrow": "✅ 可借鉴：分层表述与按读取方式决定放哪一层",
            "adapt": "⚠️ 需改造：换成自己真实接触过的文档类型与审核规则",
            "breaks": "🔴 一抄就穿：耗时那一段与样本规模的数字",
        },
    }
