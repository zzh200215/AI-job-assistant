import request from './request'

export const getEvalReportSummary = (params = {}) =>
  request.get('/eval-reports/summary', { params })

export const getEvalReportList = (params = {}) =>
  request.get('/eval-reports/list', { params })

export const getEvalReportDetail = (reportId) =>
  request.get(`/eval-reports/${reportId}`)

export const compareEvalReports = (params) =>
  request.get('/eval-reports/compare', { params })
