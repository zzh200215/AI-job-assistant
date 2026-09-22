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
| **B3** | 推荐召回升级 —— **已交付主体**（持久向量 / 显式降级 / 多样性，`5d7508a`；可见性下推，`999f509`）。`multi_recall` 接岗位与 ANN 属带理由的延后 | 余 0 | 见 §5 B3 的状态复核 |
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

状态（2026-09-21 复核，别照这段字面理解成"都没做"——下面 4 条已交付，见 `5d7508a`）：

- ~~持久化 embedding，去掉进程内 LRU-512 反复重嵌~~ → 已交付（`jd_embedding` 表 + 文本指纹，migration `0025`）
- ~~结果做多样性打散（当前纯按分数排序）~~ → 已交付（`_spread_by_company(per_company=2)`）
- ~~embedding 故障时报错或显式降级，不再静默 `50.0`~~ → 已交付（`vector_score=None` + `retrieval_basis: rule_only` + Prometheus）
- ~~替掉全量 JD 载入内存算 cosine（`job_recommend_engine.py:221-248`）~~ → **没做，但证据不支持现在做**：真库活跃岗位 72 条 / 持久向量 77 条（qwen, 1024 维），全量扫一遍是微秒级；ANN 要到几千条才有意义，`5d7508a` 的撤回理由仍成立
- **`multi_recall` 接岗位召回** → 同上，已带理由撤回（知识库的语料/权限层与岗位不同构）
- **技能相似度 embedding 化** → 已带理由撤回（展示分必须可解释，见 B2.1）

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

> ~~若未来引入服务端向量库（Qdrant / pgvector），租户过滤应下推到检索层~~ → **2026-09-21 已修（E9，提交 `999f509`）**：可见集合现在下推进 Chroma 的 `where`。这条不是"等换库再说的性能项"，而是**当时就在丢结果的正确性缺陷**——`n_results` 是候选槽位数，先取后滤让看得到文档的用户拿到 0 条：16 篇 / 91 切片、只见 2 篇的用户 7 条查询里 3 条召回为 0，修复后 0/7 且每条都不少于下推能给出的数量。将来换服务端向量库时，这个 `where` 子句就是下推接口；`knowledge_where_filter()` 是唯一出口。

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

#### 已交付：C7 重复 agent 与 critical 标志（提交 `fd1272b`、`1d4e16a`）

**计划里的两条，实测一条是错的**

| 计划说法 | 实测 |
|---|---|
| 五对重复 agent 待清理 | **不是重复**。每对是两个不同实现的节点：`ResumeAgent` 问模型要诊断报告（真机 1293 tok），`ResumeParseAgent` 用规则解析文件（0 tok）——分层流水线用前者，线性用后者。第五对 `SummaryReportAgent` 已在 C4 删掉。真正的 bug 是 registry 用 alias 把两个名字缝合，`get("ResumeParseAgent")` 可能返回另一个 agent，于是 `agent_message` 里的执行者名字和步骤日志里请求的名字不一致。处理：删 alias、把分工写进 registry docstring（两个实现都保留）、未知名字抛带已知清单的 `KeyError` |
| `is_critical` 恒为 True 属无效标志 | 成立，但后果比"无效"重：`partial` 状态因此**永远不可达**。优化/面试节点挂掉会把已经做完的匹配分析一起判废（真机发生过一次）。把 `ResumeOptimizeAgent`/`InterviewQuestionAgent` 改成 `critical=False` 之后才发现更深一层：**这个标志只有两条线性路径在读**——原生分层是"任何一步失败就整单 failed"，分层 LangGraph 的汇聚节点也只看"有没有失败"，两者都不查 `is_critical`。所以 `1f3a953` 把四条路径统一成"非关键失败 → 继续跑、落 `partial`、结果照入库"，并把分层侧 `InterviewAgent` 也改为非关键；取消仍然停图（那时"停下"才是目的）。前端两张状态表补上 `partial` 标签 |

**顺带查出 A4 的漏网——这条才是 C7 真正的收获**

默认编排路径写进 `analysis_record.match_score` 的一直是**模型在 JSON 里自报的数**。A4 定了唯一权威，但只管住推荐页与解释页，落库这一路没接上。开发库只读实测（70 条带 resume+jd 双 id 的记录，配对全部仍可解析）：

| 实测 | 值 |
|---|---|
| 存储值 == 权威算法值 | **0 / 70** |
| 存储值 > 权威值 | 66（另 4 条存的是 0） |
| 虚高 | 平均 **+36.5** 分，最大 +69 |
| 权威值 < 40（弱匹配）却显示 ≥80 | 14 条 |
| 66 条里出现过的不同取值 | **只有 3 个：82（35 次）、85（31 次）、0（4 次）** |

最后一行是决定性的：候选人看到的"匹配分"与简历内容基本无关，它是模型的习惯输出。

现在 `_save_analysis_record` 按 `canonical_match_score` 重算后落库，并把 `score_method` / `cap_applied` / `skill_gap` 写进 `match_report`；模型自报数保留为 `model_reported_score`，作为对照证据而不是显示分。简历或 JD 已不可见时写 `score_unavailable_reason`、分数记 0，**不回退**成模型自报数。

**历史数据没有回算**：那 70 条旧记录仍是模型自报分。回算会改动候选人已经看过的历史分数，属于产品决策，没有擅自动手。

**验收**：backend 668 passed；`test_orchestration_plan.py` +2（critical 策略表；非关键失败 → `partial` 且 `AnalysisRecord.match_score` 等于权威分、后续节点仍跑完，两条线性路径都跑）；`test_langgraph_topology.py` +2（同一件事在 `layered` 与 `langgraph_layered` 上各自成立）；`test_match_score_single_source.py` +2（canonical 落库、不可见时标 unavailable）；frontend `vitest` 24 passed，`eslint` 对改动文件 0 error 0 warning。

**同时暴露的一条工程债（后来在 E2 清零）**：当时 `ruff check .` 有 **48 个错误 + 64 个文件待重排**（15 `I001` / 10 `F401` / 7 `UP038` / 5 `B904` / 5 `F841` / 4 `E402` / 1 `B009` / 1 `UP035`）。C7 当时只把动过的文件修到 clean，没有顺手全量重排（爆炸半径太大、会污染后续 diff）；这批基线后来由 `0496c54` + `bc882cd` 清完，细节见 §8 的 E2 记录。

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
| 1 | 共享层 `components/ui/`：`AppPanel`、`AppTag`（唯一状态色表）、`AppScoreBar`、`AppTable`+分页、空/错/骨架态；`utils/format/` 统一日期；`composables/useLatestCall`（竞态令牌。原计划的 `useAsync` 经实测撤销，见 D3） | 已收：**3 套互相矛盾的分数色板 → `utils/scoreTone.js`**（分数→显示共 17 处，见 D1 第一~二段）；**状态色表中真跨页矛盾的两处 → `utils/statusTone.js`**（17 份表里先收任务/面试两组，其余 51 条手写映射由棘轮 `statusTagEntries` 按数字盯着）；**日期格式化 18 份副本 → `utils/format/date.js` 的 7 个具名输出**（34 个调用点，见 D2）；**并发覆盖：95 个"await 后直接写 ref"里已给 8 个加载函数加令牌（5 个页面），其中 7 处有红→绿测试为证（见 D3、D7、D9、D10）**；**"失败被说成没有数据"：D4+D5 共 9 处接进 `components/ui/AppLoadError`，棘轮 `silentEmptyCatches` 11 → 3 盯着（见 D4、D5；**这一维有已知漏数**，见 D10 末段）**。未收：`AppPanel`/`AppTable`/骨架态这些需要逐路由 computed-style 复核的组件抽取（浏览器工具目前被策略拦），以及其余尚未逐个证明可否被并发触发的加载函数 |

| 2 | 按 feature 重组 `src/features/{resume,analysis,jobs,pipeline,interview,planning,eval,admin,legal}/`；先出纯 `git mv` + alias 的机械提交，再拆 5 个巨页 | `JobSearch.vue`(3344)、`SmartAnalysis.vue`(2914)、`CareerPlanning.vue`(2164)、`PipelineKanban.vue`(1661)、`InterviewRoom.vue`(1462)。抽一个 `JobCard` 同时让 4 个文件变短（`JobSearch.vue:276,391,476` + `JobRecommend.vue` 重复渲染同一卡片） |
| 3 | TypeScript（`allowJs` 渐进、新文件强制 `.ts`）+ `unplugin` 自动导入，删掉 `plugins/element.js` 的 111 行手写注册 | 视图数从 45 降至约 41（去 `OrganizationWorkspace`、`admin/{Tenants,Orders}`，`Subscription` 视付费决策） |

其他已知项：`localStorage` 9 个 key 分散在 64 个调用点，其中 `token`/`user` 在 `api/request.js:17` 与 `stores/auth.js:35` **两处读取**（双份真相源）；~~`recruit.lastResumeId`/`lastJDId`/`lastRecordId` 是跨页隐式握手，应改由 Pinia 承载~~ → 已收进 `utils/lastSelection` 并按登录用户分槽（E13，提交 `67688cd`；量的结果是**两套互不读取的键名**、25 处裸访问，详见 E13 那节），是否再升为 Pinia store 见 §10.9；`.vite-startup-error.log`、`dist/`、`backend/.coverage` 属被提交的构建产物。

---

## 8. 阶段 E｜工程债（1 周，穿插做）

**建议立刻顺手修的两项（一行级）：**

- ~~`GET /api/system/metrics` **无鉴权**（`api/system.py:510-513`，router 裸挂在 `:37`）→ 泄露内部模型名、队列深度、失败计数~~ → **已修（E1）**，见下方"已交付：E1"
- ~~`orchestration/registry.py:138-141` 用裸 `except Exception` 包裹 registry 构造，异常时静默重置为**空**registry~~ → 已在 C7a（`fd1272b`）修掉：构造失败现在 `logger.exception` 出真实 import error

#### 已交付：E1 指标端点收口 + 公开面变成一张有理由的清单

**先把"泄露"量成事实**：改动前用只读脚本遍历真实路由图，232 条已声明操作中 15 条不带任何凭据依赖，其中 `GET /api/system/metrics` 是**唯一一个没有理由公开**的——其余分别是登录/注册/找回（6）、探活（2）、登录页要用的静态字典与品牌（4）、SSO 入口与回调（2）、支付回调（1，签名在处理体内校验）。`/v1/external/*` 三条走 `X-API-Key`（`app/api/external/auth.py`），不是漏洞。

暴露面也不是理论问题：`frontend/nginx.conf:49-50` 把整段 `/api/` 反代给后端，而 `docker-compose.prod.yml` 只发布前端 80 端口——所以按仓库自带的生产编排，公网路径 `https://<site>/api/system/metrics` 可直接读到计数器。本机开发实例（127.0.0.1:8010，旧代码）匿名 `curl` 实测返回 200 + 计数器转储，里面连 `path="/api/auth/register"` 这样的调用路径与状态码都在。

**做法**：`require_metrics_reader` 依赖，两种凭据任一即可——① `METRICS_TOKEN` 静态 Bearer 令牌（`secrets.compare_digest` 比较，给采集端用，它没有会话可登）；② 管理员会话（复用 `_can_view_system_overview`）。令牌没配就只剩第 ②，端点**不会退回公开**。配套改了仓库内唯一的消费方：`monitoring/prometheus.yml` 加 `authorization.credentials: '${METRICS_TOKEN}'`，`docker-compose.prod.yml` 的 prometheus 服务加 `--config.expand-env=true` 并透传该变量（两个 YAML 都过 `yaml.safe_load` 校验）；`backend/.env.example`、`.env.production.example`、`docs/setup-and-security.md` 同步口径（示例文件里只放占位值）。

**公开面从"逐端点自觉"变成清单**：`tests/test_public_api_surface.py` 遍历真实路由图，把匿名可调集合与 `PUBLIC_OPERATIONS` 逐条比对——新加一条公开路由就失败，除非在清单里写出理由；同时有反向断言（清单里条目若已加凭据也要删掉），以及一条"遍历确实能看到 ≥200 条凭据依赖"的防空转断言。这条测试是 §8"缺少 router 级鉴权、保护是 opt-in"那一行针对读路径的最小构造保证，不是把 232 条都塞进 `dependencies=[...]` 的那件大事。

**验收**：backend 664 passed（新增 7：匿名 401、候选人会话 403、管理员 200、令牌 200、错令牌匿名仍 401，加清单三条）；`ruff check` + `ruff format --check` 对本次 3 个文件均 clean。

**真机验证（另起一台一次性实例，不动 8010）**：在 8011 上用改动后的代码起服务、`METRICS_TOKEN` 设成一次性值，同库同机、只差代码版本：

| 请求 | 8011（改后） | 8010（旧代码，对照） |
|---|---|---|
| 匿名 `GET /api/system/metrics` | **401** `{"code":-6,"message":"未提供认证 Token"}` | 200 + 计数器转储 |
| `Bearer wrong-token` | 401 | — |
| `Bearer ${METRICS_TOKEN}` | **200**，正文首行 `# HELP http_requests_total` | — |
| 匿名 `GET /api/system/health`（对照：探活必须仍然公开） | 200 | 200 |

