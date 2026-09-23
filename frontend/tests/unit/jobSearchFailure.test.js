import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobSearch from '@/views/JobSearch.vue'
import { installElement } from '@/plugins/element'

/* `request.js` 对 GET 失败默认什么都不弹（`notifyError !== false && method !== 'get'`，
   见 request.js:42,56）。这两处 catch 曾经只把值清掉，于是：
   - 推荐取不到 → `recommendations = []` → 命中"还没有足够贴合的推荐结果，可以先补充岗位池"，
     一次 500 被说成候选人简历的问题；
   - 简历详情取不到 → `selectedResumeDetail = null` → `selectedResumeSummary` 变成空串，
     "改写搜索词"接着对一个已经选了简历的人说"先输入岗位关键词，或先选择一份简历"。 */
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

async function renderSearch() {
  const router = createRouter({
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

/** 切到"智能推荐"标签页：el-tab-pane 首次激活才渲染内容。 */
async function openRecommendTab(wrapper) {
  const tab = wrapper.findAll('.el-tabs__item').find((n) => n.text().includes('智能推荐'))
  expect(tab, '标签头没渲染出来，测试前提不成立').toBeTruthy()
  await tab.trigger('click')
  await flushPromises()
  await flushPromises()
}

function failWith(userMessage) {
  const err = new Error('boom')
  err.userMessage = userMessage
  err.isApiError = true
  return err
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  api.jobs.getCities.mockResolvedValue({ cities: [] })
  api.jobs.getJobList.mockResolvedValue({ items: [] })
  api.jobs.getJobPipelineList.mockResolvedValue({ items: [] })
  api.resume.getResumeList.mockResolvedValue({ items: [{ id: 7, file_name: '我的简历' }] })
  api.resume.getResume.mockResolvedValue({
    id: 7,
    parsed_json: { skills: [], current_title: '后端工程师' },
  })
})

describe('推荐拉取失败不能被说成"没有贴合的推荐"', () => {
  it('GET 失败时给出失败与重试，不给出那条怪简历的空态文案', async () => {
    api.jobs.getJobRecommendations.mockRejectedValue(failWith('推荐服务暂时不可用（500）'))
    const wrapper = await renderSearch()
    await openRecommendTab(wrapper)
    const text = document.body.textContent

    expect(text).toContain('推荐结果拉取失败')
    expect(text).toContain('推荐服务暂时不可用（500）')
    expect(text).not.toContain('还没有足够贴合的推荐结果')

    // 失败态必须给出路：重试真的再发一次同样的请求
    const callsBefore = api.jobs.getJobRecommendations.mock.calls.length
    const retry = wrapper.findAll('button').find((b) => b.text() === '重试')
    expect(retry).toBeTruthy()
    api.jobs.getJobRecommendations.mockResolvedValue({ recommendations: [] })
    await retry.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(api.jobs.getJobRecommendations.mock.calls.length).toBe(callsBefore + 1)
    wrapper.unmount()
  })

  it('对照组：真的没有推荐时，空态文案原样留着（失败和空是两回事）', async () => {
    api.jobs.getJobRecommendations.mockResolvedValue({ recommendations: [] })
    const wrapper = await renderSearch()
    await openRecommendTab(wrapper)
    const text = document.body.textContent

    expect(text).toContain('还没有足够贴合的推荐结果')
    expect(text).not.toContain('推荐结果拉取失败')
    wrapper.unmount()
  })
})

describe('简历详情拉取失败不能变成"你没选简历"', () => {
  it('列表成功、只有详情失败时，页面说出来而不静默丢掉摘要', async () => {
    api.resume.getResume.mockRejectedValue(failWith('详情读取超时'))
    const wrapper = await renderSearch()
    const text = document.body.textContent

    expect(text).toContain('简历详情拉取失败')
    expect(text).toContain('详情读取超时')
    // 列表是好的：不能把两件事混成一条"简历列表拉取失败"
    expect(text).not.toContain('简历列表拉取失败')
    wrapper.unmount()
  })

  it('对照组：详情正常时不出现任何失败块', async () => {
    const wrapper = await renderSearch()
    const text = document.body.textContent

    expect(text).not.toContain('简历详情拉取失败')
    expect(text).not.toContain('简历列表拉取失败')
    wrapper.unmount()
  })
})
