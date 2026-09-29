import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobSearch from '@/features/jobs/views/JobSearch.vue'
import { installElement } from '@/plugins/element'

/* JobSearch 一页上有 8 个 `await` 后直接写 ref 的加载函数。这一份逐个跑「用户能不能在同一时刻
   叠出两个在途请求，并且落回屏幕的是旧那一轮」：
   - loadLocalJobs / loadRecommendations：共用一个令牌实例，所以其中一条链会把另一条的响应误判为过期；
   - runSearch：预设词标签常驻可点，搜索按钮的 :loading 挡不住它；
   - loadResumeDetail：简历选择器没有 disabled，换两次就是两个在途详情；
   - openJobDetail：抽屉是模态的，但点卡片之后请求并不因关闭而取消，路由跳转也会再开一个。
   证明「并发不了」的那三个（loadCities / loadResumes / loadPipelineEntries）不写在这里，记在 D30。 */

const api = vi.hoisted(() => ({
  jobs: {
    getCities: vi.fn(),
    getJobList: vi.fn(),
    getJobPipelineList: vi.fn(),
    getJobRecommendations: vi.fn(),
    searchExternalJobs: vi.fn(),
    seedDemoJobs: vi.fn(),
    startFullAnalysis: vi.fn(),
    getJobDetail: vi.fn(),
    createJobPipelineEntry: vi.fn(),
    updateJobPipelineEntry: vi.fn(),
    deleteJobPipelineEntry: vi.fn(),
    clearRejectedJobPipeline: vi.fn(),
  },
  resume: { getResumeList: vi.fn(), getResume: vi.fn() },
  analysis: { explainMatch: vi.fn() },
  knowledge: { queryRewriteTest: vi.fn() },
}))

vi.mock('@/api/jobs', () => api.jobs)
vi.mock('@/api/resume', () => api.resume)
vi.mock('@/api/analysis', () => api.analysis)
vi.mock('@/api/knowledge', () => api.knowledge)

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { resolve, reject, promise }
}

/** 每个受测函数的返回值都挂在一个没人推的手上，由测试决定谁先落地。 */
const inflight = {}

function hang(group, name) {
  inflight[name] ||= []
  api[group][name] = vi.fn((...args) => {
    const record = { args, ...deferred() }
    inflight[name].push(record)
    return record.promise
  })
}

function lastOf(name) {
  return [...inflight[name]].pop()
}

function firstOf(name) {
  return inflight[name][0]
}

function countOf(name) {
  return inflight[name].length
}

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const resumeDetail = (id, title, skill) => ({
  id,
  parsed_json: { current_title: title, skills: [skill] },
})

const job = (id, title, company) => ({
  id,
  title,
  company,
  location: '北京',
  salary: '30-50K',
  source: 'boss',
})

let router

