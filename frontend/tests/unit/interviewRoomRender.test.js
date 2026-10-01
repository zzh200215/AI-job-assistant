import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import InterviewRoom from '@/features/interview/views/InterviewRoom.vue'
import { installElement } from '@/plugins/element'
import { useInterviewStore } from '@/stores/interview'
import { getInterviewDetail } from '@/api/interview'

/* jsdom 没实现 `scrollIntoView`，而这页每次聚焦回答框都会调它（状态转到 ongoing、清空草稿、
   语音追加都会）——不调就攒下三个"未处理的 Promise 拒绝"，十条断言全绿而整轮 exit=1。
   补的是测试环境的洞：浏览器里这个方法存在，不该因此给生产代码加可选链兜底。 */
Element.prototype.scrollIntoView = function () {}

/* D60 把显示层搬进 lib 之后，这一页**第一次**有测试。lib 那 20 条只证明函数本身对；
   这一组证明的是"值真的走到了屏幕上"——D51 的教训：搬完之后测试全绿而模板少画一块，
   没人会红。所以每条都读 DOM，不读 computed。 */

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

function text(selector) {
  return document.querySelector(selector)?.textContent.trim() ?? null
}

function texts(selector) {
  return [...document.querySelectorAll(selector)].map((el) => el.textContent.trim())
}

