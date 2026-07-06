# AI 应用工程师成长路线

## 适合人群

- 已有后端、数据或算法基础，希望转向 AI 应用落地
- 对 RAG、Agent、工作流编排、企业知识库有持续兴趣
- 目标岗位偏向 AI 工程、智能应用平台、企业 Copilot

## 典型阶段

### Phase 1: 基础补齐

- 理解 LLM 基础能力边界：上下文长度、工具调用、结构化输出
- 掌握向量检索、Chunking、Embedding、Rerank 的基本链路
- 具备 Python 服务化能力，能用 FastAPI 或 Flask 封装应用

### Phase 2: 单体应用落地

- 独立完成一个 RAG 问答系统
- 能评估召回质量、回答质量和成本
- 具备 Prompt 版本管理和失败兜底意识

### Phase 3: 多 Agent 与生产化

- 能将任务拆成检索、规划、执行、校验等节点
- 掌握 LangGraph 或等价编排框架
- 理解缓存、限流、日志、评测、灰度发布等生产约束

## 岗位核心能力

- Prompt engineering
- RAG pipeline design
- Tool calling and workflow orchestration
- Backend engineering and API design
- Evaluation and observability

## 建议项目

- 企业知识库问答助手
- 面向招聘场景的多 Agent 分析系统
- 带权限控制与引用溯源的 Copilot

## 面试关注点

- 你如何判断检索质量差是 Chunk、Embedding 还是 Query Rewrite 的问题
- 你如何控制 LLM 成本和响应时间
- 你如何设计多 Agent 之间的上下文传递结构
