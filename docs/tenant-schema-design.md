# 租户表结构设计（T2-1 租户需求细化）

> 版本：v1.1（定稿）
> 日期：2026-08-01
> 对应任务：产品化需求文档 T2-1「租户需求细化（表设计评审）」
> 前置：T1-2（数据模型基线已冻结）
> 状态：✅ 已定稿（2026-08-01 经产品化负责人确认，评审记录见 §7）

---

## 1. 核心决策：Organization = Tenant（单一租户概念，不新建平行 tenant 表）

### 1.1 现状盘点

代码库已存在一套「组织工作区」租户雏形（迁移 0013~0016、org workspace 前端已上线）：

| 已有资产 | 位置 | 说明 |
| --- | --- | --- |
| `organization` 表 | `backend/app/models/organization.py` | id / name / slug(unique) / owner_id / status / sso_provider / created_at |
| `organization_membership` | 同上 | org 成员 N:M（role: owner/admin/member） |
| `organization_sso_identity` / `_state` | 同上 | 飞书 SSO 身份绑定与授权状态 |
| `tb_user.active_organization_id` | `backend/app/models/user.py` | 用户当前工作区 |
| `kb_document.organization_id` | `backend/app/models/knowledge.py` | 知识库按 org 隔离 |
| 组织 API | `backend/app/api/organization.py` | 创建/切换/成员/飞书 SSO；`get_active_organization` 依赖（`X-Organization-Id` 头或 `active_organization_id`） |
| 前端组织工作区 | `frontend/src/views/OrganizationWorkspace.vue`、`src/api/organization.js` | 工作区 UI 已存在 |

`docs/schema-baseline.md` §3 已将 4 张 organization 系列表标记为「与租户模型关系待评审（T2-1）」——本设计即该评审结论。

### 1.2 决策结论

**演化 `organization` 为租户核心表**，不新增平行的 `tenant` 表。多租户的 `tenant_id` 即 `organization.id`。

理由：

1. **语义自然**：SaaS 客户即用人单位/组织，一个客户 = 一个 organization，命名自洽；
2. **复用已投资**：组织工作区、成员角色、飞书 SSO、知识库 org 隔离全部继续生效，无需另起炉灶或双写；
3. **避免双外键混乱**：若另建 `tenant` 表，业务表会出现 `tenant_id` + `organization.tenant_id` 两套维度，迁移、回填、查询过滤都要处理一致性，与「第二个客户 80% 配置化」目标无增量收益；
4. **降低 M2 风险**：M2 里程碑（双租户 Demo）要求品牌/域名/隔离，核心能力是把 `organization` 表加字段 + 新增两张附属表，改动面可控。

> 若评审认为必须保留「SaaS 账号」与「工作区」两层概念（未来一个客户可能开多个工作区），替代方案 B 见 §9——本期不推荐，避免过度设计。

---

## 2. 隔离策略（T2-1 步骤 1）

| 维度 | 决策 | 说明 |
| --- | --- | --- |
| 默认模式 | **共享库 + 共享表 + 行级 `tenant_id`** | 绝大多数客户适用，运营成本最低 |
| 高安全客户 | **独立 schema（同实例独立 database）** | `organization.isolation_mode` 标记（`shared`/`schema`）；本期只落定字段与开关，**不实现切库**（T2-4 高级项） |
| 数据访问 | 统一封装 `tenant_filter(model)`（T2-3 实现） | 业务代码**禁止**散写 `tenant_id` 判断 |

隔离原则：**逻辑隔离是默认且唯一的实现路径**，schema 级隔离作为可扩展选项保留字段位。

---

## 3. 表设计

### 3.1 `organization`（租户核心，改造现有表）

现有列保持不动（id / name / slug / owner_id / status / sso_provider / created_at），新增列：

| 列 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `industry` | VARCHAR(50) | NULL | 行业 |
| `logo_url` | VARCHAR(500) | NULL | 品牌 logo |
| `primary_color` | VARCHAR(20) | NULL | 品牌主色 `#RRGGBB` |
| `plan_tier` | VARCHAR(20) | `free` | 套餐：`free`/`pro`/`enterprise`（复用 `SubscriptionTier`） |
| `admin_user_id` | BIGINT | NULL | 租户管理员；创建时回填 `owner_id` |
| `expires_at` | DATETIME | NULL | 订阅到期；过期 → status=`expired`（T4-3 定时任务） |
| `isolation_mode` | VARCHAR(20) | `shared` | `shared`/`schema` |

