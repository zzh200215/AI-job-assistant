# 已交付索引

> 状态：截至 **2026-11-25**。三轮计划（A–E 升级、P1–P5 专项、D1–D5 体验与演示收口）**全部交付**，在册待拍项 **open = 0**。
> 本文档只留**结论与出口**；逐条测量读数、变异证据、被推翻的旧判断在 `docs/archive/` 的两份过程账里，按需查。

---

## 1. 一句话现状

后端 **1631 tests / 0 failed**（2026-11-25 复跑，192.59s）、前端 **129 文件 / 825 条**、静态守卫 **57 条**；
首屏 **406 kB gzip**（预算 420，`tests/bundleBudget.test.mjs`）；eslint / prettier / ruff format 三条格式门全绿。
RAG / Agent / 推荐 / 解析四轨进 AI 发布门；简历与面试 P1–P5 已落地。

怎么跑、怎么部署、接口概览、项目结构见 [README](../README.md)。

---

## 2. 交付总表

### 2.1 求职侧升级（A–E，`docs/archive/upgrade-plan.md`）

| 阶段 | 内容 | 状态 | 出口 |
|---|---|---|---|
| **A** | 诚实性修复：区分真实推理与 mock/模板、统一匹配分、补最小反馈闭环 | ✅ 已交付（A1–A6） | mock 可辨识、一个 (简历,岗位) 一个权威分、负反馈生效 |
| **B1** | 行级简历改写闭环 + 改后重打分 | ✅ 已交付（B1.1–B1.4） | 一键应用 ≥5 条行级改写并看到分数变化；撤销端点与界面按钮已补 |
| **B2** | 证据锚定的职业规划（JD 库 + 薪资分位数 + 技能缺口图） | ✅ 已交付（B2.1–B2.4） | 每个分数与薪资区间可反查支撑样本 |
| **C** | 让 "Agentic RAG + 多智能体协作" 这个说法成立 | ✅ 已交付（C1–C7） | `/api/multi-agent` 返回真实消息；成本非零；编排收敛到 2 条路径且结果一致 |
| **B3** | 推荐召回升级（持久向量 / 显式降级 / 多样性 / 可见性下推） | ✅ 已交付 | 故障不再静默降级；`multi_recall` + ANN 按证据撤下（72 条活跃 JD 全量打分，重开阈值已钉成数） |
| **D** | 前端阶段 0–3（共享层 → feature 重组 → TypeScript） | ✅ 阶段 0/1/2 已交付；阶段 3 的 `unplugin` 那半**按测量撤销** | 棘轮数字单调下降；`src/components/` 长出组件层 |
| **E** | 工程债（鉴权泄露、静默失败、阻塞 I/O、schema 单一权威） | ✅ 已交付 | metrics 已鉴权；公开面变成有理由的清单；CI 基线清零 |

关键提交：A `b5461aa`…`37a1f45`；B1 `019f40c`/`5239d26`/`dfee148`/`37d5766`；B2 `d0cc34c`/`a7161de`/`eb539a6`/`a8e5e00`；
C7a `fd1272b`；B3 `5d7508a`/`999f509`；D 阶段 0 `3987eb0`、机械重组 `ac65850`、unplugin 守卫 `5ef7f68`；
企业侧出树 D137：`fa4bed1`/`e289ce8`/`03ab605`/`4a7341c`。

### 2.2 简历与面试专项（P1–P5，`docs/archive/简历与面试优化.md`）

| 期 | 内容 | 状态 | 出口 |
|---|---|---|---|
| **P1** | 地基必修：解析截断修复 + schema 校验重试 + 面试超时按题型可配 | ✅ 已交付 | 20 份真简历 20/20 首发过校验；超时 45/90/120 三档真 WS 量过 |
| **P2** | 解析质量评测：`parse_eval` 评测集 + 脚本 + CI 门 + 报表四轨同框 | ✅ 已交付 | 列表 F1 skills 0.8660 / work 1.0 / project 0.8182，门槛 0.75；parse 已进 AI 发布门 |
| **P3** | 动态面试官（LangGraph 出题决策器 + 候选池 + 针对性追问） | ✅ 已工程收口 | no-thinking 上产品路径 9/12 真组织；weak 决策均值 2164ms |
| **P4** | 弱点回流闭环 + 题库种子扩充 + 两套出题入口打通 | ✅ 已交付 | 三条回流（改写 prompt / 职业规划缺口 / 画像进新会话）齐；种子两类各 26 条入库 |
| **P5** | 体验短板收尾：断线重连 UI、报告页闭环入口、解析进度感知 | ✅ 已交付 | 断线重连 UI + 报告页入口 + 三步进度条均上屏 |

