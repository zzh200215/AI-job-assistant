# 求职模块升级方案

> 版本：v1.0
> 日期：2026-09-19
> 面向：产品负责人 + 后端/AI 工程
> 前提决策：产品收缩为**单一求职者（求职）侧**，停止对企业/多租户/招聘侧投入
> 证据来源：对 `backend/app` 与 `frontend/src` 的代码审计，关键结论（`strategies.py:90,116`、`base_agent.py:59`、`task_center_service.py:73`、`llm_service.py:1043-1171`、`system.py:510-513`、`registry.py:138-141`）已逐条人工复核
> 配套：`docs/engineering-quality.md`、`docs/db-migrations.md`、`docs/tenant-schema-design.md`（本方案后转为历史文档）

---

## 1. 结论摘要

| 阶段 | 内容 | 工作量 | 为什么排在这个位置 |
|---|---|---|---|
| **A** | 诚实性修复（区分真实推理与 mock/模板、统一匹配分、补最小反馈闭环） | 2–3 天 | **测量前提**。不做这步，后续所有评测都在量 mock 数据 |
| **B1** | 行级简历改写闭环 + 改后重打分 | 1–1.5 周 | 所有下游功能都建立在"只能读不能改"的简历上 |
| **B2** | 证据锚定的职业规划（接 JD 库 + 薪资分位数，产出技能缺口图） | 1–1.5 周 | 让招牌功能从"编造文本"变成可执行；缺口图同时喂推荐与面试 |
| **C** | 让 "Agentic RAG + 多智能体协作" 这个说法成立 | 1.5–2 周 | 只修真实性，不追自主性 |
| **B3** | 推荐召回升级（`multi_recall` 接岗位 + ANN + 持久 embedding） | 1 周 | 依赖 A 的统一匹配分先落地 |
| **D** | 前端阶段 1–3（共享层 → feature 重组 → TypeScript） | 3–4 周，可与 A/B 并行 | 阶段 0 已交付（见 §7） |
| **E** | 工程债（鉴权泄露、静默失败、阻塞 I/O、schema 单一权威） | 1 周，穿插做 | 其中两项是一行级修复，建议立刻顺手做 |

**一句话优先级：A → B1 → B2 → C → B3，D/E 并行。**

---

## 2. 范围决策：收缩到求职侧

### 2.1 两种"砍掉"，成本差两个数量级

| 做法 | 成本 | 建议 |
|---|---|---|
| 从**路线图**上砍掉（冻结投入，不再演进） | 零 | ✅ 采用 |
| 从**代码库**里删掉 | 60+ 个 `tenant_filter`/`stamp_tenant` 调用点、6 张候选表上的 `TenantScopedMixin`、4 个 migration | ❌ 暂不 |

### 2.2 一个附带收益

此前审计发现的安全隐患——22/44 张表无 `tenant_id`、10 个 router 无租户谓词（`agent`、`prompt_trace`、`notification`、`reminder`、`timeline`、`career_path`、`salary_insight`、`jd`、`evaluation`、`organization`）——在单用户求职定位下**自动降级**：`tenant_id` 退化为常量 `1`，不再是安全边界，只是历史包袱。

### 2.3 必须先拆的两处地雷（不拆会直接坏）

1. **`backend/app/api/resume.py:121` 调用 `check_quota(resume_count)`**
   订阅表一旦移除，**简历上传直接失败**。这是全项目唯一的服务端配额强制点——`deep_analysis` / `ats_check` 从未在服务端校验过，付费墙是装饰性的（仅 `Subscription.vue:126-208` 有对比表）。
2. **`frontend/src/api/request.js:22-25` 给每个请求注入 `X-Organization-ID`**
   同时 `core/tenant_context.py:143-149,182` 的中间件每次请求都查 `tenant_domain_bindings` 表。表删了中间件还在 → **每请求 500**。

**推荐解耦手法**：保留 `tenant_id` 列（默认 `1`，惰性），只删中间件与 `tenant_filter`/`stamp_tenant` 调用点。**不要**改 migration、不要 drop 列——省掉约 90% 工作量且零回归风险。

### 2.4 企业侧资产清单

