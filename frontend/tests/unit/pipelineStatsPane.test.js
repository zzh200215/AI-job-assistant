import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import StatsPane from '@/features/pipeline/components/StatsPane.vue'
import { installElement } from '@/plugins/element'
import {
  conversionRate,
  funnelPercent,
  funnelRows,
  rejectionRate,
  stageCounts,
  stageToRate,
} from '@/features/pipeline/lib/pipelineBoard'

/* D62 把两块统计搬进面板。页面那三条用例（pipelineKanbanStatsRender）钉的是"屏幕上的数字"，
   但它们经过整页挂载：如果**面板自己的 props 名字接错**（`:avg-response-days` 写成
   `:avg-response-day`、`versionPerformance` 传成别的），页面用例里那份 props 恰好也错了，
   两边一起绿而面板永远画不出东西。所以这里直接挂面板：props 的形状就是它的接口。
   顺带补上一件 D57 就没做的事：`.version-performance` 那块此前一条用例都没有
   （页面那三条的版本表现数组恒为空数组）。 */

const KANBAN = {
  todo: [{ id: 1 }],
  applied: [{ id: 2 }, { id: 3 }, { id: 4 }],
  written_test: [],
  interview: [{ id: 5 }, { id: 6 }],
  offer: [{ id: 7 }],
  accepted: [],
  rejected: [{ id: 8 }],
  withdrawn: [],
}

function renderPane(extra = {}) {
  return mount(StatsPane, {
    global: { plugins: [installElement] },
    props: {
      counts: stageCounts(KANBAN),
      totalCards: 8,
      avgResponseDays: '6d',
      versionPerformance: [],
      ...extra,
    },
  })
}

function texts(wrapper, selector) {
  return wrapper.findAll(selector).map((n) => n.text().trim())
}

describe('面板的 props 就是它的接口', () => {
  /* 期望值一律用 lib 直接算一遍：这条测试管的是"面板有没有把 props 正确地递进规则里"，
     不是把 lib 的数字再抄一遍。分母换成 totalCards 之外的数、stage 名字写错、
     `counts` 与 `totalCards` 位置对调——这些都不会报错，只会显示另一个数字。 */
  const counts = stageCounts(KANBAN)
  const rows = funnelRows(counts)

  it('六个格子等于 lib 拿同样 props 算出来的那六个数', () => {
    const wrapper = renderPane()
    expect(texts(wrapper, '.stat-value')).toEqual([
      '8',
      `${conversionRate(counts, 8, 'applied')}%`,
      `${conversionRate(counts, 8, 'interview')}%`,
      `${conversionRate(counts, 8, 'offer')}%`,
      `${rejectionRate(counts, 8)}%`,
      '6d',
    ])
    // 时间相关的换算不在面板里做：页面给 '6d' 就画 '6d'，页面是唯一读时间的地方
    expect(texts(wrapper, '.stat-value')[5]).toBe('6d')
  })

  it('漏斗每一段的标签、计数、动态配色类名与相邻转化率都来自同一批 lib 调用', () => {
    const wrapper = renderPane()
    const barRows = wrapper.findAll('.funnel-bar-wrapper')
    expect(barRows.length).toBe(rows.length)
    expect(texts(wrapper, '.funnel-label')).toEqual(rows.map((r) => r.label))
    expect(texts(wrapper, '.funnel-count')).toEqual(rows.map((r) => String(r.count)))
    // 配色走 `'fill-' + stage.accent`：D44 量过的动态类名，静态切分会把它整条切没
    expect(
      wrapper.findAll('.funnel-fill').map((n) => n.classes().filter((c) => c.startsWith('fill-')))
    ).toEqual(rows.map((r) => ['fill-' + r.accent]))
    expect(
      wrapper.findAll('.funnel-fill').map((n) => n.attributes('style').replace(/\s/g, ''))
    ).toEqual(rows.map((r) => `width:${funnelPercent(r.count, rows)}%;`))
    expect(texts(wrapper, '.funnel-rate')).toEqual(
      rows.slice(0, -1).map((r, idx) => String(stageToRate(counts, r.key, rows[idx + 1].key)))
    )
    /* 漏斗是固定五段（`funnelRows` 按一张写死的清单挑列）：计数为 0 的「笔试」也在里面，
       而三个终止态（已入职/已拒绝/已放弃）永远不进漏斗——拒绝率有自己那个格子。 */
    expect(texts(wrapper, '.funnel-label')).toEqual(['待投递', '已投递', '笔试', '面试', 'Offer'])
  })

  it('totalCards 为 0 时整块转化分析不画（不出现除零的那串 NaN）', () => {
    const wrapper = renderPane({ totalCards: 0 })
    expect(wrapper.find('.stats-panel').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('NaN')
  })

  it('版本表现：有几条画几行，空数组整块不出现', () => {
    const wrapper = renderPane({
      versionPerformance: [
        {
          resume_version_id: 11,
          label: '后端 Go 版',
          submitted: 6,
          interviews: 3,
          offers: 1,
          interview_rate: 50,
          offer_rate: 17,
        },
        {
          resume_version_id: 12,
          label: '通用版',
          submitted: 2,
          interviews: 0,
          offers: 0,
          interview_rate: 0,
          offer_rate: 0,
        },
      ],
    })
    const rows = wrapper.findAll('.version-performance-row')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('后端 Go 版')
    expect(rows[0].text()).toContain('6 次投递')
    expect(texts(wrapper, '.version-metric strong')).toEqual(['50%', '17%', '0%', '0%'])
    expect(rows[0].text()).toContain('3 面试')
    expect(rows[0].text()).toContain('1 Offer')

    expect(renderPane().find('.version-performance').exists()).toBe(false)
  })
})