验完 8011 已停（`netstat` 再查为 0 监听）。**随后按要求重启了 8010 那台开发实例**（先用 `Get-CimInstance` 核对命令行确为本项目 `uvicorn app.main:app --port 8010`，再按 PID 定点重启，新监听 PID 9228），在它上面复测同一组：匿名 metrics **401**、`Bearer nonsense` 401、`/health` 与 `/jobs/cities` 仍 200。因为 `backend/.env` 里没有 `METRICS_TOKEN`，这台跑的是"仅管理员会话"模式。

**~~CI 基线已经红了~~ → 已清零（E2，提交 `0496c54` + `bc882cd`）**：`.github/workflows/ci.yml:41,44` 声明每次 push 跑 `ruff check .` 与 `ruff format --check .`，接手时基线是 **48 个 lint 错误 + 64 个文件待重排**。现在两条都 clean（`All checks passed!` / `336 files already formatted`），backend 664 passed 在改动前后都成立。

不是 `--fix` 一键过的：35 个可自动修的里面，只有 28 个属于 ruff 认定的"安全修复"，其余按规则逐个处理——5 处 `B904` 补 `from exc`（400 响应不再吞掉真正的 ValueError）；6 处 `F841` 里 4 处那个**调用本身就是测试目的**（账单重跑幂等、租户/岗位 fixture 需要多一行对照数据），所以只删绑定、保留调用；`scripts/export_schema_baseline.py` 的两行 import 必须在 `sys.path` 插入之后，标 `noqa: E402` 而不是搬走。顺带在 `webhook_service` 里发现一处真 bug：私网 IP 的拒绝异常被同一个 `except ValueError: pass` 吞掉，绕到 DNS 分支才拦下（结论正确、报的却是另一句），已挪进 `else`。

这条 bug 之所以能活着，是因为**原有测试看不出走错了路**：`test_webhook_subscribe_rejects_private_url` 只断言 `"内网" in detail`，而"指向内网/保留地址"和"解析到内网地址"两条消息都含"内网"。补的两条测试把路堵死：把 `socket.getaddrinfo` 换成"一旦被调用就 fail"，于是私网字面量必须在字面量分支就被拒（`getaddrinfo` 调用次数为 0），同时公网字面量 `8.8.8.8` 仍然放行（不许过度拦截）。改动前后各跑一次同一探针：

| 同一输入 `http://169.254.169.254/latest/meta-data/` | `getaddrinfo` 是否被调用 | 结果 |
|---|---|---|
| 修复前（`git show 1742bd5:…webhook_service.py` 单独加载） | **被调用**（`['169.254.169.254']`） | 异常被自己的 except 吞掉，落到 DNS 分支 |
| 修复后 | **0 次** | `ValueError: url 指向内网/保留地址 169.254.169.254，禁止投递` |

**一处值得记住的连锁反应**：给 `app/models/__init__.py` 排 import 顺序，改变了模型注册顺序；SQLAlchemy 用注册顺序决定"彼此无依赖"的表在 DDL 里的先后；于是 `docs/schema-baseline.sql` 的 179 条语句换了顺序，被 `test_schema_baseline` 判成"schema 漂移"。修法是让 `render_ddl()` 像它已经对 `CREATE INDEX` 做的那样对 `CREATE TABLE` 排序（这份快照没有任何消费方按顺序执行），并用"排序前语句集合 == 排序后"证明**schema 一个字没变**，只有 17 行换了位置。

#### 已交付：E3 RAG 评估门第一次真的量了检索

**查出来的根因比"CI 红"更难看**：`scripts/eval_rag.py` 调的是 `multi_recall(query, top_k=k)`——**不带 db**。而 `multi_recall` 是 fail-closed 的（`app/services/multi_recall.py:460-468`：没有会话就没法做可见性过滤，直接 `return []`）。所以每一条 query 都拿到空结果，recall 恒为 0.0：不是库里没内容，也不是权限不对，是**这道门从来没调用过检索**。本机用真 provider + 今天重建的 413 切片库跑 50 条，也一样是 0.0。

**同时，报告把三种完全不同的事写成同一个数**：`except Exception → results=[]` 然后照旧计入平均。于是"数据库连不上""库是空的""检索到了但不相关"都长成 `recall@5 0.0`。

**改法**：
- 检索抛异常的 query **不进指标**，单独计数；报告新增 `retrieved / retrieval_errors / empty_results / error_samples(≤3，带 query 与异常类型)`。
- 一条都没测出来时指标是 `None`（没测出），不再是 `0.0`（测了，很差）；门槛检查遇到 `None` 明确说"无从比较"，不会因为跳过就变成通过。
- 新增 `--max-retrieval-errors`（默认 0）：只要有异常，先报这条，再谈阈值。
- 评估必须带会话与身份：默认取 `ADMIN_USERNAMES`，没有管理员就按 id 找一个"真的看得到知识文档"的用户，并把口径写进 `run_meta` 和摘要行——评估用的是谁的权限，不能是隐变量。库连不上时退出码 2 说清原因，不再交一份 0.0 的报告。

**第一次真数据**（本机真 provider，5 条样本）：口径 `testu(id=1) 可见 22 篇知识文档`，检索成功 5 条 / 异常 0 / 空结果 0，**recall@5 = 0.9，MRR 0.533，keyword hit 1.0**，退出码 0（门槛 0.5 第一次是真的在比大小）。`transition_guide` 这一类召回 0.0，样本太少先不下结论。全量 50 条大约要打 50 次 LLM + 140 次 embedding（按 5 条样本外推），我没有擅自跑。（**E6 补一刀**：同一份评估集上"随机抓 5 个切片"的 recall@5 就有 0.479，所以"门槛 0.5 真的在比大小"只对了一半——它在比，但赢不了抛硬币。）

**同样的形状还留在别处（随后在 E4 一起改了）**：`scripts/eval_agent.py:110-112` 出错时写 `predicted = 0`，会污染 MAE/Spearman 两道门，性质与这里一样。CI 侧的结构性问题也还在（**E6 已解决**）：`ci.yml` 没有 MySQL service、`backend/chroma_db` 里只跟踪了一个 `.gitkeep`，所以这道门在 CI 里当时会以"数据库不可用"退出码 2 失败——**明确地红，而不是假装测过**。

**测试**：`tests/test_eval_thresholds.py` +4（异常单独计数且指标为 None、空结果仍是可测的 0.0、一条炸一条中时只按测出的算、门槛先报异常再报未测出）；原有 hybrid-recall 测试改为断言 `db/user_id` 确实被透传。该文件 11 passed，全量 672 passed。

#### 已交付：E4 剩下那两条 CI 小事（提交 `bd0b986`、`889be6b`）

**前端 lint 的唯一那条 error**（`bd0b986`）：`vite.config.js` 读 `process.env.VITE_PROXY_TARGET`，而 flat config 的 `globals` 里从来没声明过 `process` → `no-undef` → `eslint .` exit 1，CI 的 "Lint frontend" 步骤一直红。改法是加一个只对 `vite.config.js` / `*.config.mjs` 生效的 config 块，**不给 `src/**`**——否则组件里谁都能顺手读 `process.env` 而没人拦。实测：`npx eslint .` 从 1 error 变成 **0 error**，`npm run lint` **exit 0**（两万六千条 warning 是本机 CRLF，CI 的 LF 检出不会有）。

**`eval_agent` 的空转门**（`889be6b`）：出错写 `predicted = 0`，于是"provider 超时/JSON 解析失败"被当成"模型给这段匹配打了 0 分"——MAE 凭空吃进 60–85 的误差、Spearman 多出一个假数据点、`hit_tol10` 把它记成 `under`。现在与 RAG 门同一套：异常单独计数并带样例、不进指标；`scored < 1` 时 `mae=None`、`scored < 2` 时 `spearman_rho=None`（顺带堵掉 `compute_spearman` 在 n<2 时返回 0.0 占位值这条暗路）；`--max-errors` 默认 0，先报异常再谈阈值。CLI 冒烟（mock provider，不花钱）：2 条全部打分成功，`mae 22.5 / ρ 0.5 / hit=1 over=1`——mock 对两条都吐 82，又一次印证"模型自报分与内容无关"。

**验证**：backend **675 passed**（+3：全异常时 scored=0 且指标 None、一条炸一条中时只按测出的算、门槛先报异常再报未测出）；`ruff check .` clean、`ruff format --check .` 336 files already formatted；`npm run lint` exit 0。**仍然没验的**：`npm run format:check` 在本机不可信（检出是 CRLF 而仓库对象是 LF），CI 上什么结果我不知道；`gh` 查远端运行记录被会话策略拦，见 [[local-dev-environment]] 的替代做法。

#### 已交付：E5 BM25 关键词索引跟着语料变（提交 `aa9d64b`）

**死在哪**：`_BM25Index` 是单例，`__init__` 里全量扫一遍 Chroma 建好就永久复用；`_dirty = True` 声明了却**没有任何一处读它或改它**（全仓 grep 只命中声明那一行），`knowledge_service` 的入库/删除/重建路径也没有一行碰过索引。所以进程启动之后入库的文档，关键词这一路**永远召不到**；反过来被删掉的切片还会继续被打分。向量那路是实时查 Chroma 的，所以症状只在"报错码、产品名、法规名"这类关键词本该赢的查询上。

**新旧对照（同一份假 collection，只换代码版本）**

| 语料 2 条 → 3 条之后，索引里的条数 | 改前 | 改后 |
|---|---|---|
| `_BM25Index.get().doc_ids` | 2 → **2**（死的） | 2 → **3**（跟着变） |
| 有没有 `invalidate_bm25_index()` 这个出口 | 无 | 有 |

**做法与两处刻意的取舍**
- `get()` 比较"建这份索引时的条数"与 `collection.count()`，不一致就**整份重建后换指针**（单次赋值，读侧不会看到半份索引）。代价是每次检索多一个 `count()`，本地 413 切片量级下是毫秒级；`_bm25_score` 每次 `multi_recall` 只调一次，不是每路调一次。
- **失败时保留旧索引，不清空**：`count()` 取不到（返回 -1）或重建过程抛异常（`build_failed`）时沿用上一份好索引。以前 `_build()` 的 `except` 会把 `doc_ids` 清成空表，等于"Chroma 抖一下 → 关键词召回静默变 0"，而 `_bm25_score` 外层还有一个吞异常的 `except`，根本看不见。
- 计数只看得见"条数变了"。**条数一样的改写**（重切片、整库重建）由 `reprocess_document` / `rebuild_all` 显式调 `invalidate_bm25_index()` 兜住——这个出口有真实调用方，不是又一个装饰性钩子。

**测试**：`tests/test_bm25_index_refresh.py` 4 条（新入库可召回、删除后不再计分、同计数改写必须靠 invalidate、计数异常不得清空好索引）。第一条在改前必红（上表的对照就是证据）。全量 **679 passed**，`ruff check .` 与 `ruff format --check .` 均 clean。

**没做真机端到端**：要现场证明"跑着的进程里入库即可召回"，得往共享开发库塞一篇真文档再删（上一轮删除数据被安全策略拦过），收益不超过上面的单元级对照，所以没做。另外 8010 上那个实例是 E4 之前起的，**不含本次改动**。

**其余：**