| 分类 | 内容 |
|---|---|
| 可安全删除（冻结即可） | `api/tenant.py`（约 12 管理端点）、`api/external/`（约 490 行 / 挂载于 `/api/v1`）、`api/organization.py`（12 端点）、`services/subscription_service.py`（592 行）、`services/{api_key,external,webhook}_service.py`、飞书 SSO（`organization.py:223-282`、`config.py:68-70`）、`OrganizationWorkspace.vue`(581)、`admin/{Tenants,Orders}.vue`、`api/{organization,tenant,subscription}.js`、`stores/tenant.js`、scheduler 中 `_run_tenant_billing_check`(`core/scheduler.py:191`) 与 `_run_external_api_monthly_billing`(`:207`) |
| **必须先解耦** | §2.3 两处；`TenantScopedMixin` 覆盖的 6 张候选表（`Resume`/`AnalysisRecord` 见 `models/history.py:11,64`，`InterviewSession` 见 `models/interview_session.py:10`，`JobApplicationPipeline` 见 `models/job_pipeline.py:50`，`JobRecommendationFeedback`/`JobBookmark` 见 `models/job_recommend.py:10,37`）；`knowledge_access.py:38-85`、`rag_service.py:99,120,257,272,327,354`、`job_recommend_engine.py:40-50,213,649-677` 的 org/tenant 入参；`interview_engine.py:382-389` → `interview_config_service.py:63-177` 的租户维度；migration `0018`/`0019`/`0020`/`0021` |
| 看着像企业侧、**其实是核心，必须留** | `prompt_trace`、评测报表、`system.py` 运行时指标、`analytics_service.py`（`tenant_id=None` 即平台行为，见 `:25-29`）、知识库（喂求职 RAG）、`interview_config` 表、`audit_log` |

> 补充事实：代码中**不存在 `recruiter` 角色**（全库 grep 0 命中）。`frontend/src/constants/roles.js:6` 的 `normalizeRole()` 把一切非 `admin` 归为 `candidate`，因此"招聘侧"实际指企业/多租户层，而非独立的招聘者界面。数据库里 role=`recruiter` 的用户是孤儿数据。

### 2.5 文档影响（需同步处理）

以下文档随企业侧冻结而失效，建议移入 `docs/archive/` 或在页首标注"已停止演进"：
`定价表.md`、`定价复盘.md`、`pilot-plan.md`、`pilot-report.md`、`产品白皮书.md`、`tenant-schema-design.md`、`api-reference.md`、`合同知识产权条款梳理.md`、`技术复用补充协议.md`、`统一交付手册.md`。

---

## 3. 求职侧现状评估

### 3.1 挂着 AI 名头、实为模板/启发式的功能

| 位置 | 现状 |
|---|---|
| `api/dashboard.py:416-545` `ai_suggestions` | 纯 if/else + f-string；**该文件未 import 任何 LLM** |
| `api/dashboard.py:257-279` `_generate_suggestions` | 同上 |
| `services/job_recommend_engine.py:520-536` `match_reason` | 字符串拼接 |
| `services/resume_analysis_service.py:79-170` `quick_score_resume` | 分节计数启发式，`len(experiences)*8` → **奖励凑字数** |
| `services/match_explainer_service.py:421-466` `_fallback_explain` | 固定输出 `"{dim}需提升"` + 静态 3 条建议 |
| `agents/career_path_agent.py:47-84` | 只喂简历摘要，**从不读 JD 库与薪资洞察**，`match_score` 与 `salary_range` 属编造 |

### 3.2 Mock 静默污染（最高危）

`services/llm_service.py` 约 500 行硬编码 `_MOCK_*`（`:163-626`），按 prompt 关键词分发（`:627-667`）；fallback 链最后一级即 mock（`:754-774`）。两条污染路径：

1. mock 结果**进入 LRU 结果缓存**（`:895-901`）
2. `persist_trace` 记录的是**配置的** provider 而非实际来源（`:856-859`）→ 一条 mock 回答被记成 `qwen`

返回字典不含 `is_mock` / `degraded` 字段，下游与前端**完全无法区分**（前端仅 `Profile.vue:64` 的 `status.demo_mode` 与 `JobRecommend.vue:810` 的 `_mock:'演示'`，后者是种子数据标签，不是 LLM 来源）。影响面：所有 `chat_json` 消费方——简历分析、匹配、优化、面试出题与报告、职业规划。

### 3.3 三套互相矛盾的匹配分

| 来源 | 计算方式 |
|---|---|
| `job_recommend_engine.py:253` | 引擎混合分 |
| `match_explainer_service.py:126-141` | 6 维加权 |
| `match_service.py:95-96` | LLM 自由打分后裁剪 |

