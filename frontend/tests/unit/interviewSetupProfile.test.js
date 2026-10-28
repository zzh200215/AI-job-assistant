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
      weakness_texts: ['成果未量化。', '结构混乱；'],
      last_session: { session_id: 12, overall_score: 64 },
    })

    const wrapper = await mounted()
    const panel = wrapper.find('.profile-focus')

    expect(panel.exists(), '画像面板没画出来（类名或渲染条件改了）').toBe(true)
    expect(panel.text()).toContain('Kafka')
    expect(panel.text()).toContain('55')
    expect(panel.text()).toContain('成果未量化；结构混乱')
    expect(panel.text()).not.toContain('。；')
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

  it('带岗位进入时用 jd_id 重取画像，把重合弱点标成本场重点', async () => {
    await router.push('/?jd_id=7')
    getInterviewProfile.mockResolvedValue({
      has_data: true,
      skill_weaknesses: [
        { skill: 'Kafka', canonical: 'kafka', avg_score: 55, sessions: 1 },
        { skill: 'Redis', canonical: 'redis', avg_score: 62, sessions: 1 },
      ],
      weakness_texts: [],
      jd_focus: {
        jd_id: 7,
        title: '后端工程师',
        required_count: 2,
        overlap: [{ skill: 'Kafka', canonical: 'kafka', avg_score: 55, sessions: 1 }],
      },
    })

    const wrapper = await mounted()
    const panel = wrapper.find('.profile-focus')

    expect(getInterviewProfile).toHaveBeenCalledWith(7)
    expect(panel.text()).toContain('Kafka')
    expect(panel.text()).toContain('本场重点')
    expect(panel.text()).toContain('开场会优先排到前面')
    // 只有交集里的那一条带标记，别把整份弱点都算成"本场重点"。
    const marked = panel.findAll('.plain-chip').filter((chip) => chip.text().includes('本场重点'))
    expect(marked).toHaveLength(1)
    expect(marked[0].text()).toContain('Kafka')
  })

  it('岗位必考项与弱点没有重合时说明按常规顺序出题', async () => {
    getInterviewProfile.mockResolvedValue({
      has_data: true,
      skill_weaknesses: [{ skill: 'Kafka', canonical: 'kafka', avg_score: 55, sessions: 1 }],
      weakness_texts: [],
      jd_focus: { jd_id: 8, title: '产品经理', required_count: 3, overlap: [] },
    })

    const wrapper = await mounted()

    expect(wrapper.find('.profile-focus').text()).toContain('没有重合')
    expect(wrapper.find('.profile-focus').text()).toContain('不会当成本场表现')
  })
})