| 项 | 证据 |
|---|---|
| 事件循环被阻塞 I/O 占用 | 195 个 `async def` 端点全部使用同步 `SessionLocal`；`chat_json` 用阻塞 `requests.post`（`llm_service.py:701`）直调于 `interview_rest.py:452` 与健康探针 `system.py:140`；`knowledge_service.save_and_process` 把 parse→chunk→embed→Chroma add 全串在请求里（`api/knowledge.py`）；`resume_export_service.py:321` 同步跑 WeasyPrint；`job_spider.py:72`、`webhook_service.py:155` 用 `time.sleep` |
| WebSocket 鉴权与内存无界 | `interview_ws.py:39-43` 绕过 FastAPI 依赖手工校验 query token；`:23-34` 的进程级 `_engine_pool` 无上限，且无跨副本亲和 |
| schema 有第四条路径 | Alembic（22 个 revision）+ `Base.metadata.create_all`（`main.py:61`）+ `core/schema_bootstrap.py`（453 行 / 13 个手写 MySQL DDL，`AUTO_CREATE_TABLES` 默认 True）+ 散落的 `add_columns.py`/`reset_kb.py`。已存在重复：`ensure_agent_message_usage_columns`(`:23-41`) vs `20260624_0003`；`ensure_user_role_column`(`:9-20`) vs `20260801_0017`。DDL 是 MySQL 方言而测试引擎是 SQLite |
| 连接池未配置 | `core/database.py:9-20` 未设 `pool_size`/`max_overflow`，默认 5+10 的 queuepool 面对线程池密集应用 |
| 测试覆盖真实路径为零 | `pytest.ini` 的 `--cov-fail-under=0`；`conftest.py` 强制 `LLM_PROVIDER=mock`/`EMBEDDING_PROVIDER=mock` + 内存 SQLite → 真实 HTTP 路径、工具循环、rerank 模型、Chroma server 行为**从未被执行**。62 文件 / 429 测试函数广度不错，但 `backend/.coverage`(122KB) 被提交进了工作树 |
| 队列无 ack/retry/DLQ | 默认 `ThreadPoolExecutor(max_workers=4)`（`orchestration_backend.py:76-79`）；Redis 队列存在（`:93-141`）。~~但 `mark_stale_running_tasks_failed` 启动时把 30 分钟以上任务一律置失败，多副本重启会误杀正常长任务~~ → 已改为按"最后一次进度写入"判静默（E12，提交 `3ecbb96`）。~~`run_strategy_async` 构造两个 `TaskPayload` 后丢弃~~ → **这条已不成立**：`orchestration_runner` 里两处 `TaskPayload(...)`（`:156`、`:204`）都紧跟 `return _get_backend().submit(payload, _run_task_payload)`，没有构造后丢弃的路径。**仍在的是**：任务入队后没有任何 lease/心跳字段，所以"排在长 backlog 里没开工"与"执行进程已经死了"在数据上仍然无法区分——这正是 E12 只把误杀范围缩到"完全静默"而没有消灭它的那一半 |
| ~~限流粒度~~ → 有身份的请求已按用户计额度（E14，提交 `63537ab`） | 原来的事实：只有 `api/auth.py` 的 5 个匿名端点自带限流，其余 **228/233 条操作只受 `RATE_LIMIT_GENERAL`（100/分钟）按 IP 管** → 一个 NAT 出口下所有人共用一份额度。**仍在的两半**：① 昂贵端点（深度分析/多智能体）没有自己的额度，一个用户照样能一分钟发 100 次真金白银的 LLM 调用；② 登录流量的每 IP 总闸随 E14 消失了，要补就是 `application_limits` 按地址再挂一层。两个数都要人定，见 §10.10 |
| ~~RAG 索引陈旧~~ → 失效链路已修（E5，提交 `aa9d64b`） | `multi_recall.py` 的 BM25 是手写内存索引，`_dirty` 标志**从未被读** → 进程启动后入库的文档在关键词这一路永远召不到；现在由"条数自愈 + 同计数改写显式 invalidate"接管。**仍然在的是性能那半句**：`score()` 为 O(terms×docs) 纯 Python 遍历，语料再大一个量级就要换实现 |
| Rerank 生产用启发式 | `rerank_service.py:125-159` 可选本地 cross-encoder，否则 jieba 词重叠 + 硬编码 0.5/0.3/0.2 权重；`RERANKER_MODEL_PATH` 默认未设 |
| 死代码 → ~~`api/tracking.py` 定义了 router 但**从未被 include**~~ 已挂载并修好整条链（E10，提交 `cb5a72b`）；**但 `track()` 调用方为 0，"要不要真埋点"回到 §10.8** | 仍在的是另一半：`agents/agent_orchestrator.py`、`services/smart_orchestrator.py`、`services/agent_workflow.py` 是 `DeprecationWarning` 垫片层，靠 import 维持存活 |
| ~~缺少 router 级鉴权~~ → 22 段纯会话前缀已改为 include 级守护（E11，提交 `21778e2`） | 原判断成立的方式：31 个 router / 218 端点无一处用 `dependencies=[...]`，鉴权靠每端点自己写。**已变**：123 条操作所在前缀"新端点默认 401"；**仍在**：混着公开端点的 8 段（110 条，含 `/jobs`、`/auth`、`/system`）仍是逐端点声明，公开面由 `PUBLIC_OPERATIONS` 清单钉住——要把它们也变成构造保证需先做端点级拆分，见 E11 末段 |
| 三个 router 共享 `/jobs` 前缀 | `api/router.py:54-56`；当前不冲突仅因 `job_recommend.py:1448` 的 `/{jd_id:int}` 是单段 |

#### 已交付：E6 CI 的 RAG 门第一次有自己的语料可查（提交 `221b191`）

**红在哪**：E3 把口径修对之后，这道门在 CI 里以"无法确定评估身份/数据库不可用"退出码 2 失败——没有 MySQL service，`backend/chroma_db` 干净检出是空的。明确地红，但依然什么都没测。这次按"备一份固定小语料"落地。

**语料从哪来**：仓库本来就带着种子文档（`docs/knowledge-seeds/`，8 个 doc_type、**16 篇** md——之前记的"28 篇"不对，根目录那篇 README 不在 `SEED_MAPPINGS` 里）。新脚本 `backend/scripts/seed_rag_corpus.py` 走**真入库链路**（落盘→解析→切片→embedding→写 Chroma→建 `knowledge_document` 行），复用 `import_knowledge.py` 的同一套 helper，把它们装进一次性 SQLite + 临时 Chroma（`CHROMA_DIR` 成为可覆盖设置，默认仍是 `backend/chroma_db`）。实测 **16 篇 → 91 切片，seed 3.2s、gate 4.0s，零外部服务**。它默认**拒绝写非 SQLite 的 `DATABASE_URL`**（要 `--force`），否则手滑一次就把种子文档和一个机器人用户灌进共享开发库，而且没有清理入口。评估用户是 candidate 而不是管理员：可见性裁剪那一步要真的被执行。

**门槛改成什么样**（重点是别把"能跑"变成"跑过一个假数"）

| 断言 | 门 | 实测 / 同语料随机基线 |
|---|---|---|
| 词法召回还能找对文档类型 | `--min-lexical-recall 0.7` | 0.813 / 0.479 |
| 词法召回的正文里真有关键词 | `--min-lexical-keyword-hit 0.7` | 0.88 / 0.411 |
| 融合链路（可见性、补水、RRF、rerank）通 | `--max-empty-results 0` + 默认 `--max-retrieval-errors 0` | 50/50 有结果，异常 0 |
| 语义向量质量 | **不门**，只报数 | mock 向量按文本 hash，无语义 |

随机基线是脚本每次自己算的（同语料随机抓 5 个切片，200 次），并且**门槛 ≤ 对应基线就直接判失败**。两条纪律由此变成机器强制：旧 CI 那行 `--min-recall 0.5` 属于"门槛比随机还低"；`EMBEDDING_PROVIDER=mock` 下给融合路设语义门槛现在直接 exit 3，而不是报一个看起来像质量分的数。

**顺手抓到的第二个 bug**：写 `_lexical_hits` 时才发现 `collection.get(ids=...)` **不保证按请求顺序返回**。按返回顺序截 top-5，量的就不是 BM25 排名而是 Chroma 的存储顺序。改成按 id 回查、保持 BM25 顺序后，词法 recall@5 从 0.703 → **0.813**、mrr 0.475 → **0.781**。（第一版报告里我给的"词法 0.903"是另一个错：按去重后的 doc_type 数 top-5，把指标放松了，作废。）

**验证**：临时目录里照抄 job env 跑 CI 那两步（无 `.env`、无 MySQL、空 Chroma）→ seed exit 0、gate exit 0；把 `CHROMA_DIR` 指到空目录（模拟语料没了）三条门一起红、exit 3，失败信息带"BM25 覆盖 0 切片"。测试 +11（`tests/test_eval_thresholds.py`）：词法路只量 BM25 且排名用 BM25 顺序、不可见文档连 doc_type 都不外泄、索引没建起来时失败信息指到"索引"、mock 下融合语义门槛被拒、空结果按"链路断"报、门槛 ≤ 随机基线不成门、单类型语料基线就是 1.0、seeder 拒写 MySQL。backend **690 passed**，`ruff check .` clean，`ruff format --check .` 338 files formatted，`ci.yml` 过 `yaml.safe_load`。**仍然没验的**：远端 CI 实跑结果（`gh` 被会话策略拦，见 [[local-dev-environment]]）；真 provider + 真语料上的融合门槛（要花钱，仍旧没跑）。

---

#### 已交付：E7 量了 agent / recommend 两道门的基线，并修掉两个把"没测"读成"成功"的 bug（提交 `fb2c8a2`）

**为什么先量**：E6 的判据是"门槛赢不过同语料的随机基线就不算门"。RAG 门照这条修完了，另外两道门从没量过。零 API 花费（纯算术 + mock + 只读 SQL）。

**agent 门**（`eval_agent`，n=10；**CI 根本不跑它**，门槛只活在 `scripts/eval-quality.ps1`：MAE ≤ 12、ρ ≥ 0.80、hit_tol10 ≥ 7）

| 空模型 | MAE | hit±10 | ρ |
|---|---|---|---|
| 任意常数（均值 66 / 中位 70 / 最优 65） | 18.0 | 2–3/10 | 未定义¹ |
| 常数 82 + 确定性封顶规则 | **9.70** | **8/10** | 0.721 |
| 今天 mock provider 实测 | **9.70** | **8/10** | 0.721 |
| 0–100 均匀随机（2000 次） | 中位 31.2（最好 5% 才 20.5） | 中位 2/10 | 95 分位 0.564；P(ρ≥0.8)=0.004 |

¹ 脚本自带的 `compute_spearman` 用 `1-6Σd²/n(n²-1)`，对**并列没有定义**却返回 **0.5** —— 什么都不判断也能白拿一半秩分。现在零方差返回 `null` + `spearman_reason`，门那边报"未测出"。新旧对照（同一组输入）：常数 0.5 → **None**；有方差 1.0 → 1.0（没碰坏能用的那半）；单条 0.0 → **None**。

**结论**：`MAE ≤ 12` 和 `hit_tol10 ≥ 7` 这两条**现在不需要语言模型就能过**（mock  literal 就是 9.70 / 8）。有区分度的只有 ρ ≥ 0.80。n=10 的分辨率：重标一条，MAE 动 1–4 分、ρ 动 ~0.1。

**recommend 门**（`eval_recommend`，n=**2**；CI 只门 `skill_match_accuracy ≥ 0.4`）——五项指标没有一项分得出好坏：

- `skill_match_accuracy` 的标签把 `expected_skill_overlap` 定义成"简历上的全部技能"（pair_1 连 JD 没要求的 `docker` 都算 matched）→ **原样抄简历技能列表得 1.000**，预测空集 0.0。0.4 看不见这个差别。
- `jd_explanation_consistency` 有读数 bug：`round(_mean(parts) or 1.0, 3)` 把"两臂全错(0.0)"读成"完全一致(1.0)"。同一份 case 新旧对照：**1.0 → 0.0**。没有可比项的案件现在如实 `null`，并新增 `measured_cases` 说清"几条真有可比数据"（今天那条 1.0 其实只有 1/2 条可比）。聚合项同样去掉 `or 0.0` 的反向伪装。
- `interview_score_stability`（0.938）算的是**评估集自带样本的离散度**，系统输出不参与；单样本案件恒 1.0。
- `recommendation_explainability`（0.875）= (关键词命中 + 模板结构)/2，而关键词是拿去匹配 explainer **自己的兜底模板**（脚本硬把 `_llm_explain` 接成 `_fallback_explain`）。
- `feedback_agreement_rate` 结构性不存在：dev 库 `job_recommend_feedback` **0 行**，且 eval case 没有 `resume_id`/`jd_id` → 配对集合永远空 → `null`。
- CI 条件下（连不上 MySQL）脚本**未捕获 `OperationalError` 直接崩**，exit 1。**这个崩故意留着**：按"优雅降级"改掉，等于把一道已被证明饱和的门从"红"改成"假绿"；要和标签一起修。

**落地（他点的 1+2）**：两个读数 bug 修掉；带来源的指标（stability / explainability / skill_match / feedback）把说明写进控制台输出、报告 `run_meta.metric_notes`、`/api/eval-reports` 透传，以及**每一条红字**里。门槛数字本身没动（那是 3/4）。测试 +4：常数预测 ρ 未测出、有方差的 ρ 照常、两臂全错读 0.0、门槛设在未测出的指标上必须失败并带来源。全量 **694 passed**，`ruff check .` clean、`ruff format --check .` 338 files。

**当时没动的三件，随后在同一天做完（提交 `fdf42a3`）**：

- **(3) recommend 评估集重做**：2 → **16 个 case**，标签改成 `skill_gap` 权威定义下的集合运算（`canonical(简历) ∩ (canonical(要求) ∪ canonical(加分))` 与 `canonical(要求) − canonical(简历)`），不再等于"简历上的全部技能"。空模型立刻掉下去：**抄简历列表 1.000 → 0.676**，"永远说没有缺失" 的缺失一致性 0.188、"说全缺" 0.38。谁想把标签改成"用被测代码回生成"，`test_fixture_labels_are_the_documented_set_rule` 会红（它同时要求 ≥10 条有期望缺失、≥12 条简历带 JD 没要求的技能，即两个臂都得有分辨率）。
- **(4) agent 门槛**：`trivial_baselines` 每次自己算"不用模型能刷到几分"（最优常数 + 确定性封顶：**MAE 9.5 / hit 8 / ρ 0.721**，随机秩 95 分位 0.576，封顶规则命中 3/10），并**拒绝赢不了基线的门槛**。`eval-quality.ps1` 默认从 12 / 7 / 0.80 抬到 **8 / 9 / 0.85**；跑真模型若红，那是信息不是门坏了。
- **(5) recommend 在 CI 的崩溃**：线上反馈那一臂现在读不到就写 `linkage_status: db unavailable: …` 继续跑。**顺序是有意的**——先把门做成有区分度的（标签 + 1.0 精确一致），再谈降级；反过来就是把一道饱和的门从红改成假绿。