### 2.3 体验与演示收口（D1–D5，2026-11-12 → 11-14）

目标只有一句：**一条主链能当着人走完**（空库 → 演示数据 → 简历 → 匹配 → 投递 → 看板 → 面试），
以及在这个前提下把"看得见的假话、走不通的入口、手机上放不下的版式"逐条清掉。

| 期 | 内容 | 状态 | 出口 |
|---|---|---|---|
| **D1** | 六条缺陷收口：改密要校验旧密码、验证邮件/忘记口令不再 500、重置口令拆成"发信→凭 token 设新密"两步、移除"分享给 HR" | ✅ 已交付 | 改密走 `PUT /auth/me/password`；无凭证的 `POST /auth/reset-password` 出树 |
| **D2** | 首次体验一键灌演示数据；两个 seed 入口归一到一份清单 | ✅ 已交付 | 空库点一次 → 1 个求职目标 + 1 份简历 + 5 个岗位 + 5 条投递；`create_demo_user.py` 造 `demo` 账号 |
| **D3** | 错误态（**失败 ≠ 空**）：六处内联错误 + 重试；四个零入口归位；运行时双提示（示例数据 / AI 降级） | ✅ 已交付 | 失败不再只闪一个 toast；侧栏 10 项；`RuntimeBanners` 两条独立提示 |
| **D4** | 移动端逐页真量（375/768/1024）+ 看板非拖拽推进 + 阶段状态机搬到前端 | ✅ 已交付 | 11 页 × 3 档无横向溢出；菜单与拖拽发同一个 `move`；非法流转前端拦下并说中文 |
| **D5** | 六族组件样式缺失补齐（**组件能渲染但裸奔**）+ 首屏字节天花板 + lint/format 清零 | ✅ 已交付 | `<el-checkbox>`/`<el-rate>`/`<el-steps>`/`<el-button-group>`/`<el-date-picker>` 不再用浏览器默认样子；`bundleBudget` 钉住 420 kB；eslint 0 warning |
| **D6** | 真 provider 跑一轮主链（读数见 [真provider实测.md](真provider实测.md)），顺手把"后台任务空转 733 秒"的根因修掉 | ✅ 已交付 | **没有进程消费队列**这件事从此可观测 + 入口拒绝：`worker_alive` 进 `queue_health`、没活人时 `/analysis/full` 503 不发任务号、从没开始的任务在读路径收口并写清原因 |
| **D7** | 出树 `POST /analysis/match`（一次性三步、整发 500、前端从未调用），连同 `match_service.py` 与前端 `runMatch` | ✅ 已交付 | `AnalysisRecord` 只剩一个写入方（`strategies.py`），并由一条判据钉住；整条链只剩 `/analysis/full` 一条路，详见 [真provider实测.md](真provider实测.md) §7 |
| **D8** | 前端 API 层清查：**16 条**零调用导出要么接上要么删（含 D7 剩下的 15 条 + 一条 WS 助手），并立一条"不许再长出来"的守卫 | ✅ 已交付 | 死导出清零；`apiLayerNoDeadExports` 按**引用图**判（注释提到不算用），自带两条反证 + 真实树变异证据，清单见 [engineering-quality.md](engineering-quality.md) |
| **D9** | 异步任务加"排队中"态：`progress=0` 那一屏不再是一个不动的进度条 | ✅ 已交付 | `taskPhase()` 由共享轮询器递出，三个消费方各自说同一句话；"没开始就失败"由前端自己的措辞说（服务端原文不上屏）；真浏览器四条读数见 [engineering-quality.md](engineering-quality.md) |
| **D10** | 把"排队/失败要说清楚"铺到剩下两屏：分析结果页的失败留在页面上（不只 5 秒 toast），任务中心区分排队与卡住 | ✅ 已交付 | 分析结果页有行内错误 + 重新分析；任务中心排队不画 0% 进度条、失败卡片用同一句前端措辞；"未知错误"这类兜底清掉（`FAILURE_FALLBACK`） |
| **D11** | 报告类作业（简历 / 项目 / 作品集）同一句话：`pending` 不再说"正在逐节生成" | ✅ 已交付 | 三份作业共用 `taskPhase()`（它们的载荷没有 progress，"排队"就是 `pending`，判据没长出第二条）；组件级测试覆盖三个视图；**浏览器截图已补（2026-11-20）**：真实报告线程池占满时三页均显示「排队中：任务已提交…」，截图存 `backend/reports/d11_screenshots/`（gitignored） |
| **D12** | 把 [交付摘要.md](交付摘要.md) 搬进应用内：`/delivery-guide` 分「产品口径 / 工程口径」两个标签页 | ✅ 已交付 | 工程口径页是文档的第二处写法，所以配了一条 `deliveryNumbersAgree` 守卫：七个数与十一条轮次必须两边都在，改一处漏一处就红（变异证据：把页面上的 1593 改成 1594，2 条里红 1 条）；真浏览器以临时 admin 会话验收后已删账号 |
| **D13** | 让"续费那天一条命令出读数"真的成立：量测脚本自己判定这次读数能不能用 | ✅ 已交付 | 新增 `scripts/measure_verdict.py`（纯函数）+ 7 条测试：`vector_score` 全空、Arrearage、429、记录没落库、没跟到终态都会进 blockers 并把结论改成"不能用于模型质量结论"；脚本结尾直接印一段可贴进文档的结论；顺带把 `measure_real_chain.py` 补进 provider 闸的接线测试、并把中文输出钉成 UTF-8 |
| **D14** | 结果页只说"分析完成，匹配度 57"，不说这 57 是几发调用换来的 | ✅ 已交付 | `GET /analysis/{id}` 新增 `provenance`（按 `AgentTask.analysis_record_id` → `PromptTrace.task_id` 汇总，**无任务/无 trace 时是 `None`，不造全零底账**）；分数下面多一行「本次分析共 10 发模型调用 · 1 发真实模型 · 2 发兜底模型 · 7 发没成功」 |
| **D15** | 匹配分析失败时，把 provider 的异常原文当 `summary` 上屏（真浏览器验收撞见） | ✅ 已交付 | `match_analysis_agent` 的三个上屏字段改成我们自己的话，原始异常只留 `_error`；新增判据钉住"上屏字段里不许出现 HTTP 429 / LLM-Tools / 英文技术句"，变异证据：把旧写法塞回去，3 条里红 1 条 |
| **D16** | 同族扫尾：`api_error(...)` 的 message 是**唯一原样上屏**的通道，里面还有 7 条英文与 4 处异常原文 | ✅ 已交付 | 11 处改成我们自己的中文（含 `task not found` 这类会变成英文 toast 的）；新增 AST 静态判据（字面量必须含中文、f-string 不许插异常对象、`str(exc)` 只放行自有异常），变异证据：把两种坏写法塞回去，判据逐行点名；约定写进 [engineering-quality.md](engineering-quality.md) |
| **D17** | 我怀疑报告载荷带着 `stage_errors`（内含 `RuntimeError: …`）进候选人浏览器——**查完是我错**，但原有证据只覆盖简历那 5 个手写键名 | ✅ 已交付 | 三份报告改成"人的断言（`MUST_BE_HIDDEN`）↔ 代码清单（`_INTERNAL_KEYS`）"对齐判据：公开视图漏一个就红、代码清单比断言窄也红、清单里过期名字也红，外加"落库只能用 `to_public_dict()`"的静态检查；变异证据：从代码清单删掉 `stage_errors`，10 条里红 2 条 |
| **D18** | 看板终态（已入职 / 已拒绝 / 已放弃）误点一下只能删除重建，阶段历史跟着一起丢 | ✅ 已交付 | 新增 `POST /jobs/pipeline/{id}/undo-terminal`：**不是**给状态机加反向边，只退回最后一次真实转移的 `from_stage`（凭 `stage_history` 里那一步），撤销本身追加一条 `action: undo` 历史，不删旧条目；卡片菜单出现「撤销这一步（退回「X」）」；没有历史的老记录不给按钮、后端也拒绝。**在册限制里那一条随之关闭**（§3 从 13 条变 12 条） |

