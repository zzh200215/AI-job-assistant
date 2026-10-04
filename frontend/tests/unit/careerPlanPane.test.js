import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import CareerPlanPane from '@/features/analysis/components/CareerPlanPane.vue'
import { installElement } from '@/plugins/element'

/* 职业规划面板：D51 从 SmartAnalysis.vue 搬出来的那一块（页面里最大的一个标签页）。
   纯展示、只吃三个 prop，所以这里测的是**边界**：prop 传错或漏传，屏幕上少的是候选人要看的
   那一整段路线图。两条判据（结构化缺口 / 阶段列表）住在 lib 与页面的链上，面板只负责把它们
   渲染成两种不同的形状。 */

function render(props = {}) {
  return mount(CareerPlanPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props,
  })
}

function texts(wrapper, selector) {
  return wrapper.findAll(selector).map((n) => n.text().trim())
}

describe('职业规划面板的四种数据形状', () => {
  it('没有 careerData 时是空态，而不是半截的路线图', () => {
    const wrapper = render({ careerData: null })
    expect(wrapper.find('.career-content').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无职业规划数据')
  })

  it('技能缺口是对象列表 → 折叠面板，优先级喂给 el-tag', () => {
    const wrapper = render({
      careerData: {
        skill_gaps: [
          { skill: 'Rust', priority: '高', current_level: 2, target_level: 4 },
          { skill: 'K8s', priority: '低', current_level: 1, target_level: 3 },
        ],
      },
      hasStructuredSkillGaps: true,
    })
    expect(texts(wrapper, '.gap-skill')).toEqual(['Rust', 'K8s'])
    const types = wrapper
      .findAll('.gap-title .el-tag')
      .map((t) => t.classes().find((c) => c.startsWith('el-tag--')))
    expect(types).toEqual(['el-tag--danger', 'el-tag--info'])
    expect(wrapper.find('li').exists()).toBe(false)
  })

  it('技能缺口是字符串列表 → 走 📌 那一支，一个折叠面板都不生成', () => {
    const wrapper = render({
      careerData: { skill_gaps: ['Rust', 'K8s'] },
      hasStructuredSkillGaps: false,
    })
    expect(wrapper.find('.gap-title').exists()).toBe(false)
    expect(texts(wrapper, '.career-section li')).toEqual(['📌 Rust', '📌 K8s'])
  })

  it('成长路线图：阶段、里程碑图标与项目技术栈都来自 prop', () => {
    const wrapper = render({
      careerData: {
        visual_roadmap: {
          total_duration_months: 18,
          career_direction: '平台工程师',
        },
      },
      visualPhases: [
        {
          id: 'p1',
          name: '打基础',
          duration_months: 6,
          color: '#196bdb',
          skills: ['Go'],
          milestones: [
            { type: 'cert', name: 'CKA' },
            { type: 'unknown-type', name: '自制项目' },
          ],
          projects: [{ name: '网关', description: '一个网关', tech_stack: ['Envoy'] }],
        },
      ],
    })
    expect(texts(wrapper, '.phase-name')).toEqual(['打基础'])
    expect(texts(wrapper, '.ms-icon')).toEqual(['🎓', '📍'])
    expect(wrapper.find('.roadmap-dir').text()).toContain('平台工程师')
    expect(texts(wrapper, '.project-desc')).toEqual(['一个网关'])
  })

  it('推荐项目的复杂度决定标签颜色，未知复杂度落到灰', () => {
    const wrapper = render({
      careerData: {
        project_recommendations: [
          { project: '短链服务', complexity: '困难', tech_stack: ['Redis'] },
          { project: '爬虫', complexity: '没见过', tech_stack: [] },
        ],
      },
    })
    expect(texts(wrapper, '.proj-name')).toEqual(['短链服务', '爬虫'])
    const types = wrapper
      .findAll('.proj-header .el-tag')
      .map((t) => t.classes().find((c) => c.startsWith('el-tag--')))
    expect(types).toEqual(['el-tag--danger', 'el-tag--info'])
  })
})

/* D99（§10.14 决定 ②）：这一屏的 7 个标题原先写成 `<div class="panel-header"><span>…</span></div>`，
   判定器看不见这种一行式，于是它既没被迁、也**没有一条测试断言过标题的文字**。
   span→h3 是候选人可见的改动（实测唯一变化的计算值是 font-weight 400 → 700），
   所以这里把七个标题逐个钉住——搬进 AppPanel 之后少画任何一个，都会在这里红。 */ describe('七个标题搬进 AppPanel 之后仍逐个在屏幕上', () => {
  it('七个都是 .panel-title-row 里的 h3，文字一个都没丢、也没并错', () => {
    const wrapper = render({
      careerData: {
        skill_radar: { dimensions: [{ name: 'Go', score: 6 }] },
        skill_gaps: [{ skill: 'Rust', priority: '高', current_level: 2, target_level: 4 }],
        visual_roadmap: { total_duration_months: 9, career_direction: '平台方向' },
        project_recommendations: [{ name: '项目甲', description: '做一个' }],
        industry_insight: { trends: ['趋势一'], career_alternatives: [], salary_range: null },
        recommended_certifications: [{ name: '证书甲' }],
        overall_advice: '先补并发',
      },
      hasStructuredSkillGaps: true,
      visualPhases: [{ id: 1, title: '打基础', color: '#22b8e8' }],
    })
    expect(texts(wrapper, '.panel-title-row h3')).toEqual([
      '📊 技能雷达',
      '⚠️ 技能提升建议（1 项）',
      '🛤️ 成长路线图（9个月）',
      '🔨 推荐项目实践',
      '📈 行业洞察',
      '📋 阶段计划',
      '🎓 推荐证书',
    ])
    // 一行式 span 已经不存在了：整页 `.panel-header` 里不该再有裸 span 当标题
    expect(wrapper.findAll('.panel-header > span')).toHaveLength(0)
  })
})

/* D113（§10.20）之前，这一屏的三根条子是**模板里的裸算式**：
   `width: dim.current_score + '%'`、`width: dim.target_score - dim.current_score + '%'`。
   同一条 AI 报告在职业规划页至少被 `safeScore` 夹过一次，在这里一次都没有，所以坏形状直接落进 CSS：
   "约80" → `width: 约80%`、漏字段 → `width: undefined%`、减法 → `width: NaN%`，三种全是非法值，
   浏览器整条忽略——那一行的目标段凭空消失，屏幕上没有任何东西说"这里少了一块"。
   所以这次既钉"读不懂要说暂无数据"，也钉"读得懂时宽度按老算法走"。 */
describe('技能雷达的宽度来自 aiScore，不再由模板自己做减法', () => {
  function radarRows(careerData) {
    return render({ careerData })
  }

  it('两端可读：当前条落在当前分，目标条是差值且停在当前分处', () => {
    const wrapper = radarRows({
      skill_radar: {
        dimensions: [
          { name: 'Go', current_score: 62.4, target_score: 90 },
          { name: 'K8s', current_score: '70', target_score: '88' },
        ],
      },
    })
    const currents = wrapper.findAll('.radar-bar.current')
    const targets = wrapper.findAll('.radar-bar.target')
    expect(currents).toHaveLength(2)
    expect(targets).toHaveLength(2)
    // 62.4 四舍五入成 62；字符串 "70" 读得懂
    expect(currents.map((n) => n.element.style.width)).toEqual(['62%', '70%'])
    expect(targets.map((n) => [n.element.style.width, n.element.style.left])).toEqual([
      ['28%', '62%'],
      ['18%', '70%'],
    ])
    expect(texts(wrapper, '.radar-val')).toEqual(['62', '70'])
    expect(texts(wrapper, '.radar-val-target')).toEqual(['→90', '→88'])
    expect(wrapper.findAll('.radar-unknown')).toHaveLength(0)
  })

  it('读不懂的那一行：没有条子、没有减法，只有暂无数据', () => {
    const wrapper = radarRows({
      skill_radar: {
        dimensions: [
          { name: '模型写了中文', current_score: '约80', target_score: 90 },
          { name: '漏了当前分', target_score: 70 },
          { name: '漏了目标分', current_score: 40 },
          { name: '两个都漏' },
          { name: '可读', current_score: 30, target_score: 55 },
        ],
      },
    })
    expect(wrapper.findAll('.radar-row')).toHaveLength(5)
    // 四条读不懂的都不给宽度：`width: NaN%` / `undefined%` / `约80%` 全是非法值，
    // 以前浏览器会静默丢掉整条，屏幕上看不出来少了什么
    expect(wrapper.findAll('.radar-bar')).toHaveLength(2)
    expect(wrapper.findAll('.radar-unknown')).toHaveLength(4)
    expect(wrapper.findAll('.radar-unknown').map((n) => n.text())).toEqual([
      '暂无数据',
      '暂无数据',
      '暂无数据',
      '暂无数据',
    ])
    expect(wrapper.text()).not.toContain('NaN')
    expect(wrapper.text()).not.toContain('undefined')
    expect(wrapper.text()).not.toContain('约80')
  })

  it('目标分低于当前分时宽度夹在 0 之上——负数同样是非法值', () => {
    const wrapper = radarRows({
      skill_radar: { dimensions: [{ name: '已经超标', current_score: 90, target_score: 70 }] },
    })
    const target = wrapper.find('.radar-bar.target')
    expect(target.element.style.width).toBe('0%')
    expect(target.element.style.left).toBe('90%')
    // 分数照旧是真的：这不是"读不懂"，是"目标已经达成"
    expect(texts(wrapper, '.radar-val-target')).toEqual(['→70'])
    expect(wrapper.findAll('.radar-unknown')).toHaveLength(0)
  })

  it('dimensions 不是数组时整块雷达不渲染，而不是抛错', () => {
    for (const careerData of [
      { skill_radar: null },
      { skill_radar: {} },
      { skill_radar: { dimensions: null } },
      { skill_radar: { dimensions: 'x' } },
      { skill_radar: { dimensions: [] } },
    ]) {
      const wrapper = radarRows(careerData)
      expect(wrapper.find('.radar-chart').exists()).toBe(false)
      expect(wrapper.findAll('.radar-row')).toHaveLength(0)
      // 面板整体不出现，标题也不出现——没数据就不该有个空标题占位
      expect(texts(wrapper, '.panel-title-row h3')).not.toContain('📊 技能雷达')
    }
  })

  it('careerData 压根没传时是空态，不是半截雷达', () => {
    for (const careerData of [undefined, null]) {
      const wrapper = radarRows(careerData)
      expect(wrapper.find('.radar-chart').exists()).toBe(false)
      expect(wrapper.text()).toContain('暂无职业规划数据')
    }
  })
})
