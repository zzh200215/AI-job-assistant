import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import request from '@/api/request'
import { getHomeRouteByRole, getRoleLabel, normalizeRole } from '@/constants/roles'

function loadStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null')
  } catch {
    localStorage.removeItem('user')
    return null
  }
}

function normalizeEmail(email) {
  return String(email || '').trim().toLowerCase()
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
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(normalizeUser(loadStoredUser()))

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => normalizeRole(user.value?.role))
  const roleLabel = computed(() => getRoleLabel(role.value))
  const homeRoute = computed(() => getHomeRouteByRole(role.value))

  function setAuth(accessToken, currentUser) {
    token.value = accessToken
    user.value = normalizeUser(currentUser)
    localStorage.setItem('token', accessToken)
    localStorage.setItem('user', JSON.stringify(user.value))
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  window.addEventListener('auth:expired', clearAuth)

  async function login(account, password) {
    const data = await request.post('/auth/login', {
      account: normalizeText(account),
      password,
    }, { notifyError: false })
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
      localStorage.setItem('user', JSON.stringify(user.value))
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
