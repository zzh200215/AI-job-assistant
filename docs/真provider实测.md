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

---

## 4. 修复建议（按性价比）

1. **给后台任务加总超时与失败收敛**（缺陷 2）。目标：3 分钟内明确失败并说明"卡住的是哪一步、为什么"，
   而不是让 `progress=0` 无限转。这一条最值：它把"不知道发生了什么"变成"知道发生了什么"。
2. **`/analysis/match` 分步返回，或直接下线**（缺陷 1 + 3）。前端既然不用它，先下线最省；
   要留就得分步返回（匹配 / 优化 / 面试题各自成功各自落库）。
3. **embedding 欠费是账号问题，不是代码问题**：续费或换 key 之后，本节 §2.2 / §2.4 必须重跑——
   在没有向量的情况下，任何"推荐质量"的结论都不成立。

---

## 5. 重跑条件

| 条件 | 怎么确认 |
|---|---|
| 主模型配额恢复（或兜底稳定） | 探针一发：`provenance.source` 是 `real` 且 `degraded=false` |
| embedding 账号正常 | `POST /embeddings` 不再返回 `type: Arrearage` |
| 依赖都绿之后 | `python scripts/measure_real_chain.py --allow-real`（会花钱，会写 `prompt_trace`） |

重跑时要一起记的四个数：**每步耗时、`response_source`、prompt/completion tokens、以及"这一步有没有落库"**。
前三个是性能，第四个是"用户到底拿到了什么"——今天恰恰是第四个先坏的。
