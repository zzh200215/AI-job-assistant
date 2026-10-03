import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import request from '@/api/request'
import { getHomeRouteByRole, getRoleLabel, normalizeRole } from '@/constants/roles'
import { setSelectionOwner } from '@/utils/lastSelection'
import {
  clearSession,
  readStoredUser,
  readToken,
  writeSession,
  writeStoredUser,
} from '@/utils/session'

/* 会话键与序列化住在 `utils/session.js`（D87）：这里原先自己读写 `localStorage` 六处，
   而 `api/request.js` 与 `api/interview.js` 还各有读方——同一对键三个文件各拿一份。 */

function normalizeEmail(email) {
  return String(email || '')
    .trim()
    .toLowerCase()
}

function normalizeText(value) {
  return String(value || '').trim()
}

function normalizeUser(currentUser) {
  if (!currentUser || typeof currentUser !== 'object') return null
  return {
    ...currentUser,
    role: normalizeRole(currentUser.role),
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(readToken() || '')
  const user = ref(normalizeUser(readStoredUser()))

  // "上一次选了哪份简历/JD/记录"按登录用户分槽，所以身份一变就要通知它（见 utils/lastSelection）。
  setSelectionOwner(user.value?.id ?? null)

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => normalizeRole(user.value?.role))
  const roleLabel = computed(() => getRoleLabel(role.value))
  const homeRoute = computed(() => getHomeRouteByRole(role.value))

  function setAuth(accessToken, currentUser) {
    token.value = accessToken
    user.value = normalizeUser(currentUser)
    writeSession(accessToken, user.value)
    setSelectionOwner(user.value?.id ?? null)
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    clearSession()
    setSelectionOwner(null)
  }

  /* 401 由 `api/request.js` 发事件、这里负责把 store 清干净；存储那一半两条路都走
     `utils/session.js`，所以不会出现"清了存储没清 ref"的中间态。 */
  window.addEventListener('auth:expired', clearAuth)

  async function login(account, password) {
    const data = await request.post(
      '/auth/login',
      {
        account: normalizeText(account),
        password,
      },
      { notifyError: false }
    )
    if (data?.access_token) {
      setAuth(data.access_token, data.user)
    }
    return data
  }

  async function register(username, email, password) {
    const data = await request.post('/auth/register', {
      username: normalizeText(username),
      email: normalizeEmail(email),
      password,
    })
    if (data?.access_token) {
      setAuth(data.access_token, data.user)
    }
    return data
  }

  async function resetPassword(account, email, newPassword, confirmPassword) {
    return request.post('/auth/reset-password', {
      account: normalizeText(account),
      email: normalizeEmail(email),
      new_password: newPassword,
      confirm_password: confirmPassword,
    })
  }

  async function fetchMe() {
    if (!token.value) return null
    try {
      const data = await request.get('/auth/me')
      user.value = normalizeUser(data)
      writeStoredUser(user.value)
      return user.value
    } catch {
      clearAuth()
      return null
    }
  }

  function logout() {
    clearAuth()
  }

  return {
    token,
    user,
    isLoggedIn,
    role,
    roleLabel,
    homeRoute,
    setAuth,
    clearAuth,
    login,
    register,
    resetPassword,
    fetchMe,
    logout,
  }
})
