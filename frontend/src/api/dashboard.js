import request from './request'

// 仪表盘总览
export const getDashboardOverview = () => request.get('/dashboard/overview')

// 今日待办
export const getTodayTasks = () => request.get('/dashboard/today-tasks')

// 下一步建议（后端为确定性规则，非 LLM）
export const getNextActions = () => request.get('/dashboard/next-actions')

// 求职周报
export const getWeeklyReport = () => request.get('/dashboard/weekly-report')