async function renderSearch(resumes = [{ id: 7, file_name: '简历甲' }]) {
  api.resume.getResumeList.mockResolvedValue({ items: resumes })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/jobs/search', name: 'job-search', component: { template: '<div />' } }],
  })
  router.push('/jobs/search')
  await router.isReady()
  const wrapper = mount(JobSearch, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

function findTab(wrapper, label) {
  const tab = wrapper.findAll('.el-tabs__item').find((n) => n.text().includes(label))
  expect(tab, `标签头「${label}」没渲染出来，测试前提不成立`).toBeTruthy()
  return tab
}

/** hero 区那几个数字常驻，不用切标签页就能读到：[本次搜索, 岗位仓库, 智能推荐, ...] */
function heroNumbers() {
  return [...document.querySelectorAll('.hero-metrics .metric-card strong')].map((n) =>
    n.textContent.trim()
  )
}

function selectResume(wrapper, id) {
  // 这一页上有来源、城市、筛选好几个 el-select，必须按简历选择器自己的 class 命中
  const select = wrapper.findComponent('.resume-select')
  expect(select, '简历选择器没渲染出来，测试前提不成立').toBeTruthy()
  select.vm.$emit('update:modelValue', id)
  select.vm.$emit('change', id)
}

function searchTitles() {
  return [...document.querySelectorAll('.job-shell .job-title-row h3')].map((n) =>
    n.textContent.trim()
  )
}

async function searchOnce(wrapper, chipIndex, jobs) {
  await wrapper.findAll('.preset-chip')[chipIndex].trigger('click')
  await settle(lastOf('searchExternalJobs'), { jobs })
}

function summarySentToRewrite(wrapper) {
  const button = wrapper.findAll('button').find((b) => b.text() === '生成建议')
  expect(button, '「生成建议」按钮没渲染出来，测试前提不成立').toBeTruthy()
  return button
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  for (const key of Object.keys(inflight)) delete inflight[key]

  api.jobs.getCities.mockResolvedValue({ cities: [] })
  api.jobs.getJobPipelineList.mockResolvedValue({ items: [] })
  api.knowledge.queryRewriteTest.mockResolvedValue({ rewritten_queries: [] })
  api.analysis.explainMatch.mockResolvedValue({})
  for (const name of [
    'seedDemoJobs',
    'startFullAnalysis',
    'createJobPipelineEntry',
    'updateJobPipelineEntry',
    'deleteJobPipelineEntry',
    'clearRejectedJobPipeline',
  ])
    api.jobs[name] = vi.fn().mockResolvedValue({})

  hang('jobs', 'getJobList')
  hang('jobs', 'getJobRecommendations')
  hang('jobs', 'searchExternalJobs')
  hang('jobs', 'getJobDetail')
  hang('resume', 'getResume')
})

