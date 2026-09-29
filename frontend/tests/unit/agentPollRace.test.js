import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import AgentAnalysis from '@/features/analysis/views/AgentAnalysis.vue'
import { installElement } from '@/plugins/element'

/* 多智能体分析面板的 pollSteps 是一条自续的轮询链：从 URL 带 task_id 进来时启动一条，
   用户点「启动分析」又在 onStart 尾巴上启动一条。两条链都读同一个 `taskId.value`，
   所以旧链在途的那一发会**用旧任务 id 发请求**，回来后把新任务的步骤/检索/检查整块换掉——
   屏幕上写着新任务的进度，内容却是上一个任务的。 */

const api = vi.hoisted(() => ({
  getAgentSteps: vi.fn(),
  startAgentAnalysis: vi.fn(),
}))

vi.mock('@/api/agent', () => api)

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const calls = []

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const trace = (task, stepName) => ({
  task: { id: task, status: 'completed' },
  steps: [{ id: 1, name: stepName, status: 'completed' }],
  retrievals: [],
  checks: [],
})

let router

async function renderPanel() {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/agent', name: 'agent', component: { template: '<div />' } }],
  })
  router.push('/agent')
  await router.isReady()
  return mount(AgentAnalysis, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  calls.length = 0
  api.getAgentSteps.mockImplementation((id) => {
    const record = { id, ...deferred() }
    calls.push(record)
    return record.promise
  })
  api.startAgentAnalysis.mockResolvedValue({ task_id: 'task-B' })
})

describe('多智能体轮询：旧任务那一发不能盖住新任务', () => {
  it('两条轮询链交叠时，屏幕上必须是当前任务的步骤', async () => {
    const wrapper = await renderPanel()

    wrapper.vm.taskId = 'task-A'
    wrapper.vm.pollSteps()
    await flushPromises()
    expect(calls[0].id).toBe('task-A')

    wrapper.vm.taskId = 'task-B'
    wrapper.vm.pollSteps()
    await flushPromises()
    expect(calls.length, '第二条链没发请求，测试前提不成立').toBe(2)
    expect(calls[1].id).toBe('task-B')

    await settle(calls[1], trace('task-B', '新任务的步骤'))
    expect(wrapper.vm.steps.map((s) => s.name)).toEqual(['新任务的步骤'])

    await settle(calls[0], trace('task-A', '旧任务的步骤'))
    expect(
      wrapper.vm.steps.map((s) => s.name),
      '旧任务的步骤盖回来了'
    ).toEqual(['新任务的步骤'])
    expect(wrapper.vm.task.id).toBe('task-B')
    wrapper.unmount()
  })

  it('对照组：单条轮询照常把步骤放上屏幕', async () => {
    const wrapper = await renderPanel()
    wrapper.vm.taskId = 'task-A'
    wrapper.vm.pollSteps()
    await flushPromises()
    await settle(calls[0], trace('task-A', '唯一一步'))

    expect(wrapper.vm.steps.map((s) => s.name)).toEqual(['唯一一步'])
    wrapper.unmount()
  })
})
