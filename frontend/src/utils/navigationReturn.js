/* 面试报告的两个闭环入口（P5(b)）跳走之后，落点页要能说明"从哪来"并能回去。

   这是一次跳转的上下文，不是登录态：只放 sessionStorage，关掉标签页就没了。
   路径只接受 `/interview/report/<id>`，避免把任意字符串当路由推出去。 */

const KEY = 'returnTo'
const REPORT_PREFIX = '/interview/report/'

export function rememberReportReturn(sessionId) {
  const id = Number(sessionId)
  if (!Number.isFinite(id) || id <= 0) return
  try {
    sessionStorage.setItem(
      KEY,
      JSON.stringify({ path: `${REPORT_PREFIX}${id}`, label: '面试报告' })
    )
  } catch {
    // 存储不可用时只是不提示，导航本身不能因此失败
  }
}

export function readReturnTo() {
  let raw = null
  try {
    raw = sessionStorage.getItem(KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed.path !== 'string' || !parsed.path.startsWith(REPORT_PREFIX))
      return null
    const label = typeof parsed.label === 'string' && parsed.label ? parsed.label : '面试报告'
    return { path: parsed.path, label }
  } catch {
    return null
  }
}

export function clearReturnTo() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // 同上：清不掉也不该抛
  }
}
