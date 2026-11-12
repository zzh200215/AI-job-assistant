import { describe, expect, it } from 'vitest'

import {
  allowedStageTargets,
  avgResponseDays,
  canMoveTo,
  conversionRate,
  flattenCards,
  followUpCount,
  followUpDays,
  followUpLevel,
  funnelPercent,
  funnelRows,
  isTerminalStage,
  menuMoveTargets,
  moveRefusalCopy,
  needsFollowUp,
  pipelineFocusDescription,
  pipelineFocusTitle,
  rejectionRate,
  stageCounts,
  stageLabel,
  stageTagType,
  stageToRate,
  totalCardCount,
} from '@/features/pipeline/lib/pipelineBoard'

/* D57 把看板页的统计与跟进判据搬进 lib。下面这组 old* 是**搬家前的原函数**，逐字抄自
   HEAD:frontend/src/features/pipeline/views/PipelineKanban.vue，只做两种替换：
   ① 把 `kanban.value` / `counts.value` / `totalCards.value` / `funnelData.value` 换成入参；
   ② 把 `Date.now()` 换成入参 `now`（这是这次唯一改到的形状，为的是"8 天前该报什么"能测）。 */

const OLD_COLUMNS = [
  { key: 'todo', label: '待投递', accent: 'slate' },
  { key: 'applied', label: '已投递', accent: 'blue' },
  { key: 'written_test', label: '笔试', accent: 'amber' },
  { key: 'interview', label: '面试', accent: 'violet' },
  { key: 'offer', label: 'Offer', accent: 'green' },
  { key: 'accepted', label: '已入职', accent: 'green' },
  { key: 'rejected', label: '已拒绝', accent: 'red' },
  { key: 'withdrawn', label: '已放弃', accent: 'gray' },
]

function oldCounts(kanban) {
  const map = {}
  OLD_COLUMNS.forEach((col) => {
    map[col.key] = (kanban[col.key] || []).length
  })
  return map
}

const oldTotal = (kanban) =>
  OLD_COLUMNS.reduce((sum, col) => sum + (kanban[col.key] || []).length, 0)

function oldAllCards(kanban) {
  const all = []
  OLD_COLUMNS.forEach((col) => {
    ;(kanban[col.key] || []).forEach((card) => {
      all.push(card)
    })
  })
  return all
}

const oldFunnel = (counts) =>
  OLD_COLUMNS.filter((c) =>
    ['todo', 'applied', 'written_test', 'interview', 'offer'].includes(c.key)
  ).map((c) => ({ ...c, count: counts[c.key] || 0 }))

function oldConversionRate(counts, total, stage) {
  if (!total) return 0
  const stageOrder = ['todo', 'applied', 'written_test', 'interview', 'offer']
  const idx = stageOrder.indexOf(stage)
  if (idx <= 0) return Math.round(((counts[stage] || 0) / total) * 100)
  const prevTotal = stageOrder.slice(0, idx).reduce((s, k) => s + (counts[k] || 0), 0)
  const current = counts[stage] || 0
  const base = prevTotal + current
  return base > 0 ? Math.round((current / base) * 100) : 0
}

const oldRejection = (counts, total) => {
  if (!total) return 0
  return Math.round((((counts.rejected || 0) + (counts.withdrawn || 0)) / total) * 100)
}

function oldAvgResponse(applied, now) {
  const days = applied
    .filter((c) => c.update_time)
    .map((c) => Math.round((now - new Date(c.update_time).getTime()) / 86400000))
  if (!days.length) return '--'
  return Math.round(days.reduce((s, d) => s + d, 0) / days.length) + 'd'
}

const oldFunnelPercent = (count, rows) => {
  const max = Math.max(1, ...rows.map((s) => s.count))
  return Math.max(2, (count / max) * 100)
}

const DAY = 86400000
const NOW = new Date('2026-05-20T12:00:00Z').getTime()
const stamp = (daysAgo) => new Date(NOW - daysAgo * DAY).toISOString()

