import request from './request'

/**
 * 一份简历版本：`original` 那一份是前端造的（`change_log` 空、`suggestion_decisions` 空对象），
 * 持久化那几份由后端给。`ResumeCompare.vue:323` 的初值原本只有四个键，导致装载后的整份赋值
 * 被 TS 判"多出来的键不存在"，所以形状记在这里——消费者的初值与响应是同一个形状。
 * @typedef {Object} ResumeVersion
 * @property {string | number} id
 * @property {string} [version_type]
 * @property {string} [label]
 * @property {string} [content]
 * @property {string} [created_at]
 * @property {any[]} [change_log]
 * @property {Record<string, any>} [suggestion_decisions]
 * @property {string} [format]
 */

export const uploadResume = (file, onUploadProgress) => {
  const form = new FormData()
  form.append('file', file)
  return request.post('/resume/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  })
}

export const parseResume = (resumeId) => request.post('/resume/parse', { resume_id: resumeId })

export const getResume = (id) => request.get(`/resume/${id}`)

// 行级改写：建议按 block_id 锚定到简历里的具体文本，采纳后才写回
export const getRewriteSuggestions = (resumeId, jdId = null) =>
  request.post(`/resume/${resumeId}/rewrite-suggestions`, jdId ? { jd_id: jdId } : {})

export const applyResumeRewrites = (resumeId, edits, jdId = null) =>
  request.post(`/resume/${resumeId}/apply-rewrites`, { edits, ...(jdId ? { jd_id: jdId } : {}) })

export const revertResumeRewrite = (resumeId, snapshotVersionId) =>
  request.post(`/resume/${resumeId}/revert-rewrite`, { snapshot_version_id: snapshotVersionId })

export const generateOptimized = (resumeId, targetJdId) =>
  request.post(`/resume/${resumeId}/generate-optimized`, { target_jd_id: targetJdId || null })

export const getResumeVersions = (resumeId) => request.get(`/resume/${resumeId}/versions`)

export const createResumeVersion = (resumeId, payload) =>
  request.post(`/resume/${resumeId}/versions`, payload)

export const updateResumeVersion = (resumeId, versionId, payload) =>
  request.patch(`/resume/${resumeId}/versions/${versionId}`, payload)

export const getResumeVersionDiff = (resumeId, compareVersionId, baseVersionId = null) =>
  request.get(`/resume/${resumeId}/versions/diff`, {
    params: {
      compare_version_id: compareVersionId,
      ...(baseVersionId ? { base_version_id: baseVersionId } : {}),
    },
  })

export const saveResumeSuggestionDecision = (resumeId, versionId, payload) =>
  request.post(`/resume/${resumeId}/versions/${versionId}/suggestions`, payload)

export const previewResumeAts = (resumeId, payload = {}) =>
  request.post(`/resume/${resumeId}/ats-preview`, payload)

export const tailorResume = (resumeId, jdId) =>
  request.post(`/resume/${resumeId}/tailor`, { jd_id: jdId })

export const getResumeQuickScore = (resumeId, config = {}) =>
  request.get(`/resume/${resumeId}/quick-score`, config)

export const diagnoseResume = (resumeId, payload = {}, config = {}) =>
  request.post(`/resume/${resumeId}/diagnose`, payload, config)

export const deleteResume = (resumeId) => request.delete(`/resume/${resumeId}`)

export const exportResume = (resumeId, format, version) =>
  request.post(`/resume/${resumeId}/export`, { format, version })

export const downloadResumeExport = (resumeId, format, version, versionId = null) =>
  request.get(`/resume/${resumeId}/download`, {
    params: { format, version, ...(versionId ? { version_id: versionId } : {}) },
    responseType: 'blob',
  })

export const getResumeList = (params = {}) => request.get('/resume/list', { params })

// 企业筛选：获取当前招聘者自己可用于筛选的简历池
export const getAccessibleResumeList = (params = {}) =>
  request.get('/resume/accessible-list', { params })

// 企业筛选：一键生成演示候选人简历
export const seedDemoResumes = () => request.post('/resume/seed-demo')
