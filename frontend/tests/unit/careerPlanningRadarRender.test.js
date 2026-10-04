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

  it('模型把分数写成"约60"时：那一角**退出折线**，那一行标暂无数据', async () => {
    /* `career_planning` 是 LLM 原始 JSON，分数字段没有任何约束（career_agent.py:55 的 chat_json）。
       这一条原来钉的是"页面上不出现 NaN"，并且把 `safeScore` 的重夹当成既成事实接受了——
       D113（§10.20）换成了拍定后的口径：读不懂的维度不进雷达、不算提升空间、不显示分数。
       三个维度里 middle 那个读不懂，所以折线**只有两个顶点**，而且第二行的文案是"暂无数据"。
       搬家前这里会是：三角折线 + 一个塌在圆心的角 + "90 分提升空间"（0→90 的假差距）。 */
    state.dimensions = [
      { name: '工程能力', current_score: 80, target_score: 95 },
      { name: '分布式', current_score: '约60', target_score: 90 },
      { name: '沟通协作', current_score: 20, target_score: 60 },
    ]
    await renderPlanned()

    // 折线：剩下两个可画的轴，顶点与两轴夹具完全一致——少的那个角没有被摆在圆心
    expect(polygonPoints('.radar-current-shape')).toBe('160.00,67.20 160.00,183.20')
    expect(polygonPoints('.radar-target-shape')).toBe('160.00,49.80 160.00,229.60')
    expect(axisLabels()).toEqual([
      ['160', '20', '工程能力'],
      ['160', '300', '沟通协作'],
    ])

    // 列表仍然三行：候选人有权知道是哪一个维度没读出来
    const rows = [...document.querySelectorAll('.radar-row')]
    expect(rows).toHaveLength(3)
    const texts = rows.map((row) => row.textContent.replace(/\s+/g, ' ').trim())
    expect(texts.join(' | ')).not.toContain('NaN')
    expect(texts[0]).toContain('15 分提升空间')
    expect(texts[1]).toContain('分布式')
    expect(texts[1]).toContain('暂无数据')
    expect(texts[1]).not.toMatch(/\d+ 分提升空间/)
    expect(texts[2]).toContain('40 分提升空间')

    // 不可读那一行不给宽度：一条空轨道读起来就是"0 分"，和这次要取消的谎是同一句话
    expect([...document.querySelectorAll('.bar-current')].map((n) => n.style.width)).toEqual([
      '80%',
      '20%',
    ])
    expect([...document.querySelectorAll('.bar-target')].map((n) => n.style.width)).toEqual([
      '95%',
      '60%',
    ])
    // 分数列也只有两行有数字
    expect(
      [...document.querySelectorAll('.radar-values')].map((n) => n.textContent.replace(/\s+/g, ''))
    ).toEqual(['8095', '2060'])
  })

  it('整份报告都读不懂时：不是一张空白方框，是一个空态', async () => {
    state.dimensions = [
      { name: '工程能力', current_score: '约80', target_score: '约95' },
      { name: '分布式', current_score: null, target_score: 90 },
    ]
    await renderPlanned()
    expect(document.querySelector('.radar-svg')).toBeNull()
    expect(document.querySelector('.el-empty__description')?.textContent).toContain(
      '没有可读出的分数'
    )
    const texts = [...document.querySelectorAll('.radar-row')].map((row) =>
      row.textContent.replace(/\s+/g, ' ').trim()
    )
    expect(texts).toHaveLength(2)
    expect(texts.every((t) => t.includes('暂无数据'))).toBe(true)
    expect(document.querySelectorAll('.bar-current, .bar-target')).toHaveLength(0)
  })
})
