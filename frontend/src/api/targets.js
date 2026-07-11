import request from './request'

// 求职目标
export const getTargets = (params = {}) =>
  request.get('/targets/list', { params })

export const getTargetDetail = (id) =>
  request.get(`/targets/${id}`)

export const createTarget = (data) =>
  request.post('/targets', data)

export const updateTarget = (id, data) =>
  request.put(`/targets/${id}`, data)

export const deleteTarget = (id) =>
  request.delete(`/targets/${id}`)

export const setPrimaryTarget = (id) =>
  request.post(`/targets/${id}/set-primary`)

// 投递看板
export const getKanban = (params = {}) =>
  request.get('/jobs/pipeline/kanban', { params })

export const movePipelineStage = (id, stage, data = {}) =>
  request.post(`/jobs/pipeline/${id}/transition`, { stage, ...data })

export const getPipelineDetail = (id) =>
  request.get(`/jobs/pipeline/${id}`)

export const createJobPipelineEntry = (data) =>
  request.post('/jobs/pipeline', data)

export const deleteJobPipelineEntry = (entryId) =>
  request.delete(`/jobs/pipeline/${entryId}`)
