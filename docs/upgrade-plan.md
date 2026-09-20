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
  （更正：审计时产品上并没有"不感兴趣"按钮——`JobBookmark.action` 支持 `dismiss`、API 也接受该值，但 `JobRecommend.vue:726` 只发 `'bookmark'`，真实可达的负反馈信号只有 ThumbsDown。A5 补齐阶段已在卡片头部加入"不感兴趣"入口，并配套"已忽略的岗位"恢复面板）
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
- 点"踩"后，该岗位在后续刷新中不再出现（可自动化测试）；`dismiss` 路径同样生效，且隐藏可逆
- 全量评测集（`backend/tests/eval/` 5 个 JSONL）在真实 provider 下重跑并入库，形成基线

### 已完成：阶段 A（提交 `b5461aa`…`37a1f45`，A5 补充入口在后续提交）

| # | 落地内容 | 证据 |
|---|---|---|
| A1 | `llm_service` 每条返回路径带 `response_source`（`real/fallback_model/truncated/mock/tool_output`）+ 原因与尝试次数；**mock/truncated 不再进缓存**；缓存命中不写 trace（保住无 DB 快路径） | `llm_service.py` `_LLM_PROVENANCE_CONTEXT`、`CACHEABLE_RESPONSE_SOURCES`；`test_llm_provenance.py` 9 例 |
| A2 | 降级对内可查：`prompt_trace` 新增 `response_source`/`degraded` 列（migration `0023`）、`/api/prompt-trace` 支持过滤并输出 `degraded_rate`；Prometheus `llm_degraded_responses_total`；APScheduler 双阈值告警（mock 1 次即 critical，其他降级 3 次 warning）。前端 `/prompt-traces` 增加应答来源列与降级卡片 | `20260919_0023_llm_response_source.py`、`operational_alert_service.py`、`test_llm_degraded_visibility.py` 8 例 |
| A3 | 六处假 AI 逐个处置：`quick_score_resume` 更名语义为"完整度"并停止凑字数奖励；`total_score` 不再由完整度回填；模板化 `structure/expression_issues` 与 `Math.random()` 假诊断整体删除，改为显式错误态；`/ai-suggestions` → `/next-actions` 并标注 `mode:"rules"`，删除"凑够 3 条"补位；career prompt 禁止输出无数据支撑的 `match_score` 与薪资区间；规则版解释器标注 `explain_mode:"rules"` | `test_rule_output_not_labelled_ai.py` 7 例 |
| A4 | 新建 `match_score` 表 + `match_score_service` 作为 `(resume_id, resume_version, jd_id)` 唯一权威；推荐引擎改为"向量召回 → 规则粗排 → canonical 重排"，展示分与召回分离（`retrieval_score` vs `match_score`）；cap 收敛进 `compute_rubric` 单一入口；`_coerce_years` 区分"未标注"与 0 年 | migration `0024`、`test_match_score_single_source.py` 8 例 |
| A5 | `dismiss` + `dislike` 合成抑制集，`recommend()` 在 **SQL 层** `notin_` 排除（不再占用 `limit` 名额），抑制指纹进缓存键；随后补齐入口与恢复：卡片"不感兴趣"按钮、点踩即时移除卡片、`GET /bookmarks/dismissed` 返回隐藏原因、`POST /bookmarks/restore` 一次清掉两类信号、`_bookmarked` 改为后端回填 | `test_recommend_suppression.py` 6 例、`test_suppressed_job_recovery.py` 11 例、`jobRecommendDismiss.test.js` 4 例 |

阶段 A 结束时：**467 后端 / 20 前端**测试通过；补齐入口与恢复后为 **478 后端 / 24 前端**。

**遗留（不阻塞 B）**：
- `chat_with_tools` 轮次耗尽时把工具回执当最终答案返回（已标 `tool_output` 可辨识，修复归入阶段 C）
- A6 仍等付费墙决策（见 §10.1）
- `.card-actions` 6 个按钮已换行成 2 排（本次改动前即如此），归入阶段 D 共享层处理

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

#### 已交付：B1.1–B1.4（提交 `019f40c`、`5239d26`、`dfee148`、`37d5766`）

落点与原计划不同的一处：改写不是打在 Markdown 上，而是打在 `parsed_json` 的**锚点块**上——`ResumeVersion.content` 是评分链路读不到的另一条轨道，改它不会影响任何分数。