`status` 枚举扩展：`active` / `suspended` / `expired`（列已存在，仅扩展语义）。

**索引**：

| 索引 | 列 | 用途 |
| --- | --- | --- |
| `uq_organization_slug`（已有） | slug | 唯一标识 |
| `ix_organization_owner_id`（已有） | owner_id | |
| `ix_organization_plan_tier`（新增） | plan_tier | 套餐筛选/报表 |
| `ix_organization_status`（新增） | status | 租户列表/筛选 |
| `ix_organization_expires_at`（新增） | expires_at | T4-3 到期扫描 |

> 关于需求文档 T2-1 字段清单中的 `domain`：**不冗余到 `organization` 列**，域名关系由 `tenant_domain_bindings` 单一维护（见 §3.3），避免双写不一致。`slug` 承担「主展示标识」职能。

### 3.2 `tenant_configs`（新增，KV 配置）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK auto | |
| `tenant_id` | BIGINT NOT NULL | 归属租户（= `organization.id`） |
| `config_key` | VARCHAR(50) NOT NULL | 配置键，如 `brand.favicon` / `brand.login_bg` / `brand.company` / `brand.contact` / `feature.xxx` / `price.xxx` |
| `config_value` | JSON NOT NULL | 配置值 |
| `created_at` | DATETIME | `utc_now` |
| `updated_at` | DATETIME | onupdate |

约束与索引：

```sql
UNIQUE KEY uq_tenant_configs_key (tenant_id, config_key),
INDEX ix_tenant_configs_tenant_id (tenant_id)
```

用途（对应 T2-5 品牌配置 + T3 配置外置化）：文案、功能开关、价格覆盖等 KV；**核心品牌字段**（name / logo / primary_color）作为列落在 `organization`，其余增强品牌项（favicon / login_bg / company / contact）放本表 KV。

### 3.3 `tenant_domain_bindings`（新增，域名 ↔ 租户）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT PK auto | |
| `tenant_id` | BIGINT NOT NULL | 归属租户（= `organization.id`） |
| `domain` | VARCHAR(255) NOT NULL | 域名（主域、www、子域、自定义域） |
| `is_primary` | INTEGER default 0 | 是否主域名（每个租户至多一个） |
| `status` | VARCHAR(20) default `active` | `active`/`inactive`（环境切换用） |
| `created_at` | DATETIME | `utc_now` |

约束与索引：

```sql
UNIQUE KEY uq_tenant_domain (domain),
INDEX ix_tenant_domain_bindings_tenant_id (tenant_id)
```

域名解析（T2-3 `resolve_tenant_by_host`）查本表；支持一个租户多域名（主域名 + 演示/别名域名），满足双租户 Demo 的「两域名」验收。

---

## 4. 外键策略

- **不加 DB 级 FOREIGN KEY**，沿用项目现有惯例（现有 organization 系列表均无 FK；`tb_user.active_organization_id` 亦无 FK）。
- 理由：多租户迁移/回填/切库时避免 FK 校验阻塞；一致性由应用层事务 + T2-3 统一过滤保证。
- `tenant_configs` / `tenant_domain_bindings` 的 `tenant_id` 同样不加 FK。
- 删除租户是「停用」（status=expired/suspended）而非物理删除（T4-1），无级联删除需求。

---

## 5. 与现有表衔接（重点：tenant_id 语义）

| 关注点 | 决策 |
| --- | --- |
| 业务表 `tenant_id` 命名 | T2-4 统一在业务表加 **`tenant_id`** 列，值引用 `organization.id`；不叫 `organization_id`，保持与需求文档口径一致，由 T2-3 `tenant_filter` 统一注入 |
| 用户与租户的关系 | `tb_user.tenant_id` = 用户账号归属租户（注册/被创建时所在租户；存量个人用户回填到内置租户 1）。注意用户可加入多组织（`organization_membership` N:M），因此**业务数据行的 `tenant_id` ≠ 用户账号 `tenant_id`**：数据行取「写入时上下文当前租户」（active_organization / `X-Organization-Id`），用户账号归属用于用户管理与配额 |
| 内置默认租户 | 约定 **`organization.id = 1`** 为「平台默认/公共租户」：存量数据、平台级数据、个人用户归属它 |
| 现有 `active_organization_id` | 即「当前租户」，T2-3 的 `get_current_tenant()` 演进自 `get_active_organization` 依赖 |
| `kb_document.organization_id` | 即租户隔离（RAG 按租户过滤，T3-3）；若统一命名，T3-3 可重命名为 `tenant_id`，本轮不动以免扩散 |

