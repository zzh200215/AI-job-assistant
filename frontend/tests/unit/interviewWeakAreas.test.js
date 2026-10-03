import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import Interview from '@/features/interview/views/Interview.vue'
import { getPerformanceTrend } from '@/api/interview'
import { installElement } from '@/plugins/element'

/* §10.6 复测出来的那条真缺陷：这一屏的"薄弱知识点"分数是 `Math.random()*40+30` 造的。
   但挂着的条目说"无趋势数据时"才造——实测**不是**：`loadWeakAreas` 读的是 `perf.dimensions`，
   而 `GET /interview/performance` 给的是 `weaknesses` / `dimension_averages`（`interview_rest.py:821-829`），
   同名的 `dimensions` 属于另一份载荷（匹配解释，`match_explainer_service.py:79`）。
   所以真数据分支一次都没进过，只要本地有 ≥2 场带分会话就永远画随机数。

   钉三件事：
   1. 画的是服务端那份真分（41 / 52），并且按分数升序；
   2. **同一次挂载跑两遍，两遍的字一模一样**——旧写法在这里必然给不同的分数（5 个维度各掷 30~69），
      这条就是"删掉随机数"的直接证据，不需要去变异已落地的代码；
   3. 空与失败都落回这一格本来就有的空态，而不是被三个位置顶上。 */

vi.mock('@/api/interview', async (importOriginal) => ({
  ...(await importOriginal()),
  getInterviewList: vi.fn(async () => [
    // 旧写的 `completed.length >= 2` 正是靠这两条满足——也就是"以前一定会掷随机数"的那个入口
    { id: 1, status: 'completed', overall_score: 62 },
    { id: 2, status: 'completed', overall_score: 71 },
  ]),
  getQuestionBank: vi.fn(async () => [
    { id: 9, question: '说一下你最棘手的一次线上故障', category: 'project' },
  ]),
  getPerformanceTrend: vi.fn(),
}))

vi.mock('@/api/jobs', async (importOriginal) => ({
  ...(await importOriginal()),
  getJobPipelineList: vi.fn(async () => ({ items: [] })),
}))

vi.mock('@/api/analysis', async (importOriginal) => ({
  ...(await importOriginal()),
  getAnalysis: vi.fn(async () => ({})),
}))

async function mounted() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/interview', component: Interview },
    ],
  })
  await router.push('/interview')
  await router.isReady()
  const wrapper = mount(Interview, {
    attachTo: document.body,
    global: { plugins: [router, installElement] },
  })
  await flushPromises()
  // 页面用 `setTimeout(loadWeakAreas, 500)` 等会话先到位，这一段是真墙钟
  await new Promise((r) => setTimeout(r, 700))
  await flushPromises()
  return wrapper
}

function weakCards() {
  return [...document.querySelectorAll('.weak-card')].map((c) =>
    c.textContent.replace(/\s+/g, ' ').trim()
  )
}

beforeEach(() => {
  document.body.innerHTML = ''
  getPerformanceTrend.mockReset()
  getPerformanceTrend.mockResolvedValue({
    total_sessions: 2,
    avg_overall_score: 66.5,
    max_overall_score: 71,
    trend: [],
    dimension_averages: { completeness: 74, accuracy: 52, depth: 41, expression: 80 },
    // 服务端那份就是"薄弱项"的正文：按维度均分 <65 挑好，名字已经本地化
    strengths: [{ dimension: '表达力', avg_score: 80 }],
    weaknesses: [
      { dimension: '深度', avg_score: 41 },
      { dimension: '准确性', avg_score: 52 },
    ],
    improvement_priority: [],
  })
})

describe('面试工作台：薄弱知识点', () => {
  it('画的是服务端那份真分，升序，不再是掷出来的数', async () => {
    await mounted()
    const cards = weakCards()
    expect(cards.length).toBe(2)
    expect(cards[0]).toContain('深度')
    expect(cards[0]).toContain('41分')
    expect(cards[1]).toContain('准确性')
    expect(cards[1]).toContain('52分')
    // 旧写法会画的五个假维度，一个都不该出现
    expect(document.body.textContent).not.toMatch(/技术深度|逻辑思维|项目经验|行为面试/)
  })

  it('同一份数据挂两次，字一模一样（随机数那条路的直接反证）', async () => {
    await mounted()
    const first = weakCards().join(' || ')
    document.body.innerHTML = ''
    await mounted()
    const second = weakCards().join(' || ')
    expect(first).toBe(second)
    expect(first).toContain('41分')
  })

  it('服务端说没有薄弱项时，是这一格本来就有的空态，不是三个空位', async () => {
    getPerformanceTrend.mockResolvedValue({
      total_sessions: 3,
      weaknesses: [],
      dimension_averages: {},
    })
    await mounted()
    expect(weakCards().length).toBe(0)
    // `.empty-inline` 这一页好几个块共用（"暂无即将到来的面试"也用它），所以按整页正文认这一格
    expect(document.body.textContent).toContain('暂无薄弱项数据')
  })

  it('那一发失败时说的是什么读不到，而不是"你没有薄弱项"', async () => {
    /* 这一条是被 `silentEmptyCatches` 那条守卫逼出来的：第一版我写成"失败 → 空态"，
       守卫当场红（`Interview.vue` 新增 1 处"失败被清成没数据"）。所以失败必须报成失败。 */
    getPerformanceTrend.mockRejectedValue(new Error('trend unavailable'))
    await mounted()
    expect(weakCards().length).toBe(0)
    expect(document.body.textContent).toContain('trend unavailable')
    expect(document.body.textContent).not.toContain('暂无薄弱项数据')
    expect(document.body.textContent).not.toMatch(/建议加强(技术深度|表达能力|逻辑思维)方向训练/)
  })
})
