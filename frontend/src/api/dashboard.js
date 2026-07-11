import request from './request'

// 仪表盘总览
export const getDashboardOverview = () =>
  request.get('/dashboard/overview')

// 今日待办
export const getTodayTasks = () =>
  request.get('/dashboard/today-tasks')

// AI下一步建议
export const getAiSuggestions = () =>
  request.get('/dashboard/ai-suggestions')

// 求职周报
export const getWeeklyReport = () =>
  request.get('/dashboard/weekly-report')
