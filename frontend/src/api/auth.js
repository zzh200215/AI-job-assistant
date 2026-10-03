import request from './request'

/* §10.22 拍的那条 ②：凭据端点、"我的数据"那批自助端点、以及管理员读用户列表，并到这一个模块里，
   与后端 `app/api/auth.py` 对齐。之前 `/auth/login` 等四条写在 `stores/auth.js` 里裸调 `request`，
   `account.js` 与 `admin.js` 又各起一名，于是棘轮那个 `viewsBypassingApiLayer = 0` 只覆盖视图
   （`src/stores` 为了让色值/日期那几把尺子不去数法定解药被整根豁免），"0"说不出"只有 api 层出网"。
   现在守卫换成自己那份文件集（只豁免 `src/api` 与 `src/plugins`），这一层就成了唯一出口。

   账号与邮箱的空白/大小写处理跟着**端点**搬到这里：那是请求体的一部分，不是 store 的状态逻辑。 */

const normalizeText = (value) => String(value || '').trim()
const normalizeEmail = (email) => normalizeText(email).toLowerCase()

// ===== 凭据 =====

/** 登录失败不弹 toast（`Login.vue` 自己把原因写在表单上方），所以这条固定 `notifyError: false`。 */
export const login = (account, password) =>
  request.post('/auth/login', { account: normalizeText(account), password }, { notifyError: false })

export const register = (username, email, password) =>
  request.post('/auth/register', {
    username: normalizeText(username),
    email: normalizeEmail(email),
    password,
  })

export const resetPassword = (account, email, newPassword, confirmPassword) =>
  request.post('/auth/reset-password', {
    account: normalizeText(account),
    email: normalizeEmail(email),
    new_password: newPassword,
    confirm_password: confirmPassword,
  })

export const getCurrentUser = () => request.get('/auth/me')

// ===== 我的数据（自助） =====

/* 隐私页与个人中心共用的那一批端点。之前它们分散写在 `Privacy.vue` 与 `Profile.vue` 里各读一次
   `request`，其中 `/auth/export-data` 两边都写了同一份 `{ responseType: 'blob' }`。 */

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

// ===== 管理员：用户列表 =====

/** 这条挂在 `auth.py` 的 `/auth/admin/*` 上，是"管理员读别人"，与上面那批自助端点是两条门。
 *  `notifyError` 在一个 GET 上只有一处承重：401 时不弹"登录已过期"那条 toast。 */
export const getAdminUsers = (params = {}, config = {}) =>
  request.get('/auth/admin/users', { params, ...config })
