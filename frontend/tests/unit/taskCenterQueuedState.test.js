/**
 * 任务中心也要说"排队中"（D9 的第二个消费方）。
 *
 * 这一屏以前对"已提交、还没开始跑"和"跑起来了但没动"给的是同一个 0% 进度条 —— 两条任务看起来
 * 一模一样，一条在等 worker，一条可能是真卡住。判据复用 `utils/taskPhase.js`（只读载荷，
 * 不看时间），所以它和求职分析页那几个下判断的地方是同一套。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import TaskCenter from '@/features/shell/views/TaskCenter.vue'
import { installElement } from '@/plugins/element'
import { NEVER_STARTED_FAILURE } from '@/utils/taskPhase'

const state = vi.hoisted(() => ({ items: [] }))

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn(async (url) => {
      if (url === '/agent/tasks') return { items: state.items }
      if (url === '/agent/tasks/summary') return { counts: {}, total: state.items.length }
      return {}
    }),
    post: vi.fn(async () => ({})),
  },
}))

async function renderCenter(items) {
  state.items = items
  const route = { path: '/tasks', name: 'tasks', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/tasks')
  await router.isReady()
  mount(TaskCenter, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
}

const card = () => document.querySelector('.task-card')
const text = () => document.body.textContent.replace(/\s+/g, ' ')

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('任务中心的排队态', () => {
  it('零步骤的 running 任务画的是"排队中"那句话，不是一条 0% 的进度条', async () => {
    await renderCenter([
      {
        id: 1,
        name: '求职分析任务',
        status: 'running',
        create_time: 0,
        progress: { progress_percent: 0, step_counts: { total: 0 }, current_step: null },
      },
    ])

    expect(text()).toContain('排队中')
    expect(text()).toContain('后台还没开始跑第一步')
    /* 反证：排队这一档不该有进度条 —— 0% 的条正是以前"看起来像卡住"的那一屏。 */
    expect(card().querySelector('.el-progress')).toBeNull()
  })

  it('有步骤之后恢复成进度条（排队那句不留着）', async () => {
    await renderCenter([
      {
        id: 2,
        name: '求职分析任务',
        status: 'running',
        create_time: 0,
        progress: {
          progress_percent: 50,
          step_counts: { total: 2 },
          current_step: { name: 'matching_analysis', label: '匹配分析' },
        },
      },
    ])

    expect(card().querySelector('.el-progress')).not.toBeNull()
    expect(text()).not.toContain('后台还没开始跑第一步')
  })

  it('"没开始就失败"的那张卡说的是我们自己的话，不是服务端原文', async () => {
    await renderCenter([
      {
        id: 3,
        name: '求职分析任务',
        status: 'failed',
        create_time: 0,
        error_msg:
          '排队 2 分钟仍未开始执行：任务队列里没有活着的 worker（心跳键不存在）。按未启动收口',
        progress: { progress_percent: 0, step_counts: { total: 0 }, current_step: null },
      },
    ])

    expect(text()).toContain(NEVER_STARTED_FAILURE)
    expect(text()).not.toContain('排队 2 分钟仍未开始执行')
  })
})
