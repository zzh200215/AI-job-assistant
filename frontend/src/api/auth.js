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

/* 忘记密码拆两步，因为中间那一步要一个**凭据**。
   原先这里是 `POST /auth/reset-password`，只收「账号 + 注册邮箱」就直接改密——
   那两个都是公开信息，等于任何知道别人用户名与邮箱的人都能改掉别人的密码。
   那条端点已从后端删除，改密现在只剩两条路，且都带凭据：
   本文件下面这两条（token 链）与已登录那条 `changePassword`（当前密码）。 */

/** 第一步：把重置令牌发到注册邮箱。本机没接邮件服务时，后端会把令牌放在响应的 `data.token` 里。 */
export const requestPasswordReset = (email) =>
  request.post('/auth/forgot-password', { email: normalizeEmail(email) })

/** 第二步：凭令牌设新密码（密码规则与注册同一套，服务端 schema 校验）。 */
export const resetPasswordWithToken = (token, newPassword, confirmPassword) =>
  request.post('/auth/reset-password-with-token', {
    token: String(token || '').trim(),
    new_password: newPassword,
    confirm_password: confirmPassword,
  })

/** 已登录改密：必须带当前密码。 */
export const changePassword = (oldPassword, newPassword, confirmPassword) =>
  request.put('/auth/me/password', {
    old_password: oldPassword,
    new_password: newPassword,
    confirm_password: confirmPassword,
  })

/** 邮箱验证落地页：token 来自验证邮件里的链接。 */
export const verifyEmail = (token) =>
  request.post('/auth/verify-email', { token: String(token || '').trim() })

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