| 件 | 内容 | 证据 |
|---|---|---|
| B1.1 | `resume_blocks.py`：`build_resume_blocks` 给出 `self_evaluation/skills/work[i].desc/proj[i].desc` 稳定锚点；`apply_block_edits` 按锚点写入并返回 `before/after`。两条约束：空 section 不进清单（否则会诱导模型编造经历），且解析锚点必须走同一份清单；返回值永远是深拷贝（否则 ORM 不标脏、改动不落库） | `test_resume_blocks.py` 12 例 |
| B1.2 | `POST /resume/{id}/rewrite-suggestions`：只把清单交给模型，服务端逐条复核——未知锚点、`original` 与简历对不上、同块重复、无改动、长度超 2 倍，全部带原因返回而非静默丢弃；建议一律不落库，mock 结果不会比请求活得更久 | `test_resume_rewrite_suggestions.py`、`prompts/resume_rewrite.py`；`blocks_json` 已加入 `rendering` 的不可信字段表 |
| B1.3 | `POST /resume/{id}/apply-rewrites`：写回 `parsed_json` + 重算目标岗位分差。`expected_original` 拒绝过期锚点（按位置寻址，建议生成后简历又改过就会覆盖新文字）；改写前的 `parsed_json` 存成 JSON 版本行，撤销才可能 | 同上，含快照与 delta 断言 |
| B1.4 | 诊断弹窗内"行级改写"面板：按需生成、逐条勾选、只应用已采纳、被拒条目连同原因展示、无目标岗位时明说不显示分数变化、应用后明确标注上方维度评分仍是改写前 | 浏览器实测：真实模型对 4 个锚点给出建议 → 全部应用 → 新文本入库、原文进快照 |

顺带修掉的两处（都在 B1 的必经之路上）：

- **`resume_version_of` 从时间戳改为 `parsed_json` 内容哈希**（`71125ff`）。原先用 `update_time.isoformat()`，而 MySQL 该列是 `DATETIME(0)`（已查 `information_schema` 确认）→ 同一秒内的两次写共享版本号，改完简历仍会读到旧分数、推荐缓存最长 24h 不刷新；反之无关列的写入会让全部缓存作废。
- **`/diagnose` 按 prompt 实际约定的形状读取模型输出**（`dfee148`）。此前 `dimensions.get("structure", 0)` 把整个 dict 当分数交给前端，五个维度条全部显示为 JSON 文本 + 0 宽进度条；`improvement_roadmap` 是三条 track 的 dict，被 `isinstance(list)` 判断丢弃，于是"改进路线图"永远显示"暂无"；模型放在 `keyword_density` 里的 `missing_keywords` 从未被读取——**缺 5 个关键词的简历被告知"关键词覆盖良好"**。三处均在浏览器中改前/改后各验证一次。

### B2 证据锚定的职业规划（1–1.5 周）

现状 `career_path_agent.py:47-84` 只看简历摘要，分数与薪资区间为编造；`CareerAgent` 硬依赖 Resume/Job/Match 三个 agent（`career_agent.py:22-25,28-32`），深度版只能在 SmartAnalysis 里跑到；RAG 退化时输出 `"暂无行业参考数据"`（`:44`）。

目标：把 **JD 库**与**薪资分位数**真正喂进推荐逻辑，产出**技能缺口图**作为共享产物。

- 缺口图成为单一权威产物，替掉 §3.5 的三套独立计算
- 同一份缺口图下游三用：推荐排序权重、面试练习重点、规划里程碑
- 无参考数据时必须**显式降级**（复用 A1 的 `source` 字段），不得静默编造

**验收**：规划给出的每个 `match_score` 与 `salary_range` 都能反查到支撑它的 JD 样本集合。

#### 已交付：B2.1–B2.4（提交 `d0cc34c`、`a7161de`、`eb539a6`、`a8e5e00`）

