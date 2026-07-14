import axios from 'axios'
import { ElMessage } from '@/plugins/element-services'
import router from '@/router'
import {
  createRequestId,
  formatApiErrorMessage,
  normalizeValidationMessage,
} from '../utils/requestTracing'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 60000,
})

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    config.headers = config.headers || {}
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    if (!config.headers['X-Request-ID']) {
      config.headers['X-Request-ID'] = createRequestId()
    }
    return config
  },
  (err) => Promise.reject(err)
)

request.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      const requestId = body.request_id || resp.headers['x-request-id']
      const msg = formatApiErrorMessage(body.message, requestId, '请求失败')
      const method = String(resp.config?.method || '').toLowerCase()
      if (resp.config?.notifyError !== false && method !== 'get') {
        ElMessage.error(msg)
      }
      const error = new Error(body.message || 'error')
      error.requestId = requestId
      error.payload = body
      error.userMessage = body.message || '请求失败'
      error.isApiError = true
      return Promise.reject(error)
    }
    return body
  },
  (err) => {
    const method = String(err?.config?.method || '').toLowerCase()
    const shouldNotify = err?.config?.notifyError !== false && method !== 'get'

    if (err?.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.dispatchEvent(new CustomEvent('auth:expired'))
      if (err?.config?.notifyError !== false) {
        ElMessage.error('登录已过期，请重新登录')
      }
      router.push('/login')
      return Promise.reject(err)
    }

    if (err?.response?.status === 422) {
      const body = err?.response?.data || {}
      const detail = body?.data?.errors || body?.detail
      const requestId = body?.request_id || err?.response?.headers?.['x-request-id']
      const msg = normalizeValidationMessage(detail, body?.message || '请求参数错误')
      if (shouldNotify) {
        ElMessage.error(formatApiErrorMessage(msg, requestId, '请求参数错误'))
      }
      const error = new Error(msg)
      error.requestId = requestId
      error.payload = body
      error.userMessage = msg
      error.isApiError = true
      return Promise.reject(error)
    }

    const requestId = err?.response?.data?.request_id || err?.response?.headers?.['x-request-id']
    const msg =
      err?.response?.data?.message ||
      err?.response?.data?.msg ||
      err.message ||
      '网络异常，请稍后重试'
    if (shouldNotify) {
      ElMessage.error(formatApiErrorMessage(msg, requestId, '网络异常，请稍后重试'))
    }
    err.userMessage = msg
    return Promise.reject(err)
  }
)

export default request
