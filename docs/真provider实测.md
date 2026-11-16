# 真 provider 主链实测（2026-11-14）

> **结论先说**：今天**跑不通一条完整的真推理主链**。卡在两处外部依赖——LLM 主模型全程 429、
> embedding 账号欠费——而这两处故障顺手照出了三个**产品级**缺陷（§3）。
> 下面每个数字都是本机跑出来的：`prompt_trace` 读数 + 真浏览器/HTTP 端到端，没有估算。
>
> 复跑工具：`backend/scripts/measure_real_chain.py`（要显式 `--allow-real` 才会真的花钱，见 `scripts/provider_guard.py`）。

---

## 1. 当时用的是谁

| 项 | 值 |
|---|---|
| LLM provider | `openai` 兼容端（SenseNova）`https://token.sensenova.cn/v1` |
| 主模型 | `deepseek-v4-flash` |
| 兜底模型 | `glm-5.2` |
| LLM 超时 / 输出上限 | 120 s / 16,384 tokens |
| Embedding | `qwen` · `text-embedding-v3` · `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 被测对象 | demo 账号（`demo`）、简历 #83（林知遥）、JD #23674（AI 大模型算法工程师/阿里巴巴） |

---

## 2. 读数

### 2.1 LLM：主模型全程 429，兜底模型能答

一次最小探针（68 prompt / 254 completion tokens）：

```
PROBE OK in 9.14 s
provenance = {"source": "fallback_model", "degraded": true,
              "reason": "主模型调用失败…primary: …HTTP 429", "attempts": ["…HTTP 429"]}
```

跑了两轮主链（中间隔 150 秒，让限流窗口过去），主模型**每一发都是 429**（内部重试 2 次后换兜底）。
兜底 `glm-5.2` 能正常作答，真实调用读数：

| trace | 步骤 | 来源 | 耗时 | prompt/completion | 结果 |
|---|---|---|---|---|---|
| #2480 | analysis/match | `real` | 10,517 ms | 993 / 455 | 成功 |
| #2481 | analysis/optimize | `fallback_model` | 39,682 ms | 952 / 3,788 | 成功 |
| #2484 | analysis/optimize（第二轮） | **`real`** | 43,300 ms | 1,033 / 4,304 | 成功 |
| #2479 | chat_json（匹配那一步） | `fallback_model` | **118,790 ms** | 488 / **16,384（打满上限）** | 失败：输出被截断 |
| #2482 / #2485 | analysis/interview | — | 10,501 / 10,567 ms | 0 / 0 | 失败：两侧都 429 |

两条值得记住的事实：

1. **兜底模型的输出会长到撞上限**：一发 JSON 用掉 16,384 个 completion token 还被截断。产品判成失败是对的
   （`LLM 输出被截断 (finish_reason=length, completion_tokens=16384…)`），但这一发既花了 118 秒也花了满额 token。
2. **同一个步骤的耗时分布**：10.5 s（真模型、短输出）→ 39.7 s / 43.3 s（优化建议，长输出）。不是"模型很慢"，
   是"输出越长越慢"，而 429 的重试会把每一次都再推高几秒到几分钟。

### 2.2 Embedding：账号欠费，向量通道整条下线

直接打 `POST /embeddings` 的原始响应：

```json
{"error": {"message": "Access denied, please make sure your account is in good standing…",
           "type": "Arrearage", "code": "Arrearage"}}