| # | 内容 | 证据 |
|---|---|---|
| B2.1 | `skill_gap.py` 成为"这个技能算不算已具备"的唯一口径：normalize + 保守 alias + 按角色读取字段 + `SkillGap` 带岗位 id 与原始拼写作证据。接手四处旧实现（引擎集合差、rubric 技能/项目/加分维、分析报告 missing_skills、面试题 required_skills）。评分语义变化 → `SCORE_METHOD` 升 v2 并收成一个常量 | `test_skill_gap_authority.py` 16 例（含 rubric 与缺口图同题一致） |
| B2.2 | `salary_evidence.py`：单一分位实现（最近秩，不插值出没人报过的薪数）、样本下限标注 `low_confidence`、每个数字带 `sample_jd_ids`。解析改严格配对（`12薪 15-25K` 原被读成 12–15K） | `test_salary_evidence.py` 26 例 |
| B2.3 | 方向由岗位库统计（按 role 归组、忽略职级）：覆盖率、缺口按"几条岗位必备"排序、该方向自身样本的薪资分位、每条带 jd_ids。模型只在给定方向里排序写理由；幻觉方向/重复/假 category 拒绝；非真实应答时理由回落规则句 | `test_career_evidence.py` 28 例 + 真实模型跑通（4 岗位→3 方向，coverage 0.5，P25/P50/P75=25/25/37.5，mysql 2 条必备） |
| B2.4 | 规划页：方向/薪资两卡从 `v-if="careerResult"` 里搬出（不需要跑完整规划）；学习资源不再按关键词硬编码书名 + `'#'` 假链接；投递策略去掉 65/25/10 无来源比例 | 浏览器实测：分析状态仍"待启动"时两卡正常渲染且数字可反查；债务棘轮把该文件字面量 29→27 收紧 |

顺带修掉：**薪资洞察页此前从未工作过**——它读的是接口从未返回的字段（`overview.p25`、`distribution[]`、`city_breakdown`），每张卡都显示 `--`，分布图还在对象上 `.map` 抛错。现按真实契约渲染，城市对比走 `/compare`，无数据时直说而不是显示 0。

口径记录：`/career-path` 用 `accessible_job_query`（本人 + 平台共享），与推荐一致；`/salary` 面向整库市场语料（`salary_evidence` 顶部写明是决策而非疏漏）。因此方向卡内的薪资（自身样本）与薪资页（全库）可能不同，两者各自标注样本数。

### B3 推荐召回升级（1 周，依赖 A4）

- 把 `multi_recall.py:315-417` 的 BM25+RRF+query-rewrite 从"只服务知识库"扩展到岗位召回
- 替掉全量 JD 载入内存算 cosine（`job_recommend_engine.py:221-248`）
- 技能相似度从 Jaccard 升级为 embedding 语义相似（`:320-360`）
- 持久化 embedding，去掉进程内 LRU-512 反复重嵌（`embedding_service.py:54-55`）
- 结果做多样性打散（当前纯按分数排序）
- embedding 故障时**报错或显式降级**，不再静默 `50.0`（`:313`）

#### 已交付：B3 持久向量 + 显式降级 + 多样性（提交 `5d7508a`）

| 项 | 结果 |
|---|---|
| 持久 embedding | 新表 `jd_embedding`（`jd_id, provider, model, text_hash, vector`，migration `0025`）。`vectors_for_jobs()` 只对缺失或文本变过的岗位重嵌；`raw_text` 优先、否则用结构化摘要，文本构造函数住在本模块，避免"存进去的指纹"和"查出来的文本"漂移 |
| 不再全库载内存重嵌 | `recommend()` 不再把全库送进 embedding。真库实测（72 条活跃岗位，provider=qwen）：首次同步嵌 72 条 = 3 个本地批 → 8 次 HTTP，9.0s；第二次 `reused=72, embedded=0`，0 次 provider 调用，0.06s。此前每一次未命中缓存的请求都要付这 8 次 |
| 静默 50.0 | `_vector_score` 缺失时返回 `None`，结果标 `retrieval_basis: "vector+rule" \| "rule_only"`，`vector_score` 为 null；Prometheus `recommend_vector_degraded_total{reason}`。按 A2 口径：这条降级**只对内可查**，候选人侧无提示 |
| 多样性 | `_spread_by_company(per_company=2)`：同一家公司在截断前最多占 2 个名额，溢出按分数留在尾部（不丢候选）。实测前 4 名来自 4 家不同公司 |
| 预热 | scheduler 每 30 分钟 `sync_active_job_embeddings`；批量导入后同步一次（失败不影响导入） |

**两处带理由的撤回**（原计划列了、本次不做）：

1. **`multi_recall` 的 BM25+RRF 不接岗位召回**。它整体是围着知识库写的：语料来自 `get_knowledge_collection()` 全量扫描、可见性走 `kb_document`、key 是 `chunk_id/doc_id`，接岗位等于再造一套语料与权限层。而本仓库岗位总量 72 条，`tb_jd` 上的 `title LIKE` + SQL 层 `notin_` 抑制 + 持久向量余弦已经覆盖召回；在加任何"召回不够"的证据之前，引入 BM25 只是多一层不可解释的融合。等岗位量级到几千再评估。
2. **技能相似度不做 embedding 化**。展示分必须由人解释得清（B2.1 刚把这件事定成唯一权威口径），把"K8s≈容器编排"塞进分数会让缺口结论变得无法追溯；而岗位与简历的**整段文本**已经走向量通道，语义近似在那一层被召回分吸收。做法上保持分离：可解释的规则决定展示分，模糊的语义只影响召回。

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