关键提交：D1 `3dd0d76`；D2 `d6fe3da`；D3 `5403ba4`；D4 `f8ff273`；D5 `7fed706`；D6 `c32507e`；D7 `4ad6874`；D8 `c07ad15`；D9 `c644275`；D10 `19456c9`；D11 `38cf935`；D12 `a0c8d32`；D13 `7c4d8b6`；D14 `9141a27`；D15 `9141a27`；D16 `a62bde6`；D17 `9912b45`；D18（本条）。

D5 里那条**样式缺口**值得单记一笔，因为它是"守卫只看一个方向"的典型：`elementRegistration.test.js`
一直有一条"`element.css` 不许导入没人用的样式"，于是它钉住的是**多余的**，而不是**缺的**。
结果是六个组件的样式表从头到尾没被导入过——`<el-checkbox>`（登录/注册那颗）、`<el-rate>`
（Offer 六维打分、投递反馈）、`<el-steps>`（简历上传三步）、`<el-button-group>`（看板视图切换）、
`<el-date-picker>`（面试时间）全都长成浏览器默认样子，而所有门都是绿的。补法不只是加 7 行 import，
是把判据改成**双向**：按磁盘上的真实文件（0 字节的桩豁免、样式寄居别处的走 `STYLE_ALIAS`）判"该导的导了没有"。

