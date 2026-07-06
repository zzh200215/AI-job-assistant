import request from './request'

export const startAgentAnalysis = (data) =>
  request.post('/agent/start', data)

export const getAgentTask = (taskId) =>
  request.get(`/agent/task/${taskId}`)

export const getAgentSteps = (taskId) =>
  request.get(`/agent/task/${taskId}/steps`)

export const getAgentTasks = (params = {}) =>
  request.get('/agent/tasks', { params })

export const getAgentTaskSummary = () =>
  request.get('/agent/tasks/summary')

export const cancelAgentTask = (taskId) =>
  request.post(`/agent/task/${taskId}/cancel`)

export const retryAgentTask = (taskId) =>
  request.post(`/agent/task/${taskId}/retry`)
