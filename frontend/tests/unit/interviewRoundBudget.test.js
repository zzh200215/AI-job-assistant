import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import InterviewRoom from '@/features/interview/views/InterviewRoom.vue'
import { installElement } from '@/plugins/element'
import { useInterviewStore } from '@/stores/interview'
import { connectInterviewWS, getInterviewDetail } from '@/api/interview'

/* D238 P1.2 的前端腿：每题的作答预算不再是页面自己抄的那个 30，而是随 `question` 消息下来的
   `metadata.timeout_seconds`（回落顺序见 `docs/面试消息协议.md`）。
   这一族为什么要读 DOM 而不是读 computed：D51 记过的教训——lib/仓库层全绿而模板少画一块，
   没人会红。倒计时那个药丸的取值链是 store → InterviewRoom 模板 → StagePane prop，
   三处任何一处接错，屏上都是同一个"--"或同一个错的数。 */

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

Element.prototype.scrollIntoView = function () {}

const DETAIL = {
  id: 7,
  status: 'ongoing',
  interview_type: 'tech',
  total_questions: 8,
  answered_count: 1,
  jd_summary: { title: '后端工程师', company: '某云厂商', required_skills: ['Go'] },
  resume_summary: { name: '张三' },
  messages: [],
}

function pillValue(label) {
  const pill = [...document.querySelectorAll('.meta-pill')].find((el) =>
    el.textContent.includes(label)
  )
  return pill ? pill.querySelector('strong')?.textContent.trim() : null
}

async function renderRoom() {
  getInterviewDetail.mockResolvedValue({ ...DETAIL })
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInterviewStore(pinia)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/interview/room/:sessionId', component: InterviewRoom },
      { path: '/interview/setup', component: { template: '<div />' } },
      { path: '/interview/report/:sessionId', component: { template: '<div />' } },
    ],
  })
  await router.push('/interview/room/7')
  await router.isReady()
  const wrapper = mount(InterviewRoom, {
    attachTo: document.body,
    global: { plugins: [installElement, pinia, router] },
  })
  await flushPromises()
  return { wrapper, store }
}

/** 从 `connectInterviewWS` 那一次调用里把回调取出来，用它推一条服务端消息。
    不直接调 store 内部的 handleWSMessage——那是把测试焊在生产代码的私有结构上。

    **必须 await 刷帧**：store 改了值不等于屏上变了。第一版我没等，于是三条断言读到的都是
    初始的 `00:45`——其中两条期望值恰好也是 45，会**空过**（错了却绿）。这种"读旧值还撞上"的
    假绿比直接红更坏，所以这条做成 async，调用点一律 await。 */
async function pushQuestion(meta) {
  const calls = connectInterviewWS.mock.calls
  if (!calls.length) throw new Error('这一场没起过 WS，取不到回调')
  const onMessage = calls[calls.length - 1][1]
  onMessage({ type: 'question', content: '讲讲你的检索链路', metadata: meta })
  await flushPromises()
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('单题倒计时跟着这一题的预算走', () => {
  it('技术题 120 秒显示成 02:00，不是 00:120', async () => {
    const { store } = await renderRoom()
    store.startWS()
    await pushQuestion({ round: 1, total: 8, category: '技术基础', timeout_seconds: 120 })

    expect(pillValue('单题倒计时')).toBe('02:00')
    expect(store.roundRemaining).toBe(120)
  })

  it('场景题 90 秒显示成 01:30', async () => {
    const { store } = await renderRoom()
    store.startWS()
    await pushQuestion({ round: 2, total: 8, category: '场景应对', timeout_seconds: 90 })

    expect(pillValue('单题倒计时')).toBe('01:30')
    expect(store.roundRemaining).toBe(90)
  })

  it('消息里没带这个字段时兜底到 45，不许掉回老的 30', async () => {
    // 本次改动之前落库的会话，重放出来的 `question` 消息就是没有这个键。
    const { store } = await renderRoom()
    store.startWS()
    await pushQuestion({ round: 3, total: 8, category: '技术基础' })

    expect(store.roundRemaining).toBe(45)
    expect(pillValue('单题倒计时')).toBe('00:45')
  })

  it('进度条的分母是这一题的预算，不是全场 30', async () => {
    const { store } = await renderRoom()
    store.startWS()
    await pushQuestion({ round: 4, total: 8, category: '技术基础', timeout_seconds: 120 })

    // 刚起表：剩余=预算，所以进度必须是 100。
    expect(store.roundProgress).toBe(100)
    store.roundRemaining = 60
    expect(store.roundProgress).toBe(50)
    store.roundRemaining = 120
    expect(store.roundProgress).toBe(100)
  })

  it('下一题换了题型，预算跟着换（不是整场记住第一个数）', async () => {
    const { store } = await renderRoom()
    store.startWS()
    await pushQuestion({ round: 5, total: 8, category: '技术基础', timeout_seconds: 120 })
    expect(store.roundRemaining).toBe(120)

    await pushQuestion({ round: 6, total: 8, category: '通用/HR', timeout_seconds: 45 })
    expect(store.roundRemaining).toBe(45)
    expect(pillValue('单题倒计时')).toBe('00:45')
  })
})

describe('页面里不许留着那第二个 30', () => {
  it('stores/interview.js 里那份自己抄的 30 已经出树', async () => {
    /* 静态腿，判的是"页面有没有第二份真相"：预算只能来自消息那一份。
       上面那五条读数是行为腿——它们绿不代表常量没被留在某个没人走的分支里。 */
    const { readFileSync } = await import('node:fs')
    const source = readFileSync('src/stores/interview.js', 'utf8')
    expect(source).not.toMatch(/ROUND_SECONDS\s*=\s*30/)
    expect(source).toMatch(/timeout_seconds/)
  })
})
