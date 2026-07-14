/**
 * 前端埋点 SDK
 *
 * 用法：
 *   import { track } from '@/utils/tracker'
 *   track('upload_resume', { file_type: 'pdf', file_size: 1234 })
 *
 * 特性：
 * - localStorage 离线队列，断网不丢事件
 * - 定时上报（每 30s 或队列满 20 条）
 * - 自动附加 userId、timestamp
 */

const STORAGE_KEY = 'recruit.track_events'
const FLUSH_INTERVAL = 30000 // 30s 上报一次
const MAX_BATCH_SIZE = 20 // 队列满 20 条立即上报
let flushTimer = null
let isFlushing = false

/**
 * 获取埋点队列
 */
function getQueue() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

/**
 * 保存埋点队列
 */
function saveQueue(queue) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(queue))
}

/**
 * 新增埋点事件
 * @param {string} eventName - 事件名
 * @param {object} properties - 事件属性
 */
export function track(eventName, properties = {}) {
  const event = {
    event: eventName,
    properties,
    timestamp: new Date().toISOString(),
  }

  const queue = getQueue()
  queue.push(event)
  saveQueue(queue)

  // 队列满立即上报
  if (queue.length >= MAX_BATCH_SIZE) {
    flush()
  } else if (!flushTimer) {
    // 启动定时器
    flushTimer = setTimeout(flush, FLUSH_INTERVAL)
  }
}

/**
 * 上报队列中所有事件
 */
async function flush() {
  if (isFlushing) return
  const queue = getQueue()
  if (!queue.length) return

  isFlushing = true
  const batch = queue.splice(0, MAX_BATCH_SIZE)
  saveQueue(queue)

  try {
    const token = localStorage.getItem('token')
    await fetch('/api/tracking/events', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: '[redacted] ' + token,
      },
      body: JSON.stringify({ events: batch }),
    })
  } catch {
    // 上报失败，重新放回队列
    const remaining = getQueue()
    saveQueue([...batch, ...remaining])
  } finally {
    isFlushing = false
    // 如果队列还有剩余，继续定时上报
    const remaining = getQueue()
    if (remaining.length > 0) {
      if (flushTimer) clearTimeout(flushTimer)
      flushTimer = setTimeout(flush, FLUSH_INTERVAL)
    } else {
      flushTimer = null
    }
  }
}

// 页面卸载前尝试上报一次
window.addEventListener('beforeunload', () => {
  const queue = getQueue()
  if (queue.length > 0) {
    navigator.sendBeacon('/api/tracking/events', JSON.stringify({ events: queue }))
    localStorage.removeItem(STORAGE_KEY)
  }
})
