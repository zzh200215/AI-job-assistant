import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import InterviewSetup from '@/features/interview/views/InterviewSetup.vue'
import { getInterviewProfile } from '@/api/interview'
import { installElement } from '@/plugins/element'

/* P4 回流③的前端面：设置页要能看见"上一场留下什么"与"本场会优先深挖什么"。
   画像读不到时主表单必须照常可用——它是锦上添花的一路。 */

vi.mock('@/api/resume', () => ({
  getResumeList: vi.fn(async () => ({ items: [], total: 0 })),
}))

vi.mock('@/api/jd', () => ({
  getJDList: vi.fn(async () => ({ items: [], total: 0 })),
}))

vi.mock('@/api/interview', () => ({
  getInterviewList: vi.fn(async () => []),
  getInterviewConfigTypes: vi.fn(async () => ({ items: [] })),
  getInterviewProfile: vi.fn(),
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

describe('面试设置页：上一场画像', () => {
  let router

  beforeEach(async () => {
    vi.clearAllMocks()
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

  it('展示上一场的技能弱点与报告原话', async () => {
    getInterviewProfile.mockResolvedValue({
      has_data: true,
      skill_weaknesses: [
        { skill: 'Kafka', canonical: 'kafka', avg_score: 55, sessions: 2 },
        { skill: 'Redis', canonical: 'redis', avg_score: 62, sessions: 1 },
      ],
      weakness_texts: ['成果未量化', '结构混乱'],
      last_session: { session_id: 12, overall_score: 64 },
    })

    const wrapper = await mounted()
    const panel = wrapper.find('.profile-focus')

    expect(panel.exists(), '画像面板没画出来（类名或渲染条件改了）').toBe(true)
    expect(panel.text()).toContain('Kafka')
    expect(panel.text()).toContain('55')
    expect(panel.text()).toContain('成果未量化')
    expect(panel.text()).toContain('不会当成本场表现')
  })

  it('没有历史画像时给出下一步提示，不画空面板', async () => {
    getInterviewProfile.mockResolvedValue({
      has_data: false,
      skill_weaknesses: [],
      weakness_texts: [],
    })

    const wrapper = await mounted()

    expect(wrapper.find('.profile-focus').exists()).toBe(false)
    expect(wrapper.text()).toContain('完成一场面试后，这里会出现下一场的考察重点')
  })

  it('画像接口失败时给出独立失败态，设置页仍然可用', async () => {
    getInterviewProfile.mockRejectedValue(new Error('profile down'))

    const wrapper = await mounted()

    expect(wrapper.find('.setup-form').exists()).toBe(true)
    expect(wrapper.find('.app-load-error').exists()).toBe(true)
    expect(wrapper.text()).toContain('上一场画像加载失败')
    expect(wrapper.text()).not.toContain('完成一场面试后，这里会出现下一场的考察重点')
  })
})
