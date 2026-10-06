import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useCareerPlanningRun } from '@/features/planning/composables/useCareerPlanningRun'
import CareerPlanning from '@/features/planning/views/CareerPlanning.vue'
import { installElement } from '@/plugins/element'
import { runFullAnalysis } from '@/api/analysis'
import { ElMessage } from '@/plugins/element-services'

/* D56 把规划运行链抽成 `useCareerPlanningRun`。这条链最贵的一件事是**任何一条终止路径都必须把
   `running` 放下来**：按钮吃的是 `:loading="running"`，停在 true 就等于这一页再也点不动了
   （同一形状的两个缺陷是 D54 在面板链上抓到的）。搬之前这些路径一条都没测。 */

const poll = { behaviour: 'completed' }

vi.mock('@/api/analysis', () => ({
  runFullAnalysis: vi.fn(async () => ({ task_id: 't1' })),
  getAnalysis: vi.fn(async (recordId) => ({
    record_id: recordId,
    match_score: 72,
    career_planning: { overall_advice: '先补分布式', current_status: { summary: '成长期' } },
  })),
}))

vi.mock('@/plugins/element-services', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/composables/useAgentTaskPolling', () => ({
  useAgentTaskPolling: () => ({
    isPolling: { value: false },
    pollTask: async (_taskId, handlers) => {
      if (poll.behaviour === 'failed') return handlers.onFailed(new Error('炸了'))
      if (poll.behaviour === 'cancelled') return handlers.onCancelled({ code: 'task_cancelled' })
      if (poll.behaviour === 'timeout') return handlers.onTimeout()
      if (poll.behaviour === 'no-record')
        return handlers.onCompleted({ status: 'completed', analysis_record_id: null })
      handlers.onProgress({ status: 'running' }, [
        { step_name: 'career_planning', status: 'completed' },
        { step_name: 'self_check', status: 'running' },
      ])
      await handlers.onCompleted({ status: 'partial', analysis_record_id: 55 })
    },
  }),
}))

// 页面挂载要读简历与 JD 列表；两个守卫用例靠这个开关决定列表里有没有简历。
const listState = { resumes: 'empty' }

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn((url) => {
      if (url === '/resume/list') {
        return Promise.resolve({
          items: listState.resumes === 'one' ? [PARSED_WITHOUT_TITLE] : [],
          total: 0,
        })
      }
      return Promise.resolve({ items: [], total: 0 })
    }),
  },
}))

const PARSED_WITHOUT_TITLE = { id: 7, name: '没有职称', parsed: { years_exp: 3 } }

function makeRun(overrides = {}) {
  const finished = []
  const chain = useCareerPlanningRun({
    getResumeId: () => 7,
    resolveJdId: async () => 3,
    onAnalysisFinished: async () => finished.push(1),
    ...overrides,
  })
  return { chain, finished }
}

