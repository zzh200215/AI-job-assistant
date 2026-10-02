import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import AnalysisResult from '@/features/analysis/views/AnalysisResult.vue'
import HistoryView from '@/features/shell/views/History.vue'
import { getAnalysis } from '@/api/analysis'
import { getHistoryDetail } from '@/api/history'
import { Clock } from '@element-plus/icons-vue'
import { installElement } from '@/plugins/element'

/* D82 把 `x.item || x` 这一族从三个屏幕上收掉（技能匹配面板 D81、这一页、历史记录详情）。
   两边钉的是**收窄之后每一代写法还剩什么**：
   - 裸字符串 → 字符串本身就是标签；
   - 对象带 item → 标签 + 补语（差距那一列 action 优先，History 还带那颗严重度标签）；
   - 对象没有 item（生产端 `normalizeLocalizedObjectList` 给的是空串而不是缺字段）→
     标签整颗不出、补语前面那颗冒号跟着撤，**绝不把对象画成 JSON**——§10.23 拍板要改的就是这一支。
   为什么两页各要一份：收窄点从模板搬到了页面的 computed 上（`.map(rubricRow)`），漏一处的后果
   是"整列空"或"画一坨 JSON"，而 D51 那条教训说过——这类接线错不报错，只是少画。
   类型门这一轮确实开始盯了（`localizedGaps` 现在是 `RubricRow[]`，模板再读 `x.item` 会红），
   但"读对了键、画错了东西"仍然只有屏幕看得见。 */

/** 三列的输入：两代写法 + 那一支空 item 的对象，一次全喂进去。 */
function rubric() {
  return {
    strengths: [
      '项目主导',
      { item: 'Go 并发', impact: '命中必需项', evidence: 'JD 第 2 条' },
      { impact: '只有补语没有标签' },
    ],
    gaps: [
      { item: 'Rust', action: '补一个副作用示例', severity: '高' },
      { action: '没有标签的一条', severity: '中' },
    ],
    risk_points: ['经验年限偏低'],
  }
}

function record(overrides = {}) {
  return {
    id: 9,
    record_id: 9,
    match_report: {
      overall_score: 82,
      recommendation: '可以投递',
      summary: '整体匹配',
      ...rubric(),
    },
    final_report: null,
    interview_questions: {},
    optimization_suggestions: {},
    ...overrides,
  }
}

/* 用 importOriginal 摊开真模块再覆盖要注的那几个：这两个页面各自还拖着别的 api
   （轮询、重新生成），只列一两个名字的 mock 会让别的 import 变成 undefined。 */
vi.mock('@/api/analysis', async (importOriginal) => ({
  ...(await importOriginal()),
  getAnalysis: vi.fn(),
  regenOptimize: vi.fn(async () => ({})),
  regenInterview: vi.fn(async () => ({})),
}))

vi.mock('@/api/history', async (importOriginal) => ({
  ...(await importOriginal()),
  listHistory: vi.fn(async () => ({ items: [{ id: 7, match_score: 88 }], total: 1 })),
  getHistoryDetail: vi.fn(),
  deleteHistory: vi.fn(async () => ({})),
}))

vi.mock('@/api/agent', async (importOriginal) => ({
  ...(await importOriginal()),
  startAgentAnalysis: vi.fn(async () => ({ task_id: 'never-polled' })),
}))

function mountPage(component, routeRecord, to) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: routeRecord, component },
    ],
  })
  // router.push 之后必须等 isReady，否则页面里 `watch(() => route.params.id, ..., { immediate: true })`
  // 在 setup 那一刻看到的还是空 params（真实路由 `/analysis/:id` 的键名就是 id）。
  return router
    .push(to)
    .then(() => router.isReady())
    .then(() =>
      mount(component, {
        attachTo: document.body,
        // Clock 在页面模板里是裸标签，靠 app 级全局注册（main.js 把整套图标注册了一遍）。
        // 测试只装 installElement，不补这一颗就有一条 "Failed to resolve component" 噪音盖住真信号。
        global: { plugins: [router, installElement], components: { Clock } },
      })
    )
}

function listItems(heading, root = document.body) {
  const block = [...root.querySelectorAll('h3, h4')].find((h) =>
    h.textContent.trim().startsWith(heading)
  )
  if (!block) return null
  const scope = block.parentElement
  return [...scope.querySelectorAll('li')].map((li) => li.textContent.replace(/\s+/g, ' ').trim())
}

describe('匹配报告页：优势/差距两列在三代输入下的样子', () => {
  it('裸字符串成标签、对象带 item 出两段、空 item 那一支不再画 JSON', async () => {
    getAnalysis.mockResolvedValue(record())
    const wrapper = await mountPage(AnalysisResult, '/analysis/:id', '/analysis/9')
    await flushPromises()
    await flushPromises()

    expect(listItems('优势', wrapper.element)).toEqual([
      '项目主导',
      'Go 并发：命中必需项（JD 第 2 条）',
      '只有补语没有标签',
    ])
    expect(listItems('差距', wrapper.element)).toEqual(['Rust：补一个副作用示例', '没有标签的一条'])
    expect(wrapper.text()).not.toMatch(/[{}"]/)
    wrapper.unmount()
  })

  it('第一列差距取的是标签本身：裸字符串那代没有因为收窄而退回兜底文案', async () => {
    getAnalysis.mockResolvedValue(
      record({ match_report: { overall_score: 82, strengths: [], gaps: ['缺 K8s'] } })
    )
    const wrapper = await mountPage(AnalysisResult, '/analysis/:id', '/analysis/9')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('缺 K8s')
    wrapper.unmount()
  })
})

describe('历史记录详情：弹窗里那两列吃的是同一份收口', () => {
  it('三代输入画成三行，空 item 那一支不出现 JSON，严重度标签照旧', async () => {
    getHistoryDetail.mockResolvedValue(record({ id: 7 }))
    const wrapper = await mountPage(HistoryView, '/history', '/history')
    await flushPromises()

    await wrapper.vm.openDetail({ id: 7 })
    await flushPromises()
    await flushPromises()

    const dialog = document.querySelector('.el-dialog')
    expect(dialog, '详情弹窗没渲染出来（showDetail 或弹窗结构改了）').toBeTruthy()
    expect(listItems('✅ 优势', dialog)).toEqual([
      '项目主导',
      'Go 并发：命中必需项（JD 第 2 条）',
      '只有补语没有标签',
    ])
    /* 这一列的 markup 里 el-tag 与补语之间只有 4px 的 margin，没有空格；而"风险"那几条
       `<li class="risk">` 本来就并排画在同一列里（不是单独一列），所以第三条是它。 */
    expect(listItems('⚠️ 差距 / 风险', dialog)).toEqual([
      'Rust：补一个副作用示例高',
      '没有标签的一条中',
      '经验年限偏低',
    ])
    expect(dialog.textContent).not.toMatch(/[{}"]/)
    wrapper.unmount()
  })
})
