import request from './request'

/* 数据分析：后端 analytics.py 的三条读侧都在这里，包括那条独立 admin_router 上的
   /admin/analytics/revenue（路径前缀是 /admin 而不是 /analytics，别按前缀拆成两个文件）。
   notifyError 在这三个 GET 上只有一处承重：401 时不弹"登录已过期"那条 toast
   （request.js:44,56 两处的通知分支都要求 method !== 'get'），所以逐字保留。

   形状抄自后端生产者，只写它**真的返回**的键：`app/services/analytics_service.py`
   （`get_summary_metrics` / `get_conversion_funnel` / `get_revenue_summary`）。
   2026-10-06 真删企业侧第六增量（D136/D137）之后：`tenant_id` 回声键与收入那格的
   `items`（按租户分组）已经不存在了，收入换成按套餐的 `by_tier`。 */

/** @typedef {{ total_users?: number, total_resumes?: number, total_analyses?: number, total_interviews?: number, pro_users?: number, paid_orders?: number }} AnalyticsSummaryPayload */

/** @typedef {{ key?: string, label?: string, count?: number, rate?: number }} AnalyticsFunnelStep */

/** @typedef {{ total_users?: number, period_days?: number, steps?: AnalyticsFunnelStep[] }} AnalyticsFunnelPayload */

/** @typedef {{ total_amount?: number, order_count?: number, by_tier?: Record<string, number> }} AnalyticsRevenuePayload */

/** @returns {Promise<AnalyticsSummaryPayload>} */
export const getAnalyticsSummary = (params = {}, config = {}) =>
  request.get('/analytics/summary', { params, ...config })

/** @returns {Promise<AnalyticsRevenuePayload>} */
export const getAdminRevenue = (params = {}, config = {}) =>
  request.get('/admin/analytics/revenue', { params, ...config })

/** @returns {Promise<AnalyticsFunnelPayload>} */
export const getAnalyticsFunnel = (params = {}, config = {}) =>
  request.get('/analytics/funnel', { params, ...config })
