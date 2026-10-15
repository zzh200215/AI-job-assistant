import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import mockPortfolioJob from '../fixtures/portfolioReportShape.json'
import mockPortfolioJob4 from '../fixtures/portfolioReportShape4.json'
import PortfolioReport from '@/features/resume/views/PortfolioReport.vue'
import { installElement } from '@/plugins/element'

/* 组合分析那一页对**后端真输出**的比对。夹具不是这里手搓的：
   `frontend/tests/fixtures/portfolioReportShape.json` 由
   `backend/scripts/collect_mock_portfolio_report_shape.py` 从一条真跑完的作业
   （前三节 + 第四节各一行，provider=mock 不打补丁）导出，
   后端有反向守卫盯着它不过期（`backend/tests/test_portfolio_mock_shape_fixture.py`）。
   两棵树各持一份形状的想象时，键名一漂就是"画少了但不报错"。 */

const api = vi.hoisted(() => ({
  getResumeList: vi.fn(),
  getResume: vi.fn(),
  createPortfolioReportJob: vi.fn(),
  getPortfolioReportJob: vi.fn(),
  createPortfolioQuestionsJob: vi.fn(),
  downloadPortfolioReportHtml: vi.fn(),
}))
const services = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/api/resume', () => api)
vi.mock('@/api/jd', () => ({ getJDList: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/plugins/element-services', () => services)

const DOC = mockPortfolioJob.report
const RESUME_ROW = { id: 1, name: '张三', file_name: 'mock.pdf' }

async function mountFromBackendBytes(job = mockPortfolioJob) {
  const doc = job.report
  api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
  api.getResume.mockResolvedValue({
    id: 1,
    parsed: { project_experience: doc.projects.map((p) => ({ name: p.name })) },
  })
  api.getPortfolioReportJob.mockResolvedValue(job)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/resume/portfolio-report',
        name: 'portfolio-report',
        component: { template: '<div />' },
      },
      { path: '/resume/center', name: 'resume-center', component: { template: '<div />' } },
    ],
  })
  await router.push({ name: 'portfolio-report', query: { resume_id: '1', job_id: '1' } })
  await router.isReady()
  const wrapper = mount(PortfolioReport, {
    global: { plugins: [installElement, router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  for (const fn of [...Object.values(api), ...Object.values(services.ElMessage)]) fn.mockClear()
})

describe('后端真输出的组合分析', () => {
  it('四大节都上屏，导航只有这四栏', async () => {
    const wrapper = await mountFromBackendBytes()
    for (const anchor of ['c-profile', 'c-diagrams', 'c-advice', 'c-questions']) {
      expect(wrapper.find(`#${anchor}`).exists()).toBe(true)
    }
    expect(wrapper.findAll('.pf-nav a')).toHaveLength(4)
  })

  it('合计那一格用的是服务端那一个数', async () => {
    const wrapper = await mountFromBackendBytes()
    const total = wrapper.find('.pf-tbl tr.total td.n b').text()
    expect(total).toBe(DOC.score_cell)
    expect(wrapper.text()).toContain('组合评分')
  })

  it('位次那一格的落档写的是占了第几位到哪几位，不是这一维的得分', async () => {
    const wrapper = await mountFromBackendBytes()
    const row = DOC.dimensions.find((item) => item.positional)
    // 这条钉的是 D236 活页量出来的那一处错：把得分当位次会打成"第 4 位"（得分是 4，位次是 1~3）。
    expect(row.score).not.toBe(row.span[1])
    const bands = wrapper.findAll('.pf-tbl tbody tr td:nth-child(4)').map((cell) => cell.text())
    expect(bands).toContain(`第 ${row.span[0]}~${row.span[1]} 位`)
    expect(bands.join(' ')).not.toContain(`第 ${row.score} 位`)
  })

  it('表头那一排把项目数与单项目均分都按服务端的话画', async () => {
    const wrapper = await mountFromBackendBytes()
    const pills = wrapper.findAll('.pf-pill').map((node) => node.text())
    expect(pills.join(' ')).toContain(`项目数${DOC.project_count} 个`)
    expect(pills.join(' ')).toContain(`单项目均分${DOC.average_cell}`)
    // 「单项目均分」这一格只有一份跑过时才带那句"只有 1/3 个跑过"，不是猜的数。
    expect(DOC.average_cell).toContain('1/3')
  })

  it('横向对比是七行乘三个项目，一格不落', async () => {
    const wrapper = await mountFromBackendBytes()
    const table = wrapper.findAll('.pf-tbl')[1]
    expect(table.findAll('thead th')).toHaveLength(DOC.project_count + 1)
    expect(table.findAll('tbody tr')).toHaveLength(DOC.compare.rows.length)
    for (const row of table.findAll('tbody tr')) {
      expect(row.findAll('td')).toHaveLength(DOC.project_count + 1)
      expect(row.text()).not.toContain('undefined')
    }
  })

  it('覆盖那一列画的是服务端按格子推出来的那一句', async () => {
    const wrapper = await mountFromBackendBytes()
    const rows = wrapper.findAll('.pf-matrix tbody tr')
    expect(rows).toHaveLength(DOC.capabilities.length)
    const MARK = { 重点覆盖: '●', 部分覆盖: '○', 未覆盖: '' }
    const cellOf = (row, index) => row.cells[index] ?? row.cells[String(index)] ?? '未覆盖'
    DOC.capabilities.forEach((row, position) => {
      const marks = rows[position].findAll('td.cov').map((cell) => cell.text())
      expect(marks).toEqual(DOC.projects.map((p) => MARK[cellOf(row, p.project_index)]))
      expect(rows[position].find('td:last-child').text()).toBe(
        `${row.verdict.word}（${row.verdict.detail}）`
      )
    })
    // 这一组里既要有一行是全项目重点覆盖（极强），也要有一行不是——否则"由格子推结论"
    // 这条判据在夹具上根本分不出真假。
    const words = DOC.capabilities.map((row) => row.verdict.word)
    expect(words).toContain('极强')
    expect(words.some((word) => word !== '极强')).toBe(true)
  })

  it('叙事主线一段一个项目，段里不出现没勾的项目', async () => {
    const wrapper = await mountFromBackendBytes()
    const nodes = wrapper.findAll('.pf-node')
    expect(nodes).toHaveLength(DOC.project_count)
    const codes = DOC.diagrams.narrative.stages.map((stage) => stage.code)
    expect(new Set(codes).size).toBe(codes.length)
    for (const stage of DOC.diagrams.narrative.stages) {
      expect(wrapper.text()).toContain(stage.code)
    }
  })

  it('共用栈那一栏画的是服务端交集算出来的那几只', async () => {
    const wrapper = await mountFromBackendBytes()
    const chips = wrapper.findAll('.pf-chip:not(.grey)').map((node) => node.text())
    expect(chips).toEqual(DOC.diagrams.stack.shared)
    expect(chips.length).toBeGreaterThan(0)
  })

  it('面试时序五轮都在，胜负手标在那两轮上', async () => {
    const wrapper = await mountFromBackendBytes()
    expect(wrapper.findAll('.pf-round')).toHaveLength(5)
    expect(wrapper.findAll('.pf-star')).toHaveLength(2)
  })

  it('使用建议四张表都有内容', async () => {
    const wrapper = await mountFromBackendBytes()
    const text = wrapper.find('#c-advice').text()
    for (const heading of [
      '3.1 项目排列建议',
      '3.2 面试叙事建议',
      '3.3 补强路径',
      '3.4 引用红线',
    ]) {
      expect(text).toContain(heading)
    }
    // 排列那一格是服务端渲染的代号串，不是模型自己拼的项目名。
    expect(wrapper.find('#c-advice').text()).toContain('PJ-0')
    expect(wrapper.findAll('#c-advice .pf-tbl')[0].findAll('tbody tr')).toHaveLength(
      DOC.advice.arrangements.length
    )
  })

  it('第四节 12 题都上屏，每题两轮追问', async () => {
    const wrapper = await mountFromBackendBytes()
    const items = wrapper.findAll('.pf-qst')
    expect(items).toHaveLength(DOC.questions.questions.length)
    expect(wrapper.find('.pf-qstat').text()).toContain(`共 ${DOC.questions.questions.length} 题`)
    for (const item of items) {
      expect(item.findAll('.pf-fu')).toHaveLength(2)
    }
    expect(wrapper.find('.pf-st.warn').exists()).toBe(true)
  })

  it('出局那一形态：没有分数，也没有题目', async () => {
    const excluded = JSON.parse(JSON.stringify(mockPortfolioJob))
    excluded.report.excluded = true
    excluded.report.excluded_note = '这一份组合分析不给总分与等级：下面几条里有一条踩中了。'
    excluded.report.excluded_by = [
      {
        key: 'duplicate_projects',
        label: '同一个项目换名字写了两遍',
        quote: 'PJ-02 与 PJ-03 逐字相同',
        why: '换皮',
      },
    ]
    excluded.report.score_cell = '不作数'
    excluded.report.total_score = null
    excluded.report.grade = null
    excluded.report.questions_state = 'deferred'
    excluded.report.questions = { deferred: true, note: '这一节先不出题。', questions: [] }
    api.getPortfolioReportJob.mockResolvedValue(excluded)
    api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
    api.getResume.mockResolvedValue({
      id: 1,
      parsed: { project_experience: [{ name: '甲' }, { name: '乙' }] },
    })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/resume/portfolio-report',
          name: 'portfolio-report',
          component: { template: '<div />' },
        },
        { path: '/resume/center', name: 'resume-center', component: { template: '<div />' } },
      ],
    })
    await router.push({ name: 'portfolio-report', query: { resume_id: '1', job_id: '1' } })
    await router.isReady()
    const wrapper = mount(PortfolioReport, { global: { plugins: [installElement, router] } })
    await flushPromises()
    await flushPromises()

    expect(wrapper.find('.pf-redline').exists()).toBe(true)
    expect(wrapper.findAll('.pf-qst')).toHaveLength(0)
    expect(wrapper.find('.pf-tbl tr.total td.n b').text()).toBe('不作数')
    expect(wrapper.text()).toContain('按口径不出跨项目的题')
  })

  it('页面上不出现内部机制字眼与省略写法', async () => {
    const wrapper = await mountFromBackendBytes()
    const text = wrapper.text()
    for (const word of ['兜底', '严格制', '软下限', '门禁', '出局阈值', '硬条件']) {
      expect(text).not.toContain(word)
    }
    expect(text).not.toMatch(/\*\*/)
  })

  it('那句"几把尺"真的上屏了，不是只住在脚本里', async () => {
    const wrapper = await mountFromBackendBytes()
    // 静态那条钉子只能证明"这行字在文件里"；模板忘了插值时它照样绿，
    // 而读者拿到的是少一句话的交付物——这条按**渲染出来的文字**比。
    expect(wrapper.find('#c-profile').text()).toContain('树里有三把尺')
    expect(wrapper.find('#c-profile').text()).toContain('三把尺的分数不能直接比')
  })
})

