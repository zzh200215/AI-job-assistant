import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import InterviewRoom from '@/features/interview/views/InterviewRoom.vue'
import { installElement } from '@/plugins/element'
import { useInterviewStore } from '@/stores/interview'
import { getInterviewDetail } from '@/api/interview'
import { ElMessage } from '@/plugins/element-services'

/* D61 把"回答草稿 + 语音输入"这条链搬进 composables/useAnswerDraft.js。
   搬之前这条链在测试里根本跑不到：jsdom 没有 SpeechRecognition，`speechSupported` 永远是
   false，那四个回调一次都没被调用过。这里装一个假的构造器，于是下面这些第一次成为事实：
   点一下真的 start()、再点真的 stop()、final 结果进草稿而 interim 只进预览、
   面试状态转走会停听写、五种 error 各说各的话、离开页面会收尾。 */

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

vi.mock('@/plugins/element-services', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve('confirm')) },
}))

class FakeRecognition {
  static instances = []

  constructor() {
    this.starts = 0
    this.stops = 0
    this.continuous = false
    this.interimResults = false
    this.lang = ''
    this.maxAlternatives = 0
    FakeRecognition.instances.push(this)
  }

  start() {
    this.starts += 1
    this.onstart?.()
  }

  stop() {
    this.stops += 1
    this.onend?.()
  }
}

// jsdom 没实现 scrollIntoView：链里每次聚焦都会调它，不补就攒一堆未处理拒绝
Element.prototype.scrollIntoView = function () {}

const DETAIL = {
  id: 7,
  status: 'ongoing',
  interview_type: 'tech',
  total_questions: 8,
  answered_count: 1,
  jd_summary: { title: '后端工程师', company: '某云厂商' },
  resume_summary: { name: '张三' },
  messages: [{ type: 'question', content: '讲讲你的项目', metadata: { category: '项目经验' } }],
}

function buttonByText(label) {
  return [...document.querySelectorAll('button')].find((b) => b.textContent.includes(label))
}