function boards() {
  const out = [{}, { todo: [] }, { todo: [{}], applied: [{}] }]
  // 覆盖"某一列为空 / 全空 / 只有尾巴列 / 漏斗中段为空"几种回退
  out.push({ rejected: [{}, {}], withdrawn: [{}] })
  out.push({
    todo: [{}, {}, {}],
    applied: [{ update_time: stamp(2) }, { update_time: stamp(9) }, {}],
    written_test: [{ update_time: stamp(3) }],
    interview: [{}],
    offer: [{}],
    accepted: [{}],
    rejected: [{}],
  })
  out.push({
    todo: [{}, {}],
    applied: [{ update_time: stamp(3) }],
    written_test: [],
    interview: [],
    offer: [],
    withdrawn: [{}, {}],
  })
  return out
}

describe('D57 搬家：统计结果与搬家前逐条相同', () => {
  it(`${boards().length} 种看板形状上，计数/总数/扁平列表/漏斗行一个不差`, () => {
    for (const kanban of boards()) {
      expect(stageCounts(kanban)).toEqual(oldCounts(kanban))
      expect(totalCardCount(kanban)).toBe(oldTotal(kanban))
      expect(flattenCards(kanban)).toEqual(oldAllCards(kanban))
      expect(funnelRows(stageCounts(kanban))).toEqual(oldFunnel(oldCounts(kanban)))
    }
  })

  it('转化率与淘汰率在每种形状、每个阶段上都相同', () => {
    for (const kanban of boards()) {
      const counts = oldCounts(kanban)
      const total = oldTotal(kanban)
      for (const stage of [...OLD_COLUMNS.map((c) => c.key), 'unknown_stage']) {
        expect(conversionRate(counts, total, stage), `${stage} 的转化率变了`).toBe(
          oldConversionRate(counts, total, stage)
        )
      }
      expect(rejectionRate(counts, total)).toBe(oldRejection(counts, total))
      for (const from of ['todo', 'applied', 'interview', 'rejected'])
        for (const to of ['applied', 'offer', 'withdrawn', 'nope'])
          expect(stageToRate(counts, from, to)).toBe(
            (() => {
              const fromCount = counts[from] || 0
              const toCount = counts[to] || 0
              if (!fromCount) return '0%'
              return Math.round((toCount / fromCount) * 100) + '%'
            })()
          )
    }
  })

  it('平均响应天数与漏斗宽度在同样输入下相同', () => {
    for (const kanban of boards()) {
      const applied = kanban.applied || []
      expect(avgResponseDays(applied, NOW)).toBe(oldAvgResponse(applied, NOW))
      const rows = oldFunnel(oldCounts(kanban))
      for (const row of rows) {
        expect(funnelPercent(row.count, rows)).toBe(oldFunnelPercent(row.count, rows))
      }
    }
  })
})