`apply_match_score_cap` 只接在 `agents/match_agent.py:11` 与 `services/agent_steps.py:35`，**从未进入 `/recommend` 与 `/explain-match`** → 推荐页与解释页分数对不上。

### 3.4 反馈闭环是断的

`/feedback/apply-tuning`（`api/job_recommend.py:1367-1399`）确实能把权重写进排序（`:971,997-999` 读取），但：

- `dry_run` 默认 `True`（`:1383`）
- 更新幅度仅 4 个标量 ±0.03–0.05，且需 `total>=10` 才触发（`api/job_recommend.py:481`、`recommendation_tuning.py:188-221`）
- **决定性缺陷**：`recommend()` 既不查 `JobRecommendationFeedback` 也不查 `JobBookmark`，`_apply_filters`（`:576-600`）只过滤地域/行业/薪资/年限 → **候选人点了"踩"，同一个岗位下次刷新照样出现**
  （更正：产品上并没有"不感兴趣"按钮。`JobBookmark.action` 支持 `dismiss`、API 也接受该值，但 `JobRecommend.vue:726` 只发 `'bookmark'`。真实可达的负反馈信号是 ThumbsDown → `feedback_type="dislike"`）
- `_build_tuning_samples` 对每个异常样本重算 embedding（`:669-692`）

### 3.5 其他深度短板

- **推荐召回**：全量 JD 载入内存算 cosine（`:221-248`）+ 技能 **Jaccard** + 规则项（`:320-360`），非 candidate-conditioned；embedding 故障时**静默返回 `50.0`**（`:313`）；缓存键为 `resume_version`（`:71,208-213`）→ 简历不改则列表冻结
- **`multi_recall`（BM25+RRF+query rewrite）只服务知识库搜索**（`agent_steps.py:176`、`tools/__init__.py:48`、`rag_service.py:286`），**从不服役岗位推荐**
- **面试无难度概念**：`difficulty|难度|adaptive` 在 `interview_engine.py`、`interview_question_agent.py`、`interview_config_service.py` 中 0 命中；`next_question` 即 `current_index += 1`（`interview_engine.py:119-124`，上限 10 见 `:38`）；唯一"适应"是预写的 `follow_up_question`（`:252-276`）；报告是 4 个自评子分加权平均（`:374-400`），`FinalReportAgent` 异常时静默返回 `{}`（`:422`）且 UI 无提示
- **技能缺口被算了三遍且互不相认**：引擎 `gap`（`job_recommend_engine.py:259`）、explainer `missing_required`、career `gap_skills`，无共享产物 → 诊断缺口 → 规划 → 推荐 → 面试 不 chaining
- **embedding 无持久层**：进程内 LRU-512（`embedding_service.py:54-55`），每次 miss 重嵌整个 JD 库（`job_recommend_engine.py:243`）

### 3.6 扎实、不要动的部分

- **投递看板**：真状态机，`VALID_TRANSITIONS` 门禁 + `stage_history` 追加（`api/job_pipeline.py:466-511`），面试/offer 字段随迁移携带
- **提醒**：APScheduler 5min/1h 任务（`core/scheduler.py:40-85`）驱动 `reminder_service.py:65,146,220`，带 `_has_reminder_today` 去重（`:48`）
- **薪资洞察**：基于解析后的 `JD.salary_range` 做真实分位数计算（`api/salary_insight.py:106-130,278,291`），并披露 `sample_size`/`parsed_count`
- **面试题目 grounding**：`interview_question_agent.py:24-58` 注入简历+JD `parsed_json`，并对 `interview_q`/`skill_model` 做 RAG
- **错误处理**：集中在 `main.py:174-238`（限流、HTTPException、ValidationError、兜底）

---

## 4. 阶段 A｜诚实性修复（2–3 天）

**目标**：让系统说的每句话可追溯到真实来源；让"匹配分"只有一个。

