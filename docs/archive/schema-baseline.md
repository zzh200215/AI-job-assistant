# 数据库 Schema 基线（T1-2 冻结数据模型基线）

> 对应任务：《产品化需求文档》M1-T1-2
> 状态：✅ 基线已冻结（2026-07）
> 基线快照：`docs/schema-baseline.sql`（由 ORM 模型离线编译，MySQL 8.0 方言）

---

## 1. 基线用途

- **多租户改造的迁移起点**（M2）：所有 `tenant_id` 改造基于本清单逐表推进；
- **CI 漂移检测**：任何表结构变更若未同步快照，CI 立即失败；
- **变更纪律**：从本基线起，表结构变更一律走 Alembic 迁移（`backend/migrations/versions/`），**禁止**手改表或依赖 `AUTO_CREATE_TABLES` 直接建表（T1-3 正式收口）。

## 2. 生成与校验方法

```bash
cd backend
.venv/Scripts/python.exe scripts/export_schema_baseline.py            # 重新生成 docs/schema-baseline.sql
.venv/Scripts/python.exe scripts/export_schema_baseline.py --check    # CI 漂移检测（不一致退出码 1）
```

- 生成方式：`Base.metadata` → SQLAlchemy MySQL 方言离线编译，**不连接数据库**；
- 稳定性：`CREATE TABLE` 按外键依赖排序，`CREATE INDEX` 统一排序，重复生成结果一致（已验证）。

## 3. ORM 模型表清单（39 张）

> 数据量：本地 `llmXM` 库（127.0.0.1:3306）`information_schema.table_rows` 估算值，2026-07 采集；生产环境数据量需在部署后重新核对。

| # | 表名 | 模块 | 用途 | 数据量（估） | 多租户改造建议（T2-4 参考） |
| --- | --- | --- | --- | --- | --- |
| 1 | `tb_user` | 用户 | 用户账号、求职意向、偏好与隐私设置 | 9 | 首批加 `tenant_id` |
| 2 | `tb_resume` | 简历 | 简历原件信息与解析结果 | 19 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 3 | `tb_jd` | 岗位 | 岗位 JD 录入与解析结果 | 71 | ✅ 已接入 `tenant_id`（T3-3，迁移 0021，NULL=平台共享岗位） |
| 4 | `tb_analysis_record` | 智能分析 | 匹配度分析记录（报告/建议/面试题 JSON） | 33 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 5 | `resume_version` | 简历 | 简历版本（原始/优化/ATS 快照） | 15 | 首批加 `tenant_id` |
| 6 | `agent_task` | 多智能体 | Agent 任务（意图、计划、状态） | 57 | 首批加 `tenant_id` |
| 7 | `agent_run` | 多智能体 | Agent 运行批次（编排方式、汇总报告） | 2 | 首批加 `tenant_id` |
| 8 | `agent_step_log` | 多智能体 | Agent 步骤日志（可追溯） | 467 | 首批加 `tenant_id` |
| 9 | `retrieval_log` | RAG | 检索日志（Query Rewrite/召回/重排） | 24 | 首批加 `tenant_id` |
| 10 | `self_check_log` | AI 治理 | 质量自检日志 | 15 | 首批加 `tenant_id` |
| 11 | `agent_message` | 多智能体 | Agent 间消息 | 6 | 首批加 `tenant_id` |
| 12 | `agent_result` | 多智能体 | Agent 产出结果 | 6 | 首批加 `tenant_id` |
| 13 | `interview_session` | 模拟面试 | 面试会话（题目、状态、报告） | 14 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 14 | `interview_question` | 模拟面试 | 面试题生成记录 | 0 | 首批加 `tenant_id` |
| 15 | `interview_turn_evaluation` | 模拟面试 | 逐题评估 | 0 | 首批加 `tenant_id` |
| 16 | `job_application_pipeline` | 求职流程 | 投递/Offer 流程管线 | 2 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 17 | `job_recommend_feedback` | 岗位推荐 | 推荐反馈（like/dislike） | 0 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 18 | `job_bookmark` | 岗位推荐 | 岗位收藏 | 0 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 19 | `job_journal` | 求职流程 | 求职周报/复盘 | 0 | 首批加 `tenant_id` |
| 20 | `job_target` | 求职流程 | 求职目标 | 0 | 首批加 `tenant_id` |
| 21 | `kb_document` | 知识库 | 知识文档（上传、切片、向量检索） | 28 | ✅ 已接入 `tenant_id`（T3-3，迁移 0021，RAG 按租户隔离） |
| 22 | `prompt_trace` | LLMOps | Prompt 版本与 Trace 回放 | 266 | 首批加 `tenant_id` |
| 23 | `ai_release` | AI 治理 | AI 发布候选与评测门禁 | 0 | 平台级，可暂不加 |
| 24 | `audit_log` | 安全合规 | 审计日志 | 0 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 25 | `embedding_usage_daily` | 成本归因 | Embedding 用量日汇总 | 21 | 平台级，可暂不加 |
| 26 | `operational_alert` | 运行治理 | 运行告警 | 1 | 平台级，可暂不加 |
| 27 | `notification` | 通知 | 站内通知 | 0 | 首批加 `tenant_id` |
| 28 | `organization` | 组织协作 | 租户核心表（组织工作区） | 0 | 已定稿：organization 即租户，T2-2 扩字段（见 `docs/tenant-schema-design.md`） |
| 29 | `organization_membership` | 组织协作 | 租户成员与角色 | 0 | 已定稿：organization 即租户（见 `docs/tenant-schema-design.md`） |
| 30 | `organization_sso_identity` | 组织协作 | 飞书 SSO 身份绑定 | 0 | 已定稿：organization 即租户（见 `docs/tenant-schema-design.md`） |
| 31 | `organization_sso_state` | 组织协作 | 飞书 SSO 授权状态 | 0 | 已定稿：organization 即租户（见 `docs/tenant-schema-design.md`） |
| 32 | `subscription_plan` | 订阅 | 套餐定义 | 0 | T3-1 扩展 `tenant_id`（可空=平台默认） |
| 33 | `user_subscription` | 订阅 | 用户订阅权益 | 0 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 34 | `subscription_order` | 订阅 | 订阅订单 | 0 | ✅ 已接入 `tenant_id`（T2-4 首批，迁移 0018） |
| 35 | `tenant_configs` | 租户 | 租户 KV 配置（品牌增强/功能开关/价格覆盖） | 0 | T2-2 新增（见 `docs/tenant-schema-design.md`） |
| 36 | `tenant_domain_bindings` | 租户 | 域名 ↔ 租户绑定 | 0 | T2-2 新增（见 `docs/tenant-schema-design.md`） |
| 37 | `interview_question_bank` | 面试配置 | 租户题型题库（type/prompt_template/静态题） | 0 | T3-2 新增（迁移 0020，tenant_id NULL=平台默认） |
| 38 | `interview_scoring_rule` | 面试配置 | 租户评分规则（dimension/weight） | 0 | T3-2 新增（迁移 0020，tenant_id NULL=平台默认） |
| 39 | `interview_report_template` | 面试配置 | 租户报告模板 | 0 | T3-2 新增（迁移 0020，tenant_id NULL=平台默认） |

