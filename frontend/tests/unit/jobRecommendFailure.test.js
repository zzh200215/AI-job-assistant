import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobRecommend from '@/views/JobRecommend.vue'
import { installElement } from '@/plugins/element'

/* request.js 对 GET 失败默认不弹提示（method !== 'get' 才 notify，见 request.js:42,56），
   所以 loadRecommendations 的 catch 把 recommendations 清成 [] 之后，页面会显示
   "暂无匹配的岗位推荐，请完善简历信息" —— 服务器 500 被说成了候选人简历的问题。 */
const api = vi.hoisted(() => ({
  getJobRecommendations: vi.fn(),
  getJobFeedbackStats: vi.fn(),
  seedMockJobs: vi.fn(),
  batchImportJobs: vi.fn(),
  submitJobFeedback: vi.fn(),
  startFullAnalysis: vi.fn(),
  getJobPipelineList: vi.fn(),
  getJobBookmarks: vi.fn(),
  getSuppressedJobs: vi.fn(),
  restoreSuppressedJob: vi.fn(),
  bookmarkJob: vi.fn(),
  unbookmarkJob: vi.fn(),
}))

vi.mock('@/api/jobs', () => api)
vi.mock('@/api/resume', () => ({
  getResumeList: vi.fn(async () => ({ items: [{ id: 7, name: '我的简历' }], total: 1 })),
}))
vi.mock('@/api/targets', () => ({ createJobPipelineEntry: vi.fn() }))

async function renderRecommend() {
  const route = {
    path: '/jobs/recommend',
    name: 'job-recommend',
    component: { template: '<div />' },
  }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/jobs/recommend?resume_id=7')
  await router.isReady()
  const wrapper = mount(JobRecommend, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  api.getJobPipelineList.mockResolvedValue({ items: [] })
  api.getJobBookmarks.mockResolvedValue({ total: 0, items: [] })
  api.getSuppressedJobs.mockResolvedValue({ total: 0, orphaned: 0, items: [] })
  api.getJobFeedbackStats.mockResolvedValue({ total: 0 })
})

describe('推荐加载失败不能被说成没有推荐', () => {
  it('GET 失败时显示失败与重试，不显示"请完善简历信息"', async () => {
    const err = new Error('boom')
    err.userMessage = '服务暂时不可用，请稍后重试'
    err.isApiError = true
    api.getJobRecommendations.mockRejectedValue(err)

    const wrapper = await renderRecommend()
    const text = document.body.textContent

    expect(text).toContain('服务暂时不可用，请稍后重试')
    expect(text).not.toContain('请完善简历信息')
    expect(text).not.toContain('岗位仓库还是空的')

    // 失败态必须给出路：重试按钮重新发一次同样的请求
    const retry = wrapper.findAll('button').find((b) => b.text().includes('重试'))
    expect(retry).toBeTruthy()
    api.getJobRecommendations.mockResolvedValue({ total: 1, recommendations: [] })
    await retry.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(api.getJobRecommendations).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('真的没有推荐时，仍然显示原来的空态文案（失败与空是两回事）', async () => {
    api.getJobRecommendations.mockResolvedValue({ total: 0, recommendations: [] })
    const wrapper = await renderRecommend()
    const text = document.body.textContent
    expect(text).toContain('暂无匹配的岗位推荐')
    expect(text).not.toContain('加载失败')
    wrapper.unmount()
  })
})