---

## 6. 迁移计划（对应 T2-2 落地）

**迁移 `20260801_0017_tenant_schema.py`**（命名 `YYYYMMDD_NNNN_描述.py`，必须带 downgrade）：

1. `organization` 增加 `industry` / `logo_url` / `primary_color` / `plan_tier` / `admin_user_id` / `expires_at` / `isolation_mode` 列（`has_column` 幂等守卫）；
2. 新建 `tenant_configs`、`tenant_domain_bindings` 表（`has_table` 幂等守卫，沿用 0007/0011 模式）；
3. 创建索引：`organization(plan_tier)`、`organization(status)`、`organization(expires_at)`；
4. 回填：`UPDATE organization SET admin_user_id = owner_id, plan_tier = 'free', isolation_mode = 'shared'`（缺省值兜底）；
5. downgrade：删列/删表/删索引，可逆。

**模型层（T2-2）**：新增 `backend/app/models/tenant.py`（`TenantConfig`、`TenantDomainBinding` 两个模型），在 `models/__init__.py` 注册；扩展 `Organization` 模型字段。

**CI 双重把关**：`alembic check` + `export_schema_baseline.py --check`（模型与迁移/快照一致性）。

---

## 7. 评审清单（已确认）

> 评审结论：**7/7 通过**。确认人：产品化负责人（经授权，2026-08-01）。以下为决策留痕。

1. ☑ **核心决策**：认可「organization = 租户」（演化现表），不新建独立 `tenant` 表。
2. ☑ **业务表命名**：T2-4 业务表统一加 `tenant_id`（值=organization.id）。
3. ☑ **域名策略**：`tenant_domain_bindings` 多域名（主域名+别名），不冗余 `domain` 列到 organization。
4. ☑ **内置租户**：约定 `organization.id=1` 为平台默认租户。
5. ☑ **FK 策略**：全部不加 DB 级外键。
6. ☑ **用户归属**：`tb_user.tenant_id`（账号归属）与业务行 `tenant_id`（数据归属）分离的语义。
7. ☑ **隔离模式**：本期只落 `isolation_mode` 字段、不实现 schema 级切库。

> T2-1 已定稿；本设计作为 T2-2~T2-5、T3-1~T3-3 的表结构依据，进入 T2-2 开发。

---

## 8. 关联任务落点

| 任务 | 与本设计的关系 |
| --- | --- |
| T2-2 新增租户模型 | `tenant.py`（TenantConfig / TenantDomainBinding）+ Organization 扩展 + 迁移 0017 |
| T2-3 租户上下文中间件 | `tenant_context.py`：`get_current_tenant`（演进自 `get_active_organization`）、`resolve_tenant_by_host`（查 tenant_domain_bindings）、`tenant_filter(model)` |
| T2-4 业务表 tenant_id | 按 §5 语义迁移 + 回填内置租户 1 + 跨租户测试 |
| T2-5 品牌配置 | organization 列 + tenant_configs KV |
| T3-1 套餐按租户覆盖 | `subscription_plan.tenant_id` 扩展（可空=平台默认） |
| T4-3 计费自动化 | 定时任务扫描 `organization.expires_at` |

---

## 9. 替代方案 B（评审备选，本期不推荐）

新建独立 `tenant` 表（按需求文档 T2-1 字段清单原样）：id / name / industry / logo_url / primary_color / domain / plan_tier / status / admin_user_id / created_at / expires_at，另加 `tenant_configs`、`tenant_domain_bindings`；`organization` 增加 `tenant_id` 外键。

**不推荐理由**：与已有 organization 工作区/SSO/知识库隔离重复造轮子，产生 `tenant_id` + `organization_id` 两套隔离维度；T2-4 数据迁移需先建 tenant 再映射 organization，工作量大且双份状态（organization.status 与 tenant.status）易漂移。除非未来明确出现「一个客户多个独立工作区且各自计费」的强需求，否则不采用。
