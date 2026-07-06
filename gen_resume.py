# -*- coding: utf-8 -*-
"""生成大模型方向简历 (Word 格式) — 基于项目当前状态更新"""
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

doc = Document()

# ===== 样式设置 =====
style = doc.styles['Normal']
font = style.font
font.name = '微软雅黑'
font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
style.paragraph_format.space_after = Pt(2)
style.paragraph_format.line_spacing = 1.25

for section in doc.sections:
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)


def add_section_title(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor(0x1A, 0x3A, 0x5C)
    pPr = p._p.get_or_add_pPr()
    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}>'
                     '<w:bottom w:val="single" w:sz="8" w:space="1" w:color="1A3A5C"/>'
                     '</w:pBdr>')
    pPr.append(pBdr)
    return p


def add_normal(text, bold=False, size=10.5, color=None, align=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = color
    if align:
        p.alignment = align
    return p


def add_bullet(text, level=0):
    p = doc.add_paragraph(text, style='List Bullet')
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.left_indent = Cm(0.5 + level * 0.5)
    return p


def add_proj_header(name, time, tech):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run(f"\u25ce{name}")
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x1A, 0x3A, 0x5C)
    run2 = p.add_run(f"    {time}")
    run2.font.size = Pt(9)
    run2.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    p2 = doc.add_paragraph()
    p2.paragraph_format.space_after = Pt(2)
    run3 = p2.add_run(f"技术栈：{tech}")
    run3.font.size = Pt(9)
    run3.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


# =========================================================================
# 正文
# =========================================================================

p = add_normal("曾子豪", bold=True, size=22, color=RGBColor(0x1A, 0x3A, 0x5C),
               align=WD_ALIGN_PARAGRAPH.CENTER)
p.paragraph_format.space_after = Pt(2)

add_normal("求职意向：大模型应用开发工程师 / AI 应用开发",
           color=RGBColor(0x66, 0x66, 0x66), size=10,
           align=WD_ALIGN_PARAGRAPH.CENTER)

add_normal("📞 17779699791  |  📧 2974467965@qq.com  |  📍 江西吉安  |  🎂 22岁",
           size=9, color=RGBColor(0x44, 0x44, 0x44),
           align=WD_ALIGN_PARAGRAPH.CENTER)

# ===== 教育背景 =====
add_section_title("教育背景")
p = doc.add_paragraph()
run = p.add_run("南昌大学科学技术学院")
run.bold = True
run.font.size = Pt(10.5)
run2 = p.add_run("    计算机科学与技术  本科    2021.09 – 2025.06")
run2.font.size = Pt(10.5)
run2.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

add_normal("核心课程：数据结构与算法、操作系统、计算机网络、数据库原理、Python程序设计、机器学习基础",
           size=9.5, color=RGBColor(0x44, 0x44, 0x44))

# ===== 专业技能 =====
add_section_title("专业技能")
skills = [
    ("AI / 大模型：", "提示词工程(Prompt Engineering)、RAG 检索增强生成、Query Rewrite 查询改写、LangChain 框架、向量数据库(Chroma)、DeepAgents、LangGraph、大模型 API 调用(OpenAI/Qwen)、Embedding 模型应用、Agent 智能体编排"),
    ("编程语言：", "Python（熟练）、C / C++（熟练）、Shell、JavaScript（基础）"),
    ("后端开发：", "FastAPI、RESTful API、WebSocket、SQLAlchemy、MySQL、Redis、Docker"),
    ("Linux / 系统：", "Linux 系统编程（文件 I/O、多进程/多线程/Socket）、TCP/IP 协议、Git"),
    ("前端 / 其他：", "Vue3、Element Plus、Qt 框架、C51/STM32 单片机、MQTT"),
]
for cat, items in skills:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run(cat)
    run.bold = True
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(0x1A, 0x3A, 0x5C)
    run2 = p.add_run(items)
    run2.font.size = Pt(9.5)
    run2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

# ===== 项目1：AI 智能招聘助手 =====
add_section_title("项目经历")

