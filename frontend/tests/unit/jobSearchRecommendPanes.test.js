import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobSearch from '@/features/jobs/views/JobSearch.vue'
import RecommendPane from '@/features/jobs/components/RecommendPane.vue'
import SearchPane from '@/features/jobs/components/SearchPane.vue'
import { installElement } from '@/plugins/element'

/* D45 把最后两个面板（实时搜索 / 智能推荐）搬出 JobSearch.vue。面板只吃值、只发事件，所以这里测的全是
   **跨边界那一条线**：卡片按钮点下去，父页面那条链有没有收到、收到的是不是这一张卡片的岗位。
   接错一次不会报错，只会把 A 卡的按钮接到 B 卡上。
   两个必须写在这里的前提（都是第一版踩出来的）：
   1) el-tabs 会把四个面板**同时**渲染在 DOM 里，所以 `wrapper.find('.el-empty')` 拿到的是搜索面板那个；
      推荐面板的 `.recommend-actions` 与流程面板共用类名。所有查询都要先锁到面板组件上。
   2) 交互前先断言元素存在（`find()` 找不到时返回空壳、不报错）。 */

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

const RESUMES = [{ id: 7, file_name: '简历甲' }]

const job = (id, title, over = {}) => ({
  id,
  title,
  company: '公司' + title,
  location: '北京',
  salary: '30-50K',
  experience: '3-5年',
  education: '本科',
  skill_tags: ['Python', 'Go'],
  jd_summary: '负责服务端',
  source: 'boss',
  ...over,
})

const recommendation = (id, title, over = {}) => ({
  jd_id: id,
  job_title: title,
  company: '推荐公司',
  location: '上海',
  salary_range: '25K-40K',
  industry: '互联网',
  match_score: 88,
  match_reason: '技能重合度高',
  skill_overlap: ['Python'],
  skill_gap: ['Rust'],
  recommendation_type: '值得一试',
  ...over,
})

let router

async function renderSearch(resumes = RESUMES) {
  api.resume.getResumeList.mockResolvedValue({ items: resumes })
  api.resume.getResume.mockResolvedValue({ id: 7, parsed_json: {} })
  api.jobs.getCities.mockResolvedValue({ cities: [] })
  api.jobs.getJobList.mockResolvedValue({ items: [] })
  api.jobs.getJobPipelineList.mockResolvedValue({ entries: [] })
  api.jobs.getJobRecommendations.mockResolvedValue({ recommendations: [] })
  api.jobs.searchExternalJobs.mockResolvedValue({ jobs: [] })
  api.jobs.getJobDetail.mockImplementation((id) => Promise.resolve({ id, title: `详情${id}` }))

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

async function runSearch(wrapper, payload) {
  api.jobs.searchExternalJobs.mockResolvedValue(payload)
  const hero = wrapper.findAll('button').find((b) => b.text().includes('搜索最新岗位'))
  expect(hero, 'hero 上的搜索按钮没渲染出来').toBeTruthy()
  await hero.trigger('click')
  await flushPromises()
}

async function gotoRecommend(wrapper, recommendations) {
  api.jobs.getJobRecommendations.mockResolvedValue({ recommendations })
  const tab = wrapper.findAll('.el-tabs__item').find((n) => n.text().includes('智能推荐'))
  expect(tab, '标签头「智能推荐」没渲染出来').toBeTruthy()
  await tab.trigger('click')
  await flushPromises()
}

function searchPane(wrapper) {
  const found = wrapper.findComponent(SearchPane)
  expect(found, '搜索面板没渲染出来，测试前提不成立').toBeTruthy()
  return found
}

function recommendPane(wrapper) {
  const found = wrapper.findComponent(RecommendPane)
  expect(found, '推荐面板没渲染出来，测试前提不成立').toBeTruthy()
  return found
}

function buttonIn(scope, text) {
  const found = scope.findAll('button').find((b) => b.text().includes(text))
  expect(found, `「${text}」按钮没渲染出来，测试前提不成立`).toBeTruthy()
  return found
}

function card(scope, cls, title) {
  const found = scope.findAll(`.${cls}`).find((c) => c.find('h3').text() === title)
  expect(found, `卡片「${title}」没渲染出来，测试前提不成立`).toBeTruthy()
  return found
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  api.jobs.startFullAnalysis.mockResolvedValue({})
  api.jobs.createJobPipelineEntry.mockResolvedValue({ id: 1, stage: 'todo' })
})

