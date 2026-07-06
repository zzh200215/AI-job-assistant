import request from './request'

export const getPromptTraceSummary = (params = {}) =>
  request.get('/prompt-traces/summary', { params })

export const getPromptTraceList = (params = {}) =>
  request.get('/prompt-traces/list', { params })

export const getPromptTraceDetail = (traceId) =>
  request.get(`/prompt-traces/${traceId}`)

export const comparePromptTraceVersions = (params) =>
  request.get('/prompt-traces/compare', { params })
