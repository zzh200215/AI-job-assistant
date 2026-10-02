import request from './request'

/* 数据分析：后端 analytics.py 的两条路由都在这里，包括那条独立 admin_router 上的
   /admin/analytics/revenue（路径前缀是 /admin 而不是 /analytics，别按前缀拆成两个文件）。
   notifyError 在这三个 GET 上只有一处承重：401 时不弹"登录已过期"那条 toast
   （request.js:44,56 两处的通知分支都要求 method !== 'get'），所以逐字保留。 */

export const getAnalyticsSummary = (params = {}, config = {}) =>
  request.get('/analytics/summary', { params, ...config })

export const getAdminRevenue = (params = {}, config = {}) =>
  request.get('/admin/analytics/revenue', { params, ...config })

export const getAnalyticsFunnel = (params = {}, config = {}) =>
  request.get('/analytics/funnel', { params, ...config })
