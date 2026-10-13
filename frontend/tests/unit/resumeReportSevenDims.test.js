import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeUpload from '@/features/resume/views/ResumeUpload.vue'
import { installElement } from '@/plugins/element'

/* 诊断弹窗换成七维口径之后，这一族钉子量的是"七行真的都画上、每行按自己那维的满分画"。
   抽走维度或把比例算错都不会报错，只会少画一根条、或者把"个人优势 5/5"画成一根 5% 的空条
   （`frontend-extraction-wiring-needs-screen-assertions` 记的就是这一族）。 */

const api = vi.hoisted(() => ({
  uploadResume: vi.fn(),
  parseResume: vi.fn(),
  getResumeList: vi.fn(),
  getResumeVersions: vi.fn(),
  getResumeQuickScore: vi.fn(),
  diagnoseResume: vi.fn(),
  getRewriteSuggestions: vi.fn(),
  applyResumeRewrites: vi.fn(),
  deleteResume: vi.fn(),
  generateOptimized: vi.fn(),
  exportResume: vi.fn(),
  downloadResumeExport: vi.fn(),
}))

vi.mock('@/api/resume', () => api)

const row = (id, name) => ({
  id,
  file_name: name,
  name,
  status: 'ready',
  create_time: '2026-09-01T00:00:00Z',
  parsed: { current_title: '后端工程师' },
})

const SEVEN = [
  ['metric_ownership', '指标责任与达成（C）★', 20, 11],
  ['interview_hooks', '面试钩子设计（E）★', 10, 5],
  ['role_fit', '岗位契合度（赛道定位）', 20, 12],
  ['transferability', '技术可迁移性', 15, 9],
  ['project_depth', '项目深度与真实感', 20, 12],
  ['expression_structure', '表达与结构', 10, 8],
  ['advantage_section', '个人优势介绍', 5, 5],
]

const diagnosis = (overrides = {}) => ({
  total_score: 62,
  grade: 'D',
  grade_desc: '先补齐再谈投递',
  grade_scale: 'A 85–100 / B 75–84 / C 65–74 / D 0–64',
  report_date: '2026-10-13',
  dimensions: SEVEN.map(([key, label, full, score], i) => ({
    key,
    label,
    full,
    star: i < 2,
    score,
    note: i === 0 ? '三个指标都只有绝对值' : '',
  })),
  verdict: { direction: 'RAG 应用（Agent / Workflow）', target_level: '中级' },
  to_next_grade: ['两个项目各补 1 处「优化前 → 优化后」'],
  missing_keywords: ['Kubernetes', '成本治理'],
  competition: {
    positioning_badge: 'B 档（中上）',
    positioning_note: '这里评的是背景在同类人里站哪',
    cards: ['检索链路与 Agent 流程都是我搭的'],
    gaps: ['指标缺优化前基线，1–2 天能补'],
    advice: ['锁定 RAG / Agent 应用开发的中级岗'],
    salary_note: '未提供期望薪资，按中级档给参考 12K–15K',
    salary_provided: false,
  },
  completeness_issues: [],
  completeness_score: 72,
  completeness_grade: 'B',
  module_check: {},
  ...overrides,
})

let router

async function openDiagnosis(payload) {
  api.getResumeList.mockResolvedValue({ items: [row(1, '简历甲')], total: 1 })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/resume/upload', name: 'resume-upload', component: { template: '<div />' } }],
  })
  router.push('/resume/upload')
  await router.isReady()
  const wrapper = mount(ResumeUpload, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()

  api.diagnoseResume.mockResolvedValue(payload)
  wrapper.vm.showDiagnosisDialog(row(1, '简历甲'))
  await flushPromises()
  await flushPromises()
  // 折叠面板默认收起，展开后内容才读得到。
  wrapper.vm.diagActivePanels = ['notes', 'next', 'competition', 'completeness', 'keywords']
  await flushPromises()
  return wrapper
}

const dimItems = () => [...document.querySelectorAll('.diag-dim-item')]
const barWidthOf = (item) =>
  item.querySelector('.el-progress-bar__inner')?.attributes.getNamedItem('style')?.value

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  api.getResumeVersions.mockResolvedValue({ versions: [] })
  api.getResumeQuickScore.mockResolvedValue({ score: 60 })
  api.parseResume.mockResolvedValue({ parsed: {} })
  api.deleteResume.mockResolvedValue({})
  api.getRewriteSuggestions.mockResolvedValue({})
  api.applyResumeRewrites.mockResolvedValue({})
  api.generateOptimized.mockResolvedValue({})
  api.exportResume.mockResolvedValue({})
  api.downloadResumeExport.mockResolvedValue(new Blob(['x']))
})

