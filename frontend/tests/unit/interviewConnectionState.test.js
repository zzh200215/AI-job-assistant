import { beforeEach, describe, expect, it, vi } from 'vitest'
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

/* P5(a)：重连状态必须是 store 的显式状态，页面才能画出"第几次/几秒后/成没成"。
   这条测试直接驱动 `connectInterviewWS` 的第 5 个回调，不经过真 WebSocket。 */

describe('面试 store：断线重连状态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    connectMock.mockReset()
  })

  it('重连中/已恢复/重连失败会分别写入可展示的状态', () => {
    const store = useInterviewStore()
    store.startWS(12)

    const [, onMessage, , , onStatus] = connectMock.mock.calls[0]
    expect(onStatus).toBeTypeOf('function')

    onStatus({ state: 'reconnecting', attempt: 1, maxAttempts: 3, delayMs: 3000 })
    expect(store.status).toBe('reconnecting')
    expect(store.connectionState).toBe('reconnecting')
    expect(store.reconnectAttempt).toBe(1)
    expect(store.reconnectMax).toBe(3)
    expect(store.reconnectDelaySeconds).toBe(3)

    onStatus({ state: 'recovered', attempt: 1, maxAttempts: 3 })
    expect(store.status).toBe('connecting')
    expect(store.connectionState).toBe('recovered')

    // 服务端第一条消息到了：恢复提示收起，状态回到正常链路
    onMessage({ type: 'question', content: '讲讲你的项目', metadata: { round: 1, total: 3 } })
    expect(store.status).toBe('ongoing')
    expect(store.connectionState).toBe('idle')

    onStatus({ state: 'failed', attempt: 3, maxAttempts: 3 })
    expect(store.status).toBe('error')
    expect(store.connectionState).toBe('failed')
    expect(store.errorMsg).toContain('重连失败')

    store.disconnect()
    expect(store.connectionState).toBe('idle')
    expect(store.reconnectAttempt).toBe(0)
  })

  it('初始连接成功不弹"重连"状态', () => {
    const store = useInterviewStore()
    store.startWS(12)

    const [, , , , onStatus] = connectMock.mock.calls[0]
    onStatus({ state: 'connected', attempt: 0, maxAttempts: 3 })

    expect(store.connectionState).toBe('idle')
    expect(store.status).toBe('connecting')

    store.disconnect()
  })
})
