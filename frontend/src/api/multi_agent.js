import request from './request'

// 智能调度：自然语言需求驱动，自动决定调用哪些智能体
export const startAutoAgent = (data) => request.post('/multi-agent/auto', data)

// 启动多智能体分析（全量流程，需手动指定 ID）
export const startMultiAgent = (data) => request.post('/multi-agent/start', data)

// 查询运行状态
export const getMultiAgentRun = (runId) => request.get(`/multi-agent/run/${runId}`)

// 查询完整详情（含消息+结果）
export const getMultiAgentDetail = (runId) => request.get(`/multi-agent/run/${runId}/detail`)