### 2.4 2026-11-20 收口补记

| 项 | 内容 | 状态 | 出口 |
|---|---|---|---|
| 忘记密码发信 | `forgot-password` 接上已有的 `send_password_reset_email`；配置 SMTP 时不再把重置 token 放进响应 | ✅ 已交付 | 无 SMTP 仍返回 token 供本机走通；有 SMTP 只发信 |
| 备份 / 恢复演练 | 本机备份 → 临时库恢复：56 张表清单与 `CHECKSUM TABLE` 一致；uploads / chroma 解包哈希一致 | ✅ 本机 | 顺带补 `restore.sh` 的 `--default-character-set=utf8mb4`；生产环境仍需按真实体量复跑 |
| 负载 smoke | mock 后端、只读接口：health 3000 发/50 并发 **329.8 rps**；jobs/list 1500 发/30 并发 **135.5 rps**；均 0 错 | ✅ 本机 | 不是生产容量测试 |
| 外部告警通知 | 配置 `OPERATIONS_ALERT_WEBHOOK_URL` 后，新告警落库即 POST JSON；外发失败只记日志，不影响落库 | ✅ 已交付 | 默认关闭；生产需配通道并联调 |
| 解析 PDF 夹具 | 新增 reportlab（STSong-Light）中文版式 PDF；抽取臂由 8 条变 9 条，9/9 一致 | ✅ 已交付 | 生成器见 `scripts/gen_resume_pdf_fixture.py`；`reportlab` 只进 `requirements-dev.txt`，运行测试不依赖它 |
| D11 浏览器截图 | 三份报告页在真实线程池占满时均显示「排队中：任务已提交…」 | ✅ 本机 | 截图存 `backend/reports/d11_screenshots/`（gitignored）；只补证据，未改业务代码 |
| 报告作业表主键 | 20261013/14 三条迁移漏了 `primary_key=True`，新建 MySQL 库后 `id` 非自增、插入报 1364；补幂等修复迁移 `20261120_0034` + 迁移守卫 | ✅ 已交付 | 本机已升级到 0034；临时坏表演练通过；schema 基线本身有 `PRIMARY KEY (id)`（从 ORM 渲染），旧基线测试没红，新守卫盯迁移链 |

> >15000 字符的**单份真实**简历本机仍不存在：库内最长 9,597，且是四份真文本的自拼件（`gen_parse_eval.py` 已明确把它排除出真实臂）；四份真文本最长 4,761。这一条要等一份真实长简历上传后补；合成 >15000 夹具已在截断护栏里。

本轮为 2026-11-20 工作区改动，提交 `6bfb578`。

### 2.5 2026-11-25 本地演示补记

