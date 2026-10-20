import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import InterviewSetup from '@/features/interview/views/InterviewSetup.vue'
import { installElement } from '@/plugins/element'

/* I1：题量不再由页面自己写 10，而是读 `/interview/config/types` 的 max_questions；
   单题节奏也不再留 P1.2 之前的“30 秒限时”。 */

vi.mock('@/api/resume', () => ({
  getResumeList: vi.fn(async () => ({ items: [], total: 0 })),
}))

vi.mock('@/api/jd', () => ({
  getJDList: vi.fn(async () => ({ items: [], total: 0 })),
}))

vi.mock('@/api/interview', () => ({
  getInterviewList: vi.fn(async () => []),
  getInterviewConfigTypes: vi.fn(async () => ({
    items: [
      {
        type: 'tech',
        title: '技术深挖',
        persona: '像一位会持续追问的技术面试官',
        description: '重点考察技术深度',
        focus: ['原理解释'],
      },
    ],
    max_questions: 6,
  })),
  getInterviewProfile: vi.fn(async () => ({
    has_data: false,
    skill_weaknesses: [],
    weakness_texts: [],
  })),
  startInterview: vi.fn(async () => ({ id: 1 })),
}))

describe('面试设置页：题量与单题节奏', () => {
  it('显示后端配置的 6 题，不再写死 10 题或 30 秒', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', name: 'interview-setup', component: InterviewSetup }],
    })
    router.push('/')
    await router.isReady()
    const wrapper = mount(InterviewSetup, {
      global: { plugins: [router, createPinia(), installElement] },
    })
    await flushPromises()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('6 题')
    expect(text).toContain('7-11 分钟')
    expect(text).toContain('按题型 45–120 秒')
    expect(text).not.toContain('30 秒限时')

    const categoryCounts = wrapper
      .findAll('.qb-item')
      .map((item) => Number(item.text().match(/(\d+) 题/)?.[1] || 0))
    expect(categoryCounts.reduce((sum, count) => sum + count, 0)).toBe(6)
  })
})
