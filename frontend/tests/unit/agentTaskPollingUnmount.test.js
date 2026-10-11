import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { useAgentTaskPolling } from '@/composables/useAgentTaskPolling'

/* D207：把 `rejectOnStop` 打开的不是轮询器自己，是这条把 `stopPolling` 挂在 `onUnmounted`
   上的组合层。所以这一组测的是**接线**：任务还在跑的时候卸载 ⇒ 那个 await 必须落地。
   不接的话调用方的 `finally { loading = false }` 永不执行（D204 数到的三处悬挂 await）。 */

const task = { status: 'running' }
const calls = { task: 0 }

vi.mock('@/api/agent', () => ({
  getAgentTask: async () => {
    calls.task += 1
    return { ...task }
  },
  getAgentSteps: async () => ({ steps: [] }),
}))

const Host = defineComponent({
  setup() {
    const polling = useAgentTaskPolling()
    return { polling }
  },
  template: '<div />',
})

/** 给一小段时间让在飞的 promise 有机会落地（落地 = 非 pending）。 */
async function settleState(promise, ms = 20) {
  return Promise.race([
    promise.then(
      (value) => ({ state: 'resolved', value }),
      (error) => ({ state: 'rejected', error })
    ),
    new Promise((resolve) => setTimeout(() => resolve({ state: 'pending' }), ms)),
  ])
}

beforeEach(() => {
  task.status = 'running'
  calls.task = 0
})

describe('卸载即落地', () => {
  it('任务还在 running 时卸载：await 以 polling_stopped 拒绝，且不再发第二轮请求', async () => {
    const wrapper = mount(Host)
    const pending = wrapper.vm.polling.pollTask(9, { intervalMs: 20 })
    await flushPromises()
    expect(calls.task).toBe(1)
    expect((await settleState(pending, 5)).state).toBe('pending')

    wrapper.unmount()
    await flushPromises()

    const outcome = await settleState(pending)
    expect(outcome.state).toBe('rejected')
    expect(outcome.error.code).toBe('polling_stopped')

    calls.task = 0
    await new Promise((resolve) => setTimeout(resolve, 60))
    expect(calls.task).toBe(0, '落地之后不能还在轮询')
    expect(wrapper.vm.polling.isPolling.value).toBe(false)
  })

  it('反证：任务先完成再卸载，成功那一发不能被自己的停表改判成拒绝', async () => {
    task.status = 'completed'
    const wrapper = mount(Host)

    const result = await wrapper.vm.polling.pollTask(9, { intervalMs: 20 })
    expect(result.status).toBe('completed')

    wrapper.unmount()
    await flushPromises()

    expect(wrapper.vm.polling.isPolling.value).toBe(false)
  })
})
