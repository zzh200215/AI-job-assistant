import request from './request'

/* 账号与"我的数据"：隐私页与个人中心共用的那一批 `/auth/*` 自助端点。
   之前它们分散写在 `Privacy.vue` 与 `Profile.vue` 里各读一次 `request`，
   其中 `/auth/export-data` 两边都写了同一份 `{ responseType: 'blob' }`。 */

// 我的数据概览（各域各有多少条）
export const getDataSummary = () => request.get('/auth/data-summary')

// 导出全量个人数据（后端回一个文件流）
export const exportMyData = () => request.get('/auth/export-data', { responseType: 'blob' })

// 分类删除：三类数据各自一个端点，删完由调用方决定是否重取概览
export const deleteMyResumes = () => request.delete('/auth/data/resumes')
export const deleteMyAnalyses = () => request.delete('/auth/data/analyses')
export const deleteMyInterviews = () => request.delete('/auth/data/interviews')

// 重发邮箱验证链接
export const sendVerificationEmail = () => request.post('/auth/send-verification-email')

// 注销账号（不可逆；确认框在页面上，不在这一层）
export const deleteMyAccount = () => request.delete('/auth/account')
