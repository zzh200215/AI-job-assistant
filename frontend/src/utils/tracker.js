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
const TRACKING_ENDPOINT = '/api/tracking/events'
const FLUSH_INTERVAL = 30000 // 30s 上报一次
const MAX_BATCH_SIZE = 20 // 队列满 20 条立即上报
// 失败重排队列的上限：反复离线时不无限占 localStorage
const MAX_QUEUE_SIZE = 200
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
 * 上报队列中所有事件。
 *
 * 两处以前是错的，都在悄悄丢数据：
 * 1. `fetch` 只对**网络异常**抛错，404/500 是 fulfilled promise——原来的 catch
 *    永远等不到"服务端拒绝"这种情况，批次已经从队列里 splice 走了，于是直接消失；
 * 2. 没登录时也会发，`Bearer null` 必定 401，同样白丢。
 * 现在按 `resp.ok` 判定，不成功就把这一批放回队头等下次。
 */
export async function flush() {
  if (isFlushing) return
  const queue = getQueue()
  if (!queue.length) return

  const token = localStorage.getItem('token')
  if (!token) return // 未登录：留在队列里，登录后再补传

  isFlushing = true
  const batch = queue.splice(0, MAX_BATCH_SIZE)
  saveQueue(queue)

  try {
    const resp = await fetch(TRACKING_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({ events: batch }),
    })
    if (!resp.ok) throw new Error(`tracking rejected: ${resp.status}`)
  } catch {
    // 上报失败（含 4xx/5xx），重新放回队列
    const remaining = getQueue()
    remaining.unshift(...batch)
    saveQueue(remaining.slice(0, MAX_QUEUE_SIZE))
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

/**
 * 页面离开前尽量补一次。
 *
 * 原来用 `navigator.sendBeacon`：它带不上 Authorization 头（`tracking/events` 要登录），
 * 而且发完就 `removeItem` 把队列删了——等于每次关页面都扔掉一批没人收下的事件。
 * `fetch(..., { keepalive: true })` 是能带头的替代品；不确认送达就不删队列，
 * 剩下的下一次打开页面由 flush() 补传。
 */
function flushOnLeave() {
  const queue = getQueue()
  if (!queue.length) return
  const token = localStorage.getItem('token')
  if (!token) return
  fetch(TRACKING_ENDPOINT, {
    method: 'POST',
    keepalive: true,
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + token,
    },
    body: JSON.stringify({ events: queue.slice(0, MAX_BATCH_SIZE) }),
  }).catch(() => {})
}

if (typeof window !== 'undefined') {
  // pagehide 在现代浏览器里覆盖关标签页/切后台；beforeunload 已不可靠
  window.addEventListener('pagehide', flushOnLeave)
}