| # | 任务 | 落点 |
|---|---|---|
| A1 | `llm_service` 所有返回路径附 `source: real\|mock\|truncated\|fallback` + `degraded_reason`；**mock 结果不入缓存**；trace 记实际来源 | `llm_service.py:754-774,856-859,895-901` |
| A2 | 前端所有 AI 输出区渲染降级标记（复用 A1 字段），mock 与真实一眼可辨 | 各视图 + 新增 `AppDegradedBadge` |
| A3 | §3.1 六处"假 AI"逐个处置：**要么真接 LLM，要么改名去掉 ai 前缀并在 UI 说明为规则计算**。`quick_score_resume` 必须重做（当前奖励凑字数） | `dashboard.py`、`job_recommend_engine.py:520-536`、`resume_analysis_service.py:79-170`、`match_explainer_service.py:421-466`、`career_path_agent.py:47-84` |
| A4 | 统一匹配分：新建 `resume_version × jd_id → score` 持久表，`/recommend`、`/explain-match`、缺口清单三处共读；`apply_match_score_cap` 接进主链路 | 新表 + `job_recommend_engine.py:253`、`match_explainer_service.py:126-141`、`match_service.py:95-96` |
| A5 | 反馈最小闭环：`dismiss` + `dislike` 合成抑制集，`recommend()` 在 SQL 层排除，并把抑制指纹接入缓存键 | `job_recommend_engine.py` |
| A6 | 摘掉 `resume.py:121` 的 `check_quota`（若确认不做商业化）；移除 `tenant_context` 中间件与 `request.js:22-25` 的 org 头 | §2.3 |

**验收**：
- 关掉真实 provider，UI 上每一处降级内容都有可见标记；`prompt_trace` 中不存在 `provider=qwen` 但内容为 mock 的记录
- 推荐页与解释页同一 `(resume_version, jd_id)` 分数一致
- 点"踩"后，该岗位在后续刷新中不再出现（可自动化测试）；`dismiss` 路径同样生效，待前端补入口
- 全量评测集（`backend/tests/eval/` 5 个 JSONL）在真实 provider 下重跑并入库，形成基线

---

## 5. 阶段 B｜核心能力升级

### B1 行级简历改写闭环（1–1.5 周）

现状 `analyze_resume`（`resume_analysis_service.py:23-76`）是单次 prompt 返回维度级 `issues`/`suggestions` + 分级路线图（`prompts/resume_analysis.py`）——**是建议，不是编辑**。

目标：产出**原文 → 改后**的行级对照，锚定到具体简历 block，可一键应用，应用后**重新打分**形成闭环。

- 数据：`Resume.parsed_json` 需保留 block 级 span 锚点（`resume_service.py:51` 目前单一解析）
- 接口：新增 `POST /resume/{id}/rewrite-suggestions` 与 `POST /resume/{id}/apply-rewrite`
- 版本：复用现有 `ResumeVersion` 与 diff 能力（`api/resume.py` 已有 versions/diff）
- 前端：`ResumeUpload.vue`(1312) / `ResumeCompare.vue`(1024) 内做左右对照 + 逐条应用

**验收**：候选人能在 5 分钟内接受/拒绝至少 5 条具体改写，并看到分数变化。

### B2 证据锚定的职业规划（1–1.5 周）

现状 `career_path_agent.py:47-84` 只看简历摘要，分数与薪资区间为编造；`CareerAgent` 硬依赖 Resume/Job/Match 三个 agent（`career_agent.py:22-25,28-32`），深度版只能在 SmartAnalysis 里跑到；RAG 退化时输出 `"暂无行业参考数据"`（`:44`）。

目标：把 **JD 库**与**薪资分位数**真正喂进推荐逻辑，产出**技能缺口图**作为共享产物。

- 缺口图成为单一权威产物，替掉 §3.5 的三套独立计算
- 同一份缺口图下游三用：推荐排序权重、面试练习重点、规划里程碑
- 无参考数据时必须**显式降级**（复用 A1 的 `source` 字段），不得静默编造

**验收**：规划给出的每个 `match_score` 与 `salary_range` 都能反查到支撑它的 JD 样本集合。

### B3 推荐召回升级（1 周，依赖 A4）

- 把 `multi_recall.py:315-417` 的 BM25+RRF+query-rewrite 从"只服务知识库"扩展到岗位召回
- 替掉全量 JD 载入内存算 cosine（`job_recommend_engine.py:221-248`）
- 技能相似度从 Jaccard 升级为 embedding 语义相似（`:320-360`）
- 持久化 embedding，去掉进程内 LRU-512 反复重嵌（`embedding_service.py:54-55`）
- 结果做多样性打散（当前纯按分数排序）
- embedding 故障时**报错或显式降级**，不再静默 `50.0`（`:313`）