**CI 现在跑三道评估门**（全部零外部服务、零 API 花费）：seed 一次性语料 → RAG 门窗法路与链路 → Recommend 门"解释层 == skill_gap 权威"（1.0）→ Agent 只门管道（`--max-errors 0`，mock 的分数不设质量门槛）。本地把 12 步 backend job 全跑过：`ruff check` clean、`ruff format --check` 338 files、**698 passed**、alembic upgrade+check、schema-baseline --check、seed / rag / recommend / agent 四步 exit 0；把两条标签改错 → recommend 0.969 / 0.962、exit 3；把门槛调回 `--min-skill-match-accuracy 0.4` → exit 3 报"门槛 0.4 ≤ 空模型基线 0.676"。

**仍然没验/没做**：远端 CI 实跑（`gh` 被策略拦）；真 provider 下 agent 门的新门槛能不能过（要花钱，没跑）；`interview_score_stability` / `recommendation_explainability` / `feedback_agreement_rate` 三项**照旧不量系统**，只是现在每处都带着来源说明（前者是评估集样本离散度、中者拿去匹配 explainer 自己的兜底模板、后者需要 0 行的线上反馈表 + case 里的 `resume_id/jd_id`）；agent 标注仍只有 10 条，重标一条就能把 MAE 动 1–4 分，加样本是唯一解，而那要人来标。

---

#### 已交付：E8 agent 标注从 10 条扩到 25 条，门槛按新基线重标（提交 `6e95a26`）

**为什么要扩**：E7 量出来 n=10 的基线是"常数 + 确定性封顶"就能拿 **MAE 9.5 / hit 8 / ρ 0.721**，而门槛是 12 / 7 / 0.80 —— 两条门模型无关地过了。抬门槛只是把线画高，**真正修分辨率的是加标注**。

**做法**：保留他原有 10 条分数不动，追加 15 对（嵌入式、UI/UX、CV 应届错配、内容运营、银行风控转算法、测开、售前架构、前端强匹配、全栈真匹配、技术转产品、应届无实习、医疗数据、IC 验证、行政转总助、跨境运营）。分数区间从 [35,92] 变成 **[12,96]**，四个分段（<40 / 40-59 / 60-79 / ≥80）分别是 4/7/6/8 条。**新加的 15 个分数是我起草的，等他改。**

**基线随之变差（正是目的）**：模型无关最优 MAE 9.5 → **16.44**，hit 8/10 → **11/25（44%）**，封顶规则 ρ 0.721 → **0.554**，随机秩 95 分位 0.576 → **0.349**。mock provider 在新门槛下三条全红（MAE 19.24 > 8、hit 11 < 17、ρ 0.543 < 0.85）——这一次它确实没信号。

**门槛与护栏**：`eval-quality.ps1` 的 `hit_tol10` 从 9 抬到 **17**（它是**条数**，评估集一变就得重算，这点写进注释）；MAE 8 / ρ 0.85 不动，仍在新基线之上。`test_agent_floors_must_beat_the_model_free_baseline` 改成按**比率**断言（基线 MAE ≥ 14、命中率 ≤ 0.5、ρ ≤ 0.7），不再钉死具体数字，这样他改分数或再加 pair 都不会把测试弄坏；新增 `test_agent_fixture_keeps_enough_score_resolution` 守分布（≥25 条、≥20 个不同分值、跨度 ≤20/≥90、四个分段各 ≥3 条）。

**验证**：backend **699 passed**（+1 条分布测试 + 改写的基线测试），`ruff check .` clean，`ruff format --check .` 338 files；25 条 mock 跑通（零花费），基线打印与新门槛行为都实跑验过。**没做**：远端 CI、真 provider 下新门槛是否过得了（花钱）、以及 15 条新标注的人工复核。

---

#### 已交付：E9 可见性下推进向量检索（提交 `999f509`）——顺带纠正一条我报错的账

**先纠错**：我上一轮把 B3 报成"唯一整块功能缺口"，这是错的。B3 的主体在 `5d7508a` 已交付（持久向量、显式降级、多样性打散、粗排后再跑 canonical rubric），另有两条**带理由的撤回**（`multi_recall` 不接岗位召回、技能相似度不做 embedding 化）。错因：我只读了 §5 的 bullet 清单，没往下看它自己的"已交付"小节。账目已按现状改写（§1 优先级表 B3 行、§5 B3 状态、M5 里程碑）。

**B3 名下真正还能动的**，就是计划自己在 §5 末尾记着的那条正确性缺陷：**可见性在向量检索之后才过滤**。`n_results` 是候选槽位数不是"可见集合里取 N 条"，所以一个明明看得到文档的用户可以被截成 0 条。

**复现（E6 那份真实 collection，91 切片 / 16 篇，mock 向量——缺陷只关乎槽位分配，与向量有没有语义无关）**：

| 可见范围 | 修复前 | 修复后 |
|---|---|---|
| 2 篇（11 个切片可查） | 7 条查询里 **3 条召回为 0**，7/7 少于下推能给出的数量 | **0/7 为空**，每条都拿满候选窗口 |
| 4 篇（29 个切片可查） | 1 条为 0，7/7 少于下推 | 0/7 为空 |

**两个只有真库能发现的形状约束**（我的第一版都踩了，mock 出来的 collection 什么都答应）：Chroma 0.5.0 的 `where` **只接受恰好一个操作符**，`{"doc_type":…, "doc_id":…}` 直接抛 `Expected where to have exactly one operator` —— 而 `_vector_recall` 外层有个吞异常的 `except`，结果**按 doc_type 检索从"少给"变成"0 条"，比原缺陷更糟**；正确形状是 `{"$and": […]}`。第二条：**空 `$in: []` 是抛错，不是匹配空集**，所以空可见集合不下推，交给调用方的提前返回 + post-filter。

**做法与边界**：`knowledge_where_filter()`（在 `app/utils/knowledge_access.py`，可见性的家）成为唯一出口，两个站点都改：`rag_service.search_knowledge`（RAG 上下文与引用）与 `multi_recall._vector_recall`（知识库多路召回）。post-filter 保留作第二层；可见集合超过 2048 时不下推（不把几万 id 展开成 SQL 参数），退回原行为，方向上不会更差。将来换服务端向量库，这个子句就是下推接口。

**验证**：新增 `tests/test_vector_visibility_pushdown.py` 7 条（含一条**非空洞性**证明：让假 collection 故意不执行 `where`，同样的查询就得 0 条，正是修复前的世界）；backend **706 passed**；`ruff check .` clean、`ruff format --check .` 339 files；E6 那道门复跑 exit 0 且数字未变（评估用户全量可见 → 下推是 no-op：词法 recall@5 仍 **0.813**、keyword 0.88），说明没有把已有行为带偏。**没验**：远端 CI；候选人推荐列表本身不受影响（这条改的是知识库检索，不是岗位召回）。

---

#### 已交付：D1（第一段）分数色板收成一个口径（提交 `fd77d2a`）

**为什么先做这个**：D 阶段 1 列了一堆（共享层、feature 重组、TS），但其中只有一条是**候选人能直接看到的自相矛盾**：分数→颜色有 **6 处实现、3 套阈值（85/70/55、80/60/40、80/60）、4 套色族**，而且**没有一套和后端推荐标签的档位一致**（`match_explainer_service.py:529-537` 是 85/70/50）。于是一张卡片可以左边写"可以投递"、右边把 72 分涂成警告橙。

**做法**：`src/utils/scoreTone.js` 只出 tone（`high|good|warn|risk|unknown`，档位与标签对齐为 **85/70/50**；面试分另用 85/70/55 但同样从这里出）；`main.css` 的 `--app-score-*` 是唯一色源（复用既有 `--app-primary/success/warning/danger`，渐变用 `color-mix` 派生，不再新增 hex）；视图只挂 `.score-tone--*` / `.score-fill--*`，`el-progress :color` 那种必须传值的场景传 `var(--app-score-*)`。已迁的匹配分页面：ExplainMatch、SmartAnalysis（3 个函数 + `.sc-*` 规则）、OfferCompare、JobRecommend，另删掉 `.badge-high/medium/low` 三条**没有任何调用点**的死规则（同一文件里的第三套孤儿色板）。

**看得见的变化**（都发生在"让颜色和标签对上"的方向）：80-84 从绿改判蓝（标签是"可以投递"，不是"强烈推荐"）；50-69 统一为警告橙；<50 才是红。ExplainMatch 的 40-49 由橙转红、SmartAnalysis/OfferCompare 的 50-59 由红转橙。`null/''` 不再是红色 0 分，而是灰的 `unknown`（OfferCompare 以前给 `''`，等于没色）。

**棘轮补了一个盲区**：分数挑选此前藏在 `<script>` 的字符串里，`hardcodedColorLiterals` 只数 `<style>`，所以六套色板一起活着没人管。新增 `scriptColorLiterals` 维度（增长即红、还债必须调小），当前预算 `InterviewReport: 4`、`ResumeUpload: 3`。**同时给 CI 接上 `npm run test:unit`**：Vitest 那套（棘轮、路由守卫、新 scoreTone）此前没有任何一步执行——门写了却没接电。数字变化：SmartAnalysis `<style>` hex 27 → **15**、JobRecommend 26 → **20**、匹配分页面上 JS 侧分数 hex **10 → 0**。

**验证**：`npm run test:unit` **30 passed**（新增 4 条 scoreTone 断言，含"这个模块不许产出 hex"）；`npm test` 11 passed；`npm run lint` **0 error**（两万六千条 warning 全是本机 CRLF，CI 的 LF 检出不出现）；`npm run build` 通过；`ci.yml` 过 `yaml.safe_load`，前端步骤现为 install → test → test:unit → lint → format:check → build → audit。**没验的**：真浏览器里的 computed-style（browser 工具被会话策略拦），所以"var() 在 el-progress/SVG stroke 上解析"是依据标准行为 + 构建产物里规则确实存在（`.score-tone--good{color:var(--app-score-good)}`）推定的，下一步该由看到页面的人复核一眼。

**下一段**：面试分两页——InterviewReport（JS 里 4 个 hex）与 InterviewRoom（`.score-strong/good/warn/risk` 是**浅底 + 描边的胶囊**，不是实心渐变，需要 `--app-score-*-soft` 一组变体才能收）；再加 ResumeUpload 的简历完整度分（JS 3 个 hex，CSS 侧已经用 token）。这三处迁完就能把 `scriptColorLiterals` 预算清零。

#### 已交付：D1（第二段）分数→显示的第 2～17 处收进同一口径（提交 `ff304b6`、`f7dcea2`）

**这一段实际不止预告的三处**。按计划先收面试报告/房间/简历上传，量到一半发现同一族问题还有别的形状：除 hex 之外，页面还用**`el-tag` 的 type** 和**本地 class**表达分数（80/60 一组、70 一组、50 一组），而 hex 棘轮对这两族完全无感。按"输出的是色值 / 标签型 / class 名"重新盘一遍，本段共迁 **17 处**：报告 3（hex + 结论 + 维度点评）、房间 3（胶囊 class + 答题小结 + 最近信号）、ResumeUpload 3（`dimColor` hex + 完整度 class + 诊断标签 70）、History / ResumeCompare / PipelineKanban / OfferCompare 各 1、AgentAnalysis 2、MultiAgentAnalysis 1、Interview 1。**其中两处是第二轮才补上的**：第一次清点按"标识符里含 score"来 grep，于是 `const scoreTag = (s) => …`（MultiAgentAnalysis 的匹配分，80/60）和 `Interview.vue:173` 的 `area.score < 50 ? 'danger' : 'warning'` 都漏了——按输出 token 扫才抓得到。

**看得见的变化**（方向都是"同一个分数只会有一种颜色/说法"）：
- **78 分不再一会儿蓝一会儿橙**：推荐卡是蓝（good），历史页/对比页/看板/汇总页此前是橙（80/60 口径），现在同为蓝。代价是 **80-84 从绿转蓝**——那正是后端"可以投递"而非"强烈推荐"的区间。
- **没算出分的地方不再显示成差评**：房间答题胶囊、历史页标签、"回答偏弱，容易触发追问"这三处的 `null` 改走 `unknown`（灰底/灰标签/"评分暂未生成"）。
- **文案与颜色同读一个 tone**：报告 55-59 的结论由"当前风险较高"改为"可继续观察"（它自己的进度条早就是橙色，字色却写风险）；薄弱项标签分界从自抄的 50 改为面试档位的 55（50-54 现在与报告一致地算"偏弱"）。
- 房间胶囊的浅底 + 描边改由 `--app-score-*-soft` / `-soft-line`（`color-mix` 派生）给出，替换 8 个手挑 hex；按 `color-mix` 计算，与旧值各通道差 ≤ 6/255，观感不变。
- **修一个上一段留下的回归**：`OfferCompare` 的"加权综合评分"仍在发 `.score-high/.score-mid/.score-low`，而这三个规则已在 `fd77d2a` 被删——**那个数字自那次提交起就没有颜色**。

**棘轮补的第二层**：hex 预算盯色值，盯不到"发了没人接的 class 名"。新增两条契约测试（`styleDebtRatchet.test.js`）：视图能发出的每个 tone 必须有对应规则（4 个前缀 × 5 档 = 20 条），`--app-score-*` token 集合必须完整（5 档 × 4 后缀 = 20 个）。非空性用假前缀验过（缺 5/5）。数字：视图与布局 `<script>` 的 hex **7 → 0**，`scriptColorLiterals` 预算清零（机制保留，再出现即红）；InterviewRoom `<style>` hex **77 → 69**。

