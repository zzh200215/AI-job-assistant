import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SkillsPane from '@/features/analysis/components/SkillsPane.vue'
import { installElement } from '@/plugins/element'

/* D65 把「技能匹配」标签页搬进 components/SkillsPane.vue。这一块的形状是"两个技能列 + 三列清单"，
   所以钉的全是只在特定输入下才成立的分支：
   - 优势/差距的条目可能是裸字符串，也可能是 `{item, impact, action, evidence, severity}` 对象
     （lib 的 `normalizeLocalizedObjectList` 对对象**一定**补齐那五个键、值都是字符串，
     但它对裸字符串原样放行——两代写法由此并存），
   - 对象而 item 为空串时标签整颗不出：这条是 §10.23 收的口，收之前 `x.item || x` 会往右走到
     对象上，把一整个 JSON 画给候选人，
   - 差距那一条 **action 优先于 impact**：两个都有时只说 action，
   - severity 只认"高/中"两个汉字，其余值（含"低"）灰标签，而这个字段**缺失**时标签整颗不出。
   本地化与归一化都不关面板的事（它们住在页面的 computed 与 lib 里），面板只保证递进来的东西按上面几条画出来。 */

function render(props = {}) {
  return mount(SkillsPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: {
      matchedSkills: [],
      missingSkills: [],
      strengths: [],
      gaps: [],
      riskPoints: [],
      ...props,
    },
  })
}

function colByLabel(label) {
  return [...document.querySelectorAll('.el-col')].find((c) =>
    c.querySelector('h4')?.textContent.trim().startsWith(label)
  )
}

function items(label) {
  const col = colByLabel(label)
  return col
    ? [...col.querySelectorAll('li')].map((li) => li.textContent.replace(/\s+/g, ' ').trim())
    : null
}

/* 只看 el-tag 的 type 那一档：`el-tag--small` / `el-tag--light` 是尺寸与效果，不是颜色。 */
function tagTypes(scope) {
  return [...scope.querySelectorAll('.el-tag')].map(
    (t) => t.className.match(/el-tag--(success|danger|warning|info|primary)/)?.[1] ?? 'default'
  )
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('技能匹配面板', () => {
  it('两列技能各自成 tag 各用自己的颜色，空列各自出空态而不是整块消失', () => {
    render({ matchedSkills: ['Go', 'K8s'], missingSkills: ['Rust'] })
    const groups = [...document.querySelectorAll('.skill-group')]
    expect(groups.map((g) => g.querySelector('h4').textContent.trim())).toEqual([
      '已匹配技能',
      '缺失技能',
    ])
    expect(
      groups.map((g) => [...g.querySelectorAll('.el-tag')].map((t) => t.textContent.trim()))
    ).toEqual([['Go', 'K8s'], ['Rust']])
    expect(tagTypes(groups[0])).toEqual(['success', 'success'])
    expect(tagTypes(groups[1])).toEqual(['danger'])

    render()
    expect(document.querySelectorAll('.skill-group .el-empty').length).toBe(2)
  })

  it('优势：对象带 impact/evidence 就三段齐，是裸字符串就直接当条目画', () => {
    render({
      strengths: [{ item: 'Go 并发', impact: '命中必需项', evidence: 'JD 第 2 条' }, '项目主导'],
    })
    expect(items('优势')).toEqual(['Go 并发：命中必需项（JD 第 2 条）', '项目主导'])
  })

  it('差距：action 说话时 impact 让位，只有没有 action 才用 impact', () => {
    render({
      gaps: [
        { item: 'Rust', action: '补一个副作用示例', impact: '差距较大' },
        { item: 'K8s', impact: '加分项缺失' },
      ],
    })
    /* 同时出 action 与 impact 会把一行挤成两句；模板里那条 `x.impact && !x.action` 就是为此。 */
    expect(items('差距')).toEqual(['Rust：补一个副作用示例', 'K8s：加分项缺失'])
  })

  it('严重度只认「高/中」两个汉字，别的值灰标签，没有这个字段就整颗标签都不出', () => {
    render({
      gaps: [
        { item: 'A', severity: '高' },
        { item: 'B', severity: '中' },
        { item: 'C', severity: '低' },
        { item: 'D' },
      ],
    })
    /* 第四条没有 severity：模板那条 `v-if="x.severity"` 让标签整颗消失，
       而不是退成灰——灰那一档只留给"有这个字段但值不认识"（低 / 英文 / 别的）。 */
    expect(tagTypes(colByLabel('差距'))).toEqual(['danger', 'warning', 'info'])
  })

  it('风险是一列纯文本，不走 item/impact 那套结构', () => {
    render({ riskPoints: ['经验年限偏低', '学历不匹配'] })
    expect(items('风险')).toEqual(['经验年限偏低', '学历不匹配'])
  })

  it('对象但没有 item：标签整颗不出，补语照说，绝不把对象打印成 JSON', () => {
    /* §10.23 收口的那一支。`normalizeLocalizedObjectList` 对"五个名字键都没有"的对象给的是
       item: ''（不是缺字段），而旧模板那句 `x.item || x` 在 '' 上会继续往右走，于是
       `<b>{{ {impact: '命中必需项'} }}</b>` 把整个对象画到屏幕上。收窄之后这条到不了候选人。
       反向证据：把 `<b v-if="r.label">` 改回 `<b>{{ x.item || x }}</b>`，这一条立刻红在 '{'。 */
    render({
      strengths: [{ impact: '命中必需项' }, { item: '', evidence: 'JD 第 4 条' }],
      gaps: [{ action: '补一个副作用示例', severity: '高' }],
    })
    expect(items('优势')).toEqual(['命中必需项', '（JD 第 4 条）'])
    const gapCol = colByLabel('差距')
    expect(gapCol.querySelectorAll('b').length).toBe(0)
    expect(gapCol.textContent).toContain('补一个副作用示例')
    expect(document.body.textContent).not.toMatch(/[{}"]/)
  })
})