> 若未来引入服务端向量库（Qdrant / pgvector），租户过滤应下推到检索层——当前是 `collection.query()` 之后用 Python 过滤（`rag_service.py:120-124`、`multi_recall.py:467-469`），`n_results` 已消耗，可见结果可能被截成 0。单租户化后此问题优先级下降，但仍是正确性缺陷。

---

## 6. 阶段 C｜让"Agentic"成立（1.5–2 周）

**原则：只修真实性，不追自主性。** 动态重规划、agent 协商、blackboard 主要是叙事价值，对求职产出质量帮助有限，本阶段不做。

| # | 任务 | 证据 |
|---|---|---|
| C1 | `BaseAgent.execute()` 恢复为唯一节点入口，找回 `AgentMessage`/`tokens_used`/`cost_cents` | `base_agent.py:59,102-103` 定义了却**全项目零调用**；策略层直打 `run_impl`（`strategies.py:90,116`）→ `api/multi_agent.py:127` 恒返回空消息列表、`task_center_service.py:138` 成本恒为 0 |
| C2 | `ctx.plan` 真正驱动执行：按 `depends_on` 生成任务图，替掉硬编码 7 个 `AGENT_ORDER` | plan 被持久化（`strategies.py:639`）但仅用于 `len()` 展示（`task_center_service.py:73`） |
| C3 | 填上 `strategies.py:778-786` 两个 `pass`，让 `RetrievalLog`/`SelfCheckLog` 有写端 | 二者被 `api/agent.py:131-132` 读取，但**从未被插入** |
| C4 | 编排实现从 6 个收敛到 2 个（native linear + langgraph）；删 `step_by_step`（绕过 agent 类直调 `agent_steps.py`）与 5 个死 agent | `StrategyFactory._STRATEGIES`（`strategies.py:808-815`）含 3 策略 + 3 个 langgraph 孪生体；死代码 `agents/interview_coach_agent.py`、`agents/summary_report_agent.py` |
| C5 | LangGraph 从线性链升级为真实拓扑：启用 checkpointer、`Send` 并行扇出、`interrupt` 人工介入 | `langgraph_flow.py:204-222` 的 `_wire_sequential_graph` 只画线性链，等价于 for 循环换写法 |
| C6 | `chat_with_tools` 补 usage recording / tracing / cache / fallback | `llm_service.py:1043-1171` 全无，而 `MatchAnalysisAgent` 是唯一工具调用者（`match_analysis_agent.py:66-80`）→ **线性策略最关键一步完全不计费**；`:1084` 是一句被丢弃的表达式 |
| C7 | 清理重复 agent：`Resume`/`ResumeParse`、`Job`/`JDParse`、`Match`/`MatchAnalysis`、`Interview`/`InterviewQuestion`、`Summary`/`SummaryReport` 五对；`is_critical` 恒为 True 属无效标志 | `registry.py:97-133` 用别名缝合，`context.py:11-22` 把两个名字映射到同一字段 |

**验收**：`/api/multi-agent` 返回真实消息序列；任务中心显示非零 token 与成本；`prompt_trace` 能还原每个节点的输入输出；评测集在收敛后的两条编排路径上结果一致。

---

## 7. 阶段 D｜前端（已完成的阶段 0 + 后续）

### 已完成：阶段 0（提交 `3987eb0`）

- Vitest + @vue/test-utils + jsdom；12 条工作台路由挂载冒烟；`node --test` 11/11、`vitest` 19/19、`eslint --quiet` 0 error、build 通过
- **棘轮守卫** `tests/unit/styleDebtRatchet.test.js`：逐文件写死色配额 + 通配选择数/`!important`/`.page-shell` 重复声明/API 越权的天花板。预算**只能下调**，还完债不降会失败并提示新值
- 61 处 `background:#fff` → `var(--app-surface-strong)`，30 个文件。用逐路由 `getComputedStyle` diff 验证：4/5 路由逐字节零差异，`/jobs/search` 恰好 10 处由白块 bug 修正为深色
- `panels.css` token 化并删除零引用死代码
- ESLint 边界规则：禁裸 `axios`；views 必须走 `src/api/*`（7 个现存越权文件列入豁免清单）
- **通配网实测为承重结构**：5 条路由上兜住 157 个元素实例 / 约 60 个类名，故未在本阶段删除，转为棘轮跟踪

### 待做