describe('钉死每条判据（含被改成入参的那些时间）', () => {
  const counts = {
    todo: 4,
    applied: 3,
    written_test: 0,
    interview: 2,
    offer: 1,
    accepted: 0,
    rejected: 5,
    withdrawn: 1,
  }
  const total = 16

  it('转化率：首段用全体做分母，中段用"经过本段之前的总数 + 本段"', () => {
    expect(conversionRate(counts, total, 'todo')).toBe(25) // 4 / 16
    expect(conversionRate(counts, total, 'applied')).toBe(43) // 3 / 7 = 42.86
    expect(conversionRate(counts, total, 'written_test')).toBe(0) // 0 / 7
    expect(conversionRate(counts, total, 'interview')).toBe(22) // 2 / 9
    expect(conversionRate(counts, total, 'offer')).toBe(10) // 1 / 10
    expect(conversionRate(counts, 0, 'applied')).toBe(0) // 没有卡片就说 0，不除零
    expect(conversionRate({}, total, 'unknown_stage')).toBe(0)
  })

  it('淘汰率只数 rejected 与 withdrawn', () => {
    expect(rejectionRate(counts, total)).toBe(38) // (5 + 1) / 16
    expect(rejectionRate(counts, 0)).toBe(0)
  })

  it('漏斗：只画推进五段，宽度有 2% 的下限、分母至少为 1', () => {
    const rows = funnelRows(counts)
    expect(rows.map((r) => r.key)).toEqual([
      'todo',
      'applied',
      'written_test',
      'interview',
      'offer',
    ])
    expect(funnelPercent(0, rows)).toBe(2)
    expect(funnelPercent(4, rows)).toBe(100)
    expect(funnelPercent(2, rows)).toBe(50)
    expect(funnelPercent(1, [])).toBe(100) // 空行集时 max 兜到 1
  })

  it('平均响应天数：没有 update_time 就说 --，并按天四舍五入', () => {
    expect(avgResponseDays([], NOW)).toBe('--')
    expect(avgResponseDays([{ update_time: null }], NOW)).toBe('--')
    expect(avgResponseDays([{ update_time: stamp(2) }, { update_time: stamp(9) }], NOW)).toBe('6d')
    expect(avgResponseDays([{ update_time: stamp(0) }, { update_time: stamp(1) }], NOW)).toBe('1d')
  })

  it('阶段标签与颜色：未知阶段透出原文 / 落到灰', () => {
    expect(stageLabel('written_test')).toBe('笔试')
    expect(stageLabel('nope')).toBe('nope')
    expect(stageLabel('')).toBe('-')
    expect(stageTagType('applied')).toBe('primary')
    expect(stageTagType('rejected')).toBe('danger')
    expect(stageTagType('nope')).toBe('info')
  })

  it('跟进提醒：只有已投递与笔试两算，3 天开始提醒、7 天升级为危险', () => {
    expect(needsFollowUp({ stage: 'todo', update_time: stamp(30) })).toBeFalsy()
    expect(needsFollowUp({ stage: 'applied' })).toBeFalsy() // 没有更新时间就不算
    expect(needsFollowUp({ stage: 'written_test', update_time: stamp(1) })).toBe(stamp(1))

    expect(followUpDays({ update_time: stamp(2) }, NOW)).toBe(2)
    expect(followUpDays({}, NOW)).toBe(0)
    expect(followUpLevel({ update_time: stamp(2) }, NOW)).toBe('ok')
    expect(followUpLevel({ update_time: stamp(3) }, NOW)).toBe('warn') // 第 3 天就该变色
    expect(followUpLevel({ update_time: stamp(6) }, NOW)).toBe('warn')
    expect(followUpLevel({ update_time: stamp(7) }, NOW)).toBe('danger') // 第 7 天升级
  })

  it("需要跟进的条数：'等满 3 天'才计入", () => {
    const cards = [
      { stage: 'applied', update_time: stamp(1) },
      { stage: 'applied', update_time: stamp(3) },
      { stage: 'written_test', update_time: stamp(9) },
      { stage: 'offer', update_time: stamp(30) },
      { stage: 'interview', update_time: stamp(30) },
    ]
    expect(followUpCount(cards, NOW)).toBe(2)
    expect(followUpCount([], NOW)).toBe(0)
  })

  it('顶部那句"现在该干什么"按 Offer > 面试 > 待跟进 > 补充排', () => {
    expect(pipelineFocusTitle(counts, 0)).toBe('优先完成 Offer 取舍与确认。')
    const noOffer = { ...counts, offer: 0 }
    expect(pipelineFocusTitle(noOffer, 0)).toBe('把面试机会转化为可执行的准备计划。')
    const noInterview = { ...noOffer, interview: 0 }
    expect(pipelineFocusTitle(noInterview, 2)).toBe(
      '有投递记录等待跟进，先处理超 3 天未回复的机会。'
    )
    expect(pipelineFocusTitle(noInterview, 0)).toBe('继续补充高匹配岗位，让投递保持稳定节奏。')
    expect(pipelineFocusDescription(counts, 0)).toContain('Offer 已进入决策阶段')
    expect(pipelineFocusDescription(noInterview, 2)).toContain('优先处理等待时间较长的投递')
    expect(pipelineFocusDescription(noInterview, 0)).toContain('从岗位推荐中挑选高匹配机会')
  })

  it('列定义仍然只有那八个阶段、顺序不变', () => {
    expect(flattenCards({ todo: [{ id: 1 }], offer: [{ id: 2 }], nope: [{ id: 3 }] })).toEqual([
      { id: 1 },
      { id: 2 },
    ])
    expect(totalCardCount({ todo: [{}, {}], rejected: [{}] })).toBe(3)
  })

  /* D4 的"非拖拽通路"取值域，现在读的是后端那张状态机表的前端镜像。
     这张镜像存在的唯一理由是：**能去哪必须在发请求之前就知道**——菜单要列选项、
     拖拽要判断这一放行不行。那条守卫（tests/stageTransitionsMatchBackend.test.mjs）
     解析后端 `job_pipeline.py` 的 VALID_TRANSITIONS 逐键比对，这里断的是**语义**：
     哪些列会出现、终态为什么是空的、以及提示措辞不再露英文阶段键。 */
  it('状态机镜像：推进链只能向前，终态一个出口都没有', () => {
    expect(allowedStageTargets('todo').map((c) => c.key)).toEqual(['applied', 'withdrawn'])
    expect(allowedStageTargets('applied').map((c) => c.key)).toEqual([
      'written_test',
      'interview',
      'rejected',
      'withdrawn',
    ])
    // 顺序跟列定义走，不跟字典里的书写顺序走
    expect(allowedStageTargets('offer').map((c) => c.key)).toEqual([
      'accepted',
      'rejected',
      'withdrawn',
    ])
    for (const terminal of ['accepted', 'rejected', 'withdrawn']) {
      expect(allowedStageTargets(terminal), terminal).toEqual([])
      expect(isTerminalStage(terminal), terminal).toBe(true)
    }
    expect(isTerminalStage('offer')).toBe(false)
    // 不认识的阶段：当"哪条都不允许"，而不是"全都允许"
    expect(allowedStageTargets('nope')).toEqual([])
    expect(allowedStageTargets(undefined)).toEqual([])
  })

  it('菜单只列"还没专门命令"的那几段：拒绝/放弃各有自己的按钮，不重复一遍', () => {
    // todo 卡：后端只给 applied / withdrawn，而 withdrawn 走「放弃」那颗
    expect(menuMoveTargets('todo').map((c) => c.key)).toEqual(['applied'])
    expect(menuMoveTargets('applied').map((c) => c.key)).toEqual(['written_test', 'interview'])
    expect(menuMoveTargets('written_test').map((c) => c.key)).toEqual(['interview'])
    expect(menuMoveTargets('interview').map((c) => c.key)).toEqual(['offer'])
    // 「已入职」只有这一条路：offer 之后没有任何别的入口能到它
    expect(menuMoveTargets('offer').map((c) => c.key)).toEqual(['accepted'])
    expect(menuMoveTargets('rejected')).toEqual([])
  })

  it('canMoveTo 是上面两条的判据，正反两面都要对', () => {
    expect(canMoveTo('applied', 'written_test')).toBe(true)
    expect(canMoveTo('applied', 'todo')).toBe(false) // 后端就是这么拒的（D4 真撞过）
    expect(canMoveTo('todo', 'interview')).toBe(false) // 跨段跳不行
    expect(canMoveTo('offer', 'accepted')).toBe(true)
    expect(canMoveTo('rejected', 'todo')).toBe(false) // 终态出不来
    expect(canMoveTo(undefined, 'applied')).toBe(false)
  })

  it('被拒时说的是中文阶段名，不露 `applied` 这种键、也不带 request id', () => {
    const refused = moveRefusalCopy('applied', 'todo')
    expect(refused).toBe('不能从「已投递」直接到「待投递」')
    expect(refused).not.toMatch(/applied|todo|\[web-/)
    expect(moveRefusalCopy('rejected', 'applied')).toBe('「已拒绝」已经结束，不能再改阶段')
    // 未知阶段不能把 undefined 塞进句子
    expect(moveRefusalCopy('nope', 'applied')).not.toContain('undefined')
  })
})