async function renderRoom() {
  getInterviewDetail.mockResolvedValue({ ...DETAIL })
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInterviewStore(pinia)
  store.startWS = vi.fn() // 不连 WS：轮询定时器会把 status 按回 connecting

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

function recognition() {
  return FakeRecognition.instances[FakeRecognition.instances.length - 1]
}

function draft(wrapper) {
  return wrapper.find('textarea').element.value
}

describe('语音那条链：假构造器下的真实行为', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    FakeRecognition.instances = []
    window.SpeechRecognition = FakeRecognition
    vi.clearAllMocks()
  })

  afterEach(() => {
    delete window.SpeechRecognition
    delete window.webkitSpeechRecognition
  })

  it('认得浏览器构造器：按钮可点，且参数按链的要求配好', async () => {
    await renderRoom()
    const instance = recognition()
    expect([
      instance.continuous,
      instance.interimResults,
      instance.lang,
      instance.maxAlternatives,
    ]).toEqual([true, true, 'zh-CN', 1])
    expect(document.querySelector('.voice-trigger').disabled).toBe(false)
    expect(document.querySelector('.voice-status').textContent).toContain(
      '可使用语音输入，提交前仍可手动修改识别文本。'
    )
  })

  it('点一下真的开始，文案换成"正在听写"', async () => {
    await renderRoom()
    document.querySelector('.voice-trigger').click()
    await flushPromises()
    expect(recognition().starts).toBe(1)
    expect(document.querySelector('.voice-trigger strong').textContent).toBe('正在听写')
    expect(document.querySelector('.voice-status').textContent).toContain(
      '正在听写，识别结果会自动追加到回答框。'
    )
  })

  it('识别开始时回答框拿到焦点（模板 ref 真的接上了链）', async () => {
    /* 这条钉的是 `answerInputRef: inputRef` 那一下改名：绑定断了的话链里
       getAnswerTextarea() 返回 null，focus 静默跳过——界面照常能用，只是每次识别完焦点丢了。
       N7 实测：只把那个改名弄断，只有这一条会红。
       测不出来的一半：`placeCursorAtEnd` 那一支。把入参删掉（N8）十条用例照旧全绿——
       jsdom 里 focus() 本身就把插入点放到末尾，先 setSelectionRange(0,0) 挪开也一样。
       浏览器里这两件事不同，但在测试环境里它没有独立的可观测差别，所以不当成守卫来宣称。 */
    const { wrapper } = await renderRoom()
    await wrapper.find('textarea').setValue('已有正文')
    const textarea = wrapper.find('textarea').element
    textarea.setSelectionRange(0, 0)
    document.querySelector('.voice-trigger').click()
    await flushPromises()
    expect(document.activeElement).toBe(textarea)
  })

  it('再点一下停，onend 之后文案与信号都退回未听写', async () => {
    await renderRoom()
    const trigger = document.querySelector('.voice-trigger')
    trigger.click()
    await flushPromises()
    document.querySelector('.voice-trigger').click()
    await flushPromises()
    expect(recognition().stops).toBe(1)
    expect(document.querySelector('.voice-trigger strong').textContent).toBe('点击开始语音输入')
    expect(document.querySelector('.voice-trigger').classList.contains('active')).toBe(false)
  })

  it('final 进草稿（已有正文就换行接），interim 只进预览那一行', async () => {
    const { wrapper } = await renderRoom()
    await wrapper.find('textarea').setValue('先写了一句')
    document.querySelector('.voice-trigger').click()
    await flushPromises()

    recognition().onresult({
      resultIndex: 0,
      results: [{ 0: { transcript: '  用 Go 写的服务  ' }, isFinal: true }],
    })
    await flushPromises()
    expect(draft(wrapper)).toBe('先写了一句\n用 Go 写的服务')

    recognition().onresult({
      resultIndex: 0,
      results: [{ 0: { transcript: '然后拆成了' }, isFinal: false }],
    })
    await flushPromises()
    expect(document.querySelector('.speech-preview').textContent).toBe('实时听写：然后拆成了')
    expect(draft(wrapper)).toBe('先写了一句\n用 Go 写的服务')

    // 纯空白的 final 不该在草稿里留下一个光秃秃的换行
    recognition().onresult({
      resultIndex: 0,
      results: [{ 0: { transcript: '   ' }, isFinal: true }],
    })
    await flushPromises()
    expect(draft(wrapper)).toBe('先写了一句\n用 Go 写的服务')
  })

  it('面试状态一转走就停听写', async () => {
    const { store } = await renderRoom()
    document.querySelector('.voice-trigger').click()
    await flushPromises()
    expect(recognition().starts).toBe(1)

    store.status = 'evaluating'
    await flushPromises()
    expect(recognition().stops).toBe(1)
  })

  it('五种 error 各说各的话，并且都退回未听写', async () => {
    await renderRoom()
    document.querySelector('.voice-trigger').click()
    await flushPromises()

    const cases = [
      ['not-allowed', '麦克风权限未开启，无法使用语音输入'],
      ['service-not-allowed', '麦克风权限未开启，无法使用语音输入'],
      ['no-speech', '没有识别到语音，请重试'],
      ['audio-capture', '未检测到可用麦克风'],
      ['aborted', '语音输入不可用：aborted'],
    ]
    for (const [error, message] of cases) {
      vi.clearAllMocks()
      recognition().onerror({ error })
      await flushPromises()
      expect(ElMessage.warning).toHaveBeenCalledWith(message)
      expect(document.querySelector('.voice-trigger strong').textContent).toBe('点击开始语音输入')
    }
  })

  it('清空回答：草稿空了，听写也停了', async () => {
    const { wrapper } = await renderRoom()
    await wrapper.find('textarea').setValue('一段没说完的话')
    document.querySelector('.voice-trigger').click()
    await flushPromises()

    buttonByText('清空回答').click()
    await flushPromises()
    expect(draft(wrapper)).toBe('')
    expect(recognition().stops).toBe(1)
    expect(document.querySelector('.voice-trigger strong').textContent).toBe('点击开始语音输入')
  })

  it('离开房间时链自己收尾，不指望页面记得', async () => {
    const { wrapper } = await renderRoom()
    document.querySelector('.voice-trigger').click()
    await flushPromises()
    expect(recognition().starts).toBe(1)

    wrapper.unmount()
    expect(recognition().stops).toBe(1)
  })

  it('不支持的浏览器上这条链整个不接：没有实例、按钮禁用并说明原因', async () => {
    delete window.SpeechRecognition
    await renderRoom()
    expect(FakeRecognition.instances.length).toBe(0)
    expect(document.querySelector('.voice-trigger').disabled).toBe(true)
    expect(document.querySelector('.voice-status').textContent).toContain(
      '当前浏览器不支持语音输入，建议使用最新版 Chrome 或 Edge。'
    )
  })
})