**验证**：`npm run test:unit` **32 passed**（+2 条契约）；`npm test` 11 passed；`npm run build` 通过；`npm run lint` **0 error**；构建产物逐条确认新规则确实落地（`.score-chip--high[data-v-…]`、`.score-level--unknown`、`--app-score-unknown-soft: color-mix(…)`）。**仍未验**：真浏览器 computed-style（browser 工具被会话策略拦），`var()` 套 `var()`（`--score-color: var(--app-score-high)` → `--app-success`）在描边/`el-progress :color` 上按标准应解析，需能看到页面的人复核一眼。

**顺手量到一条与 D1 无关但更糟的**：`Interview.vue:464` 的"薄弱项"在没有可反查趋势时**用 `Math.random()*40+30` 造分数**，再配上颜色与"该维度需要加强训练"——A3 撤掉的是简历侧那批假诊断，这里还在。修法要么是按真实会话维度算，要么去掉这块改为显式空态，两种都会改变候选人所见，故按待决策项处理。

**这段没动的 80 分界**（是产品口径，不是颜色）：`JobRecommend.vue:380` 在 `match_score >= 80` 时挂"优先投递"徽章，而后端 `_recommendation` 要 85 且无必需技能缺口才给"强烈推荐"——同一张卡片可能一边写"可以投递"一边挂"优先投递"；同源的还有 `priorityJobCount`、`History.vue:318` 的"高匹配记录"、`Profile.vue:492` 的成就解锁、`CareerPlanning.vue:968` 的投递策略分档（80/70/60，还叠加缺口数）。见 §10。

**棘轮的第三个盲区（已入账，未清偿，提交 `3bbc343`）**：`hardcodedColorLiterals` 数 `<style>`、`scriptColorLiterals` 数 `<script>`，而**模板属性里的色值两边都不算**——实测 **25 处分布在 6 个文件**（`Login.vue` 17、`DefaultLayout.vue` 3、`ExplainMatch.vue` 2、`CareerPlanning.vue`/`NotFound.vue`/`ResumeUpload.vue` 各 1）。已新增第三条预算 `templateColorLiterals`（同样"增长即红、还债必须调小"），三个维度改由同一对测试驱动：**抽取坏掉也无法蒙混**（template 取空会让 6 个文件全被"预算比现实松"那条点名）。用一次性探针验过三件事——预算数字与实测逐文件相等、多一处即红、未列进预算的文件里有 hex 也红。

这 25 处里 17 处是 Login 的第三方登录品牌色（Google/GitHub 官方值，本就该写死）；其余 **8 处是真债**，和 D1 同源，且**没有一处等于最近的主题 token**：`DefaultLayout.vue:51-52` 导航菜单 `#4b5563` / `#196bdb`（主题里是 `--app-muted #697386` / `--app-primary #2563eb`）、`ExplainMatch.vue:131,140` 的"风险点/改进建议"标题吃 Element 默认橙 `#e6a23c` 与默认蓝 `#409eff`、`CareerPlanning.vue:523` 兜底 `#409EFF`、`NotFound.vue:4` 图标 `#667eea`（不是 `--app-violet #7147d9`）、`ResumeUpload.vue:156` 环形轨道 `#eee`。**本段一条都没换成 var()**：`stroke="var(--app-…)"` 这类 SVG 表现属性、以及 el-menu/el-icon 传色值 prop 的路径，必须真在浏览器里看结果才敢改，而 browser 工具被会话策略拦着——留待能验时逐条做，届时数字只会往下走。预算生成脚本 `scripts/style-budget.mjs` 同步改为三个维度都输出（此前只印 `<style>` 一条，谁照它重生成预算就会把另外两条写没了）。当前账本：`<style>` **510 处 / 34 文件**、`<script>` **0**、模板 **25 处 / 6 文件**。

#### 已交付：D1（第三段）状态→颜色也收成一个口径（提交 `a4156f5`）

**先把"8 套状态色映射"量成事实**：`<script>` 里手写 `状态: 'el-tag 类型'` 的地方实测 **17 份表 / 32 个键 / 85 条**。**重复本身不是缺陷**——KnowledgeBase 的文档类型、PipelineKanban 的阶段、CareerPlanning 的策略各是一套领域，同名不同义不该强行合并。真正的矛盾只有两个键：

| 状态 | 之前 | 现在 |
|---|---|---|
| 任务 `running` | 任务中心蓝、两个 agent 页**橙**（而橙在这几页已表示 `partial`＝部分完成、要看一眼） | 全站蓝 |
| 面试会话 `ongoing` | 房间页**绿**、设置页**橙**，而房间页的绿又同时表示 `completed` | 全站蓝 |

**新口径（`utils/statusTone.js`）**：绿只代表"完成"；进行中的一律 primary；橙留给 `partial`；红留给失败；灰留给"未开始 / 已取消 / 不认识"。随之而来的可见变化共 4 处染色：`running`/`ongoing`/`connecting`/`evaluating` 变蓝，多智能体页的 `partial` 由"没命中→灰"改为橙。**未识别状态保持灰**，后端新增枚举不会把任务画成红色失败（这条写进测试）。

**5 条契约测试**钉住形状：值必须是真实 el-tag 类型、两表共用的键只能有一种颜色、只有 `completed` 可以绿、进行中集合必须是 primary。**棘轮加第四维** `statusTagEntries`（数每条手写 `状态: 'tag'`，不数 `ElMessageBox` 的 `{type:'warning'}` 这类噪声）：**85 → 51**，分布在 11 个文件，后续每收一份领域表就得调小。

**验证**：`npm run test:unit` **34 → 41 passed**；`npm test` 11 passed；`npm run lint` 0 error；`npm run build` 通过。**没验**：真浏览器里的标签颜色（工具被策略拦），但这次改的是 el-tag 的 `type` 属性值——它只有 5 个合法取值且由 Element 自己上色，不涉及 `var()` 解析，风险面比第二段小。

**这一段没做的**：PipelineKanban 的 7 条阶段色、KnowledgeBase 的 12 条文档类型、CareerPlanning 的 9 条策略/优先级等，仍各留本地表（它们没有跨页矛盾，只是重复），由新维度按数字盯着。

#### 已交付：D2 日期格式化 18 份副本收进一个模块（提交 `df263d5`）

**数量按行为数，不按函数名数**：按名字 grep 得到"15 份副本 / 14 个文件"，按行为（视图里出现 `toLocale*` / `Intl`）再数一遍是 **18 份 / 16 个文件**——漏掉的三份是 `PipelineKanban.formatShortDate`、`JobSearch.formatPipelineTime`、`JobRecommend.formatShortDate`，与上一段分数梯级漏两处是同一个盲区（**函数名是不可靠的索引**）。收进 `src/utils/format/date.js` 的 **7 个具名输出**：`monthDay`（9月21日）、`monthDayTime`（9月21日 18:05）、`dateTime`（2026/9/21 18:05:00）、`compactDateTime`（09/21 18:05）、`isoMonthDay`（09-21，图表轴，不经过 Date）、`utcStamp` / `rawStamp`（不本地化的服务端串），共 34 个调用点。

**两对"看起来不一样其实完全一样"是量出来的，不是猜的**：`toLocaleDateString` 带 hour/minute 与 `toLocaleString` 带同样选项逐字节相同（Interview 与看板各写一份）；`toLocaleString('zh-CN')` 与带 `hour12:false` 也相同（中文默认 24 小时制，任务中心与 admin 四页共 5 份其实是同一份）。

**三处故意不同，写成断言而不是藏起来**：
1. `Profile.vue` 那份写的是**不带 locale** 的 `toLocaleString()` —— 同一条时间戳在英文浏览器上会变成 `9/21/2026, 6:30:05 PM`，而全站其他地方是中文格式；现在与全站一致（中文浏览器上输出不变）。
2. 那些 `catch { return d }` 是**死代码**：`toLocaleXxx` 对坏值不抛异常，而是返回字符串 `Invalid Date`，所以注释承诺的"保留后端返回的原始时间"从未发生。现在坏值真的显示后端原文。
3. 缺值占位符保持各页原样（`''` / `'-'` / `'--'`），不改任何列的宽度。

**证明方式**：`tests/unit/dateFormat.test.js` 把迁移前的实现**逐字抄进去**当黄金对照，对 ISO / 带 Z / 带偏移 / 仅日期 / 毫秒数等 7 个输入逐个断言输出相同；上面三处不同则单独断言"旧的是那样、新的是这样"。对照跑在同一进程同一时区，所以不需要在测试里写死任何日期字符串（本机 `Asia/Shanghai`，CI 是 UTC，结论不变）。`locale` 相关那条按运行环境分支断言，避免在 en-US runner 上假失败。

**棘轮第五道**：视图与布局里再出现 `toLocale*` / `Intl.DateTimeFormat` 直接红。数字：`test:unit` **41 → 51 passed**，smoke 11，lint 0 error，build 通过，本单元净 **-102 行**；顺手清掉 `fd77d2a` 在 OfferCompare 留下的空行。

**没做的**：`Home.vue` 里 `new Date().getHours()` 那种"取小时做问候语"不是格式化，未动；`InterviewReport.formattedDuration`（秒→"x 分 y 秒"）是时长不是日期，也未动。

#### 已交付：D3 并发请求改为"新的一次赢"（提交 `630846c`）

**先量再改**（这次仍按行为数，不按名字数）：视图里有 **95 个函数 `await` 之后直接写 ref，一个带请求序号的都没有**；`loading` 泄漏实测 **0 处**。**本段初稿里我写过"静默 catch 是拦截器契约下的正确形状"——那句是错的，已撤**：`request.js` 的两处通知条件是 `shouldNotify = notifyError !== false && method !== 'get'`（`request.js:42,56`），也就是 **GET 失败默认不弹任何提示**。所以安静 catch 一个 GET 的结果是"失败被显示成没有数据"，这条另立 D4 处理（见下）。**真正的顺序缺陷**是：`await` 之后谁后回来谁写，于是**最后完成的赢，而不是最后发起的赢**。

**两处可达、先写成红测试再修**：
1. `TaskCenter` 每 10 秒轮询（全项目唯一的 `setInterval`），概览卡片在 loading 期间仍可点（"刷新"按钮反而有 `:loading` 禁用，所以那条路径本来就安全）。后端一慢，两轮请求叠加，**用户看到的是上一轮的列表**。
2. `KnowledgeBase` 的列表由 `watch([filterType, filterStatus, myOnly])` 触发。先改类型再改状态，两次请求同时在飞，慢的那次后回来时**表格显示的是旧筛选组合的结果，而下拉框显示的是新组合**。

`src/composables/useLatestCall.js`（14 行）每次发起给一个令牌，写 `list/tasks`、写 `loading`、写错误前都先问"我还是最新那次吗"；过期那一次不动 spinner（转圈归更新的那次）。同样的接线用在了 `JobSearch` 的 `loadLocalJobs` / `loadRecommendations`（`watch(activeTab)` 触发），**这两处我没有单独写红测试证明**，只是同一形状，且 `/jobs/search` 已被路由冒烟挂载覆盖。

**证明与数字**：`test:unit` **51 → 57 passed**（TaskCenter 2 例断言渲染出的 `.task-card`；KnowledgeBase 1 例断言 `el-table` 绑定的 `list`——jsdom 下 el-table 不渲染行，DOM 断言拿不到东西，这点写在测试注释里；composable 3 例）；smoke 11；lint 0 error；build 通过。三条红测试在改之前都实测为红（TaskCenter 显示 `任务1`、知识库显示 `最早那次的结果`）。

**计划修正**：阶段 1 原写"`composables/useAsync` 收 24 处手写 loading、150+ 个 catch"。**量完不成立**：`loading` 泄漏实测 0 处，为它们做一层包装就是"没有可见收益的重构"，所以这条从待做里撤下，改为按缺陷逐个取证（本次是竞态，下一次见 D4）。剩下 95−4 个未接线的"await 后写 ref"仍是潜在竞态面，但**哪些真的可被用户并发触发需要逐点读代码或真浏览器验证**，我没有一个能负责的总数，故列为待查而不是待做。（我当时随这条写下的"catch 是拦截器契约下的正确写法"半句是错的，见 D4 开头。）

#### 已交付：D4 加载失败不再被显示成"没有数据"（提交 `613af71`）

**起因是 D3 里我自己写错的一句话**（已在上面撤回）：`request.js:42,56` 的通知条件是 `notifyError !== false && method !== 'get'` —— **GET 失败默认什么都不弹**。于是"catch 里把列表清空"这种写法会把一次 500 渲染成页面的空态。

**最坏的一处在推荐页**：`JobRecommend` 拉推荐失败 → `recommendations = []` → 命中
`暂无匹配的岗位推荐，请完善简历信息或导入更多岗位数据`，并给出"生成模拟岗位"按钮。
**服务器报错被说成是候选人简历的问题**，还给了一条会把人带偏的操作。

**改法**：失败成为独立状态（`recommendError`，取 `e.userMessage`），渲染 `.load-error` 块 +
"重试"按钮（重试会真的重新发同一次请求，测试断言调用次数从 1 变 2）；**真的没有推荐时空态文案原样保留**——这条也写成断言，防止两个状态以后又并回一个。`JobSearch` 的"本地岗位仓库"分支同病（失败会说成"岗位仓库还是空的"），用了同一套接线；没为它写 DOM 测试，因为挂载该页要 mock 约 20 个 api 模块，而路由冒烟已经会挂载 `/jobs/search`，至少保证不炸。

