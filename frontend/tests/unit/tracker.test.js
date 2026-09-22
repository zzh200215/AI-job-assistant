import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/* 埋点队列的三条硬规矩，都是这次修之前做不到的：
   1) HTTP 4xx/5xx 也算失败——`fetch` 在这种情况不抛错，旧代码因此把已经 splice
      走的批次直接丢掉，还自称"断网不丢事件"；
   2) 没登录不发（旧代码发 `Bearer null`，必定 401 并白丢一批）；
   3) 关页面不再用 sendBeacon + removeItem：sendBeacon 带不上 Authorization 头，
      而队列被无条件删掉，等于每次离开页面扔一批没人收下的事件。 */
const QUEUE_KEY = 'recruit.track_events'

async function freshTracker() {
  vi.resetModules()
  return import('@/utils/tracker')
}

function queued() {
  return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]')
}

function respond({ ok, status }) {
  return vi.fn(async () => ({ ok, status }))
}

beforeEach(() => {
  localStorage.clear()
  vi.stubEnv('DEV', false)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('埋点上报', () => {
  it('服务端拒绝（404/500）时事件留在队列里，不当成功', async () => {
    localStorage.setItem('token', 'tok-1')
    vi.stubGlobal('fetch', respond({ ok: false, status: 404 }))
    const { track, flush } = await freshTracker()

    track('upload_resume', { file_type: 'pdf' })
    expect(queued()).toHaveLength(1)

    await flush()
    expect(queued()).toHaveLength(1)
    expect(queued()[0].event).toBe('upload_resume')
  })

  it('只有服务端确认收下才把这一批从队列里去掉', async () => {
    localStorage.setItem('token', 'tok-1')
    const fetchMock = respond({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)
    const { track, flush } = await freshTracker()

    track('apply_job', { jd_id: 12 })
    await flush()
    expect(queued()).toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/tracking/events')
    expect(init.headers.Authorization).toBe('Bearer tok-1')
    expect(JSON.parse(init.body).events).toHaveLength(1)
  })

  it('未登录时一个请求都不发，事件留着等登录后补传', async () => {
    const fetchMock = respond({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)
    const { track, flush } = await freshTracker()

    track('view_job', { jd_id: 3 })
    await flush()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(queued()).toHaveLength(1)
  })

  it('离开页面用能带头的 keepalive 请求，并且不删未确认的队列', async () => {
    localStorage.setItem('token', 'tok-1')
    const fetchMock = respond({ ok: false, status: 500 })
    vi.stubGlobal('fetch', fetchMock)
    const beacon = vi.fn(() => true)
    vi.stubGlobal('navigator', { ...window.navigator, sendBeacon: beacon })

    const { track } = await freshTracker()
    track('finish_interview', { score: 88 })
    expect(queued()).toHaveLength(1)

    window.dispatchEvent(new PageTransitionEvent('pagehide'))
    await Promise.resolve()

    expect(beacon).not.toHaveBeenCalled()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/tracking/events')
    expect(init.keepalive).toBe(true)
    expect(init.headers.Authorization).toBe('Bearer tok-1')
    // 没收到确认就不清空：这批下一次打开页面还会补传
    expect(queued()).toHaveLength(1)
  })
})
