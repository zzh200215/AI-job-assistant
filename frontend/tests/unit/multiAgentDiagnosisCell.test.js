import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MultiAgentAnalysis from '@/features/analysis/views/MultiAgentAnalysis.vue'
import { installElement } from '@/plugins/element'

/* 「简历诊断」那一格的数据来源（§10.41 他点的 ③）。
   改之前这一格读 `summaryReport.resume_diagnosis.score`，而后端那份汇总 prompt 从没要求过
   `resume_diagnosis` 这个键——真 provider 下它永远是空白，只有 mock 载荷里写着 78，
   于是演示看起来像"有数"。这一族最贵的错法就是"画得出来但来源不存在"（与抽取搬家那三次同源）。
   现在这一格由服务端从 ResumeAgent 的七维结果折出来，所以三条都要在屏上成立：
   ① 有七维结果 ⇒ 显示相加的总分与等级，并说清是哪张表；
   ② 七维里有没读出来的 ⇒ 明写"未评分"，不显示一个数；
   ③ 那一步根本没跑 ⇒ 整格不出现假数据，给一句没有内容。 */

const api = vi.hoisted(() => ({
  startAutoAgent: vi.fn(),
  getMultiAgentDetail: vi.fn(),
}))
const services = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/api/multi_agent', () => api)
vi.mock('@/plugins/element-services', () => services)

const DIMENSIONS = [
  {
    key: 'metric_ownership',
    label: '指标责任与达成',
    full: 20,
    star: true,
    score: 12,
    note: '（mock）没有个人达成数',
  },
  {
    key: 'interview_hooks',
    label: '面试钩子设计',
    full: 10,
    star: true,
    score: 5,
    note: '（mock）只有团队量级',
  },
  {
    key: 'role_fit',
    label: '岗位契合度',
    full: 20,
    star: false,
    score: 16,
    note: '（mock）方向词表没出现',
  },
  { key: 'transferability', label: '技术可迁移性', full: 15, star: false, score: 10, note: '' },
  { key: 'project_depth', label: '项目深度与真实感', full: 20, star: false, score: 13, note: '' },
  { key: 'expression_structure', label: '表达与结构', full: 10, star: false, score: 6, note: '' },
  { key: 'advantage_section', label: '个人优势介绍', full: 5, star: false, score: 3, note: '' },
]

const DIAGNOSIS = {
  total_score: 65,
  grade: 'C',
  dimensions: DIMENSIONS,
  key_findings: ['指标责任与达成：（mock）没有个人达成数', '面试钩子设计：（mock）只有团队量级'],
  scale_note: '与简历评估报告同一张七维表：总分是七维相加，不是模型自己报的那一个。',
}

async function renderWithSummary(summaryReport) {
  api.startAutoAgent.mockResolvedValue({ run_id: 7 })
  api.getMultiAgentDetail.mockResolvedValue({
    run: { id: 7, status: 'completed', summary_report: summaryReport, selected_agents: [] },
    messages: [],
    results: [],
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/multi-agent', name: 'multi-agent', component: { template: '<div />' } }],
  })
  router.push('/multi-agent')
  await router.isReady()
  const wrapper = mount(MultiAgentAnalysis, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()

  await wrapper.find('textarea').setValue('看看这份简历')
  const start = wrapper.findAll('button').find((b) => b.text().includes('开始智能分析'))
  await start.trigger('click')
  await flushPromises()
  await flushPromises()

  const tab = wrapper.findAll('.el-tabs__item').find((t) => t.text().trim() === '简历诊断')
  await tab.trigger('click')
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  document.body.innerHTML = ''
  for (const fn of [...Object.values(api), ...Object.values(services.ElMessage)]) fn.mockClear()
})

describe('汇总报告里的简历诊断那一格', () => {
  it('显示七维相加的总分与等级，并写明用的是哪张表', async () => {
    const wrapper = await renderWithSummary({ report_title: '汇总', resume_diagnosis: DIAGNOSIS })
    const pane = wrapper.findAll('.el-tab-pane').find((p) => p.text().includes('七维总分'))

    expect(pane.text()).toContain('65 / 100')
    expect(pane.text()).toContain('C 档')
    expect(pane.text()).toContain('与简历评估报告同一张七维表')
    expect(pane.text()).toContain('指标责任与达成：')
    wrapper.unmount()
  })

  it('七维里有没读出来的就写未评分，不摆一个数', async () => {
    const wrapper = await renderWithSummary({
      report_title: '汇总',
      resume_diagnosis: { ...DIAGNOSIS, total_score: null, grade: null, key_findings: [] },
    })
    const pane = wrapper.findAll('.el-tab-pane').find((p) => p.text().includes('七维总分'))

    expect(pane.text()).toContain('未评分')
    expect(pane.text()).not.toContain('65 / 100')
    wrapper.unmount()
  })

  it('那一步没跑时这一格没有假数据，只说一句没有内容', async () => {
    const wrapper = await renderWithSummary({ report_title: '汇总' })
    const tabText = wrapper.findAll('.el-tab-pane').map((p) => p.text())

    expect(tabText.join('\n')).toContain('这次编排没跑「简历诊断」那一步')
    expect(tabText.join('\n')).not.toContain('七维总分')
    wrapper.unmount()
  })

  it('载荷里若混进旧那一格的自由分，也不上屏——这一格只认七维相加的那个数', async () => {
    const wrapper = await renderWithSummary({
      report_title: '汇总',
      resume_diagnosis: { score: 99, top_improvements: ['旧形状'], key_findings: [] },
    })
    const text = wrapper.text()

    expect(text).not.toContain('99')
    expect(text).not.toContain('旧形状')
    wrapper.unmount()
  })
})