**验证**：`test:unit` **57 → 59 passed**（1 红→绿证明失败态，1 反证空态未被吃掉）；smoke 11；lint 0 error；build 通过。**没验**：视觉呈现仍是本机浏览器级别（`.load-error` 的边框色用 `color-mix(--app-danger, white 66%)` 复算了旧 `#f2c5bf`，各通道差 ≤ 3/255）。

**还剩多少**（按"渲染 el-empty 且 catch 只清列表"扫出来的清单，逐条判过性质）：
- **同类可见谎**：`JobSearch.vue:1484`（简历列表）、`:1496`（简历详情）、`:1520`（工作台条目）、`PipelineKanban.vue:753`（版本列表）、`JobRecommend.vue:745`（反馈统计面板 → 显示"暂无反馈分布"）、`History.vue:348`（详情抽屉）、`admin/Overview.vue:229,264`、`admin/Tenants.vue:343`（企业侧，冻结中）。
- **看着像但不是**（有意降级或语义上等价，注释也写清了）：`JobRecommend.vue:721,731`（投递/收藏状态拿不到时宁可显示未投未收藏）、`InterviewSetup.vue:398`（接口失败保留内置面试类型配置）、`AgentAnalysis.vue:548`（轮询瞬断继续）、`MultiAgentAnalysis`/`AnalysisResult` 若干。
- 另有一批注释写着"request.js 已提示"其实**只对非 GET 成立**（`History.vue:348,367`、`PipelineKanban.vue:816,841,849`、`JobSearch.vue:1903,2098,2107`），注释本身在误导后人；改注释可以顺手做，但要先逐个确认那一次调用到底是 GET 还是 POST。

#### 已交付：D5 剩下 8 处"失败说成没有数据"收进 `AppLoadError`（提交 `bd7fa68`）

**先把度量定准**：D4 末尾那份清单是按"渲染 el-empty 且 catch 清列表"粗扫的（18 条，含假阳性）。这轮把判据写进棘轮并**把 catch 之后 12 行一起看**（批量诊断就是先清值、后在函数里报告），得到基线 **11 处 / 8 个文件**——`admin/Overview` 2、`CareerPlanning` 2、`Interview` 1、`JobSearch` 2、`PipelineKanban` 1、`Privacy` 1、`ResumeCompare` 1、`ResumeUpload` 1。上面对 GET/POST 的那批注释判断也逐条查过：薪资那次确实带 `notifyError: false` 主动关掉了提示，所以"什么都不说"就是它唯一的对外表现。

**候选人侧 8 处已接**到 `components/ui/AppLoadError.vue`（另有 1 处判据没数到但同病的 `Interview` 历史记录一并接了，所以数字降 8、分支加 9）：
- `Privacy.vue` 个人数据概览：失败时整块消失＝对用户说"我们没存你的数据"，这是合规面，现在显式失败。
- `CareerPlanning.vue` 薪资行情 + 职业方向：两个证据面板拉不到时不再靠"面板不见了"表达。
- `Interview.vue` 近期面试 / 历史记录；`JobSearch.vue` 简历选择器 / 跟进记录；`PipelineKanban.vue` 简历版本下拉；`ResumeCompare.vue` 岗位下拉。

**为什么新建组件**：这是第四个需要同一块视图，D4 手写的 `.load-error` 再复制 8 份就是 9 份；顺手把它做成阶段 1 计划的 `components/ui/` 第一个成员，并把 D4 的两处改用它（两份 scoped 复制删掉）。

**剩 3 处**，每条的理由写在预算注释里：admin 两处随企业侧冻结不动；`ResumeUpload` 的版本计数失败改为存 `null`（"不知道"）而不是 `0`——卡片因此不显示数字，也不再作出"0 个版本"的断言，判据仍计它，属明知故留。

**棘轮第六维** `silentEmptyCatches`：**11 → 3**，只降不升。非空性用对照组验过：合成一条静默 catch 计 1、该处开始报告后计 0、报告写在 catch 之后 12 行内也计 0（这条就是消除假阳性的 widening）。`test:unit` **62 → 64 passed**；smoke 11；lint 0 error；build 通过，`dist` 里有 `.app-load-error[data-v-*]`。**没验**：真机渲染（浏览器工具被策略拦）；`el-select` 下方插一条错误块的排版好不好看，需要人看一眼。

#### 已交付：D6 注释里"请求层已提示"的假话与它盖住的 3 处（提交 `38eb6d4`）

D5 的判据只数"catch 里清值"，所以**注释型 catch whole 类是它的盲区**（`silentEmptyCatches = 3` 因此是下限，不是"全修完"——这条已写进棘轮注释）。这轮把 20 条"注释声称 request.js/请求层已提示"的 catch 逐条对着 `src/api/*` 的 HTTP 动词核：6 条命中 GET，其中 **4 条是我自己 40 行回看窗口跨函数误判**（`deleteHistory` 是 DELETE；`AnalysisResult:580`/`SmartAnalysis:1620` 那两个 catch 包的是轮询 helper，失败本来会走 `onFailed/onCancelled/onTimeout` 回调弹提示），**真问题 3 条，全是 GET**：

- `SalaryInsight.doSearch`：先 `overview.value = null` 再 await，注释却写"保留上一次查询结果"。真实行为是查询失败后**整页空白**，且因为 GET 不弹提示，没有任何地方说为什么。注释与代码相互矛盾，两个都错。
- `SalaryInsight.checkExpectation`：**最有害的一条**。失败时旧结论原地留着，于是"算法工程师 35k 是否合理"的提问，屏幕上显示的是上一次那个岗位的"薪资期望合理"——**一个错误答案被当成新答案读走**。现在失败即撤旧结论 + 显式失败 + 重试。
- `History.openDetail`：详情弹窗 GET 失败时 `detail` 保持 null，弹窗里什么都不渲染 = 空盒子。现在是"分析详情加载失败 + 重试"。

**测试**：`tests/unit/salaryInsightFailure.test.js` 2 例，关键断言不是"有没有错误条"，而是**旧结论文本从 DOM 消失**（只加横幅证不到这一条）。`test:unit` 64 → **66 passed**，smoke 11，lint 0 error，build 通过。
**过程自纠**：History 那次改动我先写坏了 `v-if/v-else-if` 链，是路由冒烟（`/history` 在 13 条挂载之列）第一次跑就报的——这也说明挂载清单保持宽是有用的。渲染层面（弹窗内、薪资面板里的排版）仍未在真浏览器验过。

**还有一类没动**：`Interview.vue:444`、`InterviewSetup.vue:398`、`JobRecommend.vue:721,731` 这些注释写的是**真实的有意降级**（拿不到收藏状态就显示未收藏、接口挂了用内置题库），不是假话，留在原处。

#### 已交付：E10 埋点链路两端都是断的，而且第 4 个发现改变了这条的定性（提交 `cb5a72b`）

**从 E 表里那行"死代码：`api/tracking.py` 定义了 router 却从未被 include"往下挖**，挖出四个事实，前三个是让这条链即使接上也不可信的缺陷：

1. **服务端端点根本不存在**：router 没被 include，`POST /api/tracking/events` 是一个 404。现已挂进 `api_router`。
2. **"断网不丢事件"是文件自己 docstring 里的假话**：客户端先把一批事件 `splice` 出队列再发，而 `fetch` **只对网络异常抛错**——404/500 是 fulfilled promise，原来那个 catch 永远等不到"服务端拒绝"，于是每次非 2xx 都静默销毁一批事件。现在按 `resp.ok` 判定，不成功就把这一批放回队头（队列上限 200，长期离线不会无限占 localStorage）。
3. **未登录时也在发**：`Bearer null` 必定 401，又是白丢一批。现在没 token 就不发，事件留在队列里等登录后补传。
4. **关页面时扔掉一批**：`navigator.sendBeacon` 带不上 `Authorization` 头（这个端点要登录），发完还无条件 `removeItem`。换成 `keepalive: true` 的 fetch（能带头），不确认送达就不删队列；监听从已不可靠的 `beforeunload` 换到 `pagehide`。

**第 4 个发现把这条的定性改了**：`grep` 过 `frontend/src` 全部 `.js`/`.vue`，**没有任何视图或 store 导入 tracker，`track()` 的调用方是 0**。所以前三条今天**没有**产生候选人可见的 404、也**没有**真的丢过数据——我明确不这么声称。这轮做完的是"管道本身不再谎报成功"，而**要不要真的埋点仍然是一个产品决定**，不是清理：这些事件会变成个人数据（服务端 stub 现在把 `user_id` + `username` 写进日志），而隐私页正在对用户承诺我们存了什么。要么点名哪些事件值得收，要么把 SDK 删掉——两条都是他的，已记进 §10.8。

**验证**：后端测试断言三件事——路由出现在**真实的 `api_router`** 里（HEAD 的 router 对 tracking 零提及，所以这条改前是红的；另配 `len(paths) > 200` 反证这个断言不是空转）、带鉴权的一次批量被接受（`received == 2`）、匿名调用拿到 **401 而不是 404**；E1 那张公开面清单仍然通过，说明新路由没被开成公开端点。前端 `tests/unit/tracker.test.js` 4 例各锁上面一条行为，**对着旧 tracker 跑是 4/4 红**。`test:unit` **66 → 70 passed**；smoke 11；后端 `pytest` 709 passed；`ruff check` / `ruff format --check` 干净；lint 0 error；build 通过。**没验**：真机网络行为（离线队列、`pagehide` 的 keepalive 是否真的送达）——没有调用方，端到端也就无从在 UI 里触发，这一层要等 §10.8 定下来才有意义。

#### 已交付：E11 会话鉴权从"每个端点自己记得写"变成"前缀默认要会话"（提交 `21778e2`）

**先把"opt-in 而非构造保证"量成一张表**：遍历真实路由图，233 条操作里 15 条匿名、218 条带凭据；按前缀（30 个 `include_router`）分组后，**22 段前缀在改动前就已经 100% 带会话依赖**，覆盖 123 条操作；剩下 8 段混着公开端点（`auth` 6、`jobs` 1、`interview` 1、`system` 2、`organizations` 2、`subscription` 2、`tenant` 1 全公开、`v1` 走 `X-API-Key`），共 110 条。

**做了什么**：给那 22 段挂 `dependencies=SESSION_GUARD`（就是 `Depends(get_current_user)`，定义在 `api/router.py` 一处）。因为这 123 条**本来就逐条写了同一个依赖**，所以**今天没有任何一条响应变化**——这一点要说明白，这条买的不是"现在更安全"，是"以后加一条忘了写凭据的端点，它出生就 401，而不是安静地对公网开放"。混着公开端点的 8 段**故意没挂**：挂上去 `GET /jobs/cities`（登录页在拿到 token 之前要用）会当场变 401，它们的公开面继续由 E1 那张 `PUBLIC_OPERATIONS` 清单逐条钉住。

**棘轮加的是四道锁，不是一道**（`tests/test_public_api_surface.py`，709 → **714 passed**）：
- 守护前缀下每条操作都能解析到会话凭据，且**覆盖数 ≥120**——防止前缀写错导致"守护了 0 条也算通过"；
- **依赖必须在 include 级**：上一条测不出守护有没有真挂上（端点自己写的 `Depends` 长得一样），这条把 `route.dependencies` 单独拆开看。**把 `router.py` 还原后这条是红的**（连同下面两条运行时测，共 3 红）；
- 公开清单里任何一条都不许落在守护前缀内——反向锁住"有人把 `/jobs` 顺手加进表里"；
- **运行时证明**：一个自己不声明凭据的探针端点，挂上守护后匿名调用 401；不挂守护时同一个 router 必须 200（这条是对照组，防上一条空转）。另外一条证明**守护没有让 `get_current_user` 每请求跑两次**（FastAPI 的依赖缓存吃住了，否则会多一趟 DB 往返）。

**装配后的真实 app 也过了一遍**（只读脚本，跑完删）：匿名 `GET /api/resume/list`、`/api/history` → 401，`POST /api/tracking/events` 无 token/坏 token → 401，而 `/api/jobs/cities`、`/api/interview/config/types`、`/api/system/health`、`/api/tenant/brand` 仍匿名 200，`/openapi.json` 仍能构建（214 条 path）。`ruff check` + `ruff format --check` 对 2 个文件 clean。

**还剩什么**：那 8 段混合格式的 110 条操作仍靠逐端点声明 + 清单兜住。要把它们也变成构造保证，需要先做**端点级拆分**（把 `auth.py` 的 6 条公开、`system.py` 的 2 条探活等挂到不带守护的子 router 上），是一次跨 6 个文件的机械改动，收益是"新端点默认 401"覆盖面从 123/233 提到 218/233。这活没干的原因：它改的是登录/回调/探活路径，属于一旦弄错就锁死入口的那类，且 E1 的清单已经把当前漏保护的实际风险压到 0。

#### 已交付：E12 启动清扫改判"静默"，不再按"多久以前开始"判死刑（提交 `3ecbb96`）

