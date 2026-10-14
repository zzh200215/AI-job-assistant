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
/**
 * 建议那一发现在是**后台作业**：POST 立刻返回 `job_id`，结果靠轮询取。
 *
 * 为什么不是同步等：它是**一次**模型调用，实测 4.58–12.08s（关掉思考链，D196）到 91.77s
 * 且返回空 content（开着思考链，D189）。同步写法下这一发会占住 anyio 20 根线程里的一根
 * （`backend/app/core/threadpool.py` 把上限钉成连接池 10+10）整整一分多钟，候选人还要对着
 * spinner 等。所以这一对函数**不带** per-request 超时：每一趟请求都是毫秒级返回的。
 * 轮询的总预算由调用方给（`ResumeUpload.vue` 的 maxPollCount × intervalMs）。
 */
export const createRewriteSuggestionJob = (resumeId, jdId = null) =>
  request.post(`/resume/${resumeId}/rewrite-suggestion-jobs`, jdId ? { jd_id: jdId } : {})

export const getRewriteSuggestionJob = (jobId) =>
  request.get(`/resume/rewrite-suggestion-jobs/${jobId}`)

export const applyResumeRewrites = (resumeId, edits, jdId = null) =>
  request.post(`/resume/${resumeId}/apply-rewrites`, { edits, ...(jdId ? { jd_id: jdId } : {}) })

/* 简历评估报告（六模块）：**同一族形状**——POST 立刻返回 `job_id`，结果靠轮询，每一发都是毫秒级。
   这里也**不带** per-request 超时（理由与上面那一对相同：一次报告最多三发模型调用，同步等会占住
   服务端线程池里的一根）。轮询总预算由调用方给，见 `ResumeReport.vue` 的那两个常量。
   载荷里**没有**服务端的失败原因，所以这一层也没有任何一处读它。 */
export const createReportJob = (resumeId, payload = {}) =>
  request.post(`/resume/${resumeId}/report-jobs`, {
    jd_id: payload.jd_id ?? null,
    target_position: payload.target_position || '',
  })

export const getReportJob = (jobId) => request.get(`/resume/report-jobs/${jobId}`)

/** 采纳批改稿里的若干处改动（按全局编号）。返回形状与 `applyResumeRewrites` 同形。 */
export const applyReportRedline = (jobId, marks) =>
  request.post(`/resume/report-jobs/${jobId}/apply-redline`, { marks })

/** 自包含的独立 HTML（离线双击可开），与页面上那一份同源。 */
export const downloadReportHtml = (jobId) =>
  request.get(`/resume/report-jobs/${jobId}/report.html`, { responseType: 'blob' })

/* 单项目分析（四大节，量的是**一个项目**）：与上面那一族同一形状——POST 立刻返回 `job_id`，
   结果靠轮询，不带 per-request 超时。两处不同是刻意的：
   * 前三节一次跑完（两发模型调用），**第四节是点按钮才跑的那一发**（`createProjectQuestionsJob`），
     没点就不花那一发的钱；
   * `getProjectReportJob` 的 `report` 由服务端装配（父行的三大节 + 最新那一发完成的第四节），
     前端不自己拼第二份文档——一份文档两个出处迟早长得不一样。 */
export const createProjectReportJob = (resumeId, payload = {}) =>
  request.post(`/resume/${resumeId}/project-report-jobs`, {
    project_index: payload.project_index ?? 0,
    jd_id: payload.jd_id ?? null,
    target_position: payload.target_position || '',
  })

export const getProjectReportJob = (jobId) => request.get(`/resume/project-report-jobs/${jobId}`)

export const createProjectQuestionsJob = (jobId) =>
  request.post(`/resume/project-report-jobs/${jobId}/questions`)

export const downloadProjectReportHtml = (jobId) =>
  request.get(`/resume/project-report-jobs/${jobId}/report.html`, { responseType: 'blob' })

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