## 4. 非 ORM 遗留表（5 张，不在模型层管理）

| 表名 | 说明 | 处置建议 |
| --- | --- | --- |
| `alembic_version` | Alembic 迁移版本记录（自动维护） | ✅ 保留 |
| `candidate_screening_session` | 企业筛选会话（后端 `app/` 已无引用） | ⚠️ 待确认是否死表，确认后走迁移删除 |
| `job_data_source` | 岗位数据源管理（后端 `app/` 已无引用） | ⚠️ 待确认是否死表，确认后走迁移删除 |
| `job_import_batch` | 岗位导入批次（后端 `app/` 已无引用） | ⚠️ 待确认是否死表，确认后走迁移删除 |
| `job_sync_log` | 数据源同步日志（后端 `app/` 已无引用） | ⚠️ 待确认是否死表，确认后走迁移删除 |

> 说明：以上 4 张表已无后端模型与服务引用（`grep backend/app` 无命中），推测为早期版本遗留。**不要手删**——确认后走 Alembic 迁移（T1-3 规范），避免影响多租户改造盘点。

## 5. 基线变更纪律（T1-2/T1-3）

1. 修改模型 → 2. 新增 Alembic 迁移脚本（`YYYYMMDD_描述.py`，必须带 downgrade）→ 3. 重新生成快照 → 4. 一并提交；
2. 未同步快照的模型改动，CI 漂移检查（`export_schema_baseline.py --check`）将失败；
3. 存量表结构手工变更（含遗留表删除）一律先评审。

## 6. 团队确认记录

> 确认结论：**已确认（2026-08-01，经产品化负责人授权确认）**。T1-2 验收通过。

| 项目 | 内容 |
| --- | --- |
| 表清单（34 张 ORM 表 + 5 张遗留表）核对 | ☑ 已核对，无遗漏（34 张 ORM 表 + `alembic_version` 等 5 张遗留表） |
| 基线快照 `docs/schema-baseline.sql` | ☑ 已确认与模型层一致（`export_schema_baseline.py --check` OK；CI 持续把关） |
| 遗留表处置意见 | ☑ 已确认：§4 中 4 张死表走 Alembic 迁移删除（列入后续任务，不在 T1-2 范围） |
| 确认人 / 日期 | 产品化负责人 / 2026-08-01 |

**验收对照**：快照文件存在 ✅；CI 漂移检测已配置 ✅（见 `.github/workflows/ci.yml`）；表清单已确认勾选 → **T1-2 完成**。

> 补充记录（2026-08-01）：T2-2 新增 `tenant_configs` / `tenant_domain_bindings` 两张表、`organization` 扩租户字段（迁移 `20260801_0017`），基线由 34 张演进为 **36 张**；快照已按 T1-3 规范重新生成并提交。

> 补充记录（2026-08-01）：T2-4 首批 9 张核心业务表（`tb_resume`/`tb_analysis_record`/`interview_session`/`job_application_pipeline`/`job_recommend_feedback`/`job_bookmark`/`subscription_order`/`user_subscription`/`audit_log`）接入租户隔离：新增 `tenant_id`（默认内置租户 1）+ 复合索引 `(tenant_id, user_id)`（迁移 `20260801_0018`，存量回填 `tenant_id=1`）。查询/写入经 `tenant_context.tenant_filter` / `stamp_tenant` 统一过滤；`tracking_events` 为 spec 规划表，代码库不存在，未纳入本批。

> 补充记录（2026-08-01）：T3-3 岗位库与知识库接入租户隔离：`tb_jd`（复合索引 `(tenant_id, is_active)`）、`kb_document`（索引 `tenant_id`）新增 `tenant_id`（**NULL=平台共享**，非空=归属租户/组织；迁移 `20260801_0021`，存量回填：用户数据→默认租户 1、组织文档→对应组织、平台文档保持 NULL）。推荐引擎/岗位检索/详情访问与 RAG 可见性按「本人 + 当前租户 + 平台共享」过滤；管理端新增 `POST /admin/tenants/{id}/jobs`（批量导入岗位）与 `POST /admin/tenants/{id}/knowledge`（上传知识文档）。T3-2 新增 3 张面试配置表后基线由 36 张演进为 **39 张**。
