// AI 模拟面试 API
import request from './request'

// === REST 接口 ===

// 创建面试会话
export const createInterview = (data) =>
  request.post('/interview/sessions', data)

// 获取面试列表
export const getInterviewList = () =>
  request.get('/interview/sessions')

// 获取面试详情（含报告）
export const getInterviewDetail = (sessionId) =>
  request.get(`/interview/sessions/${sessionId}`)

// 删除面试
export const deleteInterview = (sessionId) =>
  request.delete(`/interview/sessions/${sessionId}`)

// 获取题库浏览（支持分类/难度/关键词过滤）
export const getQuestionBank = (params = {}) =>
  request.get('/interview/question-bank', { params })

// 获取题库分类统计
export const getQuestionCategories = () =>
  request.get('/interview/question-bank/categories')

// 获取针对 JD 的面试准备建议
export const getInterviewPrep = (jdId) =>
  request.get(`/interview/preparation/${jdId}`)

// 获取面试表现趋势分析
export const getPerformanceTrend = () =>
  request.get('/interview/performance')

// === WebSocket 连接 ===

let ws = null
let heartbeatTimer = null
let reconnectTimer = null
let reconnectAttempts = 0

const MAX_RECONNECT_ATTEMPTS = 3
// 这些关闭码表示无需重连：正常关闭 / 面试已结束 / 认证失败 / 无权限 / 会话不存在
const NO_RECONNECT_CODES = [1000, 4000, 4001, 4003, 4004]
const isDev = import.meta.env.DEV
const wsLog = (...args) => {
  if (isDev) console.log(...args)
}
const wsWarn = (...args) => {
  if (isDev) console.warn(...args)
}
const wsError = (...args) => {
  if (isDev) console.error(...args)
}

/**
 * 建立 WebSocket 连接
 * @param {number} sid - 面试会话 ID
 * @param {function} onMessage - 消息回调
 * @param {function} onError - 错误回调
 * @param {function} onClose - 关闭回调
 * @returns {WebSocket}
 */
export function connectInterviewWS(sid, onMessage, onError, onClose) {
  const token = localStorage.getItem('token')
  if (!token) {
    if (onError) onError(new Error('未登录'))
    return null
  }

  // 如果已有连接的 ws，先关闭
  disconnectInterviewWS()

  // WS 基础地址：优先用环境变量 VITE_WS_BASE，否则按当前页面推断
  // 开发态前端常跑在 5173，后端在 8000，故 localhost 默认指向 8000
  const wsBase = import.meta.env.VITE_WS_BASE
  let base
  if (wsBase) {
    base = wsBase.replace(/\/$/, '')
  } else {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname === 'localhost'
      ? 'localhost:8000'
      : window.location.host
    base = `${protocol}//${host}`
  }

  const url = `${base}/ws/interview/${sid}`

  // 通过 Sec-WebSocket-Protocol 子协议传递 token，避免 token 出现在 URL（访问日志/浏览器历史）
  ws = new WebSocket(url, ['jwt', token])

  ws.onopen = () => {
    wsLog('[Interview WS] 连接已建立')
    reconnectAttempts = 0 // 连接成功，重置重连计数
    // 启动心跳
    startHeartbeat()
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'pong') return // 心跳回应，忽略
      if (onMessage) onMessage(data)
    } catch (e) {
      wsError('[Interview WS] 消息解析失败:', e)
    }
  }

  ws.onerror = (err) => {
    wsError('[Interview WS] 错误:', err)
    if (onError) onError(err)
  }

  ws.onclose = (event) => {
    wsLog('[Interview WS] 连接关闭:', event.code, event.reason)
    stopHeartbeat()
    if (onClose) onClose(event)

    // 鉴权失败 / 正常结束等不重连
    if (NO_RECONNECT_CODES.includes(event.code)) {
      return
    }
    // 超过最大重连次数则放弃，避免无限重连
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      wsWarn('[Interview WS] 已达最大重连次数，停止重连')
      if (onError) onError(new Error('连接已断开，重连失败，请刷新页面重试'))
      return
    }
    scheduleReconnect(sid, onMessage, onError, onClose)
  }

  return ws
}

/**
 * 发送答案
 * @param {string} content - 回答内容
 */
export function sendAnswer(content) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'answer', content }))
  }
}

/**
 * 跳过当前题
 */
export function skipQuestion() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'skip', content: '' }))
  }
}

/**
 * 主动结束面试
 */
export function endInterview() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'end', content: '' }))
  }
}

/**
 * 断开连接
 */
export function disconnectInterviewWS() {
  stopHeartbeat()
  clearReconnect()
  reconnectAttempts = 0
  if (ws) {
    ws.onclose = null // 防止触发重连
    ws.close(1000, '用户断开')
    ws = null
  }
}

// === 内部工具 ===

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping', content: '' }))
    }
  }, 15000) // 每15秒发送一次心跳
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

function scheduleReconnect(sid, onMessage, onError, onClose) {
  clearReconnect()
  reconnectAttempts++
  const delay = 3000 * reconnectAttempts // 指数退避：3s / 6s / 9s
  wsLog(`[Interview WS] 第 ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS} 次重连将在 ${delay}ms 后开始...`)
  reconnectTimer = setTimeout(() => {
    connectInterviewWS(sid, onMessage, onError, onClose)
  }, delay)
}

function clearReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

// WS 连接状态检查
export function isWSConnected() {
  return ws && ws.readyState === WebSocket.OPEN
}
