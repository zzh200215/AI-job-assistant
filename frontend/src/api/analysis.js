import request from './request'

/**
 * 一键智能分析（统一编排 Agent 工作流）
 * POST /api/analysis/full
 */
export const runFullAnalysis = (data) => request.post('/analysis/full', data)

/**
 * 获取单条分析详情
 * GET /api/analysis/:id
 */
export const getAnalysis = (id) => request.get(`/analysis/${id}`)

/**
 * 重新生成简历优化建议
 * POST /api/analysis/:id/optimize/regenerate
 */
export const regenOptimize = (id) => request.post(`/analysis/${id}/optimize/regenerate`)

/**
 * 重新生成面试题
 * POST /api/analysis/:id/interview/regenerate
 */
export const regenInterview = (id) => request.post(`/analysis/${id}/interview/regenerate`)

/**
 * 一键分析（旧接口，直接调用 LLM 匹配）
 * POST /api/analysis/match
 */
export const runMatch = (data) => request.post('/analysis/match', data)

/**
 * 获取分析引用的知识库来源
 * GET /api/analysis/:id/references
 */
export const getAnalysisReferences = (id) => request.get(`/analysis/${id}/references`)

/**
 * 匹配度深度解释
 * POST /api/analysis/explain-match
 */
export const explainMatch = (data) => request.post('/analysis/explain-match', data)