describe('七维评分概览上屏', () => {
  it('七行都画上，每行带着自己的满分', async () => {
    await openDiagnosis(diagnosis())

    const items = dimItems()
    expect(items).toHaveLength(7)
    expect(items.map((el) => el.querySelector('.dim-label span').textContent.trim())).toEqual(
      SEVEN.map(([, label]) => label)
    )
    expect(items[0].querySelector('strong').textContent).toBe('11 / 20')
    expect(items[6].querySelector('strong').textContent).toBe('5 / 5')
  })

  it('条与色按该维满皮的几成，不是原始分', async () => {
    await openDiagnosis(diagnosis())

    const items = dimItems()
    // 5/5 那一维必须画满；按原始分上色就是 5%，看起来像个塌陷项。
    expect(barWidthOf(items[6])).toContain('width: 100%')
    expect(barWidthOf(items[0])).toContain('width: 55%')
  })

  it('读不出分的那一维说"未给出"，并且不画一根空条', async () => {
    const payload = diagnosis()
    payload.dimensions = payload.dimensions.map((d) =>
      d.key === 'role_fit' ? { ...d, score: null } : d
    )

    await openDiagnosis(payload)

    const missing = dimItems()[2]
    expect(missing.querySelector('.dim-none').textContent).toBe('本次分析未给出该维度评分')
    expect(missing.querySelector('.el-progress')).toBeNull()
    expect(missing.querySelector('strong').textContent).toBe('— / 20')
  })

  it('评级与总分同屏，未知时不画 0', async () => {
    await openDiagnosis(diagnosis())

    expect(document.querySelector('.diag-score-label').textContent.trim()).toBe('D 级 · 七维合计')
    expect(document.querySelector('.gauge-text').textContent.trim()).toBe('62')
  })

  it('总分未知时量表写"未评分"，等级那半句整个消失', async () => {
    const payload = diagnosis()
    payload.total_score = null
    payload.grade = null
    payload.dimensions = payload.dimensions.map((d) => ({ ...d, score: null }))

    await openDiagnosis(payload)

    expect(document.querySelector('.gauge-text').textContent.trim()).toBe('未评分')
    expect(document.querySelector('.diag-score-label').textContent.trim()).toBe('七维合计')
  })

  it('首屏结论段那行念出方向、目标等级与日期', async () => {
    const wrapper = await openDiagnosis(diagnosis())

    const verdict = [...document.querySelectorAll('.diag-note')].map((el) => el.textContent)
    expect(verdict.join(' ')).toContain('方向定位：RAG 应用（Agent / Workflow）')
    expect(verdict.join(' ')).toContain('目标等级：中级')
    expect(verdict.join(' ')).toContain('日期：2026-10-13')
    expect(wrapper.vm.currentDiagnosis.model_reported_total).toBeUndefined()
  })

  it('待优化点只列模型真写过的那几维', async () => {
    await openDiagnosis(diagnosis())

    const notes = [...document.querySelectorAll('.diag-issue')].filter((el) =>
      el.textContent.includes('指标责任与达成')
    )
    expect(notes).toHaveLength(1)
    expect(notes[0].textContent).toContain('三个指标都只有绝对值')
  })

  it('竞争分析把档位、牌、短板、建议与薪资口径分列出来', async () => {
    await openDiagnosis(diagnosis())

    const body = document.querySelector('.diag-details').textContent
    expect(body).toContain('B 档（中上）')
    expect(body).toContain('这里评的是背景在同类人里站哪')
    expect(body).toContain('能打的牌：检索链路与 Agent 流程都是我搭的')
    expect(body).toContain('要补的短板：指标缺优化前基线，1–2 天能补')
    expect(body).toContain('针对性建议：锁定 RAG / Agent 应用开发的中级岗')
    expect(body).toContain('期望薪资：未提供期望薪资，按中级档给参考 12K–15K')
    expect(body).toContain('距上一档还差什么')
    expect(body).toContain('两个项目各补 1 处「优化前 → 优化后」')
  })

  it('竞争分析整块缺席时给一句"未给出"，不是一片空白', async () => {
    const payload = diagnosis()
    payload.competition = {
      positioning_badge: '',
      cards: [],
      gaps: [],
      advice: [],
      salary_note: '',
    }
    payload.to_next_grade = []
    payload.dimensions = payload.dimensions.map((d) => ({ ...d, note: '' }))

    await openDiagnosis(payload)

    const body = document.querySelector('.diag-details').textContent
    expect(body).toContain('本次分析未给出竞争分析')
    expect(body).toContain('本次分析未给出升档项')
    expect(body).toContain('本次分析没有逐维写出待优化点')
  })

  it('完整度那一屏仍写着它是规则检查，不与七维混读', async () => {
    const payload = diagnosis()
    payload.completeness_issues = ['缺少教育背景']

    await openDiagnosis(payload)

    const titles = [...document.querySelectorAll('.el-collapse-item__header')].map(
      (el) => el.textContent
    )
    expect(titles.join(' ')).toContain('模块完整度（规则检查，非 AI）')
    expect(document.querySelector('.diag-details').textContent).toContain('缺少教育背景')
  })
})
