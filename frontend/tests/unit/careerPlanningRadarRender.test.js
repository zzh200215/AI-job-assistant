import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElInput } from 'element-plus'

import CareerPlanning from '@/features/planning/views/CareerPlanning.vue'
import { installElement } from '@/plugins/element'

/* 这一页的雷达是**真算出来的 SVG 坐标**：圆心 160、半径 116、标签再往外 24。D53 把
   `makeRadarPolygon` / `safeScore` 搬进 lib、把这两个常量也搬进 lib 之后，页面只剩"传参"这一层
   接线，而接错是**不会报错的**：把 `RADAR_CENTER_POINT` 与 `RADAR_RADIUS` 的别名对调，圆心变成
   116、半径变成 160，图形照样画得出来，只是整张图偏移、标签戳出画布。
   所以这里断言的是屏幕上的坐标字符串，而不是函数返回值（函数那层由
   planningModelMoveProof.test.js 钉）。 */

vi.mock('@/api/resume', () => ({
  getResumeList: vi.fn(async () => ({
    items: [{ id: 7, name: '后端三年', parsed: { current_title: '后端工程师' } }],
    total: 1,
  })),
}))

vi.mock('@/api/jd', () => ({
  getJDList: vi.fn(async () => ({ items: [], total: 0 })),
  createJD: vi.fn(async () => ({ id: 9 })),
  parseJD: vi.fn(async () => ({})),
}))

const state = { dimensions: null }

const DEFAULT_DIMENSIONS = [
  { name: '工程能力', current_score: 80, target_score: 95 },
  { name: '分布式', current_score: 20, target_score: 60 },
]

state.dimensions = DEFAULT_DIMENSIONS

function analysisRecord(dimensions) {
  return {
    record_id: 55,
    match_score: 72,
    career_planning: {
      skill_radar: { dimensions },
      visual_roadmap: { phases: [] },
      skill_gaps: [],
      project_recommendations: [],
    },
  }
}

vi.mock('@/api/analysis', () => ({
  runFullAnalysis: vi.fn(async () => ({ task_id: 't1' })),
  // 由测试自己写 recordedDimensions：不靠 mockResolvedValueOnce 的"下一次"语义，
  // 免得被别的调用消费掉之后测试静默地测着默认夹具（第一版就是这么假绿的）。
  getAnalysis: vi.fn(async () => analysisRecord(state.dimensions)),
}))

vi.mock('@/api/jobs', () => ({
  recommendCareerPaths: vi.fn(async () => ({ career_paths: [], summary: '', corpus: {} })),
}))

vi.mock('@/api/salary', () => ({
  getSalaryOverview: vi.fn(async () => ({ has_data: false, statistics: {} })),
}))

vi.mock('@/composables/useAgentTaskPolling', () => ({
  useAgentTaskPolling: () => ({
    isPolling: { value: false },
    pollTask: async (_id, handlers) => {
      handlers.onProgress({ status: 'completed' }, [
        { step_name: 'career_planning', status: 'completed' },
      ])
      await handlers.onCompleted({ status: 'completed', analysis_record_id: 55 })
    },
  }),
}))

async function renderPlanned() {
  const route = {
    path: '/career-planning',
    name: 'career-planning',
    component: { template: '<div />' },
  }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/career-planning')
  await router.isReady()
  const wrapper = mount(CareerPlanning, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()

  const roleInput = wrapper
    .findAllComponents(ElInput)
    .find((w) => (w.props('placeholder') || '').includes('AI 应用工程师'))
  roleInput.vm.$emit('update:modelValue', '平台后端工程师')
  await flushPromises()

  await wrapper.find('.action-buttons button:last-child').trigger('click')
  await flushPromises()
  return wrapper
}

function polygonPoints(selector) {
  return document.querySelector(selector)?.getAttribute('points') ?? null
}

function axisLabels() {
  return [...document.querySelectorAll('.radar-text')].map((t) => [
    t.getAttribute('x'),
    t.getAttribute('y'),
    t.textContent.trim(),
  ])
}

describe('雷达图上的坐标来自 lib 的那两个常量', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    state.dimensions = DEFAULT_DIMENSIONS
  })

  it('当前分与目标分两张折线的顶点字符串', async () => {
    await renderPlanned()
    /* 两个维度：正上方与正下方。圆心 160、半径 116 ⇒ 满分顶点在 44 / 276。
       current 80 → 160−92.8 = 67.20，20 → 160+23.2 = 183.20
       target  95 → 160−110.2 = 49.80，60 → 160+69.6 = 229.60 */
    expect(polygonPoints('.radar-current-shape')).toBe('160.00,67.20 160.00,183.20')
    expect(polygonPoints('.radar-target-shape')).toBe('160.00,49.80 160.00,229.60')
  })

  it('四条参考环与两根轴线的标签各在其位', async () => {
    await renderPlanned()
    expect(document.querySelectorAll('.radar-ring').length).toBe(4)
    // 25% 那一环：半径 29 ⇒ 顶点 131 与 189
    expect(polygonPoints('.radar-ring')).toBe('160.00,131.00 160.00,189.00')
    expect(axisLabels()).toEqual([
      ['160', '20', '工程能力'],
      ['160', '300', '分布式'],
    ])
  })

  it('轴线从圆心出发，端点落在半径上', async () => {
    await renderPlanned()
    const axis = document.querySelector('.radar-axis')
    expect([axis.getAttribute('x1'), axis.getAttribute('y1')]).toEqual(['160', '160'])
    expect([axis.getAttribute('x2'), axis.getAttribute('y2')]).toEqual(['160', '44'])
  })

  it('模型把分数写成"约80"时，页面上不出现 NaN', async () => {
    /* `career_planning` 是 LLM 原始 JSON，分数字段没有任何约束（career_agent.py:55 的 chat_json）。
       这条用例一开始是为了钉"NaN 一路传进 SVG 的 points、整张雷达静默消失"——**那个前提是错的**：
       页面把 `safeScore` 套了两次（`map(safeScore)` 之后 `makeRadarPolygon` 内部又夹一次），
       而 `Number(NaN || 0)` 恰好是 0，所以折线被这道意外的重夹保护住了。
       真正没被保护的是**只夹一次**的那几处：`.radar-values` 的两个分数、"N 分提升空间"那行字，
       以及 `width: NaN%`（非法值被浏览器忽略，条子直接不画）。所以这里钉的是那几处。 */
    state.dimensions = [
      { name: '工程能力', current_score: '约80', target_score: 95 },
      { name: '分布式', current_score: 20, target_score: '未知' },
    ]
    await renderPlanned()
    const metrics = [...document.querySelectorAll('.radar-row')].map((row) =>
      row.textContent.replace(/\s+/g, ' ').trim()
    )
    expect(metrics.join(' | ')).not.toContain('NaN')
    expect(metrics[0]).toContain('95 分提升空间')
    expect(metrics[1]).toContain('20 分提升空间')
    const widths = [...document.querySelectorAll('.bar-current, .bar-target')].map((n) =>
      n.getAttribute('style')
    )
    expect(widths.join(' ')).not.toContain('NaN')
    /* 折线那两串照旧钉住：它们同时也是"重夹"这一事实的证据——单应用 safeScore 时同样的输入
       会产出 NaN,NaN（见 planningModelMoveProof 里那条）。 */
    expect(polygonPoints('.radar-current-shape')).toBe('160.00,160.00 160.00,183.20')
    expect(polygonPoints('.radar-target-shape')).toBe('160.00,49.80 160.00,160.00')
  })
})
