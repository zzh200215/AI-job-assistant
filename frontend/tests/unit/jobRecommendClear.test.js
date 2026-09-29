import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobSearch from '@/features/jobs/views/JobSearch.vue'
import { installElement } from '@/plugins/element'

/* D28 给简历详情立的那条规矩——"清空也是一次意图，要作废仍在途的那一发"——推荐链没有照做：
   `handleResumeChange` 的清空分支就地写 `recommendations.value = []` / `recommendError.value = ''`，
   而不走 `loadRecommendations()`，所以它不领令牌。选择器是 clearable 的（`JobSearch.vue:111`），
   于是默认简历的推荐请求还在途时点✕，那份推荐会照常落地——屏幕上是旧简历的推荐，
   而选择器已经空了，hero 的「智能推荐」也跟着变成非零。 */

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
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const recommendCalls = []

/** hero 那排数字的顺序就是标签页的顺序：[本次搜索, 岗位仓库, 智能推荐, ...] */
function heroNumbers() {
  return [...document.querySelectorAll('.hero-metrics .metric-card strong')].map((n) =>
    n.textContent.trim()
  )
}

let router

async function renderSearch(resumes) {
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

function selectResume(wrapper, id) {
  const select = wrapper.findComponent('.resume-select')
  expect(select, '简历选择器没渲染出来，测试前提不成立').toBeTruthy()
  select.vm.$emit('update:modelValue', id)
  select.vm.$emit('change', id)
}

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const recommendation = (id, title) => ({ jd_id: id, job_title: title, match_score: 88 })

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  recommendCalls.length = 0
  api.jobs.getCities.mockResolvedValue({ cities: [] })
  api.jobs.getJobList.mockResolvedValue({ items: [] })
  api.jobs.getJobPipelineList.mockResolvedValue({ entries: [] })
  api.jobs.searchExternalJobs.mockResolvedValue({ jobs: [] })
  api.resume.getResume.mockResolvedValue({ id: 7, parsed_json: {} })
  api.jobs.getJobRecommendations.mockImplementation(() => {
    const record = deferred()
    recommendCalls.push(record)
    return record.promise
  })
})

describe('清空简历选择时，旧简历的推荐不能落到屏幕上', () => {
  it('推荐在途时点✕，那一发回来只能算过期', async () => {
    const wrapper = await renderSearch([{ id: 7, file_name: '简历甲' }])
    expect(recommendCalls.length, '挂载没有为默认简历发推荐请求，测试前提不成立').toBe(1)

    selectResume(wrapper, null)
    await flushPromises()
    expect(wrapper.vm.selectedResumeId).toBeNull()

    await settle(recommendCalls[0], { recommendations: [recommendation(9, '旧简历的推荐岗')] })

    expect(wrapper.vm.recommendations, '清空之后旧简历的推荐又回来了').toEqual([])
    expect(heroNumbers()[2], 'hero 的「智能推荐」被旧那一轮改成了非零').toBe('0')
    wrapper.unmount()
  })

  it('对照组：不清空时这份推荐照常落地，hero 也跟着变成 1', async () => {
    const wrapper = await renderSearch([{ id: 7, file_name: '简历甲' }])

    await settle(recommendCalls[0], { recommendations: [recommendation(11, '当前简历的推荐岗')] })

    expect(wrapper.vm.recommendations.length).toBe(1)
    expect(wrapper.vm.recommendations[0].job_title).toBe('当前简历的推荐岗')
    expect(wrapper.vm.recommendLoading).toBe(false)
    expect(heroNumbers()[2]).toBe('1')
    wrapper.unmount()
  })
})
