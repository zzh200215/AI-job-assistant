# 外部能力 API 对接文档（M6 / T6-3）

> 版本：v1.0
> 日期：2026-08-01
> 面向：第三方开发者（人才服务商 / 渠道 / 集成方）
> 说明：本文档描述能力 API 的鉴权、请求/响应、错误码与 Webhook 事件。定价见 `docs/定价表.md` §7。

---

## 1. 概览

| 项 | 值 |
| --- | --- |
| Base URL | `https://<api-domain>/api/v1/external` |
| 鉴权 | 请求头 `X-API-Key: sk-...`（平台签发，明文仅创建时返回一次） |
| 协议 | HTTPS + JSON（UTF-8） |
| 限流 | 每 Key 每日调用上限（默认 1000 次，可配置），超额返回 429 |
| 幂等 | 请求体可携带 `request_id`，响应原样回显，便于追踪 |

能力端点（X-API-Key 鉴权）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/resume/parse` | 简历解析（文本或 base64 文件） |
| POST | `/match/evaluate` | 简历 × JD 匹配评估 |
| POST | `/interview/simulate` | 模拟面试（生成题 + 可选逐题评分） |

---

## 2. 鉴权

每个请求携带：

```
X-API-Key: sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

无 Key / Key 无效 → **401**；已停用 / 已过期 → **403**；当日额度用尽 → **429**。

> 示例代码：`docs/api-examples/python_client.py`、`docs/api-examples/node_client.js`。

---

## 3. 简历解析

**`POST /resume/parse`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `content` | string | 二选一 | 简历纯文本 |
| `file_base64` | string | 二选一 | 简历文件（PDF/DOCX/TXT/MD）base64 编码 |
| `filename` | string | 选填 | 配合 `file_base64`，用于识别格式 |
| `request_id` | string | 选填 | 调用方追踪 ID |

请求示例：

```json
{
  "content": "张三，5 年后端开发经验，精通 Python / Django / MySQL，主导过电商订单系统重构",
  "request_id": "req-20260801-001"
}
```

响应示例：

```json
{
  "success": true,
  "data": {
    "name": "张三",
    "contact": {"phone": "", "email": ""},
    "skills": ["Python", "Django", "MySQL"],
    "experience": [{"company": "", "title": "后端开发", "years": "5"}],
    "education": []
  },
  "request_id": "req-20260801-001"
}
```

> 结构化字段以模型返回为准；解析失败返回 `{"success": false, "error": "..."}`，不计费。

---

## 4. 匹配评估

**`POST /match/evaluate`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `resume` | object 或 string | 是 | 简历结构化 JSON 或文本 |
| `jd` | object 或 string | 是 | 岗位 JD 结构化 JSON 或文本 |
| `use_rag` | bool | 否 | 是否走租户知识库 RAG 检索（默认 false） |
| `request_id` | string | 否 | 追踪 ID |

请求示例：

```json
{
  "resume": {"name": "张三", "skills": ["Python", "MySQL"], "years_exp": 5},
  "jd": {"title": "资深后端工程师", "required_skills": ["Python", "Django", "Redis"]},
  "request_id": "req-20260801-002"
}
```

响应示例：

```json
{
  "success": true,
  "data": {
    "match_score": 82,
    "matched": ["Python"],
    "missing": ["Django", "Redis"],
    "summary": "整体匹配度良好，技能面覆盖核心要求，缺 Redis 与 Django 深度经验",
    "suggestions": ["补充 Redis 缓存实战项目", "突出系统设计能力"]
  }
}
```

---

## 5. 模拟面试（简化版）

**`POST /interview/simulate`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `resume` | object 或 string | 是 | 简历 |
| `jd` | object 或 string | 是 | 岗位 JD |
| `answers` | array | 否 | 逐题回答 `[{question, answer, ref_answer?}]`，提供则返回逐题评分 |

请求示例：

```json
{
  "resume": {"name": "张三", "skills": ["Python"]},
  "jd": {"title": "后端工程师"},
  "answers": [
    {"question": "请简述 Python 中 GIL 的作用", "answer": "GIL 使同一时刻仅一个线程执行字节码，影响多线程 CPU 密集场景"}
  ]
}
```

响应示例：

```json
{
  "success": true,
  "data": {
    "questions": [...],
    "evaluations": [
      {
        "question": "请简述 Python 中 GIL 的作用",
        "evaluation": {"overall_score": 78, "accuracy": 85, "feedback": "回答准确但深度不足", "improvement": "补充 GIL 对 IO/CPU 场景的对比"}
      }
    ]
  }
}
```

---

## 6. 错误码表

| HTTP | code | 说明 | 处理建议 |
| --- | --- | --- | --- |
| 401 | — | 缺少 / 无效 X-API-Key | 检查 Key 是否正确签发 |
| 403 | — | Key 已停用 / 已过期 | 联系平台续期或重新签发 |
| 429 | — | 当日调用额度用尽 | 次日重试或升级配额 |
| 400 | — | 参数缺失 / 格式错误 | 按请求字段表修正 |
| 500 | — | 服务端处理失败 | 携带 `request_id` 联系平台 |

业务错误体（HTTP 200 但 `success=false`）：

```json
{"success": false, "error": "content 不能为空"}
```

> 业务失败不消耗额度、不计费。

---

## 7. Webhook 事件回调

平台在操作完成后向订阅 URL 异步推送事件。投递失败自动重试 3 次（0.5s/1s/2s 退避）。

### 7.1 订阅（管理端）

**`POST /api/v1/admin/external/webhooks`**（Bearer 平台管理员 Token）

```json
{
  "api_key_id": 1,
  "event": "resume.parsed",
  "url": "https://customer.example.com/hooks/resume",
  "secret": "your-webhook-secret"
}
```

支持事件：

| 事件 | 触发时机 |
| --- | --- |
| `resume.parsed` | 简历解析成功 |
| `match.evaluated` | 匹配评估成功 |
| `interview.completed` | 模拟面试完成 |

### 7.2 推送格式

**`POST <订阅 URL>`**，头：

```
X-Webhook-Event: resume.parsed
X-Webhook-Signature: <HMAC-SHA256(secret, raw_body) hex>
Content-Type: application/json
```

Body：

```json
{
  "event": "resume.parsed",
  "data": { "name": "张三", "skills": ["Python"] }
}
```

### 7.3 签名校验（订阅方）

```python
import hashlib, hmac
def verify(secret, raw_body, signature):
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

> 订阅方校验签名后应尽快返回 2xx；返回非 2xx 会触发平台重试。

---

## 8. 计费与账单（管理端）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/admin/external/api-keys` | 创建 Key（返回明文一次） |
| GET | `/api/v1/admin/external/api-keys` | Key 列表 |
| POST | `/api/v1/admin/external/api-keys/{id}/revoke` | 吊销 Key |
| POST | `/api/v1/admin/external/billing/run` | 手动触发某月结算 |
| GET | `/api/v1/admin/external/billing/bills` | 账单列表 |
| GET | `/api/v1/admin/external/billing/bills/{id}/export` | 导出账单 CSV |

计费规则：按端点单价 × 成功次数聚合（`resume.parse` ¥0.30/次、`match.evaluate` ¥0.30/次、`interview.simulate` ¥0.80/次），每月生成账单。

---

## 9. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-08-01 | 初版：鉴权 + 3 能力端点 + Webhook + 计费 |
