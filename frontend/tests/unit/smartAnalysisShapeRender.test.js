import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import SmartAnalysis from '@/features/analysis/views/SmartAnalysis.vue'
import { getAnalysis } from '@/api/analysis'
import { installElement } from '@/plugins/element'

/* 这一页此前**一条测试都没有**：D49 把 16 个纯函数搬进 lib 之后，页面只剩"把 result 传进去"这一层
   接线，而那层接线坏了是**不会报错的**——`dimensionScore('skills')` 少传一个参数，函数里
   `'skills'?.match_report` 得到 undefined，页面照样渲染，只是四个维度分全变成 0。
   所以这个文件钉的是接线：一条后端记录进来，屏幕上出现的必须是这几个数。 */

const RECORD = {
  id: 99,
  record_id: 99,
  match_score: 76,
  matched_skills: ['Go', 'K8s'],
  missing_skills: ['Rust'],
  match_report: {
    recommendation: '可以投递',
    summary: '整体匹配',
    dimension_scores: { skills: 0.72, experience: { score: 0.5 }, education: 3, industry: {} },
  },
  /* 面试题故意混着两代字段写：新键 hr_questions 有值，legacy 键 tech 才有值。 */
  interview_questions: {
    hr_questions: [{ question: '为什么离开上一家', focus: '稳定性' }],
    tech: [{ q: '解释事件循环', intent: '基础' }],
  },
  rag_confidence: { score: 0.8, level: 'high' },
  career_planning: {
    skill_gaps: [{ skill: 'Rust', priority: '高' }],
    /* D51 之后这一段的渲染住在 CareerPlanPane 里，页面只做一件事：把 `visualPhases`
       （由这条记录推出来的那条链的产物）作为 prop 递进去。递错对象是**不会报错**的，
       所以这里要有一条屏幕上看得见的断言。 */
    visual_roadmap: {
      total_duration_months: 18,
      career_direction: '平台工程师',
      phases: [{ id: 'p1', name: '打基础', duration_months: 6, color: '#196bdb' }],
    },
  },
}

/* `weights_used` 不是可选的：`schemas/analysis.py:23` 声明成必填 dict，取的是评分卡里的六个权重，
   而视图直接读它的六个键。夹具按后端的真实形状给，免得把一个生产到不了的路径当成缺陷。 */
const EXPLAIN = {
  recommendation: '可以投递',
  overall_reason: '技能与经验都够',
  weights_used: {
    skill: 0.35,
    project: 0.2,
    experience: 0.2,
    education: 0.1,
    keyword: 0.1,
    bonus: 0.05,
  },
  skill_match: { matched: ['Go'], missing_required: ['Rust'], missing_nice: ['K8s', 'Rust'] },
}

vi.mock('@/api/analysis', () => ({
  runFullAnalysis: vi.fn(async () => ({ task_id: 't1' })),
  getAnalysis: vi.fn(async () => RECORD),
  getAnalysisReferences: vi.fn(async () => ({
    references: [
      {
        doc_title: '简历模板 A',
        doc_type: 'resume_template',
        chunks: [{ text: '片段一', score: 0.9 }],
      },
      {
        doc_title: '能力模型 B',
        doc_type: 'skill_model',
        chunks: [{ text: '片段二', score: 0.4 }],
      },
    ],
    query: '检索词',
  })),
  explainMatch: vi.fn(async () => EXPLAIN),
}))

vi.mock('@/composables/useAgentTaskPolling', () => ({
  useAgentTaskPolling: () => ({
    isPolling: { value: false },
    pollTask: async (_taskId, handlers) => {
      handlers.onProgress({ status: 'running' }, [
        { step_name: 'intent_recognition', status: 'completed' },
      ])
      handlers.onCompleted({ status: 'completed', analysis_record_id: 99 })
    },
  }),
}))

