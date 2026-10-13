import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElProgress } from 'element-plus'

import ResumeReport from '@/features/resume/views/ResumeReport.vue'
import { installElement } from '@/plugins/element'

/* 简历评估报告那一页的六模块上屏。这一族最容易出错的地方都不在接口里，而在"画出来的东西"：
   ① 七维每维满分不同（5~20），进度条与色调必须按 `score / full` 的比例，拿原始分上色会把
      个人优势那一档（最高 5 分）画成一个大红项；
   ② 未评分不是 0 分——那一行既不画条也不涂色，合计跟着变"未评分"；
   ③ 批改稿左栏是**候选人的原简历**，按 `sections` 顺序全部铺开，一段都不许省；
   ④ 左栏的上标编号与右栏批注严格一一对应，`key` 的那几条要带「关键」；
   ⑤ 只有 `editable` 块的编号才许发"采纳"请求——基本信息、经历抬头、技术栈、教育背景那几栏
      在 `parsed_json` 里没有可写字段，只能提示候选人自己在简历文件里改；
   ⑥ 作业没跑完就离开这一页：停轮询，并且不再弹任何一句提示。 */

const api = vi.hoisted(() => ({
  getResumeList: vi.fn(),
  createReportJob: vi.fn(),
  getReportJob: vi.fn(),
  applyReportRedline: vi.fn(),
  downloadReportHtml: vi.fn(),
}))
const services = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/api/resume', () => api)
vi.mock('@/api/jd', () => ({ getJDList: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/plugins/element-services', () => services)

const SECTION_LABELS = [
  '基本信息',
  '个人优势',
  '个人技能',
  '工作经历',
  '某科技公司 · 后端工程师',
  '项目经验',
  '技术栈',
  '内部检索演示 · 算法负责人',
  '教育背景',
]

function sections() {
  return [
    {
      block_id: 'basic',
      kind: 'basic',
      label: '基本信息',
      text: '测试候选人 · 13800000000 · 求职意向：RAG 应用开发',
      char_count: 20,
      editable: false,
    },
    {
      block_id: 'self_evaluation',
      kind: 'self_evaluation',
      label: '个人优势',
      text: '三年后端开发经验，做过内部知识库问答',
      char_count: 18,
      editable: true,
    },
    {
      block_id: 'skills',
      kind: 'skills',
      label: '个人技能',
      text: 'Python、LangChain、Milvus',
      char_count: 18,
      editable: true,
    },
    {
      block_id: 'work[0].header',
      kind: 'work_header',
      label: '工作经历',
      text: '某科技公司　后端工程师　2023.06–至今',
      char_count: 18,
      editable: false,
    },
    {
      block_id: 'work[0].desc',
      kind: 'work',
      label: '某科技公司 · 后端工程师',
      text: '负责订单链路重构，接口 P90 从 800ms 降到 400ms',
      char_count: 24,
      editable: true,
    },
    {
      block_id: 'proj[0].header',
      kind: 'project_header',
      label: '项目经验',
      text: '项目 1 · 内部检索演示　算法负责人',
      char_count: 16,
      editable: false,
    },
    {
      block_id: 'proj[0].tech',
      kind: 'project_tech',
      label: '技术栈',
      text: 'Milvus、bge、ES',
      char_count: 12,
      editable: false,
    },
    {
      block_id: 'proj[0].desc',
      kind: 'project',
      label: '内部检索演示 · 算法负责人',
      text: '搭建召回链路，离线评测集 300 条',
      char_count: 16,
      editable: true,
    },
    {
      block_id: 'education',
      kind: 'education',
      label: '教育背景',
      text: '本科　计算机科学与技术',
      char_count: 10,
      editable: false,
    },
  ]
}

/** 六个编号按 `sections` 的顺序连续分配：1 基本信息、2 个人优势、3 技能、4 工作段、5 技术栈、6 项目段。 */
function redline() {
  return {
    mode: 'changes',
    stat: '共 6 处改动，其中 3 处是关键项（改完并补齐【待补】数据就能投）',
    total: 6,
    key_total: 3,
    free_note: '',
    blocks: [
      {
        block_id: 'basic',
        label: '基本信息',
        text: '测试候选人 · 13800000000 · 求职意向：RAG 应用开发',
        editable: false,
        edits: [
          {
            mark: 1,
            block_id: 'basic',
            del: '求职意向：RAG 应用开发',
            ins: '求职意向：RAG 应用开发（1 年 8 个月）',
            note: '方向标签要 5 秒判得出来，现在这一栏只有岗位名没有年限。',
            key: true,
          },
        ],
      },
      {
        block_id: 'self_evaluation',
        label: '个人优势',
        text: '三年后端开发经验，做过内部知识库问答',
        editable: true,
        edits: [
          {
            mark: 2,
            block_id: 'self_evaluation',
            del: '三年后端开发经验',
            ins: '三年后端开发经验，其中 1 年 8 个月在做 RAG 应用交付',
            note: '优势段要指向与项目呼应的方向，现在只有一句年限。',
            key: true,
          },
        ],
      },
      {
        block_id: 'skills',
        label: '个人技能',
        text: 'Python、LangChain、Milvus',
        editable: true,
        edits: [
          {
            mark: 3,
            block_id: 'skills',
            del: 'Python、LangChain、Milvus',
            ins: 'Python、LangChain、Milvus、【待补：按评测脚本跑出的召回率】',
            note: '写了名词的项要能在项目里找到对应实践。',
            key: false,
          },
        ],
      },
      {
        block_id: 'work[0].desc',
        label: '某科技公司 · 后端工程师',
        text: '负责订单链路重构，接口 P90 从 800ms 降到 400ms',
        editable: true,
        edits: [
          {
            mark: 4,
            block_id: 'work[0].desc',
            del: '接口 P90 从 800ms 降到 400ms',
            ins: '接口 P90 从 800ms 降到 400ms（口径：网关侧 7 天均值）',
            note: '指标没有口径，面试官第一个问题就是"这数怎么量的"。',
            key: true,
          },
        ],
      },
      {
        block_id: 'proj[0].tech',
        label: '技术栈',
        text: 'Milvus、bge、ES',
        editable: false,
        edits: [
          {
            mark: 5,
            block_id: 'proj[0].tech',
            del: 'Milvus、bge、ES',
            ins: 'Milvus、bge、ES BM25',
            note: '这一栏是字段值，采纳写不进去，请在简历文件里自己补上。',
            key: false,
          },
        ],
      },
      {
        block_id: 'proj[0].desc',
        label: '内部检索演示 · 算法负责人',
        text: '搭建召回链路，离线评测集 300 条',
        editable: true,
        edits: [
          {
            mark: 6,
            block_id: 'proj[0].desc',
            del: '离线评测集 300 条',
            ins: '离线评测集 300 条，前 5 召回【待补：按评测脚本跑一遍】',
            note: '只给绝对值、没有优化前后对照，细节密度就上不去。',
            key: false,
          },
        ],
      },
    ],
  }
}

function dimensions() {
  const fulls = [20, 10, 20, 15, 20, 10, 5]
  const scores = [14, 6, 15, 9, 13, 7, 3]
  const labels = [
    '指标责任与达成（C）★',
    '面试钩子设计（E）★',
    '岗位契合度（赛道定位）',
    '技术可迁移性',
    '项目深度与真实感',
    '表达与结构',
    '个人优势介绍',
  ]
  return labels.map((label, i) => ({
    key: `dim_${i}`,
    label,
    full: fulls[i],
    star: i < 2,
    score: scores[i],
    note: `第 ${i + 1} 处的待优化点`,
  }))
}

function reportObject(overrides = {}) {
  return {
    resume_id: 1,
    jd_id: null,
    target_position: 'RAG 应用开发',
    report_date: '2026-10-13',
    verdict: {
      direction: 'RAG 应用开发',
      direction_basis: '按简历关键词自动识别（本次没有附目标岗位）',
      target_level: '中级',
      level_basis: '一年八个月同类交付',
      candidate_name: '测试候选人',
    },
    dimensions: dimensions(),
    total_score: 67,
    grade: 'C',
    grade_desc: '项目描述需要重构后再投',
    grade_scale: 'A 85 以上 / B 75–84 / C 65–74 / D 64 及以下',
    to_next_grade: ['把订单链路那条指标的口径补上'],
    missing_keywords: ['RAG 评测', '重排'],
    competition: {
      positioning_badge: '同赛道前 20%',
      positioning_note: '基础盘够用，缺一个报得出数的指标',
      cards: ['打招呼第一句可以直接说：做过三年后端、上手过完整召回链路'],
      gaps: ['评测数字要在 1–2 天内补上'],
      advice: ['投 AI 应用开发方向，不碰纯算法岗'],
      salary_note: '25–35K 一段',
      salary_provided: false,
    },
    redline: redline(),
    interview: {
      deferred: false,
      note: '',
      questions: [
        {
          no: 1,
          question: '订单链路重构你先动了哪一块？',
          kind: '项目深挖',
          project: '项目 1',
          answer: '我先从网关侧的统计口径开始，把 P90 的算法定下来再改代码。',
          followups: [
            { kind: '为什么', text: '为什么不先加缓存？' },
            { kind: '权衡/代价', text: '改了口径之后老告警怎么对齐？' },
            { kind: '数据', text: '优化前后的样本量各是多少？' },
          ],
          status: '需补强',
          missing: ['P90 的统计口径', '样本量'],
        },
        {
          no: 2,
          question: 'BM25 与向量召回你怎么混？',
          kind: '对比权衡',
          project: '通用',
          answer: '两路各取前 50，再用一个轻量重排合在一起。',
          followups: [{ kind: '边界', text: '向量库挂了的时候怎么办？' }],
          status: '可答',
          missing: [],
        },
      ],
      distribution: {
        total: 2,
        by_kind: { 项目深挖: 1, 对比权衡: 1 },
        by_project: { '项目 1': 1, 通用: 1 },
        weak: 1,
      },
    },
    apply_strategy: {
      source: 'docs/report-templates/boss_zhipin_strategy.md',
      chapters: [
        {
          title: '三、打招呼话术',
          paragraphs: [
            '**第一句**要短，先把能报出的结果说出来。',
            '| 岗位 | 说法 |\n| --- | --- |\n| 后端 | 先给结果 |',
          ],
        },
      ],
    },
    sections: sections(),
    personalization: {
      one_line_label: '1 年多 AI 应用开发经验',
      opener: '三个项目的检索链路都是我搭的',
    },
    ...overrides,
  }
}

function jobPayload(report, status = 'completed') {
  return {
    job_id: 77,
    resume_id: 1,
    jd_id: null,
    target_position: 'RAG 应用开发',
    status,
    total_score: report ? report.total_score : null,
    grade: report ? report.grade : null,
    create_time: '2026-10-13T00:00:00Z',
    finished_at: status === 'completed' ? '2026-10-13T00:02:00Z' : null,
    report: report || null,
  }
}

const RESUME_ROW = { id: 1, name: '测试候选人', file_name: 'a.pdf', parsed: {} }

async function mountPage({ report = reportObject(), jobId = 77 } = {}) {
  api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
  api.getReportJob.mockResolvedValue(jobPayload(report))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/resume/report', name: 'resume-report', component: { template: '<div />' } },
      { path: '/resume-center', name: 'resume-center', component: { template: '<div />' } },
    ],
  })
  const query = jobId ? { resume_id: '1', job_id: String(jobId) } : { resume_id: '1' }
  await router.push({ name: 'resume-report', query })
  await router.isReady()
  const wrapper = mount(ResumeReport, {
    attachTo: document.body,
    global: { plugins: [installElement, router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

/** 只在第一个用例里用到：从"没有 job"那一屏点一次「开始生成报告」。 */
async function mountAndStart() {
  api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
  api.createReportJob.mockResolvedValue({ job_id: 77, status: 'pending' })
  api.getReportJob.mockResolvedValue(jobPayload(reportObject()))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/resume/report', name: 'resume-report', component: { template: '<div />' } },
      { path: '/resume-center', name: 'resume-center', component: { template: '<div />' } },
    ],
  })
  await router.push({ name: 'resume-report', query: { resume_id: '1' } })
  await router.isReady()
  const wrapper = mount(ResumeReport, {
    attachTo: document.body,
    global: { plugins: [installElement, router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  for (const fn of [...Object.values(api), ...Object.values(services.ElMessage)]) fn.mockClear()
  document.body.innerHTML = ''
})

/** 与 `resumeRewriteJobPolling.test.js` 同一个 `tick`：推进假表之后还要把微任务队列排干净，
    否则那一趟轮询根本没机会把下一次 `setTimeout` 排上。 */
async function tick(ms) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

describe('评分概览那一屏', () => {
  it('七个维度全画出来，进度条按 score / full 的比例而不是原始分', async () => {
    const wrapper = await mountPage()
    expect(wrapper.findAll('.rr-dim-row')).toHaveLength(7)
    expect(wrapper.findAllComponents(ElProgress).map((p) => p.props('percentage'))).toEqual([
      70, 60, 75, 60, 65, 70, 60,
    ])
    // 画到 DOM 上的那一条宽度必须是同一个数
    const widths = wrapper
      .findAll('.el-progress-bar__inner')
      .map((bar) => /width:\s*(\d+)%/.exec(bar.attributes('style') || '')?.[1])
    expect(widths).toEqual(['70', '60', '75', '60', '65', '70', '60'])
    expect(wrapper.find('#m-score').text()).toContain('14 / 20')
    expect(wrapper.find('#m-score').text()).toContain('3 / 5')
    wrapper.unmount()
  })

  it('未评分那一维不画成 0：没有进度条、写着未评分，合计跟着变未评分', async () => {
    const dims = dimensions()
    dims[3] = { ...dims[3], score: null }
    const wrapper = await mountPage({
      report: reportObject({ dimensions: dims, total_score: null, grade: null }),
    })
    expect(wrapper.findAllComponents(ElProgress)).toHaveLength(6)
    const rowText = wrapper.findAll('.rr-dim-row')[3].text()
    expect(rowText).toContain('未评分')
    expect(rowText).toContain('本次分析未给出该维度评分')
    expect(rowText).not.toContain('0 / 15')
    expect(wrapper.find('.rr-total-row').text()).toContain('未评分')
    wrapper.unmount()
  })

  it('等级说明与「距上一档还差什么」都在评分概览结尾', async () => {
    const wrapper = await mountPage()
    const text = wrapper.find('#m-score').text()
    expect(text).toContain('A 85 以上')
    expect(text).toContain('C：项目描述需要重构后再投')
    expect(text).toContain('距上一档还差：把订单链路那条指标的口径补上')
    wrapper.unmount()
  })
})

describe('批改稿那一屏', () => {
  it('左栏按 sections 顺序把原简历全部铺开，一段都不省', async () => {
    const wrapper = await mountPage()
    const blocks = wrapper.findAll('.rr-block')
    expect(blocks).toHaveLength(9)
    expect(blocks.map((b) => b.find('.rr-block-label').text())).toEqual(SECTION_LABELS)
    const paper = wrapper.find('.rr-paper').text()
    // 没被改动的句子原样保留：教育背景、项目抬头、工作经历抬头都在
    for (const fragment of [
      '13800000000',
      '2023.06–至今',
      '项目 1 · 内部检索演示',
      '计算机科学与技术',
      '做过内部知识库问答',
    ]) {
      expect(paper).toContain(fragment)
    }
    expect(paper).not.toMatch(/同上|以此类推|其余项目照此|此处省略/)
    wrapper.unmount()
  })

  it('左栏上标编号与右栏批注一一对应，关键的那几条带徽标', async () => {
    const wrapper = await mountPage()
    const leftMarks = wrapper.findAll('.rr-mark').map((n) => n.text())
    const rightMarks = wrapper.findAll('.rr-note .el-checkbox__label').map((n) => n.text().trim())
    expect(leftMarks).toEqual(['1', '2', '3', '4', '5', '6'])
    expect(rightMarks).toEqual(leftMarks)
    expect(wrapper.findAll('.rr-note')).toHaveLength(6)
    expect(wrapper.findAll('.rr-note-key')).toHaveLength(3)
    expect(wrapper.findAll('.rr-note-key .el-tag').map((t) => t.text())).toEqual([
      '关键',
      '关键',
      '关键',
    ])
    expect(wrapper.find('.rr-stat').text()).toBe(
      '共 6 处改动，其中 3 处是关键项（改完并补齐【待补】数据就能投）'
    )
    wrapper.unmount()
  })

  it('不可写回的那几栏标出来后给的是"自己改"的提示，勾选框同时被禁用', async () => {
    const wrapper = await mountPage()
    expect(wrapper.findAll('.rr-manual-hint').length).toBeGreaterThan(0)
    const boxes = wrapper.findAll('.rr-note .el-checkbox')
    expect(boxes).toHaveLength(6)
    expect(boxes.filter((b) => b.classes().includes('is-disabled'))).toHaveLength(2) // 编号 1 与编号 5
    wrapper.unmount()
  })

  it('切到「仅看改后净稿」：删除线与编号消失、改后内容退回正文、右栏整列收起', async () => {
    const wrapper = await mountPage()
    expect(wrapper.findAll('del')).toHaveLength(6)
    expect(wrapper.findAll('ins')).toHaveLength(6)
    wrapper.vm.cleanOnly = true
    await flushPromises()
    expect(wrapper.findAll('del')).toHaveLength(0)
    expect(wrapper.findAll('ins')).toHaveLength(0)
    expect(wrapper.findAll('.rr-mark')).toHaveLength(0)
    expect(wrapper.find('.rr-side').exists()).toBe(false)
    // 净稿里改后的内容还在，只是不再是"插进去的记号"
    expect(wrapper.find('.rr-paper').text()).toContain('口径：网关侧 7 天均值')
    wrapper.unmount()
  })

  it('只有 editable 块的编号会进"采纳"请求；默认勾上的只有可写回的关键项', async () => {
    const wrapper = await mountPage()
    expect(wrapper.vm.pickedMarks).toEqual([2, 4])
    api.applyReportRedline.mockResolvedValue({
      changed: true,
      applied: [{ block_id: 'self_evaluation', before: 'b', after: 'a' }],
      rejected: [],
      snapshot_version_id: 9,
      resume_version: 3,
      block_total: 4,
      score: { before: { score: 67 }, after: { score: 71 }, delta: 4 },
    })
    wrapper.vm.pickedMarks = [1, 2, 4, 5]
    const button = wrapper.findAll('button').find((b) => b.text().includes('应用已采纳'))
    await button.trigger('click')
    await flushPromises()
    expect(api.applyReportRedline).toHaveBeenCalledTimes(1)
    expect(api.applyReportRedline.mock.calls[0]).toEqual([77, [2, 4]])
    expect(wrapper.text()).toContain('匹配分 67 → 71（+4）')
    expect(wrapper.text()).toContain('已写回 1 处：个人优势')
    wrapper.unmount()
  })

  it('没指定目标岗位时不说分数变化，只说不显示', async () => {
    const wrapper = await mountPage()
    api.applyReportRedline.mockResolvedValue({
      changed: true,
      applied: [{ block_id: 'work[0].desc' }],
      rejected: [],
      score: { before: null, after: null, delta: null },
    })
    wrapper.vm.pickedMarks = [4]
    const button = wrapper.findAll('button').find((b) => b.text().includes('应用已采纳'))
    await button.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('未指定目标岗位，本次不显示匹配分变化')
    expect(wrapper.text()).not.toContain('匹配分 67')
    wrapper.unmount()
  })

  it('批改稿这一节没出来时只说没生成，不伪造内容', async () => {
    const wrapper = await mountPage({ report: reportObject({ redline: null }) })
    expect(wrapper.find('#m-resume').text()).toContain('这一节这次没能生成')
    expect(wrapper.find('.rr-paper').exists()).toBe(false)
    expect(wrapper.find('.rr-side').exists()).toBe(false)
    wrapper.unmount()
  })

  it('「复制净稿」拿走的是九段齐全、del 已换成 ins 的干净文本，不带编号与批注', async () => {
    const wrapper = await mountPage()
    const draft = wrapper.vm.cleanDraft
    for (const label of SECTION_LABELS) expect(draft).toContain(label)
    expect(draft).toContain('求职意向：RAG 应用开发（1 年 8 个月）')
    expect(draft).toContain('其中 1 年 8 个月在做 RAG 应用交付')
    expect(draft).toContain('口径：网关侧 7 天均值')
    // 建议改掉的原话不留：那一处 `del` 的整串不该再出现
    expect(draft).not.toContain('三年后端开发经验，做过内部知识库问答')
    expect(draft).not.toContain('负责订单链路重构，接口 P90 从 800ms 降到 400ms\n')
    // 编号与右栏批注都不进净稿
    expect(draft).not.toContain('方向标签要 5 秒判得出来')
    wrapper.unmount()
  })
})

describe('竞争分析、面试预演与投递策略', () => {
  it('竞争分析给出档位徽标、能打的牌、短板、建议与薪资参考', async () => {
    const wrapper = await mountPage()
    const text = wrapper.find('#m-fit').text()
    expect(wrapper.find('.rr-badge').text()).toBe('同赛道前 20%')
    expect(text).toContain('能打的牌')
    expect(text).toContain('要补的短板')
    expect(text).toContain('针对性建议')
    expect(text).toContain('薪资参考')
    expect(text).toContain('这一段是按目标等级给的参考区间')
    wrapper.unmount()
  })

  it('面试预演每题带标准答案、三条追问的类型标签与状态；标题上有题型分布与总数', async () => {
    const wrapper = await mountPage()
    const text = wrapper.find('#m-interview').text()
    expect(wrapper.findAll('.rr-question')).toHaveLength(2)
    expect(text).toContain('【标准答案】')
    expect(text).toContain('【追问 3】（数据）')
    expect(text).toContain('共 2 题')
    expect(text).toContain('项目深挖 1')
    expect(text).toContain('需补强 1')
    expect(text).toContain('⚠️ 需补强（缺：P90 的统计口径、样本量）')
    expect(text).toContain('✅ 可答')
    wrapper.unmount()
  })

  it('面试那一节被换成暂缓版时，只显示那一段话，不出题', async () => {
    const wrapper = await mountPage({
      report: reportObject({
        interview: {
          deferred: true,
          note: '先把三处必改项补上、跑完【待补】的数，这一节再做价值更大。',
          questions: [],
          distribution: null,
        },
      }),
    })
    expect(wrapper.find('#m-interview').text()).toContain('先把三处必改项补上')
    expect(wrapper.find('#m-interview').text()).toContain('这一节现在做价值不大')
    expect(wrapper.find('#m-interview').text()).not.toContain('【标准答案】')
    expect(wrapper.findAll('.rr-question')).toHaveLength(0)
    wrapper.unmount()
  })

  it('投递策略逐节渲染，段里的表格行画成表、粗体转成 strong', async () => {
    const wrapper = await mountPage()
    const chapter = wrapper.find('.rr-chapter')
    expect(chapter.text()).toContain('三、打招呼话术')
    const table = chapter.find('table')
    expect(table.exists()).toBe(true)
    expect(table.findAll('th').map((h) => h.text())).toEqual(['岗位', '说法'])
    expect(table.findAll('td').map((c) => c.text())).toEqual(['后端', '先给结果'])
    expect(chapter.find('strong').text()).toBe('第一句')
    wrapper.unmount()
  })
})

it('两处填空用的是后端算好的引用，不是这一页另写一句', async () => {
  const wrapper = await mountPage()

  const chapter = wrapper
    .findAll('.rr-chapter')
    .find((node) => node.text().includes('本报告的两处填空'))

  expect(chapter.text()).toContain('在线简历一句话标签')
  expect(chapter.text()).toContain('1 年多 AI 应用开发经验')
  expect(chapter.text()).toContain('三个项目的检索链路都是我搭的')
  expect(chapter.find('.rr-quote').exists()).toBe(true)
})

it('报告里没有填空素材时那一块整个不出现，不拿空壳占位', async () => {
  const wrapper = await mountPage({ report: reportObject({ personalization: {} }) })

  expect(wrapper.text()).not.toContain('本报告的两处填空')
})

describe('这一页的导航、作业与下载', () => {
  it('六个模块按固定锚点成屏，顶部导航有六项并能高亮', async () => {
    const wrapper = await mountPage()
    for (const anchor of ['m-summary', 'm-score', 'm-fit', 'm-resume', 'm-interview', 'm-boss']) {
      expect(document.getElementById(anchor), `缺 #${anchor}`).not.toBe(null)
    }
    const links = wrapper.findAll('.rr-nav-link')
    expect(links.map((l) => l.text().replace(/\s+/g, ''))).toEqual([
      '小结',
      '一、评分概览',
      '二、竞争分析',
      '三、修改建议',
      '四、面试预演',
      '五、投递策略',
    ])
    await links[2].trigger('click')
    expect(wrapper.vm.activeAnchor).toBe('m-fit')
    expect(links[2].classes()).toContain('is-active')
    wrapper.unmount()
  })

  it('小结那一段只有方向、目标等级、评级与日期四件事', async () => {
    const wrapper = await mountPage()
    const text = wrapper.find('#m-summary').text()
    expect(text).toContain('方向定位：RAG 应用开发')
    expect(text).toContain('目标等级：中级（一年八个月同类交付）')
    expect(text).toContain('评级：C（67/100）')
    expect(text).toContain('日期：2026-10-13')
    wrapper.unmount()
  })

  it('没有 job 那一屏点一次就建一个作业并轮询到完成', async () => {
    const wrapper = await mountAndStart()
    expect(wrapper.find('.rr-paper').exists()).toBe(false)
    await wrapper.vm.startReport()
    await flushPromises()
    expect(api.createReportJob).toHaveBeenCalledTimes(1)
    expect(api.getReportJob).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.rr-paper').exists()).toBe(true)
    wrapper.unmount()
  })

  it('在途时重复点不建第二个作业', async () => {
    // 假表要在 mount 之前开：轮询器在组件 setup 时就把 `setTimeout` captured 走了
    vi.useFakeTimers()
    const wrapper = await mountAndStart()
    api.getReportJob.mockResolvedValue(jobPayload(null, 'running'))
    wrapper.vm.startReport()
    await tick(0)
    expect(api.createReportJob).toHaveBeenCalledTimes(1)
    wrapper.vm.startReport()
    wrapper.vm.startReport()
    await tick(0)
    expect(api.createReportJob, '第二发作业要付第二次模型钱').toHaveBeenCalledTimes(1)
    wrapper.unmount()
    vi.useRealTimers()
  })

  it('卸载后停止轮询，并且不再弹提示', async () => {
    vi.useFakeTimers()
    const wrapper = await mountAndStart()
    api.getReportJob.mockResolvedValue(jobPayload(null, 'running'))
    wrapper.vm.startReport()
    await tick(0)
    const before = api.getReportJob.mock.calls.length
    await tick(6000)
    expect(api.getReportJob.mock.calls.length, '还在跑的那一趟没有继续打接口').toBeGreaterThan(
      before
    )
    wrapper.unmount()
    const afterUnmount = api.getReportJob.mock.calls.length
    await tick(20000)
    expect(api.getReportJob.mock.calls.length, '卸载之后还在打接口').toBe(afterUnmount)
    expect(services.ElMessage.error).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('作业失败时屏上只有我们自己的那句话——载荷里若混进服务端原因也不上屏', async () => {
    vi.useFakeTimers()
    const wrapper = await mountAndStart()
    let calls = 0
    api.getReportJob.mockImplementation(async () => {
      calls += 1
      if (calls === 1) return jobPayload(null, 'running')
      return { ...jobPayload(null, 'failed'), error_msg: 'MODEL_RAW_TEXT_should_not_reach_screen' }
    })
    wrapper.vm.startReport()
    await tick(0)
    await tick(4000)
    expect(wrapper.find('.rr-paper').exists()).toBe(false)
    expect(wrapper.text()).toContain('这一份报告没能生成')
    expect(wrapper.text()).not.toContain('MODEL_RAW_TEXT')
    wrapper.unmount()
    vi.useRealTimers()
  })

  it('下载按钮取的是 blob，文件名是「简历评估报告_{姓名}.html」', async () => {
    const blob = { size: 10 }
    api.downloadReportHtml.mockResolvedValue(blob)
    const createObjectURL = vi.fn(() => 'blob:report')
    const revokeObjectURL = vi.fn()
    window.URL.createObjectURL = createObjectURL
    window.URL.revokeObjectURL = revokeObjectURL
    const clicked = []
    vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(function test() {
      clicked.push(this.download)
    })
    const wrapper = await mountPage()
    const button = wrapper.findAll('button').find((b) => b.text().includes('下载独立 HTML'))
    await button.trigger('click')
    await flushPromises()
    expect(api.downloadReportHtml).toHaveBeenCalledWith(77)
    expect(createObjectURL).toHaveBeenCalledWith(blob)
    expect(clicked).toEqual(['简历评估报告_测试候选人.html'])
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:report')
    wrapper.unmount()
    vi.restoreAllMocks()
  })
})
