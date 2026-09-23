// 岗位推荐 API
import request from './request'

// 获取岗位推荐
export const getJobRecommendations = (params) => request.get('/jobs/recommend', { params })

// 写入模拟数据
export const seedMockJobs = () => request.post('/jobs/seed')

// 批量导入 JD
export const batchImportJobs = (file, source = 'imported') => {
  const form = new FormData()
  form.append('file', file)
  form.append('source', source)
  return request.post('/jobs/batch-import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 提交推荐反馈
export const submitJobFeedback = (resumeId, jdId, feedbackType, matchScore) =>
  request.post('/jobs/feedback', null, {
    params: {
      resume_id: resumeId,
      jd_id: jdId,
      feedback_type: feedbackType,
      match_score: matchScore,
    },
  })

// 推荐反馈汇总
export const getJobFeedbackStats = () => request.get('/jobs/feedback/stats')

export const getJobFeedbackEvaluation = () => request.get('/jobs/feedback/evaluation')

export const getJobTuningSamples = (params = {}) =>
  request.get('/jobs/feedback/tuning-samples', { params })

export const exportJobTuningSamples = (params = {}) =>
  request.get('/jobs/feedback/tuning-export', { params, responseType: 'blob' })

export const getJobRecommendConfig = () => request.get('/jobs/recommend-config')

export const updateJobRecommendConfig = (data) => request.put('/jobs/recommend-config', data)

export const resetJobRecommendConfig = () => request.post('/jobs/recommend-config/reset')

export const compareJobRecommendConfig = (data) =>
  request.post('/jobs/recommend-config/compare', data)

// 获取 JD 列表
export const getJobList = (params = {}) => request.get('/jobs/list', { params })

// 获取 JD 详情
export const getJobDetail = (jdId) => request.get(`/jobs/${jdId}`)

// === 投递流程 ===

// 获取投递流程列表
export const getJobPipelineList = (params = {}) => request.get('/jobs/pipeline/list', { params })

// 创建投递流程记录
export const createJobPipelineEntry = (data) => request.post('/jobs/pipeline', data)

// 更新投递流程记录
export const updateJobPipelineEntry = (entryId, data) =>
  request.put(`/jobs/pipeline/${entryId}`, data)

// 删除投递流程记录
export const deleteJobPipelineEntry = (entryId) => request.delete(`/jobs/pipeline/${entryId}`)

// 清理已淘汰记录
export const clearRejectedJobPipeline = () => request.delete('/jobs/pipeline/terminal')

// 发起完整分析（复用已有接口）
export const bookmarkJob = (jdId, action = 'bookmark') =>
  request.post('/jobs/bookmarks', { jd_id: jdId, action })

export const unbookmarkJob = (jdId) => request.delete(`/jobs/bookmarks/${jdId}`)

// 被推荐引擎隐藏的职位（不感兴趣 + 点踩），用于"恢复"入口
export const getSuppressedJobs = () => request.get('/jobs/bookmarks/dismissed')

export const getJobBookmarks = (pageSize = 100) =>
  request.get('/jobs/bookmarks/list', { params: { page: 1, page_size: pageSize } })

// 一次调用清掉所有隐藏信号，避免出现"已恢复但仍不出现"的假成功
export const restoreSuppressedJob = (jdId) =>
  request.post('/jobs/bookmarks/restore', { jd_id: jdId })

export const startFullAnalysis = (resumeId, jdId) =>
  request.post('/analysis/full', { resume_id: resumeId, jd_id: jdId })

// === 岗位搜索 ===

// 搜索外部岗位
export const searchExternalJobs = (params) =>
  request.post('/jobs/search-external', null, { params })

// 抓取岗位详情
export const fetchJobDetail = (source, url) =>
  request.post('/jobs/fetch-detail', null, { params: { source, url } })

// 获取支持的城市列表
export const getCities = () => request.get('/jobs/cities')

// 一键导入演示岗位数据 (10 条本地 JD，便于体验推荐)
export const seedDemoJobs = () => request.post('/jobs/seed-demo')

// === 职业方向推荐 ===

// 根据简历推荐岗位方向
export const recommendCareerPaths = (resumeId) =>
  request.post('/career-path/recommend', null, { params: { resume_id: resumeId } })

// 获取岗位推荐 (合并了 JobRecommend 页面) - 注：原文件第5行已声明，此处删除重复
// export const getJobRecommendations = (resumeId, params = {}) =>
//   request.get('/jobs/recommend', { params: { resume_id: resumeId, ...params } })
