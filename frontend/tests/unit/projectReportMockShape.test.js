import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import mockProjectJob from '../fixtures/projectReportShape.json'
import ProjectReport from '@/features/resume/views/ProjectReport.vue'
import { installElement } from '@/plugins/element'

/* 单项目分析那一页对**后端真输出**的比对。夹具不是这里手搓的：
   `frontend/tests/fixtures/projectReportShape.json` 由
   `backend/scripts/collect_mock_project_report_shape.py` 从一条真跑完的作业（前三节 + 第四节
   各一行，provider=mock 不打补丁）导出，后端有反向守卫盯着它不过期
   （`backend/tests/test_mock_project_report_shape_fixture.py`）。
   两棵树各持一份形状的想象时，键名一漂就是"画少了但不报错"。 */

const api = vi.hoisted(() => ({
  getResumeList: vi.fn(),
  getResume: vi.fn(),
  createProjectReportJob: vi.fn(),
  getProjectReportJob: vi.fn(),
  createProjectQuestionsJob: vi.fn(),
  downloadProjectReportHtml: vi.fn(),
}))
const services = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/api/resume', () => api)
vi.mock('@/api/jd', () => ({ getJDList: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/plugins/element-services', () => services)

const DOC = mockProjectJob.report
const RESUME_ROW = { id: 1, name: '张三', file_name: 'mock.pdf' }

async function mountFromBackendBytes() {
  api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
  api.getResume.mockResolvedValue({
    id: 1,
    parsed: { project_experience: [{ name: DOC.excerpt.name, desc: '一句话项目正文' }] },
  })
  api.getProjectReportJob.mockResolvedValue(mockProjectJob)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/resume/project-report',
        name: 'project-report',
        component: { template: '<div />' },
      },
      { path: '/resume/center', name: 'resume-center', component: { template: '<div />' } },
    ],
  })
  await router.push({ name: 'project-report', query: { resume_id: '1', job_id: '1' } })
  await router.isReady()
  const wrapper = mount(ProjectReport, {
    attachTo: document.body,
    global: { plugins: [installElement, router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  for (const fn of [...Object.values(api), ...Object.values(services.ElMessage)]) fn.mockClear()
  document.body.innerHTML = ''
})

describe('后端真输出的单项目分析', () => {
  it('四大节都上屏，导航只有这四栏', async () => {
    const wrapper = await mountFromBackendBytes()
    for (const anchor of ['p-profile', 'p-diagrams', 'p-advice', 'p-questions']) {
      expect(wrapper.find(`#${anchor}`).exists()).toBe(true)
    }
    expect(wrapper.findAll('.pr-nav a')).toHaveLength(4)
  })

  it('六维表每行一条，位次那一行是排位的函数', async () => {
    const wrapper = await mountFromBackendBytes()
    const rows = wrapper.findAll('.scorecard tbody tr')
    expect(rows).toHaveLength(DOC.dimensions.length + 1) // 多出来的一行是合计
    // 落档那一格是"排第几"，不是这一维的得分：第 1 位拿 5 分。
    // 这条断言原来抄的是 `第 ${positional.score} 位`——把我自己的错钉成了期望，活页读出来才发现。
    const positional = DOC.dimensions.find((row) => row.positional)
    expect(DOC.contribution.rank).not.toBe(positional.score)
    expect(wrapper.find('#p-profile').text()).toContain(`第 ${DOC.contribution.rank} 位`)
    expect(wrapper.find('#p-profile').text()).not.toContain(`第 ${positional.score} 位`)
    expect(wrapper.find('#score-total').text()).toBe(DOC.score_cell)
    expect(wrapper.find('.scorecard .total').text()).toContain(DOC.grade)
  })

  it('合计取服务端算的那一个，不取模型自报的任何数', async () => {
    const wrapper = await mountFromBackendBytes()
    const sum = DOC.dimensions.reduce((acc, row) => acc + row.score, 0)
    // `#score-total` 这个 id 与下载那一份 HTML 同名：两份形态读的是同一个格子里同一个数。
    expect(wrapper.find('#score-total').text()).toBe(String(sum))
    expect(wrapper.find('.pr-pills').text()).toContain(`${DOC.total_score}/100`)
  })

  it('位次、系数与占比按后端装配好的那一句画', async () => {
    const wrapper = await mountFromBackendBytes()
    const pills = wrapper.find('.pr-pills').text()
    expect(pills).toContain(`简历第 ${DOC.contribution.rank} 个项目`)
    expect(pills).toContain(`系数 ${DOC.contribution.coefficient}`)
    expect(pills).toContain(`${DOC.contribution.share}%`)
  })

  it('四张图各自的格子、节点、泳道与深挖点都按载荷数量画', async () => {
    const wrapper = await mountFromBackendBytes()
    const figs = DOC.diagrams
    expect(figs.figures).toEqual(['function_arch', 'core_flow', 'system_arch', 'sequence'])
    expect(wrapper.findAll('#p-diagrams .pr-node')).toHaveLength(
      figs.core_flow.nodes.length + 2 // 输入与出口
    )
    expect(wrapper.findAll('#p-diagrams .pr-lane')).toHaveLength(figs.sequence.lanes.length)
    expect(wrapper.findAll('#p-diagrams .pr-mine')).toHaveLength(
      figs.function_arch.layers.filter((layer) => layer.mine).length
    )
    const sources = wrapper.findAll('#p-diagrams tbody tr td:last-child')
    const totalRows = Object.values(figs).reduce(
      (acc, value) => acc + (Array.isArray(value?.deep_dive) ? value.deep_dive.length : 0),
      0
    )
    expect(totalRows).toBeGreaterThan(0)
    expect(sources.length).toBeGreaterThanOrEqual(totalRows)
  })

  it('第三节五张表都在，必练题与高危题是第四节回填的那两个值', async () => {
    const wrapper = await mountFromBackendBytes()
    const advice = wrapper.find('#p-advice')
    for (const title of ['3.1', '3.2', '3.3', '3.4', '3.5']) {
      expect(advice.text()).toContain(title)
    }
    expect(advice.text()).toContain(DOC.advice.practice.must_practice)
    expect(advice.text()).toContain(DOC.advice.practice.high_risk)
    expect(wrapper.findAll('#p-advice .pr-table')).toHaveLength(5)
  })

  it('题目、追问、三态与配图数量都按后端数出来的那一份画', async () => {
    const wrapper = await mountFromBackendBytes()
    const dist = DOC.questions.distribution
    expect(wrapper.findAll('.pr-q')).toHaveLength(dist.total)
    expect(wrapper.findAll('.pr-lbl-z')).toHaveLength(dist.total * 2)
    expect(wrapper.findAll('.pr-st.danger')).toHaveLength(dist.high_risk)
    expect(wrapper.findAll('.pr-st.warn')).toHaveLength(dist.weak)
    expect(wrapper.findAll('.pr-dcards')).toHaveLength(dist.diagrammed)
    expect(wrapper.find('.pr-qstat').text()).toContain(`共 ${dist.total} 题`)
    expect(wrapper.find('.pr-qstat').text()).not.toContain(String(dist.target))
  })

  it('页面上不出现对内字眼：拒因、阶段失败、模型出处都不上屏', async () => {
    const wrapper = await mountFromBackendBytes()
    const text = wrapper.text()
    for (const word of [
      '兜底',
      '严格制',
      '软下限',
      '门禁',
      '可面试水位',
      '硬条件',
      '双轴',
      '收敛',
      '档内区分项',
    ]) {
      expect(text).not.toContain(word)
    }
    for (const key of [
      'stage_errors',
      'red_line_rejected',
      'diagram_rejected',
      'advice_rejected',
      'provenance',
      'error_msg',
    ]) {
      expect(text).not.toContain(key)
    }
  })

  it('【待补】那一段有底色，且不是靠 v-html 画出来的', async () => {
    const wrapper = await mountFromBackendBytes()
    const todos = wrapper.findAll('.todo-text')
    expect(todos.length).toBeGreaterThan(0)
    expect(todos[0].text()).toMatch(/^【待补：.*】$/)
    expect(wrapper.html()).not.toContain('v-html')
  })

  /* 项目下拉的键名必须和后端 `project_report_service.project_entries` 一样是两级回退：
     只读 `project_experience` 时，那种把项目存在 `projects` 里的简历在这页上就是"没解析出项目经历"，
     而后端拿着同一份 parsed_json 能算——两棵树各持一半退，界面就永远够不到那条链。 */
  async function mountFormOnly(parsed) {
    api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
    api.getResume.mockResolvedValue({ id: 1, parsed })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/resume/project-report',
          name: 'project-report',
          component: { template: '<div />' },
        },
        { path: '/resume/center', name: 'resume-center', component: { template: '<div />' } },
      ],
    })
    await router.push({ name: 'project-report', query: { resume_id: '1' } })
    await router.isReady()
    const wrapper = mount(ProjectReport, {
      attachTo: document.body,
      global: { plugins: [installElement, router] },
    })
    await flushPromises()
    await flushPromises()
    return wrapper
  }

  it('项目存在 projects 键上时，这一页也说得出有几个项目', async () => {
    const wrapper = await mountFormOnly({ projects: [{ name: '甲项目', desc: '做过的事' }] })
    expect(wrapper.text()).not.toContain('这份简历里没解析出项目经历')
    wrapper.unmount()
  })

  it('真的没有项目时，说的是没解析出项目经历，而不是把下拉空着让人猜', async () => {
    const wrapper = await mountFormOnly({})
    expect(wrapper.text()).toContain('这份简历里没解析出项目经历')
    wrapper.unmount()
  })
})
