import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElInput } from 'element-plus'

import SmartAnalysis from '@/features/analysis/views/SmartAnalysis.vue'
import { installElement } from '@/plugins/element'

/* 这一页从没进过 D28–D32 那轮并发审计（那轮有结论的 23 个页面里没有它）。D50 搬这三条链时补上：
   它们都在 `await` 之后直接写 ref，而"再跑一次分析"会换掉它们请求的对象——换了 JD 再跑，上一份
   JD 的解释如果回得晚，就盖在新 JD 的结果上面；换了简历再跑，职业方向与引用来源同理。
   三条用例同一个形状：第一轮的发出去不回，跑第二轮，第二轮先回来，第一轮回得晚。
   **搬之前这条文件是红的**（屏幕上留下的是第一轮的内容），每条链各自领了令牌之后才绿。 */

function deferred() {
  let resolve
  const promise = new Promise((res) => {
    resolve = res
  })
  return { resolve, promise }
}

const explains = []
const referenceCalls = []
const careerCalls = []
const records = new Map()
let recordSeq = 0

vi.mock('@/api/analysis', () => ({
  runFullAnalysis: vi.fn(async () => ({ task_id: `task-${++recordSeq}` })),
  getAnalysis: vi.fn(async (recordId) => records.get(recordId)),
  getAnalysisReferences: vi.fn((recordId) => {
    const d = deferred()
    referenceCalls.push({ ...d, recordId })
    return d.promise
  }),
  explainMatch: vi.fn((params) => {
    const d = deferred()
    explains.push({ ...d, params })
    return d.promise
  }),
}))

vi.mock('@/api/jobs', () => ({
  recommendCareerPaths: vi.fn((resumeId) => {
    const d = deferred()
    careerCalls.push({ ...d, resumeId })
    return d.promise
  }),
}))

vi.mock('@/api/jd', () => ({
  createJD: vi.fn(async (body) => ({ id: body.title === '岗位A' ? 11 : 22 })),
  parseJD: vi.fn(async () => ({})),
}))

vi.mock('@/composables/useAgentTaskPolling', () => ({
  useAgentTaskPolling: () => ({
    isPolling: { value: false },
    pollTask: async (taskId, handlers) => {
      handlers.onCompleted({
        status: 'completed',
        analysis_record_id: Number(taskId.split('-')[1]),
      })
    },
  }),
}))

const WEIGHTS = {
  skill: 0.35,
  project: 0.2,
  experience: 0.2,
  education: 0.1,
  keyword: 0.1,
  bonus: 0.05,
}

function record(id, resumeId, jdId) {
  return {
    id,
    record_id: id,
    resume_id: resumeId,
    jd_id: jdId,
    match_score: 70,
    match_report: { dimension_scores: {}, recommendation: '可以投递', summary: '' },
  }
}

async function typeJD(wrapper, title) {
  const inputs = wrapper
    .findAllComponents(ElInput)
    .filter((w) => w.element.closest('.jd-form'))
    .map((w) => w.vm)
  inputs[0].$emit('update:modelValue', title)
  inputs[2].$emit('update:modelValue', `${title} 的 JD 正文`)
  await flushPromises()
}

async function analyze(wrapper, title) {
  if (wrapper.find('.jd-ready').exists()) {
    await wrapper.find('.jd-ready button').trigger('click')
    await flushPromises()
  }
  await typeJD(wrapper, title)
  await wrapper.find('.action-bar button').trigger('click')
  await flushPromises()
}

async function clickTab(wrapper, name) {
  const nav = wrapper
    .findAll('.el-tabs__item')
    .find((n) => n.attributes('aria-controls') === `pane-${name}`)
  await nav.trigger('click')
  await flushPromises()
}

/* 记录 1 = 简历 7 + 岗位 A，记录 2 = 简历 8 + 岗位 B：两条链的入参都换了。
   `runFullAnalysis` 每次自增一个记录号，所以第二轮拿到的一定是记录 2。 */