| 项 | 内容 | 状态 | 出口 |
|---|---|---|---|
| 本地一键演示 | `scripts/local-demo.ps1`：mock + thread、demo 账号、8001/5173、`-Stop` 只停这两个端口的监听进程 | ✅ 已交付 | 启动 / 二次运行 / 停止 / 重启四态实测；README「方式三」 |
| 3 分钟分镜 | [本地演示分镜.md](本地演示分镜.md)：8 格时间轴 + 8 张 1440×900 桌面截图（已入 `docs/assets/demo/`） | ✅ 已入仓库 | 登录 → 首页 → 简历 → 结果 → 看板 → 面试设置 → Q1 → 作答 |
| 首页今日任务 500 | `utc_now()` 带 tzinfo，MySQL 读回 naive，相减抛 `TypeError`；四处统一 `utc_now_naive()`，周报 ISO 时间先归一到 naive UTC | ✅ 已修复 | `test_dashboard_today_tasks` 先红后绿；全量 1631 passed |
| SummaryAgent mock 摘要 | mock 返回字符串 `summary`，`_make_summary` 只认 dict；改为 dict/str 兼容 | ✅ 已修复 | 3 条 `test_summary_agent`；第 7 步不再 500 |

本轮为 2026-11-25 工作区改动，提交 `6bfb578`。测试读数：后端 **1631** / 前端 **825** / 守卫 **57** / ruff **498** / 首屏 **406 kB**（预算 420，Element Plus 239 kB）。

---

## 3. 仍然在册的已知限制

这些**不是欠账**，是明确拍过"不动 / 接受"的口径。每一条都配了可查的重开条件——达到条件就回来重开，不用凭感觉。

| # | 事项 | 今天的口径 | 重开条件 |
|---|---|---|---|
| 1 | 浅色作用域那一整族（tag/follow/dot/score-fill 在浅色下不达标） | 拍 ①「不动」，决定记在 D161 | 加主题开关，或往登录前四屏塞 tone 标签——`styleDebtRatchet` 的普查腿会先红 |
| 2 | 深色工作台那张 `[class*=…] !important` 通配网要不要收 | 拍「网不动，棘轮继续盯」 | 摘网实测 5 条路由出现 157 个元素实例回归；收窄需先完成组件抽取 |
| 3 | 加载态骨架屏 | 拍 ①「不动」 | 纯观感改动，无缺陷撑着；要做先定占位规范 |
| 4 | 扩副本 | 调度器那一半已上跨副本槽位，**仍被 Chroma 单进程持有拦着** | 想扩副本先解决向量库状态外置；`test_single_process_shape_is_pinned.py` 盯着 `replicas>1` |
| 5 | `recommendation_tuning` 之外，`thread` 后端仍是内存 fire-and-forget | E24 只收口 `redis_queue` | 换默认后端是部署决定，不是代码债 |
| 6 | rerank 走启发式 | 拍「不上模型、不改文案」，`rerank_source` 如实写 `heuristic` | 要上模型需先有区分度证据 |
| 7 | 投递优先级里那 8 分"城市匹配"与两种求值时机不一致 | 拍「保持现状」 | `jobRecommendPriority.test.js` 前两条记录的就是现状，改就要一起改 |
| 8 | 外部 provider 429 配额（P3.2 真追问） | 按现有样本收口；mid 侧 429 属外部配额边界。**2026-11-14 真环境实测**：主模型全程 429、embedding 账号欠费（`type: Arrearage`），主链跑不通——读数与三个产品级缺陷见 [真provider实测.md](真provider实测.md)。其中"后台任务空转 733 秒"当天查明根因（**没有进程消费队列**）并修掉：入口没活人即 503、`queue_health.worker_alive` 可观测、从没开始的任务在读路径收口（见该文档 §6） | 干净单发延迟与质量样本仍缺，配额恢复后补跑 |
| 9 | 列表视图批量栏那三颗（面试 / Offer / 标记拒绝）跨卡片聚合 | 保留"成功 X/Y"那句真话，不逐张预判合法性 | 要按卡判，需后端给出每张卡的 `allowed_transitions` |
| 10 | 首屏里最大的一块 gzip 是 Element Plus（**239 kB**，`bundleBudget` 每次构建打印的是 `vendor-element*.js`；首屏合计 406 kB） | 接受 D90 的产品决定。**2026-11-16 复查这件事值不值得动**：① 那 239 kB 是 **JS 闭包**不是样式，把样式按页懒加载对这个数一分不动；② `elementRegistration` 是双向判据（用了哪些 `<el-*>` ↔ 注册了哪些组件与样式），"有多余的"早就被它拦住了；③ 全仓用了 **54 个标签**，其中 15 个只出现在**一个文件**里（`el-date-picker` 在面试排期、`el-steps/el-step` 在简历上传、`el-container/aside/menu/…` 那一族在 `DefaultLayout`、`el-radio`、`el-button-group`、`el-checkbox-group`、`el-divider`、`el-text`），`el-rate` 两处 | 唯一能动的杠杆是**减少组件族**——每一族都只在一个屏上，换掉它就是换那个屏的交互，属于产品决定；做了决定再开一次 spike 量单族的体积 |
| 11 | 首页四颗 `ui-link` 触控高度 19px | 2.5.8 有"间距例外"，且它是全仓共用 primitive | 要改就是一次版式决定（二十屏一起动），不是单页修补 |
| 12 | 简历版本横条在 375 下溢出 27px | 设计如此：横滑轮播露半格是在说"还有更多" | 若改成折行，先定"版本 ≥3 时怎么排" |