add_proj_header(
    "AI 智能招聘助手 — 基于 RAG 与大模型的多智能体协作平台",
    "2025.03 – 至今",
    "Python、FastAPI、LangChain、Chroma、DeepAgents、Qwen(通义千问)、Vue3、WebSocket"
)
add_normal(
    "独立开发全栈 AI 招聘平台，集成 6 个 Agent 多智能体协作系统、Agentic RAG 11 步工作流、"
    "AI 模拟面试(WebSocket 实时对话)、岗位混合推荐、岗位搜索爬虫、职业路径规划、"
    "匹配度规则解释器、Query Rewrite 查询改写、RAG 知识库管理等 9 大模块，"
    "覆盖求职者从简历优化到面试准备的完整链路。",
    size=9.5
)
for duty in [
    "设计 Agentic RAG 工作流引擎：11 步串行步骤（意图识别→解析→RAG 检索→匹配→优化→面试题→职业规划→校验→报告），"
    "关键步骤失败自动降级，非关键步骤错误跳过，保障分析可用性",
    "实现 多智能体编排系统：6 个 Agent（简历诊断/岗位分析/匹配评估/面试辅导/职业规划/汇总）按依赖层级并行执行，"
    "支持意图驱动的动态 Agent 选择",
    "设计 RAG Query Rewrite 查询改写服务：LLM 将用户原始检索意图改写为 3-5 个多维度检索 query "
    "（技能方向/职责方向/面试方向/能力模型方向），多 query 并行检索 Chroma 后合并去重，显著提升召回质量",
    "实现 匹配度规则解释器：6 维规则引擎（技能 Jaccard/项目命中/经验年限/学历等级/关键词覆盖/加分项）+ "
    "LLM 自然语言解释，支持按岗位类型自动切换权重（技术岗/产品岗/校招），不依赖 LLM 做评分计算",
    "基于 FastAPI WebSocket 实现 AI 模拟面试引擎：30 秒超时控制、四维实时评分（完整性/准确性/深度/表达）、"
    "低分自动追问机制、累计 3 次超时结束",
    "设计 混合排序推荐引擎：向量相似度(Chroma)×0.6 + 规则匹配(Jaccard/薪资/地点/经验)×0.4，"
    "支持多维度筛选与推荐反馈闭环",
    "实现 招聘网站爬虫：统一 JobSpider 接口（BOSS直聘 API + BeautifulSoup HTML 降级 + 本地模拟数据三级降级），"
    "搜索结果去重入库，爬虫失败自动降级到本地历史数据兜底",
    "构建 CareerPathAgent 职业方向推荐：LLM 根据简历技能/经验推荐 5-8 个适合岗位方向，"
    "含匹配度评分、已具备/需提升技能标注、薪资范围参考",
    "对接通义千问 Qwen API 实现简历解析、JD 匹配、面试评估、职业规划等 8+ 场景的 LLM 调用，"
    "Exception 捕获 + 结构化 fallback 输出保障系统稳定",
]:
    add_bullet(duty)
add_normal("💡 覆盖大模型应用全链路：RAG → Agent 编排 → Prompt Engineering → LLM API → 向量检索 → Query Rewrite → 规则引擎",
           size=9, color=RGBColor(0x66, 0x66, 0x77))

