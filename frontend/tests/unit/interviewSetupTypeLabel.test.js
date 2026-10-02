import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import InterviewSetup from '@/features/interview/views/InterviewSetup.vue'
import { installElement } from '@/plugins/element'

/* 这条断言钉的是 §10.24 那个缺陷的形状：面试类型标签写成 `typeConfigs[type]?.label`，
   而 `typeConfigs` 是个 ref —— 索引 Ref 对象本身永远拿不到东西，于是历史列表那一行
   一直显示后端原始键（'tech'）而不是配置里的中文标签（'技术深挖'）。
   类型门对这件事完全无声：`strict:false` 下用字符串索引一个 Ref 得到的是 `any`。
   所以判据必须是屏幕上的字，不是函数返回值。 */

vi.mock('@/api/resume', () => ({
  getResumeList: vi.fn(async () => ({ items: [{ id: 7, name: '后端三年' }], total: 1 })),
}))

vi.mock('@/api/jd', () => ({
  getJDList: vi.fn(async () => ({ items: [{ id: 9, title: '平台工程师' }], total: 1 })),
}))

vi.mock('@/api/interview', () => ({
  // `fetchHistory()` 是 `historyList.value = await getInterviewList()`（InterviewSetup.vue:470），
  // 后端 `GET /interview/sessions` 返回的是**数组**（interview_rest.py:159-163 的 `data=[...]`），
  // 所以夹具必须给数组；给 `{ items: [...] }` 会让那句 filter 当场炸。
  getInterviewList: vi.fn(async () => [
    {
      id: 12,
      interview_type: 'tech',
      status: 'completed',
      jd_summary: { title: '平台工程师' },
      resume_summary: { name: '后端三年' },
    },
  ]),
  // 返回空 items → 页面保留内置的五档配置，标签就该来自 defaultTypeConfigs
  getInterviewConfigTypes: vi.fn(async () => ({ items: [] })),
  startInterview: vi.fn(async () => ({ id: 1 })),
}))

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'interview-setup', component: InterviewSetup },
      { path: '/interview/report', name: 'interview-report', component: { template: '<div />' } },
    ],
  })
}

describe('面试设置页：历史列表里的面试类型标签', () => {
  let router

  beforeEach(async () => {
    router = makeRouter()
    await router.push('/')
    await router.isReady()
  })

  async function mounted() {
    const wrapper = mount(InterviewSetup, {
      global: { plugins: [router, createPinia(), installElement] },
    })
    await flushPromises()
    await flushPromises()
    return wrapper
  }

  it('把后端原始键换成配置里的中文标签', async () => {
    const wrapper = await mounted()
    const meta = wrapper.find('.history-meta')
    expect(meta.exists(), '历史列表那一行没画出来（夹具或类名改了）').toBe(true)
    const text = meta.text()
    expect(text).toContain('技术深挖')
    expect(text).not.toContain('tech')
  })
})
