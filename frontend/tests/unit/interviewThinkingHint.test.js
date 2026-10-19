import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'

import TranscriptPane from '@/features/interview/components/TranscriptPane.vue'
import { useInterviewStore } from '@/stores/interview'
import { connectInterviewWS } from '@/api/interview'

/* D240 的过渡态：现场组织追问最多要等 6 秒，但正常的"评完就出下一题"是毫秒级。
   所以判据是**延迟**，不是"有没有显示"：
   - 不足 400ms 的等待不换文案（否则每次答题都闪一下，比不显示更糟）；
   - 超过 400ms 才把底部那句换成"面试官正在思考下一问"；
   - 收到下一题、结束、出错时都必须清掉（否则那句话会一直挂在屏上）。 */

vi.mock('@/api/interview', () => ({
  getInterviewDetail: vi.fn(),
  connectInterviewWS: vi.fn(),
  disconnectInterviewWS: vi.fn(),
  createInterview: vi.fn(),
  endInterview: vi.fn(),
  getInterviewEvaluations: vi.fn(() => Promise.resolve({})),
  sendAnswer: vi.fn(),
  skipQuestion: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.useRealTimers()
  setActivePinia(createPinia())
})

describe('面试官思考中的延迟判据（store）', () => {
  it('提交答案后 400ms 内不算思考中，越过后才算', async () => {
    vi.useFakeTimers()
    const store = useInterviewStore()
    store.submitAnswer('我做过一个检索增强的项目')
    expect(store.interviewerThinking).toBe(false)

    await vi.advanceTimersByTimeAsync(399)
    expect(store.interviewerThinking).toBe(false)

    await vi.advanceTimersByTimeAsync(2)
    expect(store.interviewerThinking).toBe(true)
  })

  it('400ms 内就收到下一题 ⇒ 一次都不会显示', async () => {
    vi.useFakeTimers()
    const store = useInterviewStore()
    store.startWS()
    const onMessage = connectInterviewWS.mock.calls.at(-1)[1]

    store.submitAnswer('答得很快')
    await vi.advanceTimersByTimeAsync(120)
    onMessage({
      type: 'question',
      content: '下一题',
      metadata: { round: 2, total: 5, timeout_seconds: 120 },
    })
    await vi.advanceTimersByTimeAsync(600)

    expect(store.interviewerThinking).toBe(false)
  })

  it('收到下一题时把已经亮起的思考态清掉', async () => {
    vi.useFakeTimers()
    const store = useInterviewStore()
    store.startWS()
    const onMessage = connectInterviewWS.mock.calls.at(-1)[1]

    store.submitAnswer('答得慢')
    await vi.advanceTimersByTimeAsync(400)
    expect(store.interviewerThinking).toBe(true)

    onMessage({
      type: 'question',
      content: '下一题',
      metadata: { round: 2, total: 5, timeout_seconds: 120 },
    })
    expect(store.interviewerThinking).toBe(false)
  })

  it('出错与结束时也清掉，不让那句话挂在屏上', async () => {
    vi.useFakeTimers()
    const store = useInterviewStore()
    store.startWS()
    const onMessage = connectInterviewWS.mock.calls.at(-1)[1]

    store.submitAnswer('答了一次')
    await vi.advanceTimersByTimeAsync(400)
    expect(store.interviewerThinking).toBe(true)
    onMessage({ type: 'error', content: '连接异常', metadata: {} })
    expect(store.interviewerThinking).toBe(false)
  })
})

describe('过渡态文案（面板）', () => {
  function mountPane(props = {}) {
    return mount(TranscriptPane, {
      props: { messages: [], status: 'evaluating', ...props },
    })
  }

  it('未越过延迟时仍是那句"正在记录"，不闪"思考下一问"', () => {
    const wrapper = mountPane({ thinking: false })
    expect(wrapper.find('.state-hint').text()).toContain('正在记录你的回答')
    expect(wrapper.find('.state-hint').text()).not.toContain('思考下一问')
  })

  it('越过延迟后换成"思考下一问"', () => {
    const wrapper = mountPane({ thinking: true })
    expect(wrapper.find('.state-hint').text()).toContain('思考下一问')
  })

  it('不在 evaluating 时，思考态也不许画出来', () => {
    const wrapper = mountPane({ thinking: true, status: 'ongoing' })
    // 判 exists() 而不是 toBeNull()：空的 DOMWrapper 是个会对任何属性抛错的代理，
    // 断言库取 Symbol.toStringTag 做 diff 时会炸，红的原因就与"没画出来"无关了。
    expect(wrapper.find('.state-hint').exists()).toBe(false)
  })
})