async function renderRoom(detail = DETAIL) {
  getInterviewDetail.mockResolvedValue({ ...detail })
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInterviewStore(pinia)
  // 别在测试里连 WS：startWS 会开轮询定时器，把断言中间的 status 改掉
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

function buttonByText(label) {
  return [...document.querySelectorAll('button')].find((b) => b.textContent.includes(label))
}

describe('房间页面上那些字来自 lib', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('hero 的标题、副标题与状态标签', async () => {
    await renderRoom()
    expect(text('.room-hero h1')).toBe('后端工程师')
    expect(texts('.room-hero p')[1]).toBe('张三 · 某云厂商')
    expect(text('.room-hero .el-tag')).toBe('进行中')
  })

  it('缺会话字段时 hero 用占位而不是空白', async () => {
    await renderRoom({ id: 7, status: 'ongoing', messages: [] })
    expect(text('.room-hero h1')).toBe('AI 模拟面试')
    expect(texts('.room-hero p')[1]).toBe('当前候选人 · 目标岗位')
    expect(text('.interviewer-name')).toBe('AI 面试官')
  })

  it('阶段那块随轮次与追问换四副面孔，标题和话术一起换', async () => {
    const { store } = await renderRoom()
    store.currentRound = 1
    await flushPromises()
    expect(text('.stage-header h2')).toBe('开场摸底')

    store.currentRound = 3
    store.isFollowUp = false
    await flushPromises()
    expect(text('.stage-header h2')).toBe('核心深挖')
    expect(text('.stage-header p')).toBe('进入项目细节、技术原理或行为案例的主体考察。')

    store.isFollowUp = true
    await flushPromises()
    expect(text('.stage-header h2')).toBe('追问深挖')

    store.currentRound = 7
    store.isFollowUp = false
    await flushPromises()
    expect(text('.stage-header h2')).toBe('收口判断')

    // 前两轮压过追问：这条在页面上也要成立，否则说明页面的 round 传参和 lib 不是一套
    store.currentRound = 2
    store.isFollowUp = true
    await flushPromises()
    expect(text('.stage-header h2')).toBe('开场摸底')
  })

  it('题卡：题目、分类、面试官那句提示、建议结构五格', async () => {
    const { store } = await renderRoom()
    expect(text('.question-card h3')).toBe('正在等待面试官提问...')
    expect(text('.question-badge')).toBe('通用问题')

    store.messages = [
      {
        type: 'question',
        content: '讲一个你做过的服务',
        metadata: { category: '项目经验', round: 4 },
      },
    ]
    await flushPromises()
    expect(text('.question-card h3')).toBe('讲一个你做过的服务')
    expect(text('.question-badge')).toBe('项目经验')
    expect(text('.interviewer-name')).toBe('技术面试官')
    expect(text('.interviewer-role')).toBe('重点看你做了什么、为什么这么做、结果如何')
    expect(text('.question-helper')).toBe('优先说你的个人贡献，不要只说团队做了什么。')
    expect(texts('.structure-tips span')).toEqual(['背景', '目标', '动作', '结果', '复盘'])
    // 侧栏"本题提醒"是同一份结构的第二个出口：它必须和上面一致
    expect(texts('.hint-list li')).toEqual(texts('.structure-tips span'))
  })

  it('追问时题卡换一套话术，分类徽章旁边多一枚"追问"', async () => {
    const { store } = await renderRoom()
    store.messages = [
      { type: 'question', content: '为什么用 Go', metadata: { category: '技术基础' } },
    ]
    await flushPromises()
    expect(text('.interviewer-role')).toBe('重点看原理、边界条件和取舍')
    expect(text('.question-helper')).toBe('避免只背概念，最好带一个真实项目中的使用场景。')

    store.messages = [
      {
        type: 'question',
        content: '为什么用 Go',
        metadata: { category: '技术基础', is_follow_up: true },
      },
    ]
    store.isFollowUp = true
    await flushPromises()
    expect(text('.interviewer-role')).toBe('你刚才的回答还不够扎实，正在触发追问')
    expect(text('.question-helper')).toBe(
      '这类追问通常不是再说一遍，而是要补细节、数据、取舍或具体案例。'
    )
    expect(texts('.question-meta .question-badge')).toContain('追问')
  })

  it('输入框那三句话真的落在 placeholder 上', async () => {
    const { store, wrapper } = await renderRoom()
    expect(wrapper.find('textarea').attributes('placeholder')).toBe('输入你的回答...')

    store.roundRemaining = 8
    await flushPromises()
    expect(wrapper.find('textarea').attributes('placeholder')).toBe(
      '时间不多了，先给结论，再补关键细节...'
    )

    store.status = 'evaluating'
    store.roundRemaining = 25
    await flushPromises()
    expect(wrapper.find('textarea').attributes('placeholder')).toBe(
      '面试官正在评估上一题，请稍等...'
    )
  })

  it('提交按钮：有正文且进行中才可点，connecting 时即使有正文也不行', async () => {
    const { store, wrapper } = await renderRoom()
    const submit = () => buttonByText('提交回答')
    expect(submit().disabled).toBe(true)

    await wrapper.find('textarea').setValue('我的回答')
    expect(submit().disabled).toBe(false)

    store.status = 'connecting'
    await flushPromises()
    expect(submit().disabled).toBe(true)

    /* 必须先让 disabled 从输入框上退掉再打字：el-input 还禁用时那一下 input 不会被
       EP 受理，正文会停在上一轮的「我的回答」上，测的就不是空白正文了。 */
    store.status = 'ongoing'
    await flushPromises()
    await wrapper.find('textarea').setValue('   ')
    await flushPromises()
    expect(submit().disabled).toBe(true)
    // 这条同时证明空白真的进了模型（不是停在上一轮正文上）：清空按钮按 trim 判断
    expect(buttonByText('清空回答').disabled).toBe(true)
  })

  it('语音那条：jsdom 里没有 SpeechRecognition，所以既禁用也说明原因', async () => {
    await renderRoom()
    expect(text('.voice-status')).toBe('当前浏览器不支持语音输入，建议使用最新版 Chrome 或 Edge。')
    expect(document.querySelector('.voice-trigger').disabled).toBe(true)
    expect(document.querySelector('.voice-trigger').classList.contains('unsupported')).toBe(true)
  })

  it('侧栏统计：已评分题数、超时次数、最近判断各按各自口径', async () => {
    const { store } = await renderRoom()
    store.messages = [
      { type: 'question', content: 'Q1', metadata: {} },
      { type: 'answer', content: 'A1' },
      { type: 'evaluation', content: '不错', metadata: { score: 88 } },
      { type: 'evaluation', content: '一般', metadata: { score: 60 } },
      { type: 'system', content: '本答题超时，已自动跳过' },
      { type: 'system', content: '面试已结束' },
    ]
    store.lastScore = { score: 88 }
    await flushPromises()
    expect(texts('.snapshot-item strong')).toEqual(['2', '1', '88', '表现强'])
    expect(texts('.score-shell .score-top span')).toEqual([
      '回答有说服力',
      '基本覆盖，但说服力一般',
    ])

    // 没有分数时："最近得分"是 --，判断是"待观察"，卡片里也不能写"回答偏弱"
    store.lastScore = null
    store.messages = [{ type: 'evaluation', content: '还没打分', metadata: {} }]
    await flushPromises()
    expect(texts('.snapshot-item strong')).toEqual(['1', '0', '--', '待观察'])
    expect(text('.score-shell .score-top span')).toBe('评分暂未生成')
  })

  it('倒计时那一格把 store 的秒数一路递到面板的红色门槛上（D66 之后门槛在 StagePane 里）', async () => {
    const { store } = await renderRoom()
    store.currentRound = 3
    store.roundRemaining = 40
    await flushPromises()
    expect(document.querySelectorAll('.meta-pill.danger').length).toBe(0)
    /* 进度那一格两个数各归各：`:round` 与 `:total` 换错时屏幕上说的是"进度 8 / 3"，
       而面板自己的用例照样全绿（它只看递进来的两个数），所以这条要在页面上钉。 */
    expect(texts('.meta-pill')[0]).toBe('进度3 / 8')
    /* 门在面板里（`remaining <= 10`），值在页面上（`store.roundRemaining`）。
       这条用例钉的是**两边接上了**：把 `:remaining` 写死成一个常数，屏幕上就永远不红，
       而面板自己的用例照样全绿——所以只有页面级才看得见这种断线。 */
    store.roundRemaining = 10
    await flushPromises()
    expect(document.querySelectorAll('.meta-pill.danger').length).toBe(1)
    expect(texts('.meta-pill')[1]).toContain('单题倒计时')
  })

  it('右栏岗位聚焦那块吃的是会话里的 jd_summary（D66 之后它在 RoomAside 里）', async () => {
    await renderRoom()
    expect(text('.side-block strong')).toBe('后端工程师')
    expect(text('.side-block p')).toBe('某云厂商')
    expect(texts('.skill-grid span')).toEqual(['Go'])
    /* 这一条是 D66 的接线断言：把 `:session` 递错（比如递成 currentQuestion）屏幕上不会报错，
       只会这一块退回两个占位——而占位本身是合法的，所以必须在这里点名。 */
    expect(texts('.side-title')).toEqual(['岗位聚焦', '表现速览', '本题提醒'])
  })

  it('四种消息行的归类：end 与 system 同一条腿', async () => {
    const { store } = await renderRoom()
    store.messages = [
      { type: 'question', content: 'Q', metadata: {} },
      { type: 'answer', content: 'A' },
      { type: 'system', content: 'S' },
      { type: 'end', content: 'E' },
    ]
    await flushPromises()
    expect(
      [...document.querySelectorAll('.msg-row')].map((row) =>
        [...row.classList].filter((c) => c.startsWith('row-')).join(',')
      )
    ).toEqual(['row-ai', 'row-user', 'row-system', 'row-system'])
  })
})