| 阶段 | 内容 | 收口目标 |
|---|---|---|
| 1 | 共享层 `components/ui/`：`AppPanel`、`AppTag`（唯一状态色表）、`AppScoreBar`、`AppTable`+分页、空/错/骨架态；`utils/format/` 统一日期；`composables/useAsync` | 收掉 15 份日期函数副本、8 套状态色映射、**3 套互相矛盾的分数色板**（`ExplainMatch.vue:179`/`SmartAnalysis.vue:1743` 的 `#67C23A` 系 vs `SmartAnalysis.vue:1749` 的 `#1DB954` 系 vs `InterviewReport.vue:388` 第三套）、24 处手写 `loading`、150+ 个 `catch` |
| 2 | 按 feature 重组 `src/features/{resume,analysis,jobs,pipeline,interview,planning,eval,admin,legal}/`；先出纯 `git mv` + alias 的机械提交，再拆 5 个巨页 | `JobSearch.vue`(3344)、`SmartAnalysis.vue`(2914)、`CareerPlanning.vue`(2164)、`PipelineKanban.vue`(1661)、`InterviewRoom.vue`(1462)。抽一个 `JobCard` 同时让 4 个文件变短（`JobSearch.vue:276,391,476` + `JobRecommend.vue` 重复渲染同一卡片） |
| 3 | TypeScript（`allowJs` 渐进、新文件强制 `.ts`）+ `unplugin` 自动导入，删掉 `plugins/element.js` 的 111 行手写注册 | 视图数从 45 降至约 41（去 `OrganizationWorkspace`、`admin/{Tenants,Orders}`，`Subscription` 视付费决策） |

其他已知项：`localStorage` 9 个 key 分散在 64 个调用点，其中 `token`/`user` 在 `api/request.js:17` 与 `stores/auth.js:35` **两处读取**（双份真相源）；`recruit.lastResumeId`/`lastJDId`/`lastRecordId` 是跨页隐式握手（`AgentAnalysis.vue:512-513`、`AnalysisResult.vue:410-422`），应改由 Pinia 承载；`.vite-startup-error.log`、`dist/`、`backend/.coverage` 属被提交的构建产物。

---

## 8. 阶段 E｜工程债（1 周，穿插做）

**建议立刻顺手修的两项（一行级）：**

- `GET /api/system/metrics` **无鉴权**（`api/system.py:510-513`，router 裸挂在 `:37`）→ 泄露内部模型名、队列深度、失败计数
- `orchestration/registry.py:138-141` 用裸 `except Exception` 包裹 registry 构造，异常时静默重置为**空**registry → 之后每次 `registry.get()` 抛 `KeyError` 且无诊断信息

**其余：**

