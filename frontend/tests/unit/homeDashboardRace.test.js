import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import Home from '@/features/shell/views/Home.vue'
import { installElement } from '@/plugins/element'

/* 工作台有三处「重新加载」（概览 `:50`、今日任务 `:110`、下一步 `:151`），都调同一个 loadDashboard，
   而它在 `await Promise.allSettled(...)` 之后连着写四块状态——形状上正是这一轮在找的那种。
   但**点不出第二次**：loadDashboard 进入就把三个错误位一起清掉，而任务/下一步两块前面还各有一个
   `v-if="*Loading"` 的 spinner 分支，所以那一发在途时屏幕上没有任何「重新加载」按钮剩下来。
   这不是设计出来的互斥，是错误位与 spinner 分支的副作用（与 D31 的看板同型），所以这里留一条绊线：
   将来谁把加载态改成"保留旧数据"或换成骨架屏，这条就会红——那时需要的是给 loadDashboard 装令牌。 */

const api = vi.hoisted(() => ({
  getDashboardOverview: vi.fn(),
  getTodayTasks: vi.fn(),
  getNextActions: vi.fn(),
}))

vi.mock('@/api/dashboard', () => api)

function deferred() {
  let resolve
  let reject
  const promise = new Promise((r, j) => {
    resolve = r
    reject = j
  })
  return { resolve, reject, promise }
}

const rounds = []

/** loadDashboard 一轮发三个请求，三个都得落地，Promise.allSettled 才会继续往下写 */
async function settleRound(index, value) {
  rounds[index].ov.resolve(value.overview)
  rounds[index].tk.resolve(value.tasks)
  rounds[index].ac.resolve({ suggestions: Array.from({ length: value.actions }, (_, i) => i) })
  await flushPromises()
}

function failRound(index) {
  rounds[index].ov.reject(new Error('概览挂了'))
  rounds[index].tk.reject(new Error('任务挂了'))
  rounds[index].ac.reject(new Error('下一步挂了'))
}

let router

async function renderHome() {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'home', component: { template: '<div />' } }],
  })
  router.push('/')
  await router.isReady()
  const wrapper = mount(Home, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function reloadButtons(wrapper) {
  return wrapper.findAll('button').filter((b) => b.text().includes('重新加载'))
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  rounds.length = 0
  api.getDashboardOverview.mockImplementation(() => {
    const round = { ov: deferred(), tk: deferred(), ac: deferred() }
    rounds.push(round)
    return round.ov.promise
  })
  api.getTodayTasks.mockImplementation(() => rounds[rounds.length - 1].tk.promise)
  api.getNextActions.mockImplementation(() => rounds[rounds.length - 1].ac.promise)
})

describe('工作台：重载入口在途时点不出第二次', () => {
  it('失败后按钮出现，一按下去就整批消失，直到这一轮落地', async () => {
    const wrapper = await renderHome()
    failRound(0)
    await flushPromises()

    const buttons = reloadButtons(wrapper)
    expect(buttons.length, '三块都失败了却没有可点的「重新加载」').toBeGreaterThanOrEqual(1)

    await buttons[0].trigger('click')
    expect(rounds.length, '点按钮没发出第二轮').toBe(2)
    expect(
      reloadButtons(wrapper).length,
      '在途期间还能再点一次，那 loadDashboard 需要的是令牌而不是这条绊线'
    ).toBe(0)

    await settleRound(1, { overview: { resumes: 3 }, tasks: { high_priority: 2 }, actions: 2 })
    expect(wrapper.vm.overview.resumes).toBe(3)
    expect(wrapper.vm.tasks.high_priority).toBe(2)
    expect(wrapper.vm.nextActions.length).toBe(2)
    wrapper.unmount()
  })

  it('对照组：这一轮落地后按钮不再挂着（成功态没有重试入口）', async () => {
    const wrapper = await renderHome()
    await settleRound(0, { overview: { resumes: 1 }, tasks: { high_priority: 0 }, actions: 1 })

    expect(reloadButtons(wrapper).length).toBe(0)
    expect(wrapper.vm.overviewLoaded).toBe(true)
    wrapper.unmount()
  })
})
