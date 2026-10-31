import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import Home from '@/features/shell/views/Home.vue'
import { installElement } from '@/plugins/element'

/* 工作台现在一轮读四块：概览、今日任务、投递管道、简历列表（有简历后再补分数和推荐）。
   这四块都在同一个 loadDashboard 的 `Promise.allSettled` 之后写状态，所以仍然留同一条绊线：
   点「重新加载」后四个错误位一起清掉、四块进入骨架态，在途期间屏幕上不能再出现第二个入口。 */

const api = vi.hoisted(() => ({
  getDashboardOverview: vi.fn(),
  getTodayTasks: vi.fn(),
}))
const targetsApi = vi.hoisted(() => ({ getKanban: vi.fn() }))
const jobsApi = vi.hoisted(() => ({ getJobRecommendations: vi.fn() }))
const resumeApi = vi.hoisted(() => ({
  getResumeList: vi.fn(),
  getResumeQuickScore: vi.fn(),
}))

vi.mock('@/api/dashboard', () => api)
vi.mock('@/api/targets', () => targetsApi)
vi.mock('@/api/jobs', () => jobsApi)
vi.mock('@/api/resume', () => resumeApi)

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

/** loadDashboard 一轮发四个请求，四个都得落地，Promise.allSettled 才会继续往下写 */
async function settleRound(index, value) {
  rounds[index].ov.resolve(value.overview)
  rounds[index].tk.resolve(value.tasks)
  rounds[index].pipe.resolve({ stages: {} })
  rounds[index].resumes.resolve({ items: [] })
  await flushPromises()
}

function failRound(index) {
  rounds[index].ov.reject(new Error('概览挂了'))
  rounds[index].tk.reject(new Error('任务挂了'))
  rounds[index].pipe.reject(new Error('管道挂了'))
  rounds[index].resumes.reject(new Error('简历挂了'))
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
    const round = {
      ov: deferred(),
      tk: deferred(),
      pipe: deferred(),
      resumes: deferred(),
    }
    rounds.push(round)
    return round.ov.promise
  })
  api.getTodayTasks.mockImplementation(() => rounds[rounds.length - 1].tk.promise)
  targetsApi.getKanban.mockImplementation(() => rounds[rounds.length - 1].pipe.promise)
  resumeApi.getResumeList.mockImplementation(() => rounds[rounds.length - 1].resumes.promise)
  jobsApi.getJobRecommendations.mockResolvedValue({ recommendations: [] })
  resumeApi.getResumeQuickScore.mockResolvedValue({ completeness_score: null })
})

describe('工作台：重载入口在途时点不出第二次', () => {
  it('失败后按钮出现，一按下去就整批消失，直到这一轮落地', async () => {
    const wrapper = await renderHome()
    failRound(0)
    await flushPromises()

    const buttons = reloadButtons(wrapper)
    expect(buttons.length, '两块都失败了却没有可点的「重新加载」').toBeGreaterThanOrEqual(1)

    await buttons[0].trigger('click')
    expect(rounds.length, '点按钮没发出第二轮').toBe(2)
    expect(
      reloadButtons(wrapper).length,
      '在途期间还能再点一次，那 loadDashboard 需要的是令牌而不是这条绊线'
    ).toBe(0)

    await settleRound(1, { overview: { resumes: 3 }, tasks: { high_priority: 2 } })
    expect(wrapper.vm.overview.resumes).toBe(3)
    expect(wrapper.vm.tasks.high_priority).toBe(2)
    wrapper.unmount()
  })

  it('对照组：这一轮落地后按钮不再挂着（成功态没有重试入口）', async () => {
    const wrapper = await renderHome()
    await settleRound(0, { overview: { resumes: 1 }, tasks: { high_priority: 0 } })

    expect(reloadButtons(wrapper).length).toBe(0)
    expect(wrapper.vm.overviewLoaded).toBe(true)
    wrapper.unmount()
  })
})
