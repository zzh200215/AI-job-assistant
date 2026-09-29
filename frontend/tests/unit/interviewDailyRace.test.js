import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import Interview from '@/features/interview/views/Interview.vue'
import { installElement } from '@/plugins/element'

/* 「换一题」按钮（`:62`）既没有 loading 也没有 disabled，而 refreshDaily 是 `await getQuestionBank`
   之后直接写 dailyQuestion——连点两次就是两发在途，屏幕上留下的由**谁后回来**决定，不是谁后点的决定。
   题库响应里是按 limit=10 抽一批、前端再随机取一条，所以两次点击拿到的是两份不同的批次，
   旧批次晚到就会把用户刚点出来的那道题顶掉。 */

const api = vi.hoisted(() => ({
  interview: { getInterviewList: vi.fn(), getQuestionBank: vi.fn() },
  analysis: { getAnalysis: vi.fn() },
  jobs: { getJobPipelineList: vi.fn() },
}))

vi.mock('@/api/interview', () => api.interview)
vi.mock('@/api/analysis', () => api.analysis)
vi.mock('@/api/jobs', () => api.jobs)

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const inflight = []

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const qbank = (title) => ({
  items: [
    {
      question: title,
      difficulty: 'medium',
      category: '通用',
      suggested_answer: `参考答案：${title}`,
    },
  ],
})

let router

async function renderInterview() {
  api.interview.getInterviewList.mockResolvedValue({ items: [] })
  api.jobs.getJobPipelineList.mockResolvedValue({ items: [] })
  api.analysis.getAnalysis.mockResolvedValue({})
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/interview', name: 'interview', component: { template: '<div />' } }],
  })
  router.push('/interview')
  await router.isReady()
  const wrapper = mount(Interview, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function nextQuestionRequest() {
  const record = { ...deferred() }
  inflight.push(record)
  return record.promise
}

function lastQuestion() {
  return [...inflight].pop()
}

function dailyTitle() {
  return document.querySelector('.daily-title')?.textContent.trim()
}

function buttonByText(wrapper, text) {
  const found = wrapper.findAll('button').find((b) => b.text().includes(text))
  expect(found, `找不到文案含「${text}」的按钮，测试前提不成立`).toBeTruthy()
  return found
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  inflight.length = 0
  api.interview.getQuestionBank.mockImplementation(nextQuestionRequest)
})

describe('每日面试题：后点的那一次必须决定屏幕上是谁', () => {
  it('连点两次换一题，先点那次的批次不能把新题顶掉', async () => {
    const wrapper = await renderInterview()
    // 挂载自己发的那一发先落地，屏幕上有一道题，「换一题」才看得见
    await settle(lastQuestion(), qbank('挂载题'))
    expect(dailyTitle()).toBe('挂载题')

    await buttonByText(wrapper, '换一题').trigger('click')
    const first = lastQuestion()
    await buttonByText(wrapper, '换一题').trigger('click')
    const second = lastQuestion()
    expect(second).not.toBe(first)

    await settle(second, qbank('第二次点出来的题'))
    expect(dailyTitle()).toBe('第二次点出来的题')

    await settle(first, qbank('第一次点出来的题'))
    expect(dailyTitle(), '旧批次晚到，把用户刚换出来的题顶回去了').toBe('第二次点出来的题')
    expect(wrapper.vm.dailyLoading, '过期那一次不许改转圈状态').toBe(false)
    wrapper.unmount()
  })

  it('对照组：只点一次时新题照常出来', async () => {
    const wrapper = await renderInterview()
    await settle(lastQuestion(), qbank('挂载题'))
    await buttonByText(wrapper, '换一题').trigger('click')
    await settle(lastQuestion(), qbank('唯一的新题'))

    expect(dailyTitle()).toBe('唯一的新题')
    expect(wrapper.vm.dailyLoading).toBe(false)
    wrapper.unmount()
  })
})
