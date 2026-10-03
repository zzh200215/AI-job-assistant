import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import HistoryView from '@/features/shell/views/History.vue'
import { listHistory } from '@/api/history'
import { Clock } from '@element-plus/icons-vue'
import { installElement } from '@/plugins/element'
import { INTERVIEW_SCORE_BANDS, MATCH_SCORE_BANDS, isTopTier } from '@/utils/scoreTone'

/* §10.5 拍的是"界面上那四处 80 分界跟随后端顶档（85）"。落地时先量到一件事：**单一出处早就存在**
   （`utils/scoreTone.js` 的 `MATCH_SCORE_BANDS` 首条 min 就是 85，注释写明对齐后端
   `match_explainer_service._recommendation` 的 85/70/50），那四处是绕过它各抄了一个 80。
   所以这一刀不引入新常数，只是把四处接回既有那把尺子上。

   钉三层：判据本身（84/85 的分界、没有分数不算顶档）、两处屏幕（推荐页徽章与历史页计数）、
   以及"不许再有人抄数"的源码扫描。 */

vi.mock('@/api/analysis', async (importOriginal) => ({
  ...(await importOriginal()),
  getAnalysis: vi.fn(async () => ({})),
  regenOptimize: vi.fn(async () => ({})),
  regenInterview: vi.fn(async () => ({})),
}))

vi.mock('@/api/history', async (importOriginal) => ({
  ...(await importOriginal()),
  listHistory: vi.fn(),
  getHistoryDetail: vi.fn(async () => ({})),
  deleteHistory: vi.fn(async () => ({})),
}))

vi.mock('@/api/agent', async (importOriginal) => ({
  ...(await importOriginal()),
  startAgentAnalysis: vi.fn(async () => ({ task_id: 'never-polled' })),
}))

function sources(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return sources(full)
    return /\.(vue|js)$/.test(e.name) ? [full.split(path.sep).join('/')] : []
  })
}

/**
 * `)?` 不是装饰：历史页那一处写的是 `Number(item.match_score) >= 80`，括号夹在标识符与比较符中间。
 * 第一版没带它，扫描对这一处**是瞎的**——下面那条反向证据当场把它逮出来。
 */
const HAND_COPIED_FLOOR = /(match_score|best_score|latestMatchScore|score)\)?\s*[<>]=?\s*(80|82)\b/

/* 顶档线的家。它的注释里必须逐字写出"历史上各处抄过的那几个数"（`:49` 那句就是），
   所以扫描放过这一个文件——数字本来就该只住在这里。 */
const DEFINES_THE_LINE = 'src/utils/scoreTone.js'

