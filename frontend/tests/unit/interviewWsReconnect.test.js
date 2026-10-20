import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { connectInterviewWS, disconnectInterviewWS } from '@/api/interview'

/* P5(a)：WS 层的重连回调。store 那一侧已经单独测了"收到状态怎么画"；
   这里钉的是**状态真的会被发出来**，第几次/几秒后/恢复/失败都不是前端猜的。 */

class FakeWebSocket {
  static OPEN = 1
  static instances = []

  constructor(url, protocols) {
    this.url = url
    this.protocols = protocols
    this.readyState = 0
    this.onopen = null
    this.onmessage = null
    this.onerror = null
    this.onclose = null
    FakeWebSocket.instances.push(this)
  }

  send() {}

  close() {
    this.readyState = 3
    if (this.onclose) this.onclose({ code: 1000 })
  }
}

describe('面试 WebSocket：重连状态回调', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', FakeWebSocket)
    FakeWebSocket.instances = []
    localStorage.clear()
    localStorage.setItem('token', 'ws-test-token')
  })

  afterEach(() => {
    disconnectInterviewWS()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('断线后先报第 1 次/3 秒，下一次 open 报恢复', () => {
    const statuses = []
    connectInterviewWS(
      12,
      () => {},
      () => {},
      () => {},
      (info) => statuses.push(info)
    )

    const first = FakeWebSocket.instances[0]
    first.onopen()
    expect(statuses[0]).toEqual({ state: 'connected', attempt: 0, maxAttempts: 3 })

    first.onclose({ code: 1006 })
    expect(statuses[1]).toEqual({
      state: 'reconnecting',
      attempt: 1,
      maxAttempts: 3,
      delayMs: 3000,
    })

    vi.advanceTimersByTime(3000)
    expect(FakeWebSocket.instances).toHaveLength(2)
    FakeWebSocket.instances[1].onopen()
    expect(statuses[2]).toEqual({ state: 'recovered', attempt: 1, maxAttempts: 3 })
  })

  it('三次都失败后停止重连并报 failed', () => {
    const statuses = []
    connectInterviewWS(
      12,
      () => {},
      () => {},
      () => {},
      (info) => statuses.push(info)
    )

    const ws1 = FakeWebSocket.instances[0]
    ws1.onclose({ code: 1006 })
    vi.advanceTimersByTime(3000)

    const ws2 = FakeWebSocket.instances[1]
    ws2.onclose({ code: 1006 })
    vi.advanceTimersByTime(6000)

    const ws3 = FakeWebSocket.instances[2]
    ws3.onclose({ code: 1006 })
    vi.advanceTimersByTime(9000)

    const ws4 = FakeWebSocket.instances[3]
    ws4.onclose({ code: 1006 })

    expect(statuses.map((item) => item.state)).toEqual([
      'reconnecting',
      'reconnecting',
      'reconnecting',
      'failed',
    ])
    expect(statuses[3]).toEqual({ state: 'failed', attempt: 3, maxAttempts: 3 })
    expect(FakeWebSocket.instances).toHaveLength(4)
  })
})