async function runAnalysis(record = RECORD) {
  vi.mocked(getAnalysis).mockResolvedValue(record)
  const route = {
    path: '/smart-analysis',
    name: 'smart-analysis',
    component: { template: '<div />' },
  }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push({ path: '/smart-analysis', query: { resume_id: '7', jd_id: '3' } })
  await router.isReady()
  const wrapper = mount(SmartAnalysis, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await wrapper.find('.action-bar button').trigger('click')
  await flushPromises()
  return wrapper
}

function dimValues() {
  return [...document.querySelectorAll('.dim-val')].map((n) => n.textContent.trim())
}

/* 面试题那一组的标题：h4 本身没有专属类，但它和 `.q-card` 同在一个 v-for 的 div 里。
   用这个结构关系筛，而不是查所有 h4 —— 技能、解释两个面板也各自有 h4。 */
function interviewGroupTitles() {
  return [...document.querySelectorAll('h4')]
    .filter((h4) => h4.parentElement.querySelector('.q-card'))
    .map((n) => n.textContent.trim())
}

function interviewQuestions() {
  return [...document.querySelectorAll('.q-card .q')].map((n) => n.textContent.trim())
}

function chips() {
  return [...document.querySelectorAll('.score-chips .chip')].map((n) => n.textContent.trim())
}

/* 解释面板的"缺失技能"那一列：夹具故意让 Rust 同时出现在必需列与加分列。
   必须按 pane 作用域查——技能标签页也有一个同名 h4，全局 `find` 会拿到技能那一列。 */
function explainMissingTags() {
  const pane = [...document.querySelectorAll('.el-tab-pane')].find((p) =>
    p.textContent.includes('六维评分详情')
  )
  const col = [...pane.querySelectorAll('.el-col')].find(
    (c) => c.querySelector('h4')?.textContent.trim() === '缺失技能'
  )
  return [...col.querySelectorAll('.el-tag')].map((n) => n.textContent.trim())
}

describe('SmartAnalysis 的展示形状接线', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('四个维度分各自走自己那条回退，屏幕上就是这四个数', async () => {
    await runAnalysis()
    /* skills 给裸数字、experience 给对象、education 给数字、industry 给空对象（→0）。
       漏传 `result` 的写法会把这四项全变成 0，而页面不会报任何错。 */
    expect(dimValues()).toEqual(['0.72', '0.5', '3', '0'])
  })

  it('维度对象没带技能列表时，回退到记录顶层的 matched/missing', async () => {
    await runAnalysis()
    expect(chips()).toEqual(['已匹配 2 项', '待补足 1 项', '置信度 0.8'])
  })

  it('面试题同时认新键与 legacy 键，分组标题从 lib 的表里来', async () => {
    await runAnalysis()
    expect(interviewGroupTitles()).toEqual(['HR 题', '技术题'])
    /* legacy 键 `tech` 归到 `tech_questions` 组，题面读的仍是旧字段名 `q`/`intent`。 */
    expect(interviewQuestions()).toEqual(['Q1：为什么离开上一家', 'Q1：解释事件循环'])
  })

  it('解释面板把必需列与加分列合成一列，重复的那项留在必需列的位置', async () => {
    await runAnalysis()
    expect(explainMissingTags()).toEqual(['Rust', 'K8s'])
  })

  it('引用文档默认只展开第一份，点第二份才展开', async () => {
    await runAnalysis()
    const wraps = () => [...document.querySelectorAll('#pane-references .el-collapse-item__wrap')]
    const headers = [...document.querySelectorAll('#pane-references .el-collapse-item__header')]
    expect(wraps().length).toBe(2)
    expect(wraps()[1].style.display).toBe('none')
    headers[1].click()
    await flushPromises()
    /* 这条**不是**"`v-model:ref-open-docs` 回写承重"的证据：把那条绑定整行删掉，16 条用例
       照样全绿——el-collapse 拿不到受控值时仍按自己的内部状态展开。留着它是因为
       "展开了哪几份"这个值归页面的链持有（面板不该自己改 props，见 analysisResultPanes 那条），
       而屏幕上要留住的是默认只展开第一份。 */
    expect(wraps()[1].style.display).not.toBe('none')
  })

  it('技能缺口第一项是对象时走结构化那一支，是字符串时走列表那一支', async () => {
    await runAnalysis()
    expect(document.querySelectorAll('.gap-skill').length).toBe(1)
    expect(document.querySelector('.gap-title').textContent).toContain('Rust')
    /* 路线图那一段的阶段名是页面递进面板的 `visualPhases` 渲染出来的：
       递 `careerData`（整条记录里的职业规划对象）而不是 `visualPhases` 时，这里就空了。 */
    expect([...document.querySelectorAll('.phase-name')].map((n) => n.textContent.trim())).toEqual([
      '打基础',
    ])
    expect(document.querySelector('.roadmap-dir').textContent).toContain('平台工程师')

    document.body.innerHTML = ''
    await runAnalysis({ ...RECORD, career_planning: { skill_gaps: ['Rust', 'K8s'] } })
    expect(document.querySelectorAll('.gap-skill').length).toBe(0)
    const gapList = [...document.querySelectorAll('.career-section li')].map((n) =>
      n.textContent.trim()
    )
    expect(gapList).toEqual(['📌 Rust', '📌 K8s'])
  })
})
