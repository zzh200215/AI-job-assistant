import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick } from 'vue'

import TranscriptPane from '@/features/interview/components/TranscriptPane.vue'
import InterviewRoom from '@/features/interview/views/InterviewRoom.vue'
import { installElement } from '@/plugins/element'
import { useInterviewStore } from '@/stores/interview'
import { getInterviewDetail } from '@/api/interview'

/* D66 把面试实录搬进 components/TranscriptPane.vue，途中删掉了页面上的 `chatRef` /
   `scrollToBottom()` 以及提交、跳过、结束三处动作后面的各一次显式滚动——这是**搬家而不是改行为**，
   所以这一份文件存在的唯一理由就是把"滚动仍然发生"钉住：
   - 提交与跳过：store 在那两个函数里同步往 messages 里 push 一条（`submitAnswer` 存 'answer'、
     `skipCurrent` 存 'system'），所以面板 watch 的 messages 长度覆盖得到；
   - 结束：`end()` 不 push 消息，改的是 status，而那块状态提示就写在面板里 → watch 的另一条腿覆盖。
   jsdom 没有真实布局，`scrollHeight` 恒为 0，所以这里把它按属性写成 800 再读 `scrollTop`：
   钉的是"那次写发生了、且写的是面板自己的那个滚动容器"。 */

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

const MSGS = [
  { type: 'question', content: '讲讲你的项目', metadata: { category: '项目深挖' } },
  { type: 'question', content: '没有分类的提问', metadata: {} },
  { type: 'answer', content: '我做了 X' },
  {
    type: 'evaluation',
    content: '整体清楚',
    metadata: { score: 82, completeness: 8, accuracy: 7, depth: 6, expression: 9 },
  },
  { type: 'system', content: '已请求跳过' },
  { type: 'end', content: '本次面试完成 4 题' },
]

function mountPane(props = {}) {
  document.body.innerHTML = ''
  return mount(TranscriptPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: { messages: [], status: 'ongoing', ...props },
  })
}

/** jsdom 没有布局，`scrollTop` 那个 setter 是个哑的（写进去读出来永远是 0——第一版就是被它骗了，
    四条"没贴底"全是它造成的假失败）。所以这里**换成自己的 setter 记下每一次写**：
    钉的是"这次写发生了、值就是当时的 scrollHeight、落在这个容器上"。 */
