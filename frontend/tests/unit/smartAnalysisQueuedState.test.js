/**
 * "排队中"那一屏：**已提交、后台还没开始跑第一步**时要有一句话。
 *
 * 背景（`docs/真provider实测.md` §6）：`/analysis/full` 现在只在有 worker 消费队列时收单，
 * 没有就 503。也就是说拿到 `task_id` 之后的那段时间里，任务是真的存在、但可能一步都没跑——
 * 以前这一屏什么都不显示（进度面板的 `v-if` 要求 `agentSteps.length`），看起来像卡死。
 *
 * 这里穿过视图的那条线：轮询器把 `taskPhase()` 的结果作为第三个参数递给 `onProgress`
 * （`utils/agentTaskPolling.js`），页面存下来，于是在"零步骤"与"有步骤"之间换话术。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import SmartAnalysis from '@/features/analysis/views/SmartAnalysis.vue'
import { installElement } from '@/plugins/element'
import { QUEUED_COPY, TASK_PHASE, NEVER_STARTED_FAILURE } from '@/utils/taskPhase'

/* `vi.mock` 的工厂会被提升到文件顶部，所以共享状态得从 `vi.hoisted` 里拿。 */
const state = vi.hoisted(() => ({ mode: 'queued' }))

vi.mock('@/api/analysis', () => ({
  runFullAnalysis: vi.fn(async () => ({ task_id: 't1' })),
  getAnalysis: vi.fn(async () => ({ id: 1, match_score: 70 })),
  getAnalysisReferences: vi.fn(async () => ({ references: [], query: '' })),
  explainMatch: vi.fn(async () => ({})),
}))

vi.mock('@/api/resume', () => ({
  uploadResume: vi.fn(async () => ({ id: 7 })),
  parseResume: vi.fn(async () => ({ parsed: true })),
  generateOptimized: vi.fn(async () => {
    throw new Error('测试内不真的生成')
  }),
}))

vi.mock('@/api/jd', () => ({
  createJD: vi.fn(async () => ({ id: 3 })),
  parseJD: vi.fn(async () => ({ parsed: true })),
}))

vi.mock('@/composables/useAgentTaskPolling', () => ({
  useAgentTaskPolling: () => ({
    isPolling: { value: true },
    pollTask: async (_taskId, handlers) => {
      if (state.mode === 'queued') {
        // 第一跳就是"任务在、零步骤"：这正是要说话的那一屏。之后**永不落地**——
        // 排队期间轮询本来也不会结束。
        await handlers.onProgress(
          { status: 'running', progress: { step_counts: { total: 0 }, current_step: null } },
          [],
          TASK_PHASE.QUEUED
        )
        return new Promise(() => {})
      }
      if (state.mode === 'failed') {
        /* 后端收口时写进 `error_msg` 的那句原因**不许直接上屏**（全仓规则：共享轮询器把
           `error_msg` 挂在 `error.message` 上，正是为了不让服务端/模型原文流给候选人）。
           页面按"失败 + 零步骤"这个可观察状态说自己的话，下面两条断言一起钉住这件事。 */
        const taskPayload = {
          status: 'failed',
          error_msg: '排队 2 分钟仍未开始执行：任务队列里没有活着的 worker（…）。按未启动收口',
          progress: { step_counts: { total: 0 }, current_step: null },
        }
        const error = new Error(taskPayload.error_msg)
        error.code = 'task_failed'
        error.task = taskPayload
        await handlers.onFailed(error)
        throw error
      }
      await handlers.onProgress(
        { status: 'running', progress: { step_counts: { total: 1 } } },
        [{ step_name: 'intent_recognition', status: 'running' }],
        TASK_PHASE.RUNNING
      )
      /* 也不落地：这一条要验的是"第一步到了"之后屏幕换成了进度面板，
         后面的完成/渲染是另一族用例（smartAnalysisShapeRender）的事。 */
      return new Promise(() => {})
    },
  }),
}))

async function startAnalysis() {
  const route = {
    path: '/smart-analysis',
    name: 'smart-analysis',
    component: { template: '<div />' },
  }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push({ path: '/smart-analysis', query: { resume_id: '7', jd_id: '3' } })
  await router.isReady()
  const wrapper = mount(SmartAnalysis, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await wrapper.find('.action-bar button').trigger('click')
  await flushPromises()
  return wrapper
}

describe('SmartAnalysis 的"排队中"屏', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    state.mode = 'queued'
  })

  it('零步骤时上屏的是"排队中"那句话，不是一片空白', async () => {
    await startAnalysis()

    const text = document.body.textContent.replace(/\s+/g, ' ')
    expect(text).toContain(QUEUED_COPY.title)
    expect(text).toContain('几秒内就会进入进度')
    /* 反证：进度面板（要求 agentSteps.length）这时候不该在。 */
    expect(text).not.toContain('分析进度')
  })

  it('第一条步骤到达后，排队那句话换成了进度面板', async () => {
    state.mode = 'running'
    await startAnalysis()

    const text = document.body.textContent.replace(/\s+/g, ' ')
    expect(text).toContain('分析进度')
    expect(text).not.toContain(QUEUED_COPY.title)
  })

  it('收口失败时留在页面上的是我们自己的那句话，服务端原文一个字都不上屏', async () => {
    /* 2026-11-14 真浏览器验收里丢过一次：`onFailed` 写下的原因被外层 catch 的兜底覆盖了，
       屏幕上只剩"分析请求失败，请稍后重试"。修的时候又撞上另一条规则——服务端那句不许上屏
       （同族的三条作业轮询用例钉着），所以这一档由前端按"失败 + 零步骤"自己说。 */
    state.mode = 'failed'
    await startAnalysis()

    const text = document.body.textContent.replace(/\s+/g, ' ')
    expect(text).toContain(NEVER_STARTED_FAILURE)
    expect(text).toContain('后台没有可用的 worker')
    expect(text).not.toContain('排队 2 分钟仍未开始执行')
    expect(text).not.toContain('分析请求失败，请稍后重试')
  })
})
