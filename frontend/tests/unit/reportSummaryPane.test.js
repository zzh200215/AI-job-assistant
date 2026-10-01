import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElTable } from 'element-plus'

import ReportSummaryPane from '@/features/analysis/components/ReportSummaryPane.vue'
import { installElement } from '@/plugins/element'

/* D65 把「综合评价」标签页搬进 components/ReportSummaryPane.vue。
   这里有一张 `el-table`，所以照 D64 那条教训先把话说清：**jsdom 里格子要等一次 flush 才画得出来**，
   直接读 `.el-table__body tr` 拿到空文本是"没等"，不是"画不出"。
   面板只吃三个值，两个字符串是页面 localize 过的成品（`localizeRecommendationText` /
   `localizeSentence`），所以这一份钉的是"递进来的东西原样上屏 + 两处回退"：
   - `report` 是 null 时走空态（记录里没有 final_report 是常态，不是错误）；
   - 候选人/目标岗位缺字段写 '-'，
   - 行动项的优先级标签只认"高/中"两个汉字，其余（含缺字段）灰。 */

const REPORT = {
  summary: {
    candidate_name: '张三',
    target_position: '平台后端',
    recommendation: '谨慎投递',
    overall_evaluation: '整体可用，项目段薄',
  },
  action_items: [
    { priority: '高', action: '补 Go 并发项目', reason: 'JD 必需项' },
    { priority: '中', action: '重写实习描述', reason: '量化不足' },
    { priority: '低', action: '加一页作品集', reason: '锦上添花' },
  ],
  development_advice: { short_term: ['两个月补 K8s'], long_term: ['一年内带到 P6'] },
}

function render(props = {}) {
  return mount(ReportSummaryPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: { report: null, recommendation: '', evaluation: '', ...props },
  })
}

async function tableRows() {
  await flushPromises()
  return [...document.querySelectorAll('.el-table__body tr')].map((tr) =>
    [...tr.querySelectorAll('td')].map((td) => td.textContent.replace(/\s+/g, ' ').trim())
  )
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('综合评价面板', () => {
  it('没有 final_report 时是一句空态，四个字段位与表都不出现', () => {
    render()
    expect(document.querySelector('.el-empty').textContent).toContain('暂无综合评价')
    expect(document.querySelectorAll('.el-descriptions').length).toBe(0)
    expect(document.querySelector('.el-table')).toBeNull()
  })

  it('头部四项：两个来自 report，两个是页面 localize 过的成品字符串', () => {
    render({
      report: REPORT,
      recommendation: '谨慎投递（本地化过）',
      evaluation: '整体可用，项目段薄（本地化过）',
    })
    const cells = [...document.querySelectorAll('.el-descriptions__cell')]
      .map((c) => c.textContent.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    expect(cells).toEqual([
      '候选人',
      '张三',
      '目标岗位',
      '平台后端',
      '推荐建议',
      '谨慎投递（本地化过）',
      '综合评价',
      '整体可用，项目段薄（本地化过）',
    ])
  })

  it('候选人或岗位没给时写的是连字符：summary 是空对象、或者整段没有，两种都不炸', () => {
    render({ report: { ...REPORT, summary: {} } })
    const cells = [...document.querySelectorAll('.el-descriptions__cell')]
      .map((c) => c.textContent.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    /* 两条 localize 过的字符串这里没往下递（默认 ''），被 filter(Boolean) 掉了；
       这一条要看的是前两项落到 '-' 而不是空——那是模板里两处 `|| '-'` 的兜底。 */
    expect(cells).toEqual(['候选人', '-', '目标岗位', '-', '推荐建议', '综合评价'])

    /* `final_report` 里有 action_items 却没有 summary 是后端给得出的形状（三段是分别生成的），
       这一支靠的是 `report.summary?.` 那条可选链：少了它整页会抛，而不是这里少一个字段。 */
    document.body.innerHTML = ''
    render({ report: { action_items: [] } })
    expect(document.querySelector('.el-descriptions')).toBeTruthy()
    expect(document.querySelectorAll('.dev-card').length).toBe(2)
  })

  it('行动项表格：三列按 priority/action/reason 的顺序，优先级只有「高/中」认颜色', async () => {
    const wrapper = render({ report: REPORT })
    expect(wrapper.findComponent(ElTable).props('data')).toEqual(REPORT.action_items)
    expect(await tableRows()).toEqual([
      ['高', '补 Go 并发项目', 'JD 必需项'],
      ['中', '重写实习描述', '量化不足'],
      ['低', '加一页作品集', '锦上添花'],
    ])
    expect(
      [...document.querySelectorAll('.el-table .el-tag')].map(
        (t) => t.className.match(/el-tag--(danger|warning|info)/)?.[1] ?? 'default'
      )
    ).toEqual(['danger', 'warning', 'info'])
  })

  it('行动项为空时表还在，出的是 EP 自己那格空态而不是我们把表切掉', async () => {
    render({ report: { ...REPORT, action_items: [] } })
    await tableRows()
    expect(document.querySelector('.el-table')).toBeTruthy()
    /* 措辞不归这个面板管：全仓从没配过 EP 的 locale（main.js 与 plugins/element.js 里各 0 处），
       所以生产上这里同样是英文 'No Data'。这条钉的是"空态那一格出现了"，即表格没被 v-if 切走。 */
    expect(document.querySelector('.el-table__empty-text').textContent).toBe('No Data')
  })

  it('发展建议两列各自回退：只给短期时长期那一列是空的 ul，标题仍成对', async () => {
    render({ report: { ...REPORT, development_advice: { short_term: ['两个月补 K8s'] } } })
    const cards = [...document.querySelectorAll('.dev-card')]
    expect(cards.map((c) => c.querySelector('h5').textContent.trim())).toEqual(['短期', '长期'])
    expect(
      cards.map((c) => [...c.querySelectorAll('li')].map((li) => li.textContent.trim()))
    ).toEqual([['两个月补 K8s'], []])
  })

  it('development_advice 整段缺失时两列都不炸', () => {
    render({ report: { summary: REPORT.summary, action_items: [] } })
    const cards = [...document.querySelectorAll('.dev-card')]
    expect(cards.length).toBe(2)
    expect(document.querySelectorAll('.dev-card li').length).toBe(0)
  })
})