| 项 | 证据 |
|---|---|
| 事件循环被阻塞 I/O 占用 | 195 个 `async def` 端点全部使用同步 `SessionLocal`；`chat_json` 用阻塞 `requests.post`（`llm_service.py:701`）直调于 `interview_rest.py:452` 与健康探针 `system.py:140`；`knowledge_service.save_and_process` 把 parse→chunk→embed→Chroma add 全串在请求里（`api/knowledge.py`）；`resume_export_service.py:321` 同步跑 WeasyPrint；`job_spider.py:72`、`webhook_service.py:155` 用 `time.sleep` |
| WebSocket 鉴权与内存无界 | `interview_ws.py:39-43` 绕过 FastAPI 依赖手工校验 query token；`:23-34` 的进程级 `_engine_pool` 无上限，且无跨副本亲和 |
| schema 有第四条路径 | Alembic（22 个 revision）+ `Base.metadata.create_all`（`main.py:61`）+ `core/schema_bootstrap.py`（453 行 / 13 个手写 MySQL DDL，`AUTO_CREATE_TABLES` 默认 True）+ 散落的 `add_columns.py`/`reset_kb.py`。已存在重复：`ensure_agent_message_usage_columns`(`:23-41`) vs `20260624_0003`；`ensure_user_role_column`(`:9-20`) vs `20260801_0017`。DDL 是 MySQL 方言而测试引擎是 SQLite |
| 连接池未配置 | `core/database.py:9-20` 未设 `pool_size`/`max_overflow`，默认 5+10 的 queuepool 面对线程池密集应用 |
| 测试覆盖真实路径为零 | `pytest.ini` 的 `--cov-fail-under=0`；`conftest.py` 强制 `LLM_PROVIDER=mock`/`EMBEDDING_PROVIDER=mock` + 内存 SQLite → 真实 HTTP 路径、工具循环、rerank 模型、Chroma server 行为**从未被执行**。62 文件 / 429 测试函数广度不错，但 `backend/.coverage`(122KB) 被提交进了工作树 |
| 队列无 ack/retry/DLQ | 默认 `ThreadPoolExecutor(max_workers=4)`（`orchestration_backend.py:76-79`）；Redis 队列存在（`:93-141`）但 `mark_stale_running_tasks_failed`（`orchestration_runner.py:236-259`）启动时把 30 分钟以上任务**一律置失败**，多副本重启会误杀正常长任务；`run_strategy_async` 构造两个 `TaskPayload` 后丢弃（`:126-132,317-323`） |
| 限流粒度 | slowapi + Redis（`core/rate_limiter.py:38-49`）仅按 IP → NAT 后用户共享额度，单用户可耗尽 LLM 花费 |
| RAG 索引陈旧 | `multi_recall.py:158-217` 的 BM25 是手写内存索引，首次调用全量扫 Chroma，`_dirty` 标志（`:140`）**从未被读** → 入库后静默返回旧 chunk；`score()` 为 O(terms×docs) 纯 Python（`:238-250`） |
| Rerank 生产用启发式 | `rerank_service.py:125-159` 可选本地 cross-encoder，否则 jieba 词重叠 + 硬编码 0.5/0.3/0.2 权重；`RERANKER_MODEL_PATH` 默认未设 |
| 死代码 | `api/tracking.py` 定义了 router 但**从未被 include**；`agents/agent_orchestrator.py`、`services/smart_orchestrator.py`、`services/agent_workflow.py` 是 `DeprecationWarning` 垫片层，靠 import 维持存活 |
| 缺少 router 级鉴权 | 31 个 router / 218 端点，无一处使用 `dependencies=[...]`，鉴权靠每端点 `Depends(get_current_user)`，**保护是 opt-in 而非构造保证** |
| 三个 router 共享 `/jobs` 前缀 | `api/router.py:54-56`；当前不冲突仅因 `job_recommend.py:1448` 的 `/{jd_id:int}` 是单段 |

---

## 9. 里程碑

| 里程碑 | 内容 | 出口判据 |
|---|---|---|
| **M1**（约 1 周） | A 全部 + E 的两项一行级修复 + A6 解耦 | mock 可辨识、匹配分唯一、负反馈生效、metrics 已鉴权、评测基线入库 |
| **M2**（约 2.5 周） | B1 | 候选人可一键应用 ≥5 条行级改写并看到分数变化 |
| **M3**（约 4 周） | B2 | 规划中每个分数与薪资区间可反查支撑样本；缺口图成为单一权威产物 |
| **M4**（约 6 周） | C | `/api/multi-agent` 返回真实消息；成本非零；编排收敛到 2 条路径且结果一致 |
| **M5**（约 7 周） | B3 | 推荐走 `multi_recall` + ANN；embedding 持久化；故障不再静默降级 |
| **持续** | D 阶段 1→3、E 余项 | 棘轮数字单调下降；`src/components/` 从空目录长出组件层 |

---

## 10. 待决策项

1. **付费墙是否保留**（阻塞 A6）。`check_quota` 仅管简历数量，`deep_analysis`/`ats_check` 从未服务端生效。确认不做商业化 → 摘掉 `resume.py:121`，企业侧即可安静冻结；要保留 → 需补齐服务端功能级校验，否则是装饰性付费墙。
2. **企业侧是冻结还是删除**。本方案建议冻结。若将来要真删，§2.3 两处地雷与 migration `0018`–`0021` 是前置。
3. **是否引入服务端向量库**（Qdrant / pgvector）。当前 Chroma 是嵌入式 persistent client（`core/chroma_client.py:16,47-50`），每个 uvicorn worker/副本各持一份（`docker-compose.prod.yml:100` 挂 volume）——多副本部署下这是一致性隐患，与 B3 一并决策。
4. **`docs/` 归档策略**（§2.5）。

---

## 11. 附录：本方案未采纳的一条建议

上一轮审计中曾提出"把全局主题从 `[class*='-card']` 类名通配改为覆盖 Element Plus `--el-*` 变量，删掉 56 个 `!important`"。实测该改法**不无损**：摘除通配网后 5 条路由出现 157 个元素实例的样式回归，而收窄到显式类名列表需先完成 D 阶段 1 的组件抽取。因此该动作已从"阶段 0"移出，改为由 `styleDebtRatchet.test.js` 以天花板数值跟踪、随 D 阶段单调下降。
