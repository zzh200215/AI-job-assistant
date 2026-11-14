/**
 * 报告类作业（简历 / 项目 / 作品集）的"排队中"那一句。
 *
 * 三份作业共用同一个轮询器，但载荷没有 `progress`：只有 `pending / running / completed / failed`。
 * 所以"排队"就是 `pending`（行已落库、已投进本地线程池，还没被 worker 领走）——
 * `taskPhase()` 对 `pending` 本来就返回 queued，三处视图只是把它接上模板。
 *
 * 这一族以前对"排队"和"逐节生成"说的是同一句「正在逐节生成，请稍候」，
 * 看上去像已经开跑了；简历报告报错时还只在页面里留一句"可以再点一次"。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeReport from '@/features/resume/views/ResumeReport.vue'
import ProjectReport from '@/features/resume/views/ProjectReport.vue'
import PortfolioReport from '@/features/resume/views/PortfolioReport.vue'
import { installElement } from '@/plugins/element'
import { JOB_QUEUED_COPY } from '@/utils/taskPhase'

const api = vi.hoisted(() => ({
  getResumeList: vi.fn(),
  getJDList: vi.fn(),
  createReportJob: vi.fn(),
  getReportJob: vi.fn(),
  createProjectReportJob: vi.fn(),
  getProjectReportJob: vi.fn(),
  createPortfolioReportJob: vi.fn(),
  getPortfolioReportJob: vi.fn(),
  applyReportRedline: vi.fn(),
  downloadReportHtml: vi.fn(),
}))
const services = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/api/resume', () => api)
vi.mock('@/api/jd', () => ({ getJDList: api.getJDList }))
vi.mock('@/plugins/element-services', () => services)

const RESUME_ROW = { id: 1, name: '测试候选人', file_name: 'a.pdf', parsed: {} }

async function mountAt(component, path, query) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/resume/report', name: 'resume-report', component: { template: '<div />' } },
      {
        path: '/resume/project-report',
        name: 'project-report',
        component: { template: '<div />' },
      },
      {
        path: '/resume/portfolio-report',
        name: 'portfolio-report',
        component: { template: '<div />' },
      },
      { path: '/resume-center', name: 'resume-center', component: { template: '<div />' } },
    ],
  })
  await router.push({ path, query })
  await router.isReady()
  const wrapper = mount(component, {
    attachTo: document.body,
    global: { plugins: [installElement, router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

/** 报告作业的轮询载荷：`serialize_job` 那一份，只有 status 没有 progress。 */
function jobPayload(status) {
  return { job_id: 77, resume_id: 1, status, report: null, total_score: null, grade: null }
}

const text = () => document.body.textContent.replace(/\s+/g, ' ')

beforeEach(() => {
  for (const fn of [...Object.values(api), ...Object.values(services.ElMessage)]) fn.mockClear()
  api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
  api.getJDList.mockResolvedValue({ items: [] })
  document.body.innerHTML = ''
})

describe('报告作业排队时说的是"排队中"，不是"正在逐节生成"', () => {
  it('简历报告：pending 时上屏排队那句，逐节生成那句不在', async () => {
    api.getReportJob.mockResolvedValue(jobPayload('pending'))
    await mountAt(ResumeReport, '/resume/report', { resume_id: '1', job_id: '77' })

    expect(text()).toContain(JOB_QUEUED_COPY)
    expect(text()).not.toContain('正在逐节生成')
  })

  it('简历报告：worker 领走之后（running）换回逐节生成', async () => {
    api.getReportJob.mockResolvedValue(jobPayload('running'))
    await mountAt(ResumeReport, '/resume/report', { resume_id: '1', job_id: '77' })

    expect(text()).toContain('正在逐节生成')
    expect(text()).not.toContain(JOB_QUEUED_COPY)
  })

  it('项目分析：pending 时同样说排队', async () => {
    api.getProjectReportJob.mockResolvedValue(jobPayload('pending'))
    await mountAt(ProjectReport, '/resume/project-report', { resume_id: '1', job_id: '77' })

    expect(text()).toContain(JOB_QUEUED_COPY)
    expect(text()).not.toContain('正在逐节生成')
  })

  it('作品集分析：pending 时同样说排队', async () => {
    api.getPortfolioReportJob.mockResolvedValue(jobPayload('pending'))
    await mountAt(PortfolioReport, '/resume/portfolio-report', { resume_id: '1', job_id: '77' })

    expect(text()).toContain(JOB_QUEUED_COPY)
    expect(text()).not.toContain('正在逐节生成')
  })
})
