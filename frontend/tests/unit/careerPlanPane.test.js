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
   所以这里把七个标题逐个钉住——搬进 AppPanel 之后少画任何一个，都会在这里红。 */
describe('七个标题搬进 AppPanel 之后仍逐个在屏幕上', () => {
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