**机制**：`app/main.py` 的 lifespan 每次 web 进程启动都调 `mark_stale_running_tasks_failed()`，旧判据只有一句 `status == "running" and start_time < now-30min`。而 `start_time` 是**建任务那一刻**写的，任务完全可能在**另一个进程**里跑（`ORCHESTRATION_BACKEND=redis_queue` 时 worker 独立），所以只重启 web（`--reload`、滚动发布、崩掉拉起）就会把 worker 手里的活任务判成 failed。落到候选人身上是一条链：`utils/agentTaskPolling.js:99` 一见到 failed 就 `stopPolling()` 并拿 `error_msg` 报错（`:102`），于是**分析页停在"失败"，而分析在几秒后正常完成并落库**——结果存在，人已经走了。

**第二条是那句话本身在说谎**：旧文案 `Marked failed on startup because the previous worker stopped before completion` 断言"上一个 worker 停了"，可清扫只看得到"没进展"，看不到进程生死；而且它是英文，会原样出现在中文界面里。

**改法**：
- 判据变成"最后一次**进度写入**也超过窗口"：`max(coalesce(completed_at, started_at, create_time))` 取 `agent_step_log` 与（经 `agent_run.task_id` 关联的）`agent_message` 两路，和 `start_time` 一起取最大——任一路还在写就不收口。cutoff 用 `utc_now_naive()`，因为 DB 读回的 DateTime 是 naive（`app/utils/time_helper.py` 早就为这个坑写了 `utc_now_naive`，之前没人用）。
- 新文案只说量得到的事：`任务超过 N 分钟没有新的步骤写入（最后一次活动 <ts>），按中断收口`。
- 顺手关掉残留：`LinearStrategy.run` 是**三个策略收尾里唯一不动 `error_msg` 的那个**（`strategies.py:599` 与 `langgraph_flow.py:438/500` 都会清），所以"先被清扫、后被跑完"的任务会带着那条假失败原因变成 completed，并且经 `_finish_run(..., task.error_msg)` 传染到 `agent_run.error_msg`。

**先量再改**（真 dev 库，只读脚本跑完删）：89 条任务，**中位耗时 0.5 分钟、p90 0.9 分钟**；带旧清扫文案的 **5 条**，逐条比"最后一条步骤日志 vs 清扫时刻"，间隔是 **12～18 天**——**这 5 条是真孤儿，新规则照样判它们失败**。所以：
- **误杀这一半是测试证明的，不是数据里抓到的**，本机没有受害者；这也是我没动 30 分钟默认值的原因（窗口约是典型任务的 30 倍，真跑长的场景是队列积压，那属于"队列无 ack/DLQ"那条）。
- 但那 5 条**确实证明**了文案在说谎：它对着 12～18 天没动的任务说"上一个 worker 停了"，这句话它无从知道。
- 另外查了"完成任务身上还挂着旧失败原因"的存量：`completed/partial` 且 `error_msg` 非空 = **0 条**，即残留 bug 目前也是无受害者的存量代码路径。

**测试**：4 条新断言，**全部红→绿**（把两个生产文件还原后确认 4 红）：步骤日志还在写 → 不判；节点消息还在写 → 不判（第二条证据源单独锁，防只接一路）；最后活动也超过窗口 → **仍判失败**（反证：不能改成"永远不收口"），且文案含阈值、不含 "worker"；策略成功清掉 inherited `error_msg`。`pytest` **714 → 718 passed**；`ruff check` + `format --check` 全库 298 文件 clean；原有的 `test_mark_stale_running_tasks_failed_only_updates_old_running_tasks`（零活动证据的老任务）仍通过。**没验**：真多进程场景（起了 web 再起 worker 去观察误杀）——`mark_stale` 只在 lifespan 跑，需要两个进程 + 一个 >30 分钟的任务才能复现，我用测试里的时间注入代替。

**故意留着没改**：清扫仍写 `end_time = utc_now()`，所以那 5 条在任务中心显示 `耗时：18天`（`TaskCenter.vue:95` 渲染 `task.duration_ms`，服务端 `task_center_service.py:31` 就是 `end_time - start_time`）。把 `end_time` 挪到最后活动会让这个数字好看，但 `operational_alert_service.py:67` 按 `end_time >= since` 统计失败任务，挪了就等于"今天发现的失败不再进今天的告警"——宁可留一个难看但真实的跨度。

#### 已交付：E13 跨页"上一次选择"收成一个按登录用户分槽的模块（提交 `67688cd`）

§7 那句"`recruit.lastResumeId/lastJDId/lastRecordId` 是跨页隐式握手，应改由 Pinia 承载"低估了它：量的时候发现**同一件事有两套键名，而且它们互不读取**。

- **19 处**用全局键 `recruit.lastX`（`AgentAnalysis` / `AnalysisResult` / `CareerPlanning` / `Interview` / `JDInput` / `MultiAgentAnalysis` / `ResumeUpload` 读写），**6 处**用按用户键 `recruit.lastX.<uid>`（`SmartAnalysis` 自己私有的 `storageKey()` 5 处 + `JobSearch:1840` 1 处）。
- 后果一：工作台里选的简历**永远传不到**规划/分析页——它写的是带 uid 的键，而那几页读全局键。
- 后果二（真正会碰到候选人的那个）：全局键**跨账号存活**。换过账号的浏览器里，`AgentAnalysis`/`MultiAgentAnalysis` 的 `fillLast()` 会把**上一个账号**的 resume_id/jd_id 预填进表单，`CareerPlanning.restoreSelections()` 一样，`Interview.useLast()` 直接拿上一个账号的 record id 去 `getAnalysis()`。
- **先查了是不是泄露**：不是。`api/analysis.py` 每条都带 `AnalysisRecord.user_id == current_user.id` / `_get_owned_resume`，所以症状是——候选人看到一个自己从没见过的记录报 `记录不存在，或无权限访问`，以及"检测到你最近用过：简历 ID=xxx"里出现别人的 id。是**假故障 + 假归属**，不是数据泄露。

**做法**：`src/utils/lastSelection.js` 成为这三个值的唯一持有者——槽位 = 登录用户 id（没有就是 `guest`），**拿到真实 id 时顺手删掉旧的全局键与 guest 槽**：无主的 id 不会嫁给下一个登录的人，因此**不做数据迁移**，这次改动之后第一次进页面是"不预填"，用户选一次之后才有（这条是有意的，写在模块头注释里）。身份只由 `stores/auth.js` 通知它（store 初始化、`setAuth`、`clearAuth` 三处），所以 `user` 这个 localStorage 键没有多出第三个读取方。**25 处裸访问清零**，`SmartAnalysis` 的私有 `storageKey`/`uid`/`authStore` 一起删掉；`ResumeUpload` 原来靠 `|| ''` 表达的"说不清属于哪份简历就擦掉"改成显式 `forgetResume()`。

**棘轮第七维**（`styleDebtRatchet`）：视图里不许再出现 `last(ResumeId|JDId|RecordId)`。**按字段名匹配而不是完整键名**，否则 `storageKey('lastResumeId')` 这种自己拼前缀的写法能躲过——把 9 个视图还原成 HEAD 后这条列出全部 9 个文件（新的 `SmartAnalysis` 也在里面），改完即绿。

**验证**：`test:unit` **70 → 77 passed**（6 条模块用例：guest 槽在登录时被清、旧全局键被清、A 的选择 B 看不见且 A 回来还在、`forget*` 只影响当前槽、坏值不当成 id；+1 条棘轮）；smoke 11；lint 0 error；build 通过；新文件 prettier clean。**没验**：真浏览器里登出→换账号→进分析页的现场（`browser-use` 被策略拦），也没验真实多标签页共享 localStorage 的情形。

**同一批里没动的**：`recruit.pendingAnalysis`（`JobSearch` → `SmartAnalysis` 的一次性载荷，3 处）仍是全局键。它装的正是用户刚点的那条 JD、且读完立刻 `removeItem`，跨账号存活窗口比上面那三个小得多——要不要一起进槽，等 §10.9 定"这些隐式握手最终归谁"时一并处理。

#### 已交付：E14 限流额度改为"有身份算到人，没身份算到地址"（提交 `63537ab`）

**先把接线量开**（不看注释看代码）：全仓只有 **5 个端点**自己声明了限流，全在 `api/auth.py`——`register` 用 `auth_limit()`(20/min)，`login`/`reset-password`/`forgot-password`/`send-verification-email` 用 `login_limit()`(5/min)；这 5 个**都是匿名路径**。也就是说 **233 条操作里剩下的 228 条只受 `default_limits = RATE_LIMIT_GENERAL`（默认 100/分钟）管**，而 key 是 `get_remote_address`。

**症状**：一个校园网/咖啡馆/热点出口下所有候选人**共用同一个 IP 桶**——谁的页面轮询最勤就把额度吃光，同出口其他人**什么都没做就被 429**。这正是 E 表那行"NAT 后用户共享额度"。

**改法**：`get_user_or_remote_address` 取代 key——`Bearer` 能解码且带 `sub` 的请求算到 `user:<sub>`，其余一律回落到地址桶。三点是有意为之：① `sub` 就是 `get_current_user` 唯一采信的那个 claim，两处口径一致；② **解不开的 token 不给独立额度**（伪造头刷不出预算），所以坏值/无 `sub` 都落回地址；③ 登录与注册**继续按地址**——还没有身份时地址是唯一能钉住人的东西，改了就等于削弱爆破防护。

**没做的一半**（是"该填哪个数"的问题，不是 bug）：**昂贵端点仍然没有自己的限流**，一个登录用户照样能一分钟发 100 次深度分析（每次都是真金白银的 LLM 调用）——记为 §10.10。另一个方向也说明白：**登录流量的每 IP 总闸随这次改动没了**（现在是每人一份 100/分钟，同一出口叠加起来会比原来高）。要那个闸就得用 `application_limits` 按地址再挂一层，而它同样需要一个数，所以留给 §10.10 一起定。

**测试 6 条，`pytest` 718 → 724 passed**：key 函数三种输入（有效 token→`user:42`；乱码 token、以及能解但没 `sub` 的 token→地址）；两个用户同一出口各自有额度（A 用满后 B 的第一次必须 200）；**对照组**——同一台 app 换回 `get_remote_address`，B 的第一次就是 429（没有这条，上一条绿了什么都证不了）；匿名流量仍然共用地址桶；以及一条"真实 app 上挂的 limiter 用的就是这个函数"的接线断言（把 `key_func` 改回旧值时唯一变红的就是它，所以这条也验了）。

**过程中查清的一件测试基建事实**：行为用例最初共用 `get_limiter()` 这个进程级单例，结果第二个 app 里同名探针路由的额度被前一个用例吃掉。我先怀疑是 `conftest.reset_rate_limiter` 没生效，用 `--setup-plan` 核过：**它确实是 autouse 且 `MemoryStorage.reset()` 真会清计数**——串扰来自单例的**路由注册表**，不是计数。所以每条行为用例各自 `Limiter(storage_uri="memory://")`，把这件事写进文件 docstring，免得下次又去怀疑 fixture。`ruff check` + `format --check` clean。**没验**：Redis 存储下的真实 keying（测试跑在 memory://），也没有真出现"某个 NAT 用户被 429"的现场记录。

#### 已交付：D7 职业规划页：旧简历的慢响应不再顶到新简历下面（提交 `fb57d7e`）

D3 结尾留的那句"哪些加载函数真的可被用户并发触发，需要逐点读代码"——这轮挑了一页去读，答案是**能**，而且症状就在候选人眼前。

**机制**：`watch(selectedResumeId)` 一次触发两个面板——`/career-path/recommend`（职业方向，按简历算）和 `/salary/overview`（薪资样本，取的是**这份简历解析出的职称**）。两处都是 `await` 之后直接写 ref，于是**后完成的赢，而不是后发起的赢**：
- 7→8 换简历：8 的方向先回来、7 的慢响应后到，屏幕上就成了**为一份已经没选中的简历算出来的方向**——而这一页对候选人的承诺恰恰是"给你这份简历的方向"；
- 8 还在飞的时候，7 的方向**原样留在屏上**，看起来像是新简历的结果；
- 薪资区间同形。

**改法**：两个面板各自一把 `useLatestCall()` 令牌，并且新一发请求在 `await` 之前先把上一份简历的结果撤下。**两把令牌不是讲究**：先照 JobSearch 那样共用一把（那里两个加载函数是互斥标签页，共用才对）会让方向在薪资请求发出的那一刻就被判成"过期"，因为这两个请求是**同一意图下一起发的**——这一条是重读 composable 时抓到的，没跑测试之前它就已经是错的。

**测试 5 条，`test:unit` 77 → 82 passed**：3 条对着 HEAD 是红的（旧响应覆盖、加载中残留旧结果、薪资被覆盖），2 条是**两条方向都绿的对照组**——丢弃旧响应不许把"加载中…"卡死；同一份简历点"刷新"必须还能显示新数据（要是把"清空"写成无条件，这条就红）。薪资那两条要先 resolve 掉方向的请求才会有第二次薪资请求，因为 watcher 里是 `await 方向; await 薪资` 的顺序——这是页面的真实性质，写进了测试注释。

