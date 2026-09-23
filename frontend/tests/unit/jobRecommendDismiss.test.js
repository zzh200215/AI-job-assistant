import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobRecommend from '@/views/JobRecommend.vue'
import { installElement } from '@/plugins/element'

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

function job(jdId, title) {
  return {
    jd_id: jdId,
    job_title: title,
    company: '示例公司',
    location: '上海',
    match_score: 86,
    match_reason: '技能重合',
    recommendation_type: '高薪',
    skill_overlap: ['Python'],
    skill_gap: [],
    source: 'manual',
  }
}

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
  api.getJobRecommendations.mockResolvedValue({
    resume_id: 7,
    total: 2,
    recommendations: [job(11, '后端工程师'), job(12, '算法工程师')],
  })
  api.getJobPipelineList.mockResolvedValue({ items: [] })
  api.getJobBookmarks.mockResolvedValue({ total: 1, items: [{ jd_id: 12 }] })
  api.getJobFeedbackStats.mockResolvedValue({ total: 0 })
  api.getSuppressedJobs.mockResolvedValue({
    total: 1,
    orphaned: 0,
    items: [
      {
        jd_id: 11,
        job_title: '后端工程师',
        company: '示例公司',
        location: '上海',
        reasons: ['dismiss'],
      },
    ],
  })
  api.bookmarkJob.mockResolvedValue({})
  api.submitJobFeedback.mockResolvedValue({})
  api.restoreSuppressedJob.mockResolvedValue({ jd_id: 11, dismiss: 1, dislike: 0 })
})

describe('岗位推荐：隐藏与恢复', () => {
  it('卡片提供"不感兴趣"入口，点击后写入 dismiss 并立即从列表移除', async () => {
    const wrapper = await renderRecommend()
    expect(wrapper.findAll('.job-card')).toHaveLength(2)

    await wrapper.findAll('.dismiss-btn')[0].trigger('click')
    await flushPromises()

    expect(api.bookmarkJob).toHaveBeenCalledWith(11, 'dismiss')
    expect(wrapper.findAll('.job-card')).toHaveLength(1)
    // ElMessage teleports outside the mounted component, so read the document.
    expect(document.body.textContent).toContain('可在「已忽略」中恢复')
    wrapper.unmount()
  })

  it('点踩会移除卡片：引擎已把 dislike 当作隐藏信号，列表不能继续展示', async () => {
    const wrapper = await renderRecommend()

    await wrapper.findAll('.feedback-btns button')[1].trigger('click')
    await flushPromises()

    expect(api.submitJobFeedback).toHaveBeenCalled()
    expect(wrapper.findAll('.job-card')).toHaveLength(1)
    expect(document.body.textContent).toContain('该岗位不再出现在推荐中')
    wrapper.unmount()
  })

  it('收藏状态由后端回填，而不是刷新后一律显示未收藏', async () => {
    const wrapper = await renderRecommend()

    expect(api.getJobBookmarks).toHaveBeenCalled()
    const cards = wrapper.findAll('.job-card')
    expect(cards[1].text()).toContain('已收藏')
    expect(cards[0].text()).not.toContain('已收藏')
    wrapper.unmount()
  })

  it('"已忽略的岗位"入口按需拉取隐藏列表', async () => {
    const wrapper = await renderRecommend()
    expect(api.getSuppressedJobs).not.toHaveBeenCalled()

    const button = wrapper.findAll('button').find((b) => b.text().trim() === '已忽略的岗位')
    expect(button).toBeTruthy()
    await button.trigger('click')
    await flushPromises()

    expect(api.getSuppressedJobs).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
