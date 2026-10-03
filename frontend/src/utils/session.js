/* 会话凭据的**唯一**持有者。
   这两个键原先散在三个文件里 12 处：`api/request.js` 每次请求读一次 token、401 时直接
   `removeItem` 两个键；`api/interview.js` 拼 WS 地址时又自己读一次；`stores/auth.js` 在建 store
   时读、在 setAuth/clearAuth/fetchMe 里写。写方不止一处、读方各拿一份，就是 §7「其他已知项」里
   那句"双份真相源"——它今天没出事是因为 401 那条路还会 `window.dispatchEvent('auth:expired')`
   把 store 一起清掉（两个机制靠一个事件对齐），而不是因为有单一出处。
   现在键名、序列化、解析容错都在这个文件里，其余地方只调函数。
   守卫：`tests/unit/styleDebtRatchet.test.js` 的 keeps the auth keys inside utils/session。 */

const TOKEN_KEY = 'token'
const USER_KEY = 'user'

/** 请求拦截器与 WS 都要它；这里**不**缓存，因为 store 的 ref 只在登录时更新，
 *  而拦截器必须拿到当下那一份（多标签页登录/退出的场景靠这个语义）。 */
export function readToken() {
  return localStorage.getItem(TOKEN_KEY)
}

/** 存的是 JSON；坏值（别的版本写坏的、手动改过的）不当成"已登录"，清掉再返回 null。 */
export function readStoredUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    localStorage.removeItem(USER_KEY)
    return null
  }
}

/** 只更新 user（`fetchMe()` 拿到新资料时不能顺手把 token 写空）。 */
export function writeStoredUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user ?? null))
}

export function writeSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  writeStoredUser(user)
}

/** 401 与退出登录共用这一条；调用方负责把 store 那边也清掉（事件或直接调 store）。 */
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
