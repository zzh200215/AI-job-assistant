/**
 * 分析结果页的两块新提示（D9 的第三个消费方）：
 *
 * 1. **排队中**：拿到 task_id 之后、第一步写下来之前，屏幕上要有一句"在等后台接单"，
 *    而不是一条不动的 0% 进度条；
 * 2. **失败留在页面上**：以前失败只弹一个 5 秒的 toast，人几十秒后回头看这一屏，
 *    看到的是"什么都没发生"。现在它和加载失败一样是一块行内提示，还带一颗重试按钮。
 *
 * "没跑第一步就失败"这一档的措辞由前端自己给（`NEVER_STARTED_FAILURE`）——
 * 共享轮询器刻意不把服务端 `error_msg` 放进 `userMessage`，服务端原文不上屏。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import AnalysisResult from '@/features/analysis/views/AnalysisResult.vue'
import { installElement } from '@/plugins/element'
import { NEVER_STARTED_FAILURE, QUEUED_COPY, TASK_PHASE } from '@/utils/taskPhase'

const state = vi.hoisted(() => ({ mode: 'queued' }))

vi.mock('@/api/analysis', () => ({
  getAnalysis: vi.fn(async () => ({ id: 1, match_score: 70 })),
  runFullAnalysis: vi.fn(async () => ({ task_id: 't1' })),
  getAnalysisReferences: vi.fn(async () => ({ references: [], query: '' })),
  explainMatch: vi.fn(async () => ({})),
  regenOptimize: vi.fn(async () => ({})),
  regenInterview: vi.fn(async () => ({})),
}))

vi.mock('@/api/agent', () => ({
  startAgentAnalysis: vi.fn(async () => ({ task_id: 't1' })),
  getAgentTask: vi.fn(async () => ({ status: 'running' })),
  getAgentSteps: vi.fn(async () => ({ steps: [] })),
}))

vi.mock('@/api/resume', () => ({
  getResume: vi.fn(async () => ({ id: 7, name: '林知遥', parsed: { skills: [] } })),
  getResumeList: vi.fn(async () => ({
    items: [{ id: 7, file_name: 'resume.pdf', name: '林知遥', parsed: { skills: [] } }],
  })),
  generateOptimized: vi.fn(async () => ({})),
  uploadResume: vi.fn(async () => ({ id: 7 })),
  parseResume: vi.fn(async () => ({ parsed: true })),
}))

vi.mock('@/api/jd', () => ({
  getJD: vi.fn(async () => ({ id: 3, title: '岗位' })),
  getJDList: vi.fn(async () => ({ items: [{ id: 3, title: '岗位' }] })),
}))

vi.mock('@/composables/useAgentTaskPolling', () => ({
  useAgentTaskPolling: () => ({
    isPolling: { value: true },
    pollTask: async (_taskId, handlers) => {
      if (state.mode === 'queued') {
        await handlers.onProgress(
          { status: 'running', progress: { step_counts: { total: 0 }, current_step: null } },
          [],
          TASK_PHASE.QUEUED
        )
        return new Promise(() => {})
      }
      const task = {
        status: 'failed',
        error_msg: '排队 2 分钟仍未开始执行：任务队列里没有活着的 worker（…）。按未启动收口',
        progress: { step_counts: { total: 0 }, current_step: null },
      }
      const error = new Error(task.error_msg)
      error.code = 'task_failed'
      error.task = task
      await handlers.onFailed(error)
      throw error
    },
  }),
}))

async function renderPage() {
  const route = { path: '/analysis', name: 'analysis-result', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/analysis')
  await router.isReady()
  const wrapper = mount(AnalysisResult, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

async function runAnalysis(wrapper, { settle = true } = {}) {
  /* 这一页的 form 平时由 `selection` 那两条持久化选择填（`fillLast`）；测试里没有那两份存储，
     直接给上，验证的是"点了之后屏幕上说什么"，不是选择链。 */
  wrapper.vm.form.resume_id = 7
  wrapper.vm.form.jd_id = 3
  const pending = wrapper.vm.onAnalyze()
  /* 排队那一档的轮询永不落地（真实排队也不会结束），所以不能 await 那个 promise。 */
  if (settle) await pending
  await flushPromises()
}

const text = () => document.body.textContent.replace(/\s+/g, ' ')

describe('分析结果页的排队与失败提示', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    state.mode = 'queued'
  })

  it('零步骤时显示"排队中"，进度条那一块不在', async () => {
    const wrapper = await renderPage()
    await runAnalysis(wrapper, { settle: false })

    expect(text()).toContain(QUEUED_COPY.title)
    expect(text()).not.toContain('当前阶段')
  })

  it('失败时行内留下我们自己的那句话，服务端原文一个字都不上屏', async () => {
    state.mode = 'failed'
    const wrapper = await renderPage()
    await runAnalysis(wrapper)

    expect(text()).toContain(NEVER_STARTED_FAILURE)
    expect(text()).not.toContain('排队 2 分钟仍未开始执行')
    /* 这颗按钮是"失败留在页面上"的另一半：不刷新、不重进页面就能再来一次。 */
    expect(text()).toContain('重新分析')
  })
})
