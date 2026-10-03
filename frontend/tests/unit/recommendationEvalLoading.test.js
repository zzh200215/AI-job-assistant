import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import RecommendationEval from '@/features/eval/views/RecommendationEval.vue'
import { installElement } from '@/plugins/element'
import { getJobFeedbackEvaluation } from '@/api/jobs'

/* §10.16 拍的那条 ②：这一页在"还没有任何结果 + 正在取数"的那几秒里**什么都不画**
   （`v-if="!loading && !evaluationData?.total"` 的空态与 `v-else-if="evaluationData"` 的数据支
   都不成立，于是既不转圈也不说在看什么）。新增的那一支排在数据支**之后**，
   所以"点刷新时旧结果仍在"这一支必须继续画旧结果——两条一起钉才有意义。 */

vi.mock('@/api/jobs', async (importOriginal) => ({
  ...(await importOriginal()),
  getJobFeedbackEvaluation: vi.fn(),
  getJobTuningSamples: vi.fn(async () => ({ items: [] })),
  exportJobTuningSamples: vi.fn(async () => new Blob(['x'])),
}))

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { resolve, reject, promise }
}

async function render() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/eval/recommendation', component: { template: '<div />' } }],
  })
  await router.push('/eval/recommendation')
  await router.isReady()
  const wrapper = mount(RecommendationEval, {
    attachTo: document.body,
    global: { plugins: [installElement, router] },
  })
  await flushPromises()
  return wrapper
}

const spinner = () => document.querySelector('.loading-state')
const dataBlock = () => document.querySelector('.summary-grid')

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('反馈评估页的在途形状', () => {
  it('还没有结果而在途时画 spinner，不再是空白页', async () => {
    const first = deferred()
    getJobFeedbackEvaluation.mockReturnValue(first.promise)
    const wrapper = await render()

    expect(spinner(), '在途期间这块仍然什么都没有').toBeTruthy()
    expect(dataBlock()).toBeNull()

    first.resolve({ total: 0 })
    await flushPromises()
    expect(spinner(), '结果落地后 spinner 没撤掉').toBeNull()
    wrapper.unmount()
  })

  it('已经有结果时点刷新，旧结果继续画，不被 spinner 顶掉', async () => {
    getJobFeedbackEvaluation.mockResolvedValue({ total: 5, evaluation: {}, trend: [] })
    const wrapper = await render()
    expect(dataBlock(), '有 total 就该进数据支，测试前提不成立').toBeTruthy()

    const second = deferred()
    getJobFeedbackEvaluation.mockReturnValueOnce(second.promise)
    const refresh = wrapper.findAll('button').find((b) => b.text().trim() === '刷新')
    expect(refresh, '找不到刷新按钮，测试前提不成立').toBeTruthy()
    await refresh.trigger('click')

    expect(dataBlock(), '在途时旧结果被撤下了——那是把"刷新中"演成"没有数据"').toBeTruthy()
    expect(spinner()).toBeNull()

    second.resolve({ total: 7, evaluation: {}, trend: [] })
    await flushPromises()
    expect(dataBlock()).toBeTruthy()
    wrapper.unmount()
  })
})