```

产品侧把这件事**如实写进了日志**（每一条都能在 `backend` 的运行日志里查到）：

```
[Embedding] 调用失败将重试(1/2)/(2/2): Embedding API 调用失败(HTTP 400)
job_embedding_service: embedding failed for 5 postings, vector channel degraded
job_recommend_engine: resume embedding failed for resume=83, ranking on rules
recommend embedding work for resume=83: scanned=5 reused=0 embedded=0 failed=5
```

`ranking on rules` 这句是关键：**推荐分不是模型算的**，是规则臂算的。这条降级路径本身是设计好的
（B3 阶段"显式降级"），今天正好被真环境走了一遍。

### 2.3 主链三步的端到端

| 步骤 | 端点 | 结果 | 用户等多久 |
|---|---|---|---|
| 智能分析（前端真正打的那个） | `POST /analysis/full` | 0.05 s 返回 `task_id`，**任务 733 秒没有推进** | 屏幕会一直转（progress 0%） |
| 智能分析（一次性三步） | `POST /analysis/match` | **500**（两轮都是） | 221.3 s / 115.8 s |
| 岗位推荐 | `GET /jobs/recommend` | 200，5 个岗位 | 首轮 10.7 s（embedding 重试），之后 0.03 s（缓存） |
| 面试建会话 | `POST /interview/sessions` | 200，`total_questions=10` | 0.04 s（题目在后台生成，那一发同样 429） |

第一行（后台任务空转）当天就查明根因并修掉了，见 **§6**——根因不是"缺一个超时"，是**没有进程在消费队列**。

`/analysis/match` 的 500 原文（产品自己的话，不是我把异常吞了）：

```
分析失败: AI 调用失败，fallback 链路均未成功:
  primary: … HTTP 429 | fallback_model: … HTTP 429
