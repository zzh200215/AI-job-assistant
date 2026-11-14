import request from './request'

// 智能调度：自然语言需求驱动，自动决定调用哪些智能体
export const startAutoAgent = (data) => request.post('/multi-agent/auto', data)

// 查询完整详情（含消息+结果）
export const getMultiAgentDetail = (runId) => request.get(`/multi-agent/run/${runId}/detail`)