**顺手量到、故意没修的两件事**：
- `targetRole` 只在为空时被第一份简历的职称填上，之后**换简历不会更新它**，所以薪资面板一直查第一份简历的职称。它显示的标签和数字自洽（写着"后端工程师"就给后端工程师的数），所以不是假话，只是没跟上选择；要改就得决定"自动填的字段能不能被下一次选择覆盖"——归 §10.11。
- 两个请求串行等待，薪资面板必然比方向慢一个来回。改成并发是一行，但它改变的是候选人看到两块的先后，不在"静默错误"这次的范围内。

**过程自纠（测具，不是产品）**：先在 api 模块层 `vi.mock('@/api/jobs')` 造 deferred，组件的 `await` 始终不返回，白跑四轮探针；这个仓库里已被证明可用的做法是像 `taskCenterRace.test.js` 那样**在 `@/api/request` 层造 deferred**，换过去一次就通。lint 0 error、smoke 11、build 通过；新测试文件 prettier clean，`CareerPlanning.vue` 自身的既有 prettier 债没被我碰（它有 19 行待重排，没有一行是我加的）。**没验**：真浏览器里连续换简历的观感（`browser-use` 被策略拦）。

#### 已交付：D8 删掉一个永远渲染不出来的按钮——它如果被渲染出来，会打开错误的记录（提交 `02f0c04`）

找下一个可证的竞态时撞上的。简历中心「AI 诊断」弹窗里有个 `查看完整匹配分析 →`，条件是 `v-if="currentDiagnosis.jd_id"`，点了执行 `router.push('/analysis/' + jd_id)`。两条事实让这段代码**既是死的、又是错的**：

1. **死的**：`POST /resume/{id}/diagnose` 打分对象是**一个岗位名称字符串**（请求体只有 `target_position`），响应字典（`app/api/resume.py:1209-1223`）里**根本没有 `jd_id` 这个键** → 条件永远为假，从来没有候选人见过这个按钮。
2. **错的**：`/analysis/:id` 打开的是 `getAnalysis(id)`，后端按 `AnalysisRecord.id` 取记录。**把 JD 的 id 塞进这条路由，渲染出来的是"恰好同号"的另一条分析记录**——另一份简历/JD 的结果，顶着"你刚诊断的这份"的语境显示。诊断本身也不产生分析记录，所以这里**没有正确的目标可链**。

**做法**：按钮与 `goAnalysisFromDiag` 删除；`currentDiagnosis.jd_id` 字段保留（行级改写接口把它当"无目标 JD"的入参），注释改成说明它**不能**用来跳分析详情。棘轮加一条路由契约：**任何视图都不许用 jd 拼 `/analysis/${...}`**——把 HEAD 的 `ResumeUpload.vue` 放回去它就点名这个文件，删掉后为绿。

**E13 的收尾**：`forgetResume` 是为这个处理器才加进 `utils/lastSelection` 的，处理器没了 → 导出也拿掉，测试用例回到只测 `forgetJD`，不留一个靠测试续命的未使用 API。

`test:unit` **82 → 83 passed**（+1 契约规则，−1 断言）；lint 0 error；smoke 11；build 通过。净变化 **−31/+20 行**。**没验**：真浏览器里那个弹窗（按钮本就不显示，也就无从截到）。

#### 已交付：D9 岗位推荐：旧那一轮不能把投递/收藏标记打到新简历的卡片上（提交 `25fc431`）

D7 之后接着量的第二页，症状比规划页更疼：**一轮 `loadRecommendations` 是一个用户动作、三个串联请求**（推荐列表 → 哪些已进看板 → 哪些已收藏），三处都是 `await` 之后直接写，而后两处遍历的是 `recommendations.value`——也就是**它们落地那一刻屏幕上的那张列表**。换简历、改四个筛选中的任何一个都会重发整串，于是：
- 旧那一轮的列表可以整块换掉新那一轮；
- 更疼的是旧轮的**回填**会把新简历的卡片标成 `已投递` / `已收藏`，并把摘要条上的 **「已加入看板」「优先投递」两个数字一起带错**——页面告诉候选人"这个岗位你已经投过了"，而他没有。

**做法**：整串一把令牌，三处写入前各查一次，`catch` 与 `finally` 也查。这一页**不需要**像 D7 那样"发起即撤下"：卡片网格在 `loading.recommend` 的骨架后面，飞行途中没有旧结果可看，风险只剩"晚到的写入"。

**测试 4 条，`test:unit` 83 → 87 passed**：2 条改前是红的（列表被旧轮覆盖：DOM 已经渲染出 岗位-B 之后又变回 岗位-A；标记串台：`cardBadges()` 里冒出旧轮的 `已投递`/`已收藏`，「已加入看板」变成 1），2 条是双向都绿的对照组——**同一轮的回填必须照常打上**（把回填整个废掉就会红）、丢弃旧轮不许把 `loading.recommend` 卡成 true。lint 0 error、smoke 11、build 通过，新测试文件 prettier clean。**没验**：真浏览器观感（策略拦）。

**下一处已经看见、这条里没动的**：`loadFeedbackStats` 同样没有令牌，而它是每次点"喜欢/不喜欢"之后重发的——连点两张卡片，先发的统计后回来，"反馈分布"就会显示**你刚那次操作之前**的计数。它比标记串台轻（数字短暂偏旧，不涉及身份错标），且我没为它写出可见断言（要先驱动卡片上的反馈按钮 + 面板形状），所以留在这里而不是顺手加一个未测的守卫。

#### 已交付：D10 反馈统计面板的两种谎：退回的计数，和把失败演成"没有反馈"（提交 `919beb7`）

D9 点名没动的那一个，量完发现它是**两个**可见问题，都在这 6 行里：

- **没有序号守卫**：这个统计是**每次点喜欢/不喜欢之后重发**的。连点两张卡片 → 先发起的那次后回来 → 面板显示的是**用户刚才那次点击之前**的计数（测试里的现象：屏幕上已经是 `4`，被旧的 `3` 盖回去）。
- **`catch { feedbackStats.value = null }` + 面板在 `v-if="feedbackStats"` 后面**：拉不到就把整块面板删掉且什么都不说。GET 失败从不弹提示，所以"消失"是它唯一的对外表现——而它表达的是"**你没有反馈历史**"，对的是一个正在这一页上点反馈的人。

**做法**：一把**自己的** `useLatestCall()` 计数器（故意的：点反馈只重发统计、不重发列表，共用 D9 那把会让两件事互相作废），失败改成走 `feedbackStatsError` + `AppLoadError`（带可用的重试）。

**测试 3 条，`test:unit` 87 → 90 passed**：2 条改前红（计数被退回、失败只留下消失的面板），1 条双向绿的对照组（成功那一轮照常出四个数字）。lint 0 error、smoke 11、build 通过，新文件 prettier clean。

**顺带量到的一条测具粗处**：棘轮的 `silentEmptyCatches` **从来没数过这一处**——它的"报告可能写在后面"窗口会往 catch 之后看 12 行，而那 12 行伸进了下面的 `seedData()` 并在那里撞到 `ElMessage`，于是被当成"有报告"。也就是说剩下的预算 3 既没包含这个谎，也不会自动逮住同类的新谎；把窗口收到**函数作用域**是另一件事，改动面不小，单独立项。

---

## 9. 里程碑

| 里程碑 | 内容 | 出口判据 |
|---|---|---|
| **M1**（约 1 周） | A 全部 + E 的两项一行级修复 + A6 解耦 | mock 可辨识、匹配分唯一、负反馈生效、metrics 已鉴权、评测基线入库 |
| **M2**（约 2.5 周） | B1 | 候选人可一键应用 ≥5 条行级改写并看到分数变化 |
| **M3**（约 4 周） | B2 | 规划中每个分数与薪资区间可反查支撑样本；缺口图成为单一权威产物 |
| **M4**（约 6 周） | C | `/api/multi-agent` 返回真实消息；成本非零；编排收敛到 2 条路径且结果一致 |
| **M5** | B3 | 已达成两项：embedding 持久化、故障不再静默降级（`5d7508a`）；另补一条原计划没写的正确性修复——可见性下推进向量检索（`999f509`）。**"推荐走 multi_recall + ANN"按证据撤下**：真库 72 条活跃岗位，全量扫是微秒级，等量级到几千再评估 |
| **持续** | D 阶段 1→3、E 余项 | 棘轮数字单调下降；`src/components/` 从空目录长出组件层 |

---

## 10. 待决策项

1. **付费墙是否保留**（阻塞 A6）。`check_quota` 仅管简历数量，`deep_analysis`/`ats_check` 从未服务端生效。确认不做商业化 → 摘掉 `resume.py:121`，企业侧即可安静冻结；要保留 → 需补齐服务端功能级校验，否则是装饰性付费墙。
2. **企业侧是冻结还是删除**。本方案建议冻结。若将来要真删，§2.3 两处地雷与 migration `0018`–`0021` 是前置。
3. **是否引入服务端向量库**（Qdrant / pgvector）。当前 Chroma 是嵌入式 persistent client（`core/chroma_client.py:16,47-50`），每个 uvicorn worker/副本各持一份（`docker-compose.prod.yml:100` 挂 volume）——多副本部署下这是一致性隐患，与 B3 一并决策。
4. **`docs/` 归档策略**（§2.5）。
5. **"优先投递"这类产品口径是否跟随后端档位（85）**。D1 只统一颜色；下面几处 80 分界表达的是徽章、统计数与解锁，改了会改变候选人看到的数字与文案，需本人定：`JobRecommend.vue:380`（优先投递徽章，配 `:655` 的计数）、`History.vue:318`（"高匹配记录"）、`Profile.vue:492`（成就解锁）、`CareerPlanning.vue:968-990`（投递策略 80/70/60 分档）。徽章与卡片上后端给的推荐标签现已可能相反（82 分：徽章"优先投递" + 标签"可以投递"）。
6. **`Interview.vue:464` 的随机"薄弱项"分数怎么处置**。当前无趋势数据时用 `Math.random()*40+30` 造分并配颜色与训练建议；选项是按真实会话维度聚合，或删掉该块改显式空态。两者都改变候选人所见。
7. **前端 `format:check` 门走哪条路**（详见 `docs/engineering-quality.md` "Open: the frontend format gate cannot pass"）。CI 安装 prettier 3.9.5，而仓库代码按 3.3 书写：**CI 检出的 `origin/master` 上 95 个文件不过**。要么一次性 `npm run format`（约 95 文件纯排版），要么把 prettier 钉回 3.3（依赖降级）。本段已刻意避开这个岔口：没跑全局格式化，改动文件的既有格式未动。
8. **埋点：补上调用方，还是删掉 SDK**（E10 留下的）。管道两端已修好且各有测试锁住，但 `track()` 调用方仍为 0，所以今天没有任何事件在流动。埋哪些点是产品/隐私决定（服务端 stub 会把 `user_id` + `username` 写进日志文件，而 `db` 参数收了不用），不该由清理顺手替用户做；反之若决定不做分析，`utils/tracker.js` + `api/tracking.py` + 刚挂上的路由一起删。
9. **跨页隐式握手的最终归属**（E13 只做了三个 id）。`recruit.lastX` 现在集中在 `utils/lastSelection` 并按用户分槽，但它仍是 localStorage；§7 原话是"应改由 Pinia 承载"。两件事需要你定：① 要不要把它再收成一个 Pinia store（则 `setSelectionOwner` 变成 store 内部细节，视图少一层 import）；② `recruit.pendingAnalysis`（`JobSearch`→`SmartAnalysis` 的一次性载荷）与 `recruit.defaultResumeId` 是否也进同一套——前者跨账号也会存活，只是窗口小得多。
10. **昂贵端点要不要单独的额度，以及每 IP 还要不要总闸**（E14 留下的两个数）。现在 228 条操作仍共用 `RATE_LIMIT_GENERAL`（默认 100/分钟，已改为按用户计），意味着一个登录用户可以一分钟发 100 次深度分析，每次都打真 LLM；而 E14 之后**同一出口的每 IP 总闸自然消失了**（原来它天然存在，因为大家共用一桶）。要收口就得填两个数：① 昂贵端点（`/api/analysis/full`、`/api/multi-agent/*`、`/api/agent/start`）的每分钟额度；② 是否用 `application_limits` 按地址再挂一层总闸、阈值多少。接线与对照组都已在 `tests/test_rate_limit_key.py` 备好，填数即可。
11. **自动填的"目标岗位"该不该被下一次选择覆盖**（D7 量到的）。`CareerPlanning` 里 `targetRole` 只在为空时由简历职称填入，之后换简历不改它，于是薪资面板继续查第一份简历的职称——标签与数字自洽，所以不是假话，但它不再代表"当前这份简历"。要么"自动填入的值在用户没编辑过时跟随选择"（需要区分自动/手输），要么在换简历时把薪资面板标注成"按 目标岗位=<现值> 查询"。两条都改变候选人看到的数字，且第 ① 条要动输入框的状态模型。

---

## 11. 附录：本方案未采纳的一条建议

上一轮审计中曾提出"把全局主题从 `[class*='-card']` 类名通配改为覆盖 Element Plus `--el-*` 变量，删掉 56 个 `!important`"。实测该改法**不无损**：摘除通配网后 5 条路由出现 157 个元素实例的样式回归，而收窄到显式类名列表需先完成 D 阶段 1 的组件抽取。因此该动作已从"阶段 0"移出，改为由 `styleDebtRatchet.test.js` 以天花板数值跟踪、随 D 阶段单调下降。