function armScroll(root = '.transcript-list') {
  const el = document.querySelector(root)
  const writes = []
  Object.defineProperty(el, 'scrollHeight', { configurable: true, get: () => 800 })
  Object.defineProperty(el, 'scrollTop', {
    configurable: true,
    get: () => (writes.length ? writes[writes.length - 1] : 0),
    set(v) {
      writes.push(v)
    },
  })
  return { el, writes }
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('实录面板：消息行的形状', () => {
  it('五种消息各画各的，没分类的提问退成「通用问题」', () => {
    mountPane({ messages: MSGS })
    expect(document.querySelectorAll('.msg-row').length).toBe(6)
    expect(document.querySelector('.msg-head span').textContent.trim()).toBe('面试官')
    expect(
      [...document.querySelectorAll('.ai-shell .msg-head span')].map((s) => s.textContent.trim())
    ).toEqual(['面试官', '项目深挖', '面试官', '通用问题'])
    expect(document.querySelector('.user-shell .msg-head span').textContent.trim()).toBe('我的回答')
    expect(document.querySelector('.system-shell').textContent.trim()).toBe('已请求跳过')
    expect(document.querySelector('.end-shell').textContent).toContain('本次面试完成 4 题')
  })

  it('评分那行按 utils 的档位上色，四维与改进建议各在位', () => {
    mountPane({ messages: [MSGS[3]] })
    const chip = document.querySelector('.score-shell')
    expect(chip.className).toContain('score-chip--good')
    expect(chip.querySelector('.score-top strong').textContent.trim()).toBe('本题评分 82')
    expect(chip.querySelector('.score-dims').textContent.replace(/\s+/g, ' ')).toContain(
      '完整 8准确 7深度 6表达 9'
    )
    expect(chip.querySelector('.score-improvement')).toBeNull()

    mountPane({
      messages: [
        { type: 'evaluation', content: '还行', metadata: { score: 40, improvement: '把取舍讲完' } },
      ],
    })
    expect(document.querySelector('.score-shell').className).toContain('score-chip--risk')
    expect(document.querySelector('.score-improvement').textContent).toContain('把取舍讲完')
    /* 没有维度分时四格说 '-'，不说 undefined 也不说 0。 */
    expect(document.querySelector('.score-dims').textContent.replace(/\s+/g, ' ')).toContain(
      '完整 -准确 -深度 -表达 -'
    )
  })

  it('没有分数时不能写「回答偏弱」——那句话是 lib 的规则', () => {
    mountPane({ messages: [{ type: 'evaluation', content: '先记着', metadata: {} }] })
    expect(document.querySelector('.score-top strong').textContent.trim()).toBe('本题评分 0')
    expect(document.querySelector('.score-top span').textContent.trim()).not.toContain('偏弱')
  })

  it('connecting 与 evaluating 各有一句状态提示，其余状态一句都没有', () => {
    mountPane({ status: 'connecting' })
    expect(document.querySelector('.state-hint').textContent).toContain('正在接入面试房间')
    mountPane({ status: 'evaluating' })
    expect(document.querySelector('.state-hint').textContent).toContain('面试官正在记录')
    mountPane({ status: 'ongoing' })
    expect(document.querySelector('.state-hint')).toBeNull()
    mountPane({ status: 'completed' })
    expect(document.querySelector('.state-hint')).toBeNull()
  })
})

describe('实录面板：滚动跟着这块 DOM 走', () => {
  it('消息多一条就贴一次底', async () => {
    const wrapper = mountPane({ messages: [MSGS[0]] })
    const { writes } = armScroll()
    wrapper.setProps({ messages: [MSGS[0], MSGS[1]] })
    await nextTick()
    await flushPromises()
    expect(writes).toEqual([800])
  })

  it('只有状态变了（结束面试那条路）也贴一次底', async () => {
    const wrapper = mountPane({ messages: [MSGS[0]] })
    const { writes } = armScroll()
    wrapper.setProps({ status: 'evaluating' })
    await nextTick()
    await flushPromises()
    expect(writes).toEqual([800])
    expect(document.querySelector('.state-hint')).toBeTruthy()
  })

  it('两个都不变时不乱写：面板不是每帧都把自己按到底', async () => {
    const wrapper = mountPane({ messages: [MSGS[0]], status: 'ongoing' })
    const { writes } = armScroll()
    wrapper.setProps({ messages: [MSGS[0]], status: 'ongoing' })
    await nextTick()
    await flushPromises()
    expect(writes).toEqual([])
  })

  it('滚动落在面板自己的那个容器上，不是页面别处', async () => {
    const wrapper = mountPane({ messages: [] })
    const { writes } = armScroll()
    const other = armScroll('.panel-body')
    wrapper.setProps({ messages: [MSGS[0]] })
    await nextTick()
    await flushPromises()
    expect(writes).toEqual([800])
    /* 旁边那个容器一次都没被写过：贴的是消息列，不是面板体。 */
    expect(other.writes).toEqual([])
  })
})

describe('页面那一侧：显式滚动删掉之后仍然贴底', () => {
  async function renderRoom() {
    getInterviewDetail.mockResolvedValue({
      id: 7,
      status: 'ongoing',
      interview_type: 'tech',
      total_questions: 8,
      answered_count: 1,
      jd_summary: { title: '后端工程师', company: '某云厂商', required_skills: ['Go'] },
      resume_summary: { name: '张三' },
      messages: [],
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useInterviewStore(pinia)
    store.startWS = vi.fn()
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

  it('提交回答：store 同步塞进一条 answer 消息，面板因此贴底', async () => {
    const { wrapper } = await renderRoom()
    const { writes } = armScroll()
    wrapper.vm.userInput = '我做过一个网关'
    await flushPromises()
    const send = [...document.querySelectorAll('button')].find((b) =>
      b.textContent.includes('提交回答')
    )
    send.click()
    await nextTick()
    await flushPromises()
    expect(document.querySelectorAll('.user-shell').length).toBe(1)
    expect(writes).toEqual([800])
  })

  it('跳过本题：塞的是一条 system 消息，同样贴底', async () => {
    const { wrapper } = await renderRoom()
    const { writes } = armScroll()
    const skip = [...document.querySelectorAll('button')].find((b) =>
      b.textContent.includes('跳过本题')
    )
    skip.click()
    await nextTick()
    await flushPromises()
    expect(document.querySelector('.system-shell').textContent).toContain('跳过')
    expect(writes).toEqual([800])
    expect(wrapper.vm).toBeTruthy()
  })
})