#### 已交付：C1 节点入口恢复为唯一路径（提交 `4e07e9a`）

真机口径：provider=qwen、`ORCHESTRATION_BACKEND=redis_queue`（独立 worker 进程消费），一次性验证账号 + 演示数据，验完删除。

| 项 | 结果 |
|---|---|
| 唯一节点入口 | `BaseAgent.execute() = run_node() + record_node_outcome()`。`run_node()` 只跑 `run_impl` + 重试 + 归集用量、**不写库**，所以分层并行策略能在工作线程里跑它、由主线程落库（session 不能跨线程复用）。三条策略不再各自 `agent.run_impl(context)` |
| 节点流水真的有行了 | 线性 task 90：1 条 `agent_run(task_id=90)` + 5 条 `agent_message`（4 completed + 1 failed）+ 4 条 `agent_result`。legacy `/multi-agent/auto` run 6：4 条消息**全部落在客户端轮询的那条 run 上**，终态 failed 且带真实 error_msg；该 task 只有 1 条 run（修复前是 2 条） |
| 并行层 | 同层 ResumeAgent(1293 tok) 与 JobAgent(887 tok) 并发执行，各自成行；步骤日志改为整层先落 `running`（过去在完成时才建，并行时只看得见先完成的那一条） |
| 用量归属 | `prompt_trace` 出现 `source='agent.IntentAgent' / 'agent.ResumeAgent' …`、`response_source='real'`、真实 total_tokens。此前编排路径所有 LLM 调用的 `task_id` 都是 NULL，无法反查到节点 |
| 任务中心 | `/api/agent/task/90` → `usage.tokens_used=1332`，来自 `AgentMessage` 列的汇总（新 join），不再是塞在 `output_data["_usage"]` 里的那份 JSON |

**四条被实测推翻的计划前提**

1. `execute()` 不只是"零调用"——它**一调用就 TypeError**：它给 `retry_call` 传 `on_retry`，而 `retry_call` 没有这个参数（只有那个同样零调用的 `with_retry` 装饰器有）。同一个重试循环写了两份，只有一份带这个参数，所以"死代码"其实一直没法被调用。现在 `retry_call` 是唯一实现（带 `on_retry`），`with_retry` 删除。
2. 计划写"`task_center_service.py:138` 成本恒为 0"，实际是**死 join**：它按 `AgentRun.user_request == f"task:{id}"` 关联，而全项目没有任何写入方产出这个字符串，`_usage_by_task` 恒命中 0 行；显示出来的成本一直来自步骤日志。改为 `agent_run.task_id` 真外键（migration `0026`）。
3. C6 说的"工具调用路径不计费"已在 A 阶段修好（`llm_service.py:1117` 有 `_record_usage`）。C6 剩下的只有 tracing / cache / fallback。
4. `langgraph_linear` / `langgraph_layered` 在测试里从未真正执行过节点（只被 `create()` 过一次）。现在 4 条编排路径都有断言。

**顺带修掉的（都在 C1 的影响面内）**

- `execute()` 原来只捕 `RuntimeError`：非 RuntimeError 会让消息行永久停在 `running`，并把裸异常抛穿编排层。现在任何异常都规整成 failed 节点。
- 重试不再丢成本：每次尝试花掉的 token 计入本节点（测试钉住"3 次尝试 = 45 token"）。
- `_usage` 不再被塞进 agent 结果体：它会随 `output_data` 进前端，还会进下游 prompt。
- `AgentStepLog.input_data` 原本写死 `{"resume_id": None, "jd_id": None}`，现在填真实 ids。
- **Redis 后端丢弃 runner**：`RedisQueueOrchestrationBackend.submit(payload, runner)` 只入队 payload，闭包过不了进程边界，所以 `start_legacy_layered_thread` 包在闭包里的 `run_id` 在真机上根本不生效——worker 会为同一任务另建一条 run，客户端轮询的那条永远 `running`、明细永远为空（现场就是这样复现的）。现在 `run_id` 进 `TaskPayload`，两种后端统一走 `_run_task_payload`。
- `scripts/run_orchestration_worker.py`：`--once` 是空开关（两个分支同一句），删掉；补上 `python -m scripts.run_orchestration_worker` 的启动方式（直接按路径跑会 `ModuleNotFoundError: app`）。
- `orchestration_runner` 里 2 处构造完即丢弃的 `TaskPayload(...)` 表达式。