> **2026-11-20 复核**：12 条重开条件均未被触发。对应守卫 `styleDebtRatchet` **68 条**、
> `jobRecommendPriority` **3 条**、`test_single_process_shape_is_pinned` **5 条**全绿；
> `rerank_results` 实测 `rerank_source=heuristic`；首屏实测 **406 kB / Element Plus 239 kB**
> （应用内工程口径页的 245 kB 已对齐为 239）。#3 的 `app-skeleton` 只存在于简历预览的局部占位，
> 不是新增的全局骨架屏；#8 的 embedding 探针今天仍报 Arrearage，未重开。

---

## 4. 文档导航

| 文档 | 用途 | 维护状态 |
|---|---|---|
| [README](../README.md) | 怎么跑、怎么部署、接口概览、项目结构、答辩要点 | 维护中 |
| [交付摘要.md](交付摘要.md) | **给外部读者的一页**：D1–D18 改了什么、凭什么说改对了、还差什么（不承载新事实，事实以本文档与 engineering-quality 为准） | 维护中 |
| [演示脚本.md](演示脚本.md) | 三分钟主链怎么演、被追问时哪四句话有测试撑着、哪些地方别点 | 维护中 |
| [本地演示分镜.md](本地演示分镜.md) | 2026-11-25 本地一键演示的 8 格分镜与口播（mock + thread） | 维护中 |
| [真provider实测.md](真provider实测.md) | 真 provider 跑主链的读数（耗时 / 谁答的 / token / 有没有落库）、三个产品级缺陷、"空转 733 秒"的根因与复验、重跑条件 | 2026-11-14 实测 + 当天修完缺陷 2；重跑后更新 |
| [engineering-quality.md](engineering-quality.md) | 工程标准与判据（测试纪律、守卫清单） | **维护中** |
| [setup-and-security.md](setup-and-security.md) | 环境配置与安全口径 | 维护中 |
| [面试消息协议.md](面试消息协议.md) | 面试 WS 消息协议 | 维护中 |
| [resume-report-spec.md](resume-report-spec.md) / [project-report-spec.md](project-report-spec.md) / [portfolio-report-spec.md](portfolio-report-spec.md) | 三类报告的规格与七维表 | 维护中 |
| [schema-baseline.sql](schema-baseline.sql) | 数据库 schema 快照（`test_schema_baseline` 与真库比对） | 随迁移重生成 |
| [knowledge-seeds/](knowledge-seeds/) | 知识库种子（可由 `import_knowledge.py` 重灌） | 维护中 |
| [api-examples/](api-examples/) | 外部能力 API 对接示例 | 维护中 |
| [archive/](archive/) | **历史过程账，只读**：`upgrade-plan.md`（A–E）、`简历与面试优化.md`（P1–P5） | 归档，不再续写 |

---

## 5. 怎么查历史

过程账按 `D<n>`（升级账）与 `P<n>.<m>`（专项账）编号，每一条都带**提交号 + 现场读数 + 变异证据**。

- 查某个提交为什么改：`git show <sha>`，再在 `docs/archive/` 里搜那个 sha；
- 查某条判据的出处：在 `docs/archive/` 里搜 `D<编号>`；
- **注意**：过程账里大量句子是**当时的读数**，有些已经被后续测量推翻（文中用 ~~删除线~~ 或"作废/翻案"标注）。**不要直接引用数字当现状**——现状以代码、测试与本文档 §1 的四把尺为准。
