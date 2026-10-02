import request from './request'

/**
 * `summary` 里那批指标。它们**同时**可能出现在顶层——`Home.vue` 与 `Profile.vue` 都写着
 * `data.summary || data`，那是两代响应留下的形状，不是笔误。所以这一份既挂在 `summary` 上，
 * 也并进顶层的形状里，让那句回退在类型层成立。
 * @typedef {Object} DashboardMetrics
 * @property {number} [total_applications]
 * @property {number} [active_applications]
 * @property {number} [upcoming_interviews]
 * @property {number} [pending_offers]
 * @property {number} [total_resumes]
 * @property {number} [total_interviews]
 * @property {number} [bookmarked_jobs]
 * @property {number} [unread_notifications]
 * @property {number|null} [avg_match_score]
 */

/**
 * `GET /dashboard/overview` 的载荷，字段抄自 `backend/app/api/dashboard.py:134-158`。
 * 抄本只写后端**真的返回**的键：`Profile.vue:494-499` 读的 `total_sessions` / `sessions` /
 * `resume_count` / `best_score` / `max_score` / `days_active` / `created_at` 一个都不在这里，
 * 所以那几条现在会红——那是报告，不是新坏的代码（见 docs/upgrade-plan.md §10.25）。
 * @typedef {DashboardMetrics & {
 *   user?: { id?: number, username?: string, nickname?: string, avatar_url?: string, job_seeking_status?: string },
 *   summary?: DashboardMetrics,
 *   weekly_new?: number,
 *   monthly_new?: number,
 *   trend?: { date?: string, count?: number }[],
 *   stage_counts?: Record<string, number>,
 *   funnel?: { todo?: number, applied?: number, written_test?: number, interview?: number, offer?: number },
 *   recent_activities?: Record<string, any>[],
 * }} DashboardOverview
 */

// 仪表盘总览
/** @returns {Promise<DashboardOverview>} */
export const getDashboardOverview = () => request.get('/dashboard/overview')

// 今日待办
export const getTodayTasks = () => request.get('/dashboard/today-tasks')

// 下一步建议（后端为确定性规则，非 LLM）
export const getNextActions = () => request.get('/dashboard/next-actions')

// 求职周报
export const getWeeklyReport = () => request.get('/dashboard/weekly-report')