```

### 2.4 分数分布：57 / 40 / 33 / 33 / 26

这个分布和 **mock 时代逐字相同**——因为 §2.2 里 embedding 挂了，排序走的是规则臂，与模型无关。
换句话说：**这一栏今天不能拿来说明"真推理的效果"**。要拿它说明效果，得先把 embedding 账号续上，
再回答一次"同一个 (简历, 岗位)，向量臂和规则臂的分数差多少"。

### 2.5 花了多少

| 项 | prompt | completion |
|---|---|---|
| 本次全部调用（探针 + 两轮主链 + 建会话） | **3,534** | **25,185** |

其中 16,384 是一个被截断的兜底输出吃掉的。价目表里没有这两个型号，所以 `cost_cents` 恒 0——**不代表没花钱**。

### 2.6 产品自己的仪表亮了

跑完之后 `/api/system/status`：`runtime_notes.ai_degraded_recent = true`（窗口 30 分钟）。
也就是说 D3 那条「AI 服务降级中」的横幅，此刻在候选人的屏幕上**是真的会出现的**——
这是它第一次被真 provider 的故障点亮，而不是靠插一条假 trace 验的。

---

## 3. 被照出来的三个产品级缺陷

| # | 缺陷 | 今天的表现 | 为什么算缺陷 |
|---|---|---|---|
| 1 | `/analysis/match` 是**一次性三步**：任一步失败，整发 500，前两步的真实产出直接丢掉 | 两轮都是先成功 2 步、第 3 步（面试题）429 → 500，`analysis_record` 一条没落地 | trace 里明明有成功的匹配与优化结果（#2480/#2481/#2484），用户手里什么都没有 |
| 2 | `/analysis/full` 的后台任务**既不失败也不超时** | 733 秒、`progress_percent=0`、`step_counts.total=0`、`current_step=None`、**0 条 trace** | 依赖全挂时它不知道该收场，屏幕上就是一个永不结束的转圈 |
| 3 | 前端 `runMatch` 定义了但**无人调用** | `src/api/analysis.js:31` 只有定义，`SmartAnalysis` / `careerPlanning` 打的都是 `/full` | 公开面里挂着一颗没有用户、也没有兜底的按钮/接口；真要有人调它，就是缺陷 1 |

> 缺陷 2 当天修掉并复验，见 §6（根因不是"缺超时"：**根本没有进程在消费队列**，而且系统里没有一个数能看出这件事）。
> 缺陷 1 + 3 也在同一天收口：**那个接口整条出树**，见 §7。

---

## 4. 修复建议（按性价比）

1. **给后台任务加总超时与失败收敛**（缺陷 2）。目标：3 分钟内明确失败并说明"卡住的是哪一步、为什么"，
   而不是让 `progress=0` 无限转。这一条最值：它把"不知道发生了什么"变成"知道发生了什么"。
   **→ 当天已按更准的根因修掉，见 §6。**
2. **`/analysis/match` 分步返回，或直接下线**（缺陷 1 + 3）。前端既然不用它，先下线最省；
   要留就得分步返回（匹配 / 优化 / 面试题各自成功各自落库）。
   **→ 当天选了"下线"，见 §7。**
3. **embedding 欠费是账号问题，不是代码问题**：续费或换 key 之后，本节 §2.2 / §2.4 必须重跑——
   在没有向量的情况下，任何"推荐质量"的结论都不成立。

---

## 5. 重跑条件

| 条件 | 怎么确认 |
|---|---|
| 主模型配额恢复（或兜底稳定） | 探针一发：`provenance.source` 是 `real` 且 `degraded=false` |
| embedding 账号正常 | 一条命令（打的是 provider，不是我们的 API）：`python -c "from app.services.embedding_service import embed_text; print(len(embed_text('探针')))"` —— 打出向量维度就是好了；打 `Embedding API 调用失败(HTTP 400)；响应体：{"error": {…"type": "Arrearage"…}}` 就是还欠着 |
| 依赖都绿之后 | `python scripts/measure_real_chain.py --allow-real`（会花钱，会写 `prompt_trace`） |

重跑时要一起记的四个数：**每步耗时、`response_source`、prompt/completion tokens、以及"这一步有没有落库"**。
前三个是性能，第四个是"用户到底拿到了什么"——今天恰恰是第四个先坏的。

> 2026-11-14 晚补的一句：`embed_text` 现在会把**响应体**带进异常信息（以前只有一句
> `400 Client Error: Bad Request`，于是"欠费"被读成"接口挂了"）。上面那条探针的实际输出是
> `{"error": {"message": "Access denied, please make sure your account is in good standing…",
> "type": "Arrearage"}}`——这就是 §2 里那个判断的来源。

脚本结尾现在会自己印一段结论，直接抄进本文档即可：

```
========== 结论（可直接贴进 docs/真provider实测.md） ==========
[analysis] partial · 6/7 步（失败 1） · 记录已落库
[arms]     3 条推荐：0 条带向量分 · 3 条只有规则分 · 方法 rubric_6dim_v2
[traces]   real 0 · fallback 3 · 失败 4
[blockers] 3/3 条推荐没有向量分（vector_score 为空）——分数只来自规则臂，不能当模型效果读；embedding 账号欠费（Arrearage）；模型侧限流（429）
[verdict]  链路跑通，产出已落库；不能用于模型质量结论
```

那段结论由 `backend/scripts/measure_verdict.py` 算（纯函数，`tests/test_measure_verdict.py` 钉着）。
它存在的理由写在那个模块的注释里：**2026-11-14 那次的分数是 57/40/33，排序看着合理，实际上
`vector_score` 全空**——如果只看"分数非空"，这在任何一版读数里都挑不出来。

### 5.1 彩排（2026-11-14 晚，脚本 v2）

修完两处超时之后按"续费那天"的姿势真跑了一遍（`--allow-real --poll-seconds 600 --step-timeout 90`）。
**它不是质量读数**（embedding 仍欠费），但它证明了一件事：这条命令现在能在十分钟内自己给出结论，
不用人去翻 JSON：

```
[analysis] completed · 7/7 步（失败 0） · 记录已落库
[arms]     5 条推荐：0 条带向量分 · 5 条只有规则分 · 方法 rubric_6dim_v2
[traces]   real 1 · fallback 1 · 失败 4
[blockers] 5/5 条推荐没有向量分（vector_score 为空）——分数只来自规则臂，不能当模型效果读
[verdict]  链路跑通，产出已落库；不能用于模型质量结论
```

三点值得记：

1. **这一发链路是 `completed`**（7/7，220.9 秒），而 §2 那一次是 `partial`：差别在兜底模型
   （`glm-5.2`）这次答上来了（trace `src=fallback_model`，44 秒）。429 仍占 4/7 条调用——
   "能跑完"与"配额够"是两件事。
2. **`blockers` 里没有出现 Arrearage 字样**，但结论照样拦住了：判据读的是 `vector_score` 为空，
   不是错误串。这一条正好说明为什么不能把"错误串匹配"当主证据。
3. 彩排还撞出两个真问题并已修掉：轮询窗口原来默认 180 秒（那条链要跑 220 秒以上，会把 `running`
   当成终态写进结论）；`/jobs/recommend` 在 embedding 欠费时曾挂十几分钟（现在单发接口各自
   `--step-timeout`，超时会被记成一条读数而不是让脚本卡死）。

### 5.2 结果页自己会说"这 57 是怎么来的"（2026-11-16）

彩排那批记录留在库里，正好拿来看屏幕：打开 `/analysis/85`，匹配度下面多了一行

> 本次分析共 10 发模型调用 · 1 发真实模型 · 2 发兜底模型 · 7 发没成功；没成功的那几处由兜底规则
> 补出，相关小节可能不如平时准确。

数字来自 `GET /analysis/{id}` 新增的 `provenance`：后端按 `AgentTask.analysis_record_id` 找到任务、
再按 `PromptTrace.task_id` 汇总——这两列本来就在库里，只是没人把它们接起来。

同一屏还**抓出一处泄漏**：那句话上面写的是

```
analysis unavailable: [LLM-Tools] 调用失败（已重试 2 次）: AI 接口调用失败(HTTP 429)，请稍后重试
```

也就是 `match_analysis_agent` 在失败分支把 provider 的异常原文塞进了 `summary`，而 `summary`
是直接渲染的。已改成我们自己的话，原始异常只留 `_error`；判据见
`tests/test_match_agent_user_facing_copy.py`（变异：把旧写法塞回去，3 条里红 1 条）。
**注意**：库里 2026-11-14 之前写下的老记录仍然带着旧文案——它记的是当时真实发生的失败，
不清洗历史数据。

---

## 6. 当天修掉的缺陷 2：根本原因不是"缺一个超时"

排查的第一个发现把 §3 那张表的前提推翻了：**733 秒里没有任何进程在消费队列**。

```
$ python -c "…health_snapshot()…"
backend=redis_queue  queue_length=2  processing_length=0  dead_letter=0
$ redis> LRANGE analysis-tasks 0 -1
{"v":1,"attempts":0,"payload":{"strategy_name":"linear","task_id":98,…}}   ← 今天这一发
{"v":1,"attempts":0,"payload":{"strategy_name":"linear","task_id":1, …}}   ← 6 月留下的化石
```

`.env` 写的是 `ORCHESTRATION_BACKEND=redis_queue`，而机器上没有 worker 进程；
`submit` 只是往 list 里 `LPUSH` 一行，接口立刻回"已启动"。加一个超时也救不了它——
超时只能让转圈提前结束，说不了"为什么"。

### 6.1 五处改动

| 原来的形状 | 现在的形状 |
|---|---|
| 队列有没有活人，**看不出来**（`ok` / 长度 / 死信三个数都正常） | worker 写心跳（`analysis-tasks:worker-heartbeat`，TTL 90 s，每 30 s 一刷），`queue_health` 多两列：`worker_alive` / `worker_last_seen_seconds` |
| 没有消费者时照样收单：200 + `task_id` | 收单前先问一句，`worker_alive=false` → **503**，**不落任务行**、不发任务号 |
| 从没开始的任务**没有任何活动行**，`mark_stale_running_tasks_failed`（30 分钟、按"最后一次活动"判）永远抓不到它 | 读任务状态那一跳收口：`排队 ≥ ORCHESTRATION_START_TIMEOUT_MINUTES(2)` + 没有步骤行 + **确认没有活着的消费者** → `failed`，原因写进 `error_msg` |
| 运维告警只认"连不上 / 积压阈值 / 死信" | 新增 `orchestration_queue_no_worker`（critical）——判据是 `worker_alive is False`，`thread` 后端的 `None`（不适用）不会误报 |
| 关键步骤失败只写一句"关键步骤执行失败" | 写成 `IntentAgent 执行失败: <原因>`（分层策略一直是这个形状，线性这条漏了） |

第二条判据（"确认没有活着的消费者"）不能省：worker 活着时，一条排队中的任务只是排在别人后面；
判死会在几分钟后与真正的完成撞车——任务被标 `failed`，随后又落了一条 `AnalysisRecord`。

### 6.2 复验读数（同一天，本机真栈）

| 检查 | 结果 |
|---|---|
| **没有 worker** 时 `POST /analysis/full` | **503**，`code=-4`，message 开头是"分析服务暂不可用：后台任务队列没有 worker 在消费…"；库里 `max(agent_task.id)` **不变**（98） |
| 起 worker 后 `/system/status` | `worker_alive: true`、`worker_last_seen_seconds: 6.2` |
| 起 worker 后 `POST /analysis/full` | 200 + `task_id=100`；第 1 条步骤（`intent_recognition` running）在 **22 秒**后出现——这 22 秒它排在 task 99 后面，不是空转 |
| task 100 全程 | 7 个步骤全部跑过，17:50:34 → 17:55:11（**4 分 37 秒**）收口成 `failed`，`error_msg` 带步骤名 |
| worker **活着**时读一条"排队 6 分钟、零步骤"的任务（直接插库造的现场） | **保持 running**——判据不误伤排队中的任务 |
| 停 worker、删心跳键后**同一跳** | `failed`，`error_msg` = "排队 2 分钟仍未开始执行：任务队列里没有活着的 worker（心跳键不存在，当前 0 条任务在等它）。任务没有跑过，按未启动收口" |

task 100 仍然是 `failed`：主模型全程 429，`ResumeOptimizeAgent` 那一步把重试打满。
**但这一次是"有原因的失败"，不是"没有尽头的等待"**——差别就是这一节的全部内容。

### 6.3 代价与残余

- `redis_queue` 的部署从此**必须**同时起 worker：`python -m scripts.run_orchestration_worker`。
  升级顺序上要先升 worker 再升 web（旧 worker 不写心跳，会被判成"没人消费"——方向是对的，
  窗口只有 worker 启动后的一两秒）。README 的本地开发块、`backend/.env.example`、
  `docs/演示脚本.md` 的"开演前 60 秒"都已补上这一条。
- `thread` 后端不受影响：消费者就是本进程，`worker_alive` 为 `None`（不适用），守门与收口都不生效。
  它那条"任务投进本地线程池、进程一死没人捡"的老口径没变（见 `delivery-index.md` §3 第 5 条）。
- 现场的队首化石（6 月那条 `task_id=1`）已清掉；`task_id=98` 由 worker 正常消费（它的策略入口看到
  `cancelled` 就地收口，没有发一次模型调用）。

**屏幕侧**：守门之后多了一个"任务在、但一步都没跑"的状态，而它以前长得和一个卡住的 0% 一模一样。
D9 给它补了说法（排队中说"等后台接单"、没开始就失败说"后台没有可用的 worker"），
见 [engineering-quality.md](engineering-quality.md) 的 "Async tasks have a queued phase"。

---

## 7. 当天出树：`POST /analysis/match`（缺陷 1 + 3）

### 7.1 为什么是删，不是修

按 §4 的第 2 条，两条路：分步返回，或者直接下线。选下线，因为它三条指标同时指向同一个结论：

| 判据 | 读数 |
|---|---|
| 有没有用户 | **没有**。前端唯一的调用方 `runMatch`（`src/api/analysis.js:31`）全树无人 import；两个分析页打的都是 `/analysis/full` |
| 有没有替代 | 有，而且更好：`/analysis/full` 是异步任务，**每步落 `agent_step_log`、失败不丢已完成步骤、进度可轮询** |
| 失败形状好不好 | 不好，而且是最坏的那种：串行三步，第 3 步炸了整发 500、`analysis_record` 一行不落——用户等 221 秒，拿到一条空 |

留着一个没人用、一用就丢活的同步入口，不是在"保留能力"，是在等下一次有人点它。

### 7.2 删了什么

| 位置 | 内容 |
|---|---|
| `app/api/analysis.py` | `POST /match` 整个端点（45 行），`MatchReq` / `match_service` 两个 import |
| `app/services/match_service.py` | **整份文件**（192 行）：`run_full_analysis` 串行调 3 个 prompt、拼 RAG、写 `AnalysisRecord` |
| `app/schemas/analysis.py` + `schemas/__init__.py` | `MatchReq` 模型与它的导出 |
| `frontend/src/api/analysis.js` | `runMatch`（4 行，含注释） |
| 测试 | `test_service_access_guards.py` 里只针对 `match_service` 的 2 条 |

**没删的**：库里已有的历史行，以及回算脚本对那批行的认法（`AUTHORITY_MARKER_KEYS` 继续认
`match_score_method`，因为旧键已经落在行里）。`scripts/score_backfill_radius.py` 的 docstring 与
`tests/test_score_backfill_radius.py` 的说明改成过去时。

### 7.3 顺带把判据收紧成"只有一个写入方"

删掉 `match_service` 之后有两件事必须重新表态，否则门会变成空的：

1. `test_match_score_single_source.py` 原来钉的是"**两条**落库路径用同一组键名"，判据里写着
   `sorted(written[key]) == ["match_service.py", "strategies.py"]`。改成单写入方的版本——
   词表外的键名照样红，但要求变成 `== ["strategies.py"]`，反证（把 `score_method` 改回历史那个
   旧拼法）打在 `strategies.py` 的副本上。**门没有退化成"没人写就不算分叉"。**
2. 新增 `test_analysis_record_has_exactly_one_writer`：全树扫 `= AnalysisRecord(`，只许命中
   `strategies.py`。这条不是洁癖——它是上面那条词表判据的前提：一旦出现第二个写入方，
   你就得**重新证明**两份词表一致，而不能靠"本来就只有一条"。

### 7.4 门

> 下面这四个数是**当次提交**（D7）的门，不是今天的；今天的读数见 [交付摘要.md](交付摘要.md) §三。

后端 **1593 passed / 0 failed**（删 2 条 `match_service` 用例、加 1 条单写入方判据）；
前端 **120 文件 / 790 条**、静态守卫 **55 条** 全绿（`runMatch` 无任何测试引用）；
`ruff check` 与 `ruff format --check` 全绿。

### 7.5 一个顺手量出来的欠账（D8 当天已清）

清 `runMatch` 时把 `src/api/` 下所有导出扫了一遍：**还有 15 个导出无人 import**
（`getSubscriptionPlans`、`checkQuota`、`getMyOrders`、`startMultiAgent`、`getMultiAgentRun`、
`seedDemoResumes`、`fetchJobDetail`、`getKnowledgeDoc`、`getQuestionCategories`、`getInterviewPrep`、
`deleteInterview`、`getNextActions`、`getAccessibleResumeList`、`getTargetDetail`、`getPipelineDetail`）。

当天就做完了清查（D8）：**16 条**（多出来那条是 `interview.isWSConnected`，没有任何调用方）全部删除，
后端端点一个没动，并立了 `apiLayerNoDeadExports` 守卫。逐条理由与守卫设计见
[engineering-quality.md](engineering-quality.md) 的 "Frontend API layer has no dead exports"。