describe('岗位搜索：同一时刻的两个在途请求，落回屏幕的必须是后发起的那一个', () => {
  it('推荐链在途时，先发起的岗位仓库响应不能被一起判为过期', async () => {
    const wrapper = await renderSearch()
    const warehouse = lastOf('getJobList')
    expect(warehouse, '挂载时应该已经发出岗位仓库请求').toBeTruthy()

    // 真实动作：仓库响应还没回来，用户切到「智能推荐」，推荐链由此发出
    await findTab(wrapper, '智能推荐').trigger('click')
    await flushPromises()
    expect(countOf('getJobRecommendations'), '切标签页没发推荐请求，测试前提不成立').toBe(1)

    await settle(warehouse, { items: [job(1, '甲岗', '公司甲'), job(2, '乙岗', '公司乙')] })
    expect(heroNumbers()[1], '岗位仓库的数字停在 0').toBe('2')

    await settle(lastOf('getJobRecommendations'), {
      recommendations: [{ jd_id: 9, job_title: '推荐岗', match_score: 88 }],
    })
    expect(heroNumbers()[2], '智能推荐的数字').toBe('1')
    wrapper.unmount()
  })

  it('连点两个快速搜索词，慢回来的那一次不能替换结果', async () => {
    const wrapper = await renderSearch()

    const chips = wrapper.findAll('.preset-chip')
    expect(chips.length).toBeGreaterThanOrEqual(2)
    await chips[0].trigger('click')
    await chips[1].trigger('click')
    expect(countOf('searchExternalJobs'), '点两个预设词只发了一次搜索').toBe(2)

    await settle(lastOf('searchExternalJobs'), { jobs: [job(2, '后点的词的结果', '公司乙')] })
    expect(searchTitles()).toEqual(['后点的词的结果'])

    await settle(firstOf('searchExternalJobs'), { jobs: [job(1, '先点的词的结果', '公司甲')] })
    expect(searchTitles(), '先点那个词的结果把后一次的换掉了').toEqual(['后点的词的结果'])
    expect(heroNumbers()[0]).toBe('1')
    wrapper.unmount()
  })

  it('快速换两次简历，旧简历的详情不能成为「当前简历摘要」', async () => {
    const wrapper = await renderSearch([
      { id: 7, file_name: '简历甲' },
      { id: 8, file_name: '简历乙' },
    ])
    expect(firstOf('getResume').args[0], '挂载后应自动选第一份并拉它的详情').toBe(7)

    selectResume(wrapper, 8)
    await flushPromises()
    expect(lastOf('getResume').args[0]).toBe(8)

    await settle(lastOf('getResume'), resumeDetail(8, '数据分析师', 'Spark'))
    await settle(firstOf('getResume'), resumeDetail(7, '后端工程师', 'Vue'))

    await summarySentToRewrite(wrapper).trigger('click')
    await flushPromises()

    const payload = api.knowledge.queryRewriteTest.mock.lastCall[0]
    expect(payload.resume_summary).toContain('数据分析师')
    expect(payload.resume_summary, '改写搜索词带的是已经换掉的旧简历').not.toContain('后端工程师')
    wrapper.unmount()
  })

  it('卡片详情在途时，路由带来的另一个岗位不能被并进同一个抽屉', async () => {
    const wrapper = await renderSearch()
    await searchOnce(wrapper, 0, [job(101, '卡片岗位', '公司甲'), job(102, '另一岗位', '公司乙')])

    const detailButtons = wrapper.findAll('.job-actions button')
    expect(detailButtons.length).toBeGreaterThanOrEqual(2)
    await detailButtons[0].trigger('click')
    expect(lastOf('getJobDetail').args[0]).toBe(101)

    // 真实动作：抽屉在途时点了站内带 job_id 的链接（watch(route.query) 会再开一个详情）
    router.push('/jobs/search?job_id=102')
    await flushPromises()
    expect(lastOf('getJobDetail').args[0]).toBe(102)

    await settle(lastOf('getJobDetail'), job(102, '路由岗位', '公司乙'))
    expect(document.querySelector('.drawer-company')?.textContent.trim()).toBe('公司乙')

    await settle(firstOf('getJobDetail'), job(101, '卡片岗位', '公司甲'))
    expect(
      document.querySelector('.drawer-company')?.textContent.trim(),
      '先发起的那份详情并进了新抽屉'
    ).toBe('公司乙')
    wrapper.unmount()
  })
  it('详情在途时清空简历选择，旧详情不能把摘要填回"未选择简历"的页面', async () => {
    const wrapper = await renderSearch([
      { id: 7, file_name: '简历甲' },
      { id: 8, file_name: '简历乙' },
    ])
    expect(firstOf('getResume').args[0]).toBe(7)

    selectResume(wrapper, null) // 选择器是 clearable 的，清空同样是一次意图
    await flushPromises()
    await settle(firstOf('getResume'), resumeDetail(7, '后端工程师', 'Vue'))

    await summarySentToRewrite(wrapper).trigger('click')
    await flushPromises()

    expect(
      api.knowledge.queryRewriteTest.mock.lastCall[0].resume_summary,
      '明明清空了却还带着摘要'
    ).toBe('')
    wrapper.unmount()
  })
})

describe('对照组：单次触发必须照常写入（修令牌不能把所有响应都废掉）', () => {
  it('只点一个搜索词时结果照常出现', async () => {
    const wrapper = await renderSearch()
    await searchOnce(wrapper, 0, [job(1, '唯一岗', '公司甲')])

    expect(searchTitles()).toEqual(['唯一岗'])
    expect(heroNumbers()[0]).toBe('1')
    wrapper.unmount()
  })

  it('只换一次简历时这份详情照常生效', async () => {
    const wrapper = await renderSearch([
      { id: 7, file_name: '简历甲' },
      { id: 8, file_name: '简历乙' },
    ])
    selectResume(wrapper, 8)
    await flushPromises()
    await settle(lastOf('getResume'), resumeDetail(8, '数据分析师', 'Spark'))

    await summarySentToRewrite(wrapper).trigger('click')
    await flushPromises()

    expect(api.knowledge.queryRewriteTest.mock.lastCall[0].resume_summary).toContain('数据分析师')
    wrapper.unmount()
  })

  it('切到岗位仓库标签页时列表照常渲染', async () => {
    const wrapper = await renderSearch()
    await settle(lastOf('getJobList'), { items: [job(1, '仓库岗位', '公司甲')] })
    await findTab(wrapper, '岗位仓库').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(document.body.textContent).toContain('仓库岗位')
    wrapper.unmount()
  })
})
