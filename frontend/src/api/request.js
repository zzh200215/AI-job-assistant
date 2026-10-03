import axios from 'axios'
import { ElMessage } from '@/plugins/element-services'
import router from '@/router'
import {
  createRequestId,
  formatApiErrorMessage,
  normalizeValidationMessage,
} from '../utils/requestTracing'
import { clearSession, readToken } from '../utils/session'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 60000,
})

request.interceptors.request.use(
  (config) => {
    const token = readToken()
    config.headers = config.headers || /** @type {import('axios').AxiosRequestHeaders} */ ({})
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    const organizationId = localStorage.getItem('organization.active_id')
    if (organizationId && !config.headers['X-Organization-ID']) {
      config.headers['X-Organization-ID'] = organizationId
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
      /** @type {import('./http-client').ApiError} */
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
      /* 清的是存储那一份；store 那边由下面那个 `auth:expired` 事件负责（stores/auth.js 注册了监听）。
         两个机制仍然要一起走，所以这里只留一条出口：`clearSession()`。 */
      clearSession()
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
      /** @type {import('./http-client').ApiError} */
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

/** @type {import('./http-client').HttpClient} */
const client = request

export default client
