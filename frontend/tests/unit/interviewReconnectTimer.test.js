import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { connectMock } = vi.hoisted(() => ({ connectMock: vi.fn() }))

vi.mock('@/api/interview', () => ({
  connectInterviewWS: connectMock,
  createInterview: vi.fn(),
  disconnectInterviewWS: vi.fn(),
  endInterview: vi.fn(),
  getInterviewEvaluations: vi.fn(async () => ({ items: [], evaluation_status: 'idle' })),
  sendAnswer: vi.fn(),
  skipQuestion: vi.fn(),
}))

import { useInterviewStore } from '@/stores/interview'

/* P5(a) 追加：断线不能刷新答题时间。服务端 resume 重发未答题时带的是
 **剩余秒数**，前端必须按它续表，而不是把整题预算重新走一遍。 */

describe('面试 store：重连后的单题计时', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    connectMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('重连先停表，服务端按剩余预算重推后接着走', () => {
    const store = useInterviewStore()
    store.startWS(12)
    const [, onMessage, , , onStatus] = connectMock.mock.calls[0]

    onMessage({
      type: 'question',
      content: '讲讲缓存',
      metadata: { round: 1, total: 3, timeout_seconds: 120 },
    })
    expect(store.roundRemaining).toBe(120)

    vi.advanceTimersByTime(5000)
    expect(store.roundRemaining).toBe(115)

    onStatus({ state: 'reconnecting', attempt: 1, maxAttempts: 3, delayMs: 3000 })
    vi.advanceTimersByTime(3000)
    // 断线期间不扣时；服务端那边超时任务也已取消
    expect(store.roundRemaining).toBe(115)

    onStatus({ state: 'recovered', attempt: 1, maxAttempts: 3 })
    onMessage({
      type: 'question',
      content: '讲讲缓存',
      metadata: { round: 1, total: 3, timeout_seconds: 115 },
    })
    expect(store.status).toBe('ongoing')
    expect(store.roundRemaining).toBe(115)
    expect(store.roundProgress).toBe(100)

    vi.advanceTimersByTime(1000)
    expect(store.roundRemaining).toBe(114)
    store.disconnect()
  })

  it('首条题到达前只显示兜底值，不凭空起表', () => {
    const store = useInterviewStore()
    store.startWS(12)

    expect(store.roundRemaining).toBe(45)
    vi.advanceTimersByTime(3000)
    expect(store.roundRemaining).toBe(45)
    store.disconnect()
  })
})