function metric(tagText) {
  const cell = [...document.querySelectorAll('.history-focus-metrics > div')].find((d) =>
    d.querySelector('span')?.textContent.includes(tagText)
  )
  return cell?.querySelector('b')?.textContent.trim() ?? null
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('顶档判据只有一个出处', () => {
  it('匹配分：84 不算顶档，85 算', () => {
    expect(isTopTier(84)).toBe(false)
    expect(isTopTier(85)).toBe(true)
    expect(isTopTier('85')).toBe(true) // 后端偶尔给字符串分数，旧写法靠隐式转换也是这个结果
  })

  it('没有分数不是 0 分，也不算顶档', () => {
    expect(isTopTier(null)).toBe(false)
    expect(isTopTier(undefined)).toBe(false)
    expect(isTopTier('')).toBe(false)
  })

  it('面试分那一把尺的顶档线同样是 85', () => {
    expect(MATCH_SCORE_BANDS[0].min).toBe(85)
    expect(INTERVIEW_SCORE_BANDS[0].min).toBe(85)
    expect(isTopTier(84, INTERVIEW_SCORE_BANDS)).toBe(false)
    expect(isTopTier(85, INTERVIEW_SCORE_BANDS)).toBe(true)
  })

  it('四处屏幕不再自己抄数（源码扫描）', () => {
    const offenders = sources('src')
      .filter(
        (rel) => rel !== DEFINES_THE_LINE && HAND_COPIED_FLOOR.test(readFileSync(rel, 'utf8'))
      )
      .map((rel) => rel)
    expect(
      offenders,
      `顶档线只能从 utils/scoreTone.js 的 bands 出来，这些地方还在抄常数：${offenders.join(', ')}`
    ).toEqual([])
  })

  it('反向证据：扫描认得改之前的那四处写法', () => {
    expect(HAND_COPIED_FLOOR.test('v-if="!job._applied && job.match_score >= 80"')).toBe(true)
    expect(
      HAND_COPIED_FLOOR.test('list.value.filter((item) => Number(item.match_score) >= 80)')
    ).toBe(true)
    expect(HAND_COPIED_FLOOR.test('unlocked: s.best_score >= 80,')).toBe(true)
    expect(HAND_COPIED_FLOOR.test('if (score >= 80 && gaps <= 3) {')).toBe(true)
    // 落地后的写法不被误判
    expect(HAND_COPIED_FLOOR.test('v-if="!job._applied && isTopTier(job.match_score)"')).toBe(false)
    /* 已知的一个"看不见"：`jobModel.js:342` 的 `finalScore >= 82` 不在口径里，因为标识符是
       大写的 `Score`，而它数的确实是本页自己合成的投递优先级（技能/经验/薪资/城市 + 匹配分 28%），
       与后端匹配分不是同一个量——`isTopTier` 的注释里点名过这条刻意不并的界。 */
    expect(HAND_COPIED_FLOOR.test('const label = finalScore >= 82')).toBe(false)
  })

  it('成就文案与判据同一条线：85 解锁，写的是"达到"不是"超过"', () => {
    const profile = readFileSync('src/features/shell/views/Profile.vue', 'utf8')
    expect(profile).toContain('综合评分达到85')
    expect(profile).not.toContain('超过80')
  })

  it('两处没做屏幕断言的站点，至少证明接线落进了文件', () => {
    /* 诚实记录：这两处**没有**页面级断言。`CareerPlanning` 的那一档吃 `latestMatchScore`，
       要把它设到 85 侧得把整条分析历史链喂进夹具（现有 harness 到不了那一层）；`Profile` 那颗
       成就有屏幕断言（`profileStatsTile.test.js` 的 84/85 两条）。所以这里退而求其次：
       证明比较式真的换成了 `isTopTier`，而不是只在注释里说换了。 */
    const planning = readFileSync('src/features/planning/views/CareerPlanning.vue', 'utf8')
    expect(planning).toContain('if (isTopTier(score) && gaps <= 3)')
    const profile = readFileSync('src/features/shell/views/Profile.vue', 'utf8')
    expect(profile).toContain('unlocked: isTopTier(s.best_score, INTERVIEW_SCORE_BANDS)')
  })
})

describe('历史页的"高匹配记录"跟随顶档', () => {
  async function renderHistory(items) {
    listHistory.mockResolvedValue({ items, total: items.length })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/history', component: HistoryView },
      ],
    })
    await router.push('/history')
    await router.isReady()
    const wrapper = mount(HistoryView, {
      attachTo: document.body,
      global: { plugins: [router, installElement], components: { Clock } },
    })
    await flushPromises()
    return wrapper
  }

  it('82 那一条不再被数进"高匹配记录"，85 那条才算', async () => {
    const wrapper = await renderHistory([
      { id: 1, match_score: 82 },
      { id: 2, match_score: 85 },
      { id: 3, match_score: 88 },
    ])
    expect(metric('高匹配记录')).toBe('2')
    // 平均匹配分不受这一刀影响（它数的是所有分数，不是档位）
    expect(metric('平均匹配分')).toBe('85')
    wrapper.unmount()
  })
})
