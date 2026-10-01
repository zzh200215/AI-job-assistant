import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import SmartAnalysis from '@/features/analysis/views/SmartAnalysis.vue'
import { getAnalysis } from '@/api/analysis'
import { generateOptimized } from '@/api/resume'
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
    /* D65 之后这三列住进 SkillsPane：它们要经过页面的两条本地化 computed 才上屏，
       所以夹具故意混着"对象条目"和"裸字符串"两种形状，递错列（把 gaps 当 strengths 递）会在屏幕上现形。 */
    strengths: [{ item: 'Go 并发', impact: '命中必需项' }, '有主导项目'],
    gaps: [{ item: 'Rust', action: '补一个副作用示例', severity: '高' }],
    risk_points: ['经验年限偏低'],
  },
  /* D65 之后 optimize 与 summary 两段各自住进一个面板，中间隔着页面的 `result`：
     页面少递一个参数不会报错，只会那一整块空掉，所以下面有一条穿过 DOM 的接线断言。 */
  optimize_suggestions: {
    overall: '结构可用',
    sections: [{ section: '工作经历', suggestions: ['量化产出'] }],
    keywords_to_add: ['K8s'],
    keywords_to_remove: ['精通'],
    format_tips: ['一页 A4'],
  },
  final_report: {
    summary: {
      candidate_name: '张三',
      target_position: '平台后端',
      recommendation: '谨慎投递',
      overall_evaluation: '整体可用',
    },
    action_items: [{ priority: '高', action: '补 Go 并发项目', reason: 'JD 必需项' }],
    development_advice: { short_term: ['两个月补 K8s'], long_term: ['一年内带到 P6'] },
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

vi.mock('@/api/resume', () => ({
  uploadResume: vi.fn(async () => ({ id: 7 })),
  parseResume: vi.fn(async () => ({ parsed: true })),
  /* 故意让它**失败**：成功那一支会写 `window.location.href`，jsdom 里那是"Not implemented: navigation"。
     这条要验的是"面板那颗按钮的出口能不能穿到页面的请求"，与请求之后发生什么无关。 */
  generateOptimized: vi.fn(async () => {
    throw new Error('测试内不真的生成')
  }),
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

/* D65 之后这两处住在面板组件里，但读的仍是同一个 DOM：优化那颗按钮、综合评价那张表。 */
function generateButton() {
  return [...document.querySelectorAll('.generate-area button')][0]
}

/* el-table 的格子要等一次 flush 才画得出来（D64 学到的：那时以为 jsdom 画不出，
   其实是探针没等，读早了拿到空文本）。 */
async function tableRows() {
  await flushPromises()
  return [...document.querySelectorAll('.el-table__body tr')].map((tr) =>
    [...tr.querySelectorAll('td')].map((td) => td.textContent.replace(/\s+/g, ' ').trim())
  )
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

  /* D65 把剩下 5 个标签页搬进 components/，其中「个性化面试题」这一页上头已经有用例在穿
     （`interviewGroupTitles` / `interviewQuestions` 现在都落在 InterviewQuestionsPane 里），
     「职业方向」由 smartAnalysisStaleChain 第三条穿过（它点标签页、发请求、按屏幕上的标题判定）。
     下面这两条补的是剩下三块没人穿过的那部分：入参少递一个不会报错，只会那一整块空掉。 */
  it('技能匹配面板拿到的就是这条记录里那三列，不是别的列', async () => {
    await runAnalysis()
    const colText = (label) => {
      const col = [...document.querySelectorAll('.el-col')].find((c) =>
        c.querySelector('h4')?.textContent.trim().startsWith(label)
      )
      return col.textContent.replace(/\s+/g, ' ').trim()
    }
    expect(colText('已匹配技能')).toBe('已匹配技能GoK8s')
    expect(colText('缺失技能')).toBe('缺失技能Rust')
    expect(colText('优势')).toContain('Go 并发：命中必需项')
    expect(colText('优势')).toContain('有主导项目')
    expect(colText('差距')).toContain('Rust：补一个副作用示例')
    expect(colText('风险')).toContain('经验年限偏低')
  })

  it('简历优化与综合评价两个面板各自吃到记录里那一段，按钮那颗出口也穿到页面', async () => {
    await runAnalysis()
    /* 优化段 */
    expect(document.querySelector('.el-collapse-item__header').textContent.trim()).toBe(
      '【工作经历】'
    )
    expect(
      [...document.querySelectorAll('.el-collapse-item li')].map((n) => n.textContent.trim())
    ).toEqual(['量化产出'])
    expect(
      [...document.querySelectorAll('.el-tab-pane .el-col .el-tag')].map((n) =>
        n.textContent.trim()
      )
    ).toContain('K8s')
    expect(generateButton().textContent).toContain('生成优化版简历')
    generateButton().click()
    await flushPromises()
    /* 面板只发事件，请求由页面发：入参是页面的 resumeInfo / jdInfo（路由 query 里的 7 与 3）。 */
    expect(generateOptimized).toHaveBeenCalledWith(7, 3)

    /* 综合评价段：这一页有**两张** el-descriptions（分数区那张四维表也叫这个类），
       所以必须按标签页的 pane 作用域查——全局第一条拿到的是四维表。 */
    const desc = document
      .querySelector('#pane-summary .el-descriptions')
      .textContent.replace(/\s+/g, ' ')
    expect(desc).toContain('张三')
    expect(desc).toContain('平台后端')
    expect((await tableRows())[0]).toEqual(['高', '补 Go 并发项目', 'JD 必需项'])
    expect([...document.querySelectorAll('.dev-card li')].map((n) => n.textContent.trim())).toEqual(
      ['两个月补 K8s', '一年内带到 P6']
    )
  })
})