/* 四个项目的那一组是**后端另一条真派发**导出的夹具（同一支 collector 一次跑出来），
   不是这里手搓的形状。参考件只有三个项目，N 变大时页面那棵树上有三处要跟着长：
   对比表的列、叙事主线的段、覆盖矩阵的格子；排列那一格还要多画一个箭头。 */
describe('后端真输出的四个项目一组', () => {
  const DOC4 = mockPortfolioJob4.report
  const N = DOC4.project_count

  it('列数、段数、格子数、箭头数都跟着勾选长', async () => {
    expect(N).toBe(4)
    const wrapper = await mountFromBackendBytes(mockPortfolioJob4)
    const compare = wrapper.findAll('#c-profile table')[1]
    expect(compare.findAll('thead th')).toHaveLength(N + 1)
    expect(compare.findAll('tbody tr')).toHaveLength(DOC4.compare.rows.length)
    for (const row of compare.findAll('tbody tr')) {
      expect(row.findAll('td')).toHaveLength(N + 1)
    }
    expect(wrapper.findAll('.pf-node')).toHaveLength(N)
    expect(wrapper.findAll('.pf-matrix tbody tr')[0].findAll('td.cov')).toHaveLength(N)
    const firstArrangement = wrapper.findAll('#c-advice table')[0].find('tbody tr').text()
    expect(firstArrangement).toContain('PJ-04')
    expect(firstArrangement.match(/→/g)).toHaveLength(N - 1)
  })

  it('表头那两格说的是四个项目与 1/4 的出处', async () => {
    const wrapper = await mountFromBackendBytes(mockPortfolioJob4)
    const pills = wrapper.findAll('.pf-pill').map((node) => node.text())
    expect(pills[0]).toBe(`项目数${N} 个`)
    expect(pills.join(' ')).toContain('1/4')
    expect(wrapper.text()).not.toContain('undefined')
    expect(wrapper.text()).not.toContain('NaN')
  })
})