describe('搜索面板的跨边界', () => {
  it('卡片上的动作各打到父页面那一个函数，带的是这一张卡片的岗位', async () => {
    const wrapper = await renderSearch()
    await runSearch(wrapper, { jobs: [job(1, '甲岗'), job(2, '乙岗')] })
    expect(searchPane(wrapper).findAll('.job-shell').length).toBe(2)

    const actions = card(searchPane(wrapper), 'job-shell', '乙岗').find('.job-actions')

    await buttonIn(actions, '查看详情').trigger('click')
    await flushPromises()
    expect(wrapper.vm.detailVisible).toBe(true)
    // 带的是这张卡的 id，不是第一张的
    expect(api.jobs.getJobDetail).toHaveBeenCalledWith(2)

    await buttonIn(actions, '加入对比').trigger('click')
    expect(wrapper.vm.compareSelection).toEqual(['search-1-2'])
    // 面板读的是 comparedUids 这个 prop：选中之后的文案要翻，否则这个 prop 传没传都没人知道
    expect(buttonIn(actions, '取消对比'), '已选中的卡片仍显示「加入对比」').toBeTruthy()

    // 搜索卡的清单位在卡头（`.bookmark-btn`），推荐卡的才在行动行里——两个面板的形状本来不同
    const bookmark = searchPane(wrapper).findAll('.bookmark-btn')[1]
    expect(bookmark, '第二张卡的清单按钮没渲染出来').toBeTruthy()
    expect(bookmark.text()).toBe('加入清单')
    await bookmark.trigger('click')
    expect(wrapper.vm.shortlist.map((x) => x.title)).toEqual(['乙岗'])
    expect(bookmark.text(), 'isShortlisted 没生效：加进去之后文案没翻').toBe('移出清单')

    await buttonIn(actions, '带入分析').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/smart-analysis')
    wrapper.unmount()
  })

  it('对比按钮要选满两个才可点，计数跟着父链走', async () => {
    const wrapper = await renderSearch()
    await runSearch(wrapper, { jobs: [job(1, '甲岗'), job(2, '乙岗')] })

    const open = () => buttonIn(searchPane(wrapper).find('.toolbar-actions'), '对比')
    expect(open().element.disabled, '一个都没选就能开对比面板').toBe(true)

    await buttonIn(
      card(searchPane(wrapper), 'job-shell', '甲岗').find('.job-actions'),
      '加入对比'
    ).trigger('click')
    expect(open().text()).toContain('1')
    expect(open().element.disabled).toBe(true)

    await buttonIn(
      card(searchPane(wrapper), 'job-shell', '乙岗').find('.job-actions'),
      '加入对比'
    ).trigger('click')
    expect(open().text()).toContain('2')
    expect(open().element.disabled).toBe(false)
    await open().trigger('click')
    expect(wrapper.vm.compareVisible).toBe(true)
    wrapper.unmount()
  })

  it('演示数据时只说演示，不把渠道报错和"最新结果"一起亮出来', async () => {
    const wrapper = await renderSearch()
    await runSearch(wrapper, {
      jobs: [job(1, '甲岗')],
      is_demo: true,
      result_mode: 'demo_fallback',
      error: '外部渠道超时',
    })

    const tags = searchPane(wrapper)
      .findAll('.toolbar-actions .el-tag')
      .map((t) => t.text())
    expect(tags).toEqual(['当前为演示数据'])
    expect(searchPane(wrapper).find('.result-source-note').text()).toContain('当前展示演示岗位数据')
    wrapper.unmount()
  })

  it('真实结果 + 渠道警告时，两个标签同时在场且都说得清', async () => {
    const wrapper = await renderSearch()
    await runSearch(wrapper, {
      jobs: [job(1, '甲岗')],
      result_mode: 'external',
      error: '部分渠道超时',
    })

    const tags = searchPane(wrapper)
      .findAll('.toolbar-actions .el-tag')
      .map((t) => t.text())
    expect(tags).toEqual(['最新结果', '部分渠道超时'])
    wrapper.unmount()
  })
})

describe('推荐面板的跨边界', () => {
  it('筛选框打字把整份新对象抛回父链，另一格保持原值', async () => {
    const wrapper = await renderSearch()
    await gotoRecommend(wrapper, [recommendation(11, '推荐甲'), recommendation(12, '推荐乙')])
    const pane = recommendPane(wrapper)
    expect(pane.findAll('.recommend-card').length).toBe(2)

    const inputs = pane.findAll('.recommend-actions input')
    expect(inputs.length, '两个筛选输入框没渲染出来').toBe(2)
    await inputs[0].setValue('北京')
    await flushPromises()

    expect(wrapper.vm.recommendFilters).toEqual({ location: '北京', industry: '' })
    wrapper.unmount()
  })

  it('没选简历时「更新推荐」是禁用的，空态说的是选简历', async () => {
    const wrapper = await renderSearch([])
    await gotoRecommend(wrapper, [recommendation(11, '推荐甲')])
    const pane = recommendPane(wrapper)

    expect(buttonIn(pane, '更新推荐').element.disabled, '没选简历却能发推荐请求').toBe(true)
    expect(pane.find('.el-empty').text()).toContain('先选择一份简历')
    wrapper.unmount()
  })

  it('推荐拉取失败 ≠ 没有贴合的推荐：两块屏幕不混', async () => {
    const wrapper = await renderSearch()
    await gotoRecommend(wrapper, [])
    expect(recommendPane(wrapper).find('.el-empty').text()).toContain('还没有足够贴合的推荐结果')

    api.jobs.getJobRecommendations.mockRejectedValue({ userMessage: '推荐服务暂时不可用' })
    await wrapper.vm.loadRecommendations()
    await flushPromises()

    const text = recommendPane(wrapper).text()
    expect(text).toContain('推荐结果拉取失败')
    expect(text).not.toContain('还没有足够贴合的推荐结果')
    wrapper.unmount()
  })

  it('卡片动作带的是这一张卡；城市筛选变化会即时重算推荐卡的分数', async () => {
    const wrapper = await renderSearch()
    await gotoRecommend(wrapper, [
      recommendation(11, '推荐甲', { location: '上海' }),
      recommendation(12, '推荐乙', { location: '杭州' }),
    ])
    const actions = card(recommendPane(wrapper), 'recommend-card', '推荐乙').find('.job-actions')

    await buttonIn(actions, '加入对比').trigger('click')
    expect(wrapper.vm.compareSelection).toEqual(['recommend-12'])
    expect(buttonIn(actions, '取消对比'), '推荐卡的对比文案没跟着 comparedUids 翻').toBeTruthy()

    await buttonIn(actions, '加入清单').trigger('click')
    expect(wrapper.vm.shortlist.map((x) => x.title)).toEqual(['推荐乙'])

    // §10.18 记着的现状：推荐卡的分数在 computed 里算，所以动搜索表单的城市会立刻重算
    wrapper.vm.city = '杭州'
    await flushPromises()
    expect(wrapper.vm.normalizedRecommendations[1].priorityReason).toContain('城市匹配')
    wrapper.unmount()
  })
})