**验收对照**（不含水分）

- "`/api/multi-agent` 返回真实消息序列" → ✅ 真机 run 6。
- "任务中心显示非零 token" → ✅ 1332 / 2787。"非零成本" → ❌ 本环境 `LLM_INPUT_COST_PER_1K_CENTS = LLM_OUTPUT_COST_PER_1K_CENTS = 0.0`，价格没配就算不出钱；算术由测试钉住（7 节点 × 0.07 = 0.49 分）。
- "`prompt_trace` 还原每个节点" → ✅ 部分：覆盖节点的**首个** LLM 调用（`chat_json` 取用一次即清空 trace 上下文）。多调用节点要等 C6 一起改。
- "两条编排路径结果一致" → ✅ 4 条路径断言同一份事实。

**阻塞项已解除：知识库向量库重建（2026-09-20）**

C1 记录里那条"嵌入式 Chroma 索引损坏"已经查明并修好，根因不是数据坏了，是**版本不匹配**：

- 仓库钉的是 `chromadb==0.5.0`，它读 `embeddings_queue.seq_id` 时期望 BLOB（`_decode_seq_id` 拿 `len()`）；而本机 `backend/chroma_db/chroma.sqlite3` 最后一次写入是 2026-07-18，那一版把 `seq_id` 建成了 `INTEGER PRIMARY KEY`——0.5.0 一打开就 `TypeError: object of type 'int' has no len()`。所以**任何**触碰 collection 的调用都炸，连 `count()` 都不行。
- 先在临时目录用同一版 0.5.0 建库→add→count→query 全通，确认"新库能用"，再动手。
- 库里 393 个切片全部是可再生的派生数据：28 篇文档的源文件 `os.path.exists` 全真，`kb_document` 才是真源。
- 做法是**改名而不是删除**：旧库移到仓库外 `D:\AI\llmXM\_chroma_store_written_by_newer_chroma_20260920\`，然后跑 `knowledge_service.rebuild_all(db)`（清空 collection → 逐篇重解析 → 重切片 → 重嵌）。
- 结果：28 篇全部 `ready`，新库 413 个切片，与 `SUM(kb_document.chunk_count)=413` **逐条相等**（旧的 393 里那 5 篇当时就是 failed）。普通候选人（非管理员、非文档属主）走 `build_rag_context` 拿到 902 字符的真实知识上下文，不再是空串。

**修好后第一次跑通的端到端编排**（linear，真机 qwen，task 93）：`completed`，7 个节点全部落库——

| 节点 | tokens | 耗时 | 说明 |
|---|---|---|---|
| IntentAgent | 607 | 1.4s | 真模型 |
| ResumeParseAgent | 0 | 1ms | 规则解析，不冒充 AI（A3 口径） |
| JDParseAgent | 0 | 0ms | 同上 |
| MatchAnalysisAgent | 729 | 2.1s | 工具调用路径 |
| ResumeOptimizeAgent | 1772 | 5.1s | C1 时它死在检索层，现在通了 |
| InterviewQuestionAgent | 2101 | 6.0s | 同上 |
| SummaryAgent | 3102 | 6.6s | — |

任务中心 `GET /api/agent/task/93` → `usage.tokens_used = 8311`（= 各节点之和，走 `agent_run.task_id` 新 join）。验证账号与它的全部行已删除，库回到 9 用户 / 20 简历 / 72 岗位。

**仍然遗留**：`cost_cents` 恒为 0，因为 `LLM_INPUT_COST_PER_1K_CENTS` / `LLM_OUTPUT_COST_PER_1K_CENTS` 在本环境是 0.0——要看到钱，得先把价格配置填上（这不是代码问题）。

#### 已交付：C4（保守版）删掉第三条流水线（提交 `5d404da`，净 −1417/+95 行）

计划原文是"6 个编排实现收敛到 2 个"。实测三条流水线都有活的后台入口，"收敛到 2"等于删掉两个页面的后端——所以按用户定的保守范围做：**只删 `step_by_step`**，`linear` 与 `layered` 各留 native + langgraph 两份实现（4 个），C1 刚拿到的多智能体消息序列不动。

| 删掉的东西 | 为什么它是重复而非能力 |
|---|---|
| `StepByStepStrategy` + `LangGraphStepByStepStrategy`（285 + 163 行） | 11 个 `step_*` 函数绕过 agent 类，把 linear 的 7 个节点重做一遍：解析、匹配、优化、面试题、汇总全部有两份实现，两份的重试/日志/意图裁剪各不相同 |
| `app/services/agent_steps.py`（532 行） | 只服务上面那条流水线。其中只有 `_build_resume_summary` / `_build_jd_summary` 被 IntentAgent 与 SummaryAgent 复用 → 移到 `app/services/analysis_summaries.py`，改名 `resume_digest` / `jd_digest`（跨模块引用私有名下划线函数本身就是味道） |
| `agents/interview_coach_agent.py`、`agents/summary_report_agent.py` | 全项目零 import，且各自定义的类名与 `interview_agent.py` / `summary_agent.py` 里的真实现**同名**（`InterviewAgent` / `SummaryAgent`），留着就是撞名风险 |
| `AgentContext.record_step_output` + `_STEP_RESULT_FIELD_MAP` + `retrieval_results` / `rag_confidence` / `self_checks` 三个字段 + `__getitem__`/`__setitem__` | 只有裸步骤读写它们；`strategies.MAX_RETRIES` 同理（重试已住进 `base_agent`） |
| `analysis_service` 里 `"step_by_step": "langgraph_step_by_step"` 别名 | 指向已删的类；配置里残留该值的部署现在会明确报"未知策略"，不静默换路 |

`/api/agent/start`（`run_workflow`）改为按 `ORCHESTRATION_STRATEGY` 启动，与 `run_smart_analysis` 同一条路——它的 deprecation 提示一直写着"请使用 run_smart_analysis"，现在才成立。

**两处随之暴露的空洞（诚实记录，C3 处理）**

1. `app/api/analysis.py:132` 从 `knowledge_retrieval` 步骤日志里读 `rag_confidence` 给"参考来源"面板——**默认策略 linear 从来不产生这个步骤**，所以该字段在主线任务上一直是 `{}`。删掉 step_by_step 后连唯一的（空）生产者也没了：C3 要把检索日志的写端放到真正发生检索的地方（工具层 / 节点结果），再把这个读端指过去。
2. `agent_task.plan` 自此**没有任何写入方**（原先只 `step_task_planning` 写）——这正好是 C2 的前提：plan 必须由 surviving 路径产出并真正驱动执行，而不是继续存一份没人读的 JSON。
3. `prompts/agent_planning.py`、`prompts/agent_self_check.py` 现在零引用：前者是 C2 的原料，后者等 C3 决定"自检"要不要活下来（原实现每目标一次 LLM 调用、`retry_needed` 算了但没人执行）。

#### 已交付：C3 检索取证回到节点路径（提交 `8c251d3`）

**先纠正计划里一条错前提**：C3 原话是 `RetrievalLog`/`SelfCheckLog` "**从未被插入**"。查 dev 库——`retrieval_log` 有 25 行、`self_check_log` 有 15 行，**全部产在 2026-06-06~06-07，之后一行没有**。也就是说写端不是"从来没写"，而是和 `agent_message` 一样，在同一次把智能体改成"策略直打 `run_impl`"的重构里被弄丢了（旧行里 `query_text` 形如 `type=resume_template query=…`，正是当年那套写法）。

| 项 | 结果 |
|---|---|
| 写端位置 | `app/services/retrieval_log.py`：contextvar 收集器，节点入口 `run_node` 每次尝试 `begin()`，`record_node_outcome` 统一落行。住在**真正发查询的** `rag_service.search_knowledge()` / `multi_recall()` 里，而不是 agent 里——agent 只拿到一段拼好的上下文，看不见自己查了几次 |
| 0 命中也留行 | 空集合、可见集为空、Chroma 抛异常三条返回路径都记一行 `result_count=0`。"查了 4 次次次空手而归"是结论，不是缺数据 |
| 不污染 | 收集器只在节点执行期间装载，知识库页自己的搜索、外部 API 的检索一行都不写 |
| 重试取证 | 三次尝试各查过的，三次都落行（测试钉住 `尝试 1/2/3` 三行且 `result_count=0`） |
| 上限 | 单节点 `MAX_TRACKED_PER_NODE=12` 行、命中正文只存 160 字符摘要——日志不变成语料库副本 |
| 读端 | `/api/agent/task/{id}/steps` 的 `retrievals` 从恒空变成真数组；分析详情/参考来源面板的 `rag_confidence` 不再读那条已删除的步骤日志，改为**用现有的唯一实现** `confidence_from_flat_results` 从取证行反推；一行都没有时返回 `{}`（"没查过"不等于"查了没信心"） |

真机验证（task 94，linear，provider=qwen）：4 行取证、9 次命中——`resume_template` 1、`skill_model` 3、`interview_q` 2、`skill_model` 3（两个节点各查一次同一类型，符合预期）；`GET /api/agent/task/94/steps` → `retrievals` 长度 4；参考来源面板 → 4 条来源 + `rag_confidence = {level: medium, score: 73, total_chunks: 9}`。

**`SelfCheckLog` 故意仍然没有写端**（测试把这条决定钉住）。唯一现成的"自检"是 `SummaryAgent` 报告里的 `quality_assurance.self_check_score`——那是模型给自己的输出打分：没有核验方，也没有通过线。把这种分数写进 `self_check_log.passed` 等于给意见盖上测量的章，跟 A3 刚清掉的六处同类是一回事。要做独立校验，得先定"谁验、验什么、过线是多少"，那是产品决策不是清理。

#### 已交付：C6 工具调用路径进入审计链（提交 `fdd9c4e`）

计划原话有两条已经不成立，实测后各归各位：

- "**线性策略最关键一步完全不计费**" → 用量在 A 阶段就修好了（`llm_service.py:1117` 有 `_record_usage`）。真正缺的是**取证与指标**：`chat_with_tools` 一行 `prompt_trace` 都不写，也没有 `record_llm_request/error/degraded`——所以 `MatchAnalysisAgent` 在审计里等于没发生过。
- "`:1084` 是一句被丢弃的表达式" → 那已经是修好的注释，不是待办。

做法：把 `chat_json` 里那个 60 行的 `persist_trace` 闭包提成 `LLMTraceScope`（begin / persist / record_metrics / record_failure），两条调用路径共用一份。这一步顺带消掉一个复发性结构问题——同一段落盘逻辑写两份，早晚会出现"只有一份带这个参数"（C1 的 `retry_call.on_retry` 就是这么坏掉的）。

工具路径现在每次调用留一行，带 `tool_rounds` / `tools_used` / `tools_offered` / `max_tool_rounds`；四种出口各有归属：模型作答=`real`、轮次耗尽兜底=**`tool_output` 且 degraded**（延续 A1 的口径：不冒充模型分析）、provider 报错=`failed`、空内容=`failed`。**缓存仍不加**：工具循环有状态，这是原设计注释里写明的取舍，不是遗漏。

真机对照（task 95，五个调模型的节点全部有取证行）：

```
agent.IntentAgent            real  tokens= 608
agent.MatchAnalysisAgent     real  tokens= 730   rounds=1 tools=[]   ← 以前完全没有这一行
agent.ResumeOptimizeAgent    real  tokens=1772
agent.InterviewQuestionAgent real  tokens=2097
agent.SummaryAgent           real  tokens=3215
```

同一任务的取证行：`resume_template` 1、`skill_model` 3、`interview_q` 2、`skill_model` 3——检索取证与节点账对得上。`ResumeParseAgent`/`JDParseAgent` 是 0 token 且**不该**有 trace 行：它们是规则解析，不挂 AI 名头（A3 口径）。

#### 已交付：C2（保守版）计划真的决定跑哪些节点（提交 `ac21af6`）

范围是和用户对齐后的"保守版"（原计划"按 depends_on 生成任务图"会改变每次请求实际跑哪些节点、跑几轮，属于更大的行为变更，未做）。

**实测到的三个事实，其中一个纠正了我自己上一轮的判断**

1. `required_steps` 一路写进 `agent_task.intent_detail`，但 `_should_execute()` 从不读它——它按一张硬编码"意图→agent"表裁剪。计划是个装饰品。
2. 意图提示词教的名单还留着 C4 删掉的 `task_planning` / `knowledge_retrieval` / `self_check`：**模型在按一份不存在的词汇表做计划**（2026-06 真实落库行里就是这个 10 项名单）。
3. 我上一轮说"置信度没被填出来"是**我查错了键**（用了 `intent_confidence`，真名是 `confidence`，值一直是 0.95）。真正的发现反而更值得记：它每个任务都恰好等于提示词里的示例值，所以是抄的，**不能参与决策**——`plan_from_intent()` 明确不读它，测试钉住"高置信与低置信给出同一份计划"。

**做法**：新增 `app/orchestration/plan.py`，把模型输出规约成可执行计划——别名归一（`matching_analysis`→`match_analysis`）、只保留真实存在的节点、**解析类前置节点模型没写也必须跑**、执行顺序按流水线而不是按模型给的顺序（乱序计划会让下游读不到上游结果）、无法识别的名字进 `dropped` 并 `logger.warning`（不静默丢弃）。`_should_execute()` 改为优先看 `context.plan`，没有计划时退回原硬编码表（等价旧行为）。`agent_task.plan` 恢复写入方。提示词名单换成现存 5 个可选节点并写明"解析与意图识别系统一定跑"。

**真机对照（task 96）**：模型返回的名单已经是新词汇 `['match_analysis','resume_optimization','interview_questions','summary_report']`（`dropped` 为空），`agent_task.plan` 有 7 个节点，**计划集合与实际执行集合完全相等**。

**这条要说白**：今天唯一的编排入口是"一键分析"，模型几乎必然返回 `full_analysis`，所以**裁剪这半段在真机上不会触发**——它的价值是把"计划"从装饰变成事实，未来加意图入口（只要优化/只要面试）时不必再改执行层。测试覆盖了触发路径（`optimize_only` 时计划里没有 Match/Interview，且 `task.plan` 与步骤日志逐一对齐）。

#### 已交付：C5（半件）分层图换成真扇出；checkpointer / interrupt 明确不做（提交 `7d4e981`）

**改之前的真相**：`_build_layered_graph` 给每层画一个节点，节点内部自己开 `ThreadPoolExecutor` —— 图是链、跑的是链，并行度全在 Python 里，LangGraph 只是把 for 循环换了个写法。计划里"`_wire_sequential_graph` 只画线性链"这句是对的，但根因不在连线，在于"并行被藏进节点体内"。

**先量后改（langgraph 1.2.10 实测）**

| 测的东西 | 结果 |
|---|---|
| 普通节点跑在哪个线程 | 与调用方**同一线程**（所以今天节点内直接写 `db` 是安全的） |
| `Send` 分支跑在哪个线程 | **别的工作线程**；4 个各睡 0.5s 的分支总墙钟 0.51s、4 个不同线程 id ⇒ 扇出是真并发 |
| 汇聚节点 | 回到调用方线程 |
| 状态里的 `AgentContext`（带 SQLAlchemy Session）能否被 checkpoint 序列化 | **不能**：`TypeError: Type is not msgpack serializable: AgentContext`；去掉 session 也只是走"unregistered type"的 msgpack 兜底，langgraph 自己警告"未来版本会直接拦掉" |

**做了什么**：每层变成 `route_i ──Send──▶ work_i ×N ──▶ join_i`。分工按线程归属来定——分支**只读**（自己开 session 跑 `run_node`，返回结果），所有落库集中在 `join_i`（调用方线程），这样 `record_node_outcome` / `_update_step_log` 永远只有一个线程在用同一个 Session。扇出通道用 `Annotated[list, operator.add]` + `Overwrite([])` 在每次汇聚后清空，否则上一级的结果会被下一级重复消费。linear **保持链状**：它本来就没有可并行的节点，不为了"看起来 agentic"加假分支。

**测试怎么证明不是自欺**：不拿墙钟当证据（CI 上一抖就假阳/假阴）。每个分支把 `started/ended/thread` 写进自己的结果，断言 ①同层两节点线程 id 不同、②**时间区间真的重叠**、③层间仍然有序（MatchAgent 必须晚于第一层全部结束）、④行数严格等于节点数（分支若偷写库就会出现重复行）、⑤与原生分层实现给出同一批节点。

**明确没做的两件（附证据，不是"忘了"）**

1. **checkpointer**：前提是状态可序列化，而我们的 state 里装着 `AgentContext`（含活动 Session）。要上就得把图状态改成纯数据（`resume_parsed`/`match_result`… 平铺进 TypedDict），约 500 行节点函数与两份策略都要重写；且 `langgraph-checkpoint-sqlite` 不在依赖里，只有 `InMemorySaver` 的话**跨进程重启仍然不能续跑**——那样"启用 checkpointer"就只是句空话。
2. **`interrupt` 人工介入**：依赖 checkpointer，被上一条卡住；而且我们的编排是**异步任务 + 前端轮询**，不是交互式会话，插进去等人点按钮需要一条"暂停-恢复"的产品路径（谁批、超时怎么办、恢复时 Session 怎么重建），这是产品设计不是清理。

**顺带**：`strategy._run_level()` 现在只服务原生分层实现，langgraph 侧不再需要它；`LayeredGraphState` 补了 `branch/log_ids/level` 三个字段，线程归属写进了模块 docstring，免得下次有人以为在节点里写库是安全的。








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
