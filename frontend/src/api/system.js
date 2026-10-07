import request from '@/api/request'

/* 系统状态与概览：三条端点的载荷形状抄自后端生产者，只写它**真的返回**的键。
   - `GET /system/status`   → `backend/app/api/system.py:184-220`
   - `GET /system/overview` → 同文件 `:246-280`
   - `POST /system/model-probe` → 同文件 `:223-243`
   每一键都留成可选：请求可能失败，视图从 `ref({})` 起步，读空值必须合法。 */

/** @typedef {'demo'|'live'|'misconfigured'|'unsupported'} ProviderMode */

/** 单个 provider 的运行时判定（`_provider_runtime_status`，system.py:71-100）。 */
/** @typedef {{ provider?: string, mode?: ProviderMode, configured?: boolean, model?: string }} ProviderRuntime */

/** @typedef {{ ready?: boolean, live_ready?: boolean, llm?: ProviderRuntime, embedding?: ProviderRuntime }} ModelRuntime */

/** @typedef {{ total_requests?: number, error_requests?: number, slow_requests?: number, avg_duration_ms?: number, max_duration_ms?: number, status_totals?: Record<string, number>, method_totals?: Record<string, number>, last_request_at?: string | null }} RuntimeMetrics */

/** @typedef {{ total_calls?: number, total_texts?: number, cache_hits?: number, cache_misses?: number, network_batches?: number, cache_hit_rate?: number, provider_totals?: Record<string, number>, model_totals?: Record<string, number>, last_call_at?: string | null }} EmbeddingStats */

/** @typedef {{ app_env?: string, log_level?: string, orchestration_strategy?: string, orchestration_engine?: string, orchestration_backend?: string, llm_provider?: string, embedding_provider?: string, reranker_provider?: string, demo_mode?: boolean, model_runtime?: ModelRuntime, capabilities?: Record<string, boolean>, runtime_notes?: { llm_mode?: ProviderMode, embedding_mode?: ProviderMode, orchestration_backend_note?: string, knowledge_seed_ready?: boolean, queue_health?: Record<string, any> } }} SystemStatusPayload */

/** @typedef {{ users?: number, resumes?: number, jds?: number, analysis_records?: number, interviews?: number, knowledge_documents?: number, pipeline_observability?: { total_applications?: number, version_attributed_applications?: number, feedback_recorded_applications?: number }, runtime_metrics?: RuntimeMetrics, embedding_metrics?: { current?: EmbeddingStats, daily?: EmbeddingStats[] }, operational_alerts?: { open?: number, acknowledged?: number } }} SystemOverviewPayload */

/** @typedef {{ runtime?: ModelRuntime, checks?: Record<string, Record<string, any>>, checked_at?: string }} ModelProbePayload */

// 运行时状态（所有登录用户可读；页面本身只挂在 admin 路由下）
/** @returns {Promise<SystemStatusPayload>} */
export const getSystemStatus = (config = {}) => request.get('/system/status', config)

// 项目概览指标（管理员）
/** @returns {Promise<SystemOverviewPayload>} */
export const getSystemOverview = (config = {}) => request.get('/system/overview', config)

// 模型连通性探测：一次真发 provider 请求，管理员手动点才跑
/** @returns {Promise<ModelProbePayload>} */
export const probeModelRuntime = (config = {}) => request.post('/system/model-probe', {}, config)
