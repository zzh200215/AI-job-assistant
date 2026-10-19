import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import InterviewReport from '@/features/interview/views/InterviewReport.vue'
import { useSelectionStore } from '@/stores/selection'
import { installElement } from '@/plugins/element'

/* P5(b)：报告页要把 P4 的三条回流接成用户能点的下一步。
   “去改简历”要顺手把这份简历设成简历中心的默认版本；“去补技能”要把简历/岗位
   写进跨页槽，否则职业规划页会落在空选择上。 */

const SESSION = {
  id: 12,
  resume_id: 7,
  jd_id: 9,
  interview_type: 'tech',
  total_questions: 5,
  answered_count: 5,
  timeout_count: 0,
  evaluation_status: 'completed',
  resume_summary: { name: '后端三年' },
  jd_summary: { title: '平台工程师', company: '示例公司' },
  evaluation: {
    overall_score: 78,
    dimension_scores: { completeness: 80, accuracy: 75, depth: 70, expression: 82 },
    question_evaluations: [],
    strengths: ['表达清楚'],
    weaknesses: ['成果未量化'],
    improvement_suggestions: ['把项目结果补成数据'],
    overall_evaluation: '整体不错',
    hiring_recommendation: '推荐',
    total_duration_seconds: 600,
  },
}

vi.mock('@/api/interview', () => ({
  getInterviewDetail: vi.fn(async () => SESSION),
}))

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/interview/report/:sessionId',
        name: 'interview-report',
        component: InterviewReport,
      },
      { path: '/resume-center', name: 'resume-center', component: { template: '<div />' } },
      { path: '/career-planning', name: 'career-planning', component: { template: '<div />' } },
      { path: '/interview/room/:sessionId', component: { template: '<div />' } },
      { path: '/interview/setup', component: { template: '<div />' } },
    ],
  })
}

async function mountReport() {
  const pinia = createPinia()
  const router = makeRouter()
  await router.push('/interview/report/12')
  await router.isReady()
  const wrapper = mount(InterviewReport, {
    global: { plugins: [installElement, pinia, router] },
  })
  await flushPromises()
  await flushPromises()
  return { wrapper, router, pinia }
}

function button(wrapper, text) {
  return wrapper.findAll('button').find((item) => item.text().includes(text))
}

describe('面试报告页的回流入口', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('token', 'smoke-test-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'smoke', role: 'candidate' }))
  })

  it('去改简历：把这场面试的简历设为简历中心的默认简历', async () => {
    const { wrapper, router, pinia } = await mountReport()

    const target = button(wrapper, '去改简历')
    expect(target, '报告页没有“去改简历”按钮').toBeTruthy()
    await target.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/resume-center')
    expect(useSelectionStore(pinia).defaultResumeId()).toBe(7)
  })

  it('去补技能：把简历与岗位一起写进跨页槽再跳职业规划', async () => {
    const { wrapper, router, pinia } = await mountReport()

    const target = button(wrapper, '去补技能')
    expect(target, '报告页没有“去补技能”按钮').toBeTruthy()
    await target.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/career-planning')
    const selection = useSelectionStore(pinia)
    expect(selection.resumeId()).toBe(7)
    expect(selection.jdId()).toBe(9)
  })
})