# ===== 项目2：深度研搜 =====
add_proj_header(
    "深度研搜 (DeepSearch) — 对话式多智能体深度研究系统",
    "2025.03 – 至今",
    "Python、DeepAgents、LangGraph、LangChain、FastAPI、WebSocket、Tavily、MySQL、RAGFlow、React、Vite"
)
add_normal(
    "独立开发面向调研问答场景的 AI 应用，基于多智能体协作整合互联网搜索、"
    "MySQL 结构化查询和 RAGFlow 私有知识库检索，支持文件上传解析、过程可视化和研究报告导出。",
    size=9.5
)
for duty in [
    "设计 主智能体 + 任务子智能体协作流程，由主智能体做问题拆解和任务分发，子智能体分别负责网络搜索、数据库查询和知识库检索，"
    "通过 DeepAgents + LangGraph 管理执行状态与结果汇总",
    "整合 三路检索能力：Tavily API 互联网搜索 + MySQL 结构化数据查询 + RAGFlow 私有知识库问答，"
    "针对同一问题做多源信息补充，提升回答完整性和可用性",
    "基于 FastAPI + WebSocket 实现研究过程实时推送，把检索进度、工具调用、异常信息和最终结果同步到前端，"
    "优化长耗时任务的交互体验",
    "实现 会话级上下文隔离，使用 ContextVar 管理 session_dir 和 thread_id，配合路径校验避免多会话数据串用和文件访问越界",
    "设计 文件处理与报告导出流程，支持 PDF/DOCX/XLSX/Markdown 等附件读取，自动生成 Markdown 研究报告并导出 PDF",
    "补充基础异常兜底和结果落库能力，便于后续做历史记录查询和问题复盘",
]:
    add_bullet(duty)
add_normal("💡 AI 应用落地方向：多智能体任务编排 → 多源检索增强 → 实时推送 → 报告交付",
           size=9, color=RGBColor(0x66, 0x66, 0x77))

# ===== 其余项目不变 =====
add_proj_header("基于 Qt 的即时通讯系统（集成 ChatGPT）", "2025.02 – 2025.04",
                "C++、Boost.Asio、Qt、gRPC、Redis、ChatGPT API、SQLite")
add_normal("跨平台 IM 系统，C++ 全栈 + 分布式微服务架构，支持万人并发，集成 ChatGPT 智能对话。", size=9.5)
for duty in [
    "Boost.Asio 搭建高性能异步网络通信模块，支持长连接与万级并发",
    "网关/验证/状态/聊天 4 微服务架构，gRPC 通信，Redis 缓存会话状态",
    "集成 ChatGPT API 实现智能对话助手，设计异步请求队列支撑高并发",
    "Qt 跨平台客户端：注册/登录/好友管理/实时消息/智能对话",
]:
    add_bullet(duty)
add_normal("💡 LLM API 集成 + 高并发对话服务设计", size=9, color=RGBColor(0x66, 0x66, 0x77))

add_proj_header("天气预报桌面应用", "2024.11 – 2024.12",
                "Qt、HTTP、JSON、QSS")
add_normal("基于 Qt 框架的桌面天气应用，HTTP 请求获取天气数据并可视化展示。", size=9.5)
for duty in [
    "Qt Creator 搭建 UI + QSS 美化，HTTP 模块请求第三方天气 API",
    "JSON 数据解析 + 信号槽机制实现城市搜索与切换交互",
    "EventFilter 绘制最高/最低温度变化曲线",
]:
    add_bullet(duty)

add_proj_header("流媒体广播系统", "2024.08 – 2024.09",
                "C、UDP 组播、多线程、令牌桶、进程间通信")
add_normal("基于 C/S + UDP 组播的广播系统，守护进程运行，令牌桶流量控制。", size=9.5)
for duty in [
    "多线程处理频道信息 + 令牌桶算法流量整形",
    "客户端多进程架构：父进程接收 → 管道 → 子进程解码播放",
]:
    add_bullet(duty)

# ===== 自我评价 =====
add_section_title("自我评价")
for item in [
    "拥有完整的大模型应用项目经验：RAG 检索增强生成、Agent 多智能体编排（DeepAgents / LangGraph）、Query Rewrite 查询改写、Prompt Engineering、LLM API 集成",
    "全栈开发能力（Python/FastAPI 后端 + Vue3/React 前端），独立完成从架构设计到部署上线",
    "扎实的计算机基础（数据结构/操作系统/网络），快速学习新技术并落地实践",
    "良好的团队协作与沟通能力，有较强的自驱力和技术热情",
]:
    add_bullet(item)

# ===== 保存 =====
output_path = "曾子豪_大模型应用开发工程师.docx"
doc.save(output_path)
print(f"简历已更新: {output_path}")