async function openPage() {
  recordSeq = 0
  explains.length = 0
  referenceCalls.length = 0
  careerCalls.length = 0
  records.set(1, record(1, 7, 11))
  records.set(2, record(2, 8, 22))
  const route = {
    path: '/smart-analysis',
    name: 'smart-analysis',
    component: { template: '<div />' },
  }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push({ path: '/smart-analysis', query: { resume_id: '7' } })
  await router.isReady()
  const wrapper = mount(SmartAnalysis, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function paneText(name) {
  return document.getElementById(`pane-${name}`)?.textContent ?? null
}

/* `onCompleted` 是先 `await loadExplainMatch(true)` 再 `await loadReferences(true)`：
   解释那一发不回，引用来源就根本不会发出去。所以除"解释"那条用例之外，
   另外两条都要先把在飞的解释放行，才拿得到引用来源的请求。 */
const explainPayload = (jdId) => ({
  recommendation: '可以投递',
  overall_reason: `JD ${jdId} 的解释`,
  weights_used: WEIGHTS,
  skill_match: {},
  dimensions: [],
})

async function releaseExplains() {
  for (const e of explains) {
    if (e.released) continue
    e.released = true
    e.resolve(explainPayload(e.params.jd_id))
  }
  await flushPromises()
}

describe('重跑分析时，上一轮的慢响应不能盖在新一轮下面', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('匹配度解释：换了 JD，旧 JD 的解释不能回来', async () => {
    const wrapper = await openPage()
    await analyze(wrapper, '岗位A')
    expect(explains.map((e) => e.params)).toEqual([{ resume_id: 7, jd_id: 11 }])

    await analyze(wrapper, '岗位B')
    /* 第二轮的记录自带 resume_id 8（职业方向那条用例要靠它区分），所以这里解释请求的
       入参也跟着变成 8 + 22：换的是"这一轮分析的是谁、投的哪个岗"两件事。 */
    expect(explains.map((e) => e.params)).toEqual([
      { resume_id: 7, jd_id: 11 },
      { resume_id: 8, jd_id: 22 },
    ])

    explains[1].resolve({
      recommendation: '谨慎投递',
      overall_reason: 'B 的解释',
      weights_used: WEIGHTS,
      skill_match: {},
      dimensions: [],
    })
    await flushPromises()
    expect(paneText('explain')).toContain('B 的解释')

    explains[0].resolve({
      recommendation: '强烈推荐',
      overall_reason: 'A 的解释',
      weights_used: WEIGHTS,
      skill_match: {},
      dimensions: [],
    })
    await flushPromises()
    expect(paneText('explain')).toContain('B 的解释')
    expect(paneText('explain')).not.toContain('A 的解释')
    expect(wrapper).toBeTruthy()
  })

  it('引用来源：旧记录那一发如果落在"新一轮已上屏、新一轮还没发出"的窗口里，也不能上屏', async () => {
    const wrapper = await openPage()
    await analyze(wrapper, '岗位A')
    await releaseExplains()
    expect(referenceCalls.map((c) => c.recordId)).toEqual([1])

    await analyze(wrapper, '岗位B')
    /* 屏幕此刻已经在讲记录 2（简历 8 + 岗位 B）—— `onCompleted` 先 `result.value = data`，
       再 `await loadExplainMatch(true)`，最后才 `loadReferences(true)`。
       所以从"新记录上屏"到"引用来源的新一发领令牌"之间隔着整整一次解释请求的往返，
       旧记录那一发完全来得及在这段窗口里落地。挡住它的是"重跑时作废"那一次领令牌。 */
    referenceCalls[0].resolve({
      references: [{ doc_id: 1, doc_title: 'A 的来源', doc_type: 'general', chunks: [] }],
      query: 'A 的检索词',
      rag_confidence: { score: 0.2, level: 'low', label: '低' },
    })
    await flushPromises()
    expect(paneText('references')).not.toContain('A 的检索词')

    await releaseExplains()
    expect(referenceCalls.map((c) => c.recordId)).toEqual([1, 2])

    referenceCalls[1].resolve({
      references: [{ doc_id: 2, doc_title: 'B 的来源', doc_type: 'general', chunks: [] }],
      query: 'B 的检索词',
      rag_confidence: { score: 0.7, level: 'medium', label: '中' },
    })
    await flushPromises()
    expect(paneText('references')).toContain('B 的检索词')
    expect(paneText('references')).not.toContain('A 的检索词')
    expect(wrapper).toBeTruthy()
  })

  it('职业方向：只在点标签页时取，旧简历的方向回得晚也不能回来', async () => {
    const wrapper = await openPage()
    await analyze(wrapper, '岗位A')
    await clickTab(wrapper, 'career-paths')
    expect(careerCalls.map((c) => c.resumeId)).toEqual([7])

    await analyze(wrapper, '岗位B')
    await clickTab(wrapper, 'career-paths')
    expect(careerCalls.map((c) => c.resumeId)).toEqual([7, 8])

    careerCalls[1].resolve({
      career_paths: [{ title: '平台后端', match_score: 88, category: '高度匹配' }],
      summary: 'B 的方向',
    })
    await flushPromises()
    expect(paneText('career-paths')).toContain('平台后端')

    careerCalls[0].resolve({
      career_paths: [{ title: '数据标注', match_score: 41, category: '可尝试' }],
      summary: 'A 的方向',
    })
    await flushPromises()
    expect(paneText('career-paths')).toContain('平台后端')
    expect(paneText('career-paths')).not.toContain('数据标注')
    expect(wrapper).toBeTruthy()
  })
})
