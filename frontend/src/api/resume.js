import request from './request'

export const uploadResume = (file, onUploadProgress) => {
  const form = new FormData()
  form.append('file', file)
  return request.post('/resume/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  })
}

export const parseResume = (resumeId) =>
  request.post('/resume/parse', { resume_id: resumeId })

export const getResume = (id) =>
  request.get(`/resume/${id}`)

export const generateOptimized = (resumeId, targetJdId) =>
  request.post(`/resume/${resumeId}/generate-optimized`, { target_jd_id: targetJdId || null })

export const getResumeVersions = (resumeId) =>
  request.get(`/resume/${resumeId}/versions`)

export const exportResume = (resumeId, format, version) =>
  request.post(`/resume/${resumeId}/export`, { format, version })

export const downloadResumeExport = (resumeId, format, version) =>
  request.get(`/resume/${resumeId}/download`, {
    params: { format, version },
    responseType: 'blob',
  })

export const getResumeList = (params = {}) =>
  request.get('/resume/list', { params })

// 企业筛选：获取当前招聘者自己可用于筛选的简历池
export const getAccessibleResumeList = (params = {}) =>
  request.get('/resume/accessible-list', { params })

// 企业筛选：一键生成演示候选人简历
export const seedDemoResumes = () =>
  request.post('/resume/seed-demo')
