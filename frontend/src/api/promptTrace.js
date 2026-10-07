import request from './request'

/* 提示溯源：四条端点的载荷形状抄自后端生产者，只写它**真的返回**的键。
   - `GET /prompt-traces/summary` → `backend/app/api/prompt_trace.py:107-168`
     （聚合数字来自同文件 `_metrics_from_rows`，分组来自 `_build_group_item`）
   - 其余三条沿用原样：调用方读的是列表字段与任意明细，没有稳定形状可抄。 */

/** @typedef {{ total?: number, success_count?: number, failed_count?: number, success_rate?: number, cache_hit_count?: number, cache_hit_rate?: number, degraded_count?: number, degraded_rate?: number, degraded_by_source?: Record<string, number>, avg_duration_ms?: number | null, avg_prompt_chars?: number | null, avg_total_tokens?: number | null, avg_cost_cents?: number | null, first_seen?: string | null, last_seen?: string | null }} PromptTraceMetrics */

/** @typedef {{ prompt_version?: string, source?: string, total?: number, success_count?: number, last_seen?: string | null, [k: string]: any }} PromptTraceGroup */

/** @typedef {PromptTraceMetrics & { sources?: string[], versions?: string[], models?: string[], response_sources?: string[], source_groups?: PromptTraceGroup[], version_groups?: PromptTraceGroup[] }} PromptTraceSummaryPayload */

/** @returns {Promise<PromptTraceSummaryPayload>} */
export const getPromptTraceSummary = (params = {}) =>
  request.get('/prompt-traces/summary', { params })

export const getPromptTraceList = (params = {}) => request.get('/prompt-traces/list', { params })

export const getPromptTraceDetail = (traceId) => request.get(`/prompt-traces/${traceId}`)

export const comparePromptTraceVersions = (params) =>
  request.get('/prompt-traces/compare', { params })