describe('运行链的四条终止路径都要把 running 放下来', () => {
  beforeEach(() => {
    /* §10.9 ①（D124）之后 `useCareerPlanningRun()` 里要取 selection store，而这一组测试
     **不挂组件**、直接调 composable，所以得自己摆一个活的 pinia（应用里它只从 setup 被调用）。 */
    setActivePinia(createPinia())
    poll.behaviour = 'completed'
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('跑完：记录、派生标签、以及"完成后刷两条面板链"的回调', async () => {
    const { chain, finished } = makeRun()
    const outcome = await chain.startCareerPlanning()
    expect(outcome.ok).toBe(true)
    expect(chain.running.value).toBe(false)
    expect(chain.analysisRecordId.value).toBe(55)
    expect(chain.careerResult.value?.overall_advice).toBe('先补分布式')
    expect(chain.taskStatus.value).toBe('partial')
    expect(chain.taskStatusLabel.value).toBe('部分完成')
    expect(chain.completedSteps.value).toBe(1)
    expect(chain.currentStepName.value).toBe('自我校验')
    /* partial 且有职业规划内容时，标签说的是"已生成"——`careerResult` 那一支排在 partial 之前。
       这条顺序是原页面的判据，搬的时候一个字没改（改它等于改候选人看到的措辞）。 */
    expect(chain.analysisStatusLabel.value).toBe('已生成')
    expect(finished).toEqual([1])
  })

  it('任务失败：不刷面板，running 归位', async () => {
    poll.behaviour = 'failed'
    const { chain, finished } = makeRun()
    const outcome = await chain.startCareerPlanning()
    /* `onFailed` 只置状态、不抛异常，所以 pollTask 正常返回 → outcome 仍是 ok。
       原页面就是这样：失败靠页面上那行状态说话，不额外弹 toast。 */
    expect(outcome.ok).toBe(true)
    expect(chain.running.value).toBe(false)
    expect(chain.taskStatus.value).toBe('failed')
    expect(chain.analysisRecordId.value).toBeNull()
    expect(finished).toEqual([])
  })

  it('超时：也说失败，而且按钮不会再亮着', async () => {
    poll.behaviour = 'timeout'
    const { chain } = makeRun()
    await chain.startCareerPlanning()
    expect(chain.taskStatus.value).toBe('failed')
    expect(chain.running.value).toBe(false)
  })

  it('取消：状态归到 cancelled 而不是 failed', async () => {
    poll.behaviour = 'cancelled'
    const { chain } = makeRun()
    const outcome = await chain.startCareerPlanning()
    expect(chain.taskStatus.value).toBe('cancelled')
    expect(chain.taskStatusLabel.value).toBe('已取消')
    expect(chain.running.value).toBe(false)
    expect(outcome.ok).toBe(true) // 取消不是异常：pollTask 正常返回
  })

  it('没有记录 id：抛出来的那句错误要被收进 failed，不能留下 running', async () => {
    poll.behaviour = 'no-record'
    const { chain, finished } = makeRun()
    const outcome = await chain.startCareerPlanning()
    expect(chain.running.value).toBe(false)
    expect(chain.taskStatus.value).toBe('failed')
    expect(chain.analysisRecordId.value).toBeNull()
    expect(finished).toEqual([])
    expect(outcome.error?.message).toContain('没有生成记录')
  })

  it('建目标 JD 就失败：一整条链路都不该发出去', async () => {
    const { chain, finished } = makeRun({
      resolveJdId: async () => {
        throw new Error('JD 创建失败')
      },
    })
    const outcome = await chain.startCareerPlanning()
    expect(runFullAnalysis).not.toHaveBeenCalled()
    expect(chain.running.value).toBe(false)
    expect(chain.taskStatus.value).toBe('failed')
    expect(finished).toEqual([])
    expect(outcome.error?.message).toBe('JD 创建失败')
  })
})

describe('两句表单守卫留在页面，而不是躲进运行链', () => {
  /* 简历 7 解析过、所以会进列表并被自动选中，但它**没有** current_title：
     于是第一道守卫（必须有简历）过得去，第二道（岗位名与 JD 至少有一个）才轮到被检验。 */

  async function mountPage() {
    const route = { path: '/career-planning', name: 'career', component: { template: '<div />' } }
    const router = createRouter({ history: createMemoryHistory(), routes: [route] })
    router.push('/career-planning')
    await router.isReady()
    const wrapper = mount(CareerPlanning, {
      attachTo: document.body,
      global: { plugins: [installElement, createPinia(), router] },
    })
    await flushPromises()
    return wrapper
  }

  function planButton(wrapper) {
    return wrapper.findAll('.action-buttons button').at(-1)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
    listState.resumes = 'empty'
    localStorage.clear()
    localStorage.setItem('token', 'smoke-test-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'smoke', role: 'candidate' }))
  })

  it('列表里一份简历都没有 → 只说"请先选择简历"，一整条链路都不发', async () => {
    listState.resumes = 'empty'
    const wrapper = await mountPage()
    await planButton(wrapper).trigger('click')
    await flushPromises()
    expect(ElMessage.warning).toHaveBeenCalledWith('请先选择简历')
    expect(runFullAnalysis).not.toHaveBeenCalled()
    /* 守卫必须在 running 之前：按钮不能带着空输入转圈（`is-loading` 是 EP 的 loading 类）。 */
    expect(planButton(wrapper).classes()).not.toContain('is-loading')
  })

  it('有简历、但岗位名与 JD 都空 → 拦在第二句，仍然不发链路', async () => {
    listState.resumes = 'one'
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('没有职称') // 简历确实被选中了，第一道守卫是过不了的对面
    await planButton(wrapper).trigger('click')
    await flushPromises()
    expect(ElMessage.warning).toHaveBeenCalledWith('请填写目标岗位，或直接选择一个现有 JD')
    expect(ElMessage.warning).not.toHaveBeenCalledWith('请先选择简历')
    expect(runFullAnalysis).not.toHaveBeenCalled()
  })
})
