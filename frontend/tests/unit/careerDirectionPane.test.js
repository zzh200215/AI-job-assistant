import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import CareerDirectionPane from '@/features/analysis/components/CareerDirectionPane.vue'
import { installElement } from '@/plugins/element'

/* D65 把「职业方向」标签页搬进 components/CareerDirectionPane.vue。
   这一块最值得钉的是**三件事共用一个位置**：加载态、有数据、没数据——它们在面板里是
   `v-if / v-else-if / v-else` 一条链，所以真正的失效形状是"递错对象"（把 loading 当 paths 递进去、
   或 paths 递成 undefined），屏幕上整段空掉而不报错。
   另外两处只有看 DOM 才钉得住：
   - 分数圆块的颜色走**动态类名** `score-fill--<tone>`（阈值 85/70/50 住在 utils/scoreTone），
     卡片左边的粗条走 `'cp-' + (category === '高度匹配' ? 'high' : 'trans')`；
     这两处静态切分会整条切错（D44），所以样式是复制过来的。
   - 顶部提示是 `summary || '根据您的技能和经验，推荐以下 N 个岗位方向'`：链上没给 summary 才现编。 */

const PATH = {
  title: '平台后端',
  match_score: 88,
  category: '高度匹配',
  seniority: 'P6',
  reason: '技能高度重合',
  matched_skills: ['Go'],
  gap_skills: ['Rust'],
  salary_range: '30-45K',
}

function render(props = {}) {
  return mount(CareerDirectionPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: { loading: false, paths: [], summary: '', ...props },
  })
}

const cards = () => [...document.querySelectorAll('.cp-card')]

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('职业方向面板', () => {
  it('loading 时只有加载态：既不画卡也不说「暂无」', () => {
    render({ loading: true, paths: [PATH] })
    expect(document.querySelector('.inline-loading').textContent).toContain('正在分析')
    expect(cards().length).toBe(0)
    expect(document.querySelector('.el-empty')).toBeNull()
  })

  it('没有方向说的是「先去跑一次分析」，而不是空白', () => {
    render()
    expect(document.querySelector('.el-empty').textContent).toContain('请先完成一键智能分析')
    expect(document.querySelector('.el-alert')).toBeNull()
    expect(cards().length).toBe(0)
  })

  it('有方向就成卡，并把条数报进那句提示', () => {
    render({ paths: [PATH, { ...PATH, title: '数据平台' }] })
    expect(cards().map((c) => c.querySelector('.cp-title').textContent.trim())).toEqual([
      '平台后端',
      '数据平台',
    ])
    expect(document.querySelector('.el-alert').textContent).toContain('推荐以下 2 个岗位方向')
  })

  it('提示语优先用链上给的 summary，没有才现编那句', () => {
    render({ paths: [PATH], summary: '按您的经验看这两条最省力' })
    const alert = document.querySelector('.el-alert').textContent
    expect(alert).toContain('按您的经验看这两条最省力')
    expect(alert).not.toContain('推荐以下')
  })

  it('分数圆块按 utils 的四个档位上色，档位边界各自站得住', () => {
    render({
      paths: [
        { ...PATH, match_score: 85 },
        { ...PATH, match_score: 84 },
        { ...PATH, match_score: 70 },
        { ...PATH, match_score: 50 },
        { ...PATH, match_score: 49 },
        { ...PATH, match_score: null },
      ],
    })
    expect(
      cards().map((c) => c.querySelector('.cp-score').className.match(/score-fill--\w+/)[0])
    ).toEqual([
      'score-fill--high',
      'score-fill--good',
      'score-fill--good',
      'score-fill--warn',
      'score-fill--risk',
      'score-fill--unknown',
    ])
  })

  it('左粗条与标签颜色都跟着 category 而不是分数', () => {
    render({
      paths: [
        { ...PATH, match_score: 41, category: '高度匹配' },
        { ...PATH, match_score: 99, category: '可尝试' },
      ],
    })
    expect(
      cards().map((c) => [...c.classList].find((k) => k === 'cp-high' || k === 'cp-trans'))
    ).toEqual(['cp-high', 'cp-trans'])
    expect(cards().map((c) => c.querySelector('.cp-info .el-tag').textContent.trim())).toEqual([
      '高度匹配',
      '可尝试',
    ])
  })

  it('已具备 / 需提升 / 薪资三段没有才不留，理由那一行是**留着空 p**的', () => {
    render({ paths: [{ title: '只有方向', match_score: 70, category: '可尝试' }] })
    const card = cards()[0]
    expect([...card.querySelectorAll('.cp-skills')].length).toBe(0)
    expect(card.querySelector('.cp-salary')).toBeNull()
    /* 理由这一行是 `<p class="cp-reason">{{ cp.reason }}</p>`，没有 v-if：字段缺失时它留着一个空 p。
       上面两段技能用 `?.length` 守卫所以整段消失，两种写法在这一张卡里并存，实测各按各自的形状钉。 */
    expect(card.querySelector('.cp-reason').textContent).toBe('')
    expect(card.querySelector('.cp-title').textContent.trim()).toBe('只有方向')
  })

  it('两列技能各标各的名字，空数组那一列整段不留', () => {
    render({ paths: [{ ...PATH, gap_skills: [] }] })
    const card = cards()[0]
    expect([...card.querySelectorAll('.cp-skill-label')].map((n) => n.textContent.trim())).toEqual([
      '已具备：',
    ])
    expect(card.querySelector('.cp-salary').textContent).toContain('30-45K')
  })
})
