import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import TaskCenter from '@/features/shell/views/TaskCenter.vue'
import { installElement } from '@/plugins/element'

/* 任务中心每 10 秒轮询一次；loadTasks 在 await 之后直接写 tasks.value，所以
   **后完成的那次请求赢，而不是后发起的那次赢**。轮询间隔不看上一次有没有回来，
   概览卡片也不像"刷新"按钮那样在 loading 时禁用，所以两条路径都能叠出并发。 */
const calls = []

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise, settled: false }
}

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn((url) => {
      const d = deferred()
      calls.push({ url, ...d })
      return d.promise
    }),
    post: vi.fn(async () => ({})),
  },
}))

async function renderCenter() {
  const route = { path: '/tasks', name: 'tasks', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/tasks')
  await router.isReady()
  const wrapper = mount(TaskCenter, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function lists() {
  return calls.filter((c) => c.url === '/agent/tasks')
}

/** 让第 index 次发起的请求带着 id 返回 */
async function respond(index, id, status = 'completed') {
  const list = lists()[index]
  const summary = calls.filter((c) => c.url === '/agent/tasks/summary')[index]
  if (!list || !summary) throw new Error(`request pair ${index} not issued`)
  list.resolve({ items: [{ id, name: `任务${id}`, status, create_time: 0 }] })
  summary.resolve({ counts: {}, total: 1 })
  await flushPromises()
}

function rendered() {
  return [...document.querySelectorAll('.task-card strong')].map((n) => n.textContent.trim())
}

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('任务中心：后发起的请求不能被旧响应覆盖', () => {
  it('轮询撞上慢请求时，屏幕留下的是新那一次', async () => {
    const wrapper = await renderCenter()
    expect(lists()).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(10000) // 上一次还没回来，10 秒轮询又发一次
    await flushPromises()
    expect(lists()).toHaveLength(2)

    await respond(1, 99) // 新的一次先回来
    await respond(0, 1) // 最早那次最后才回来

    expect(rendered()).toEqual(['任务99'])
    wrapper.unmount()
  })

  it('真实任务形状：对象进度、当前步骤、耗时与结果链接都能上屏', async () => {
    const wrapper = await renderCenter()
    lists()[0].resolve({
      items: [
        {
          id: 33,
          status: 'completed',
          create_time: 0,
          analysis_record_id: 77,
          progress: {
            progress_percent: 100,
            current_step: { label: '汇总结果' },
            duration_ms: 65000,
          },
        },
      ],
    })
    calls
      .filter((c) => c.url === '/agent/tasks/summary')[0]
      .resolve({
        counts: { completed: 1 },
        total: 1,
      })
    await flushPromises()

    expect(wrapper.find('.task-card strong').text()).toBe('求职分析任务')
    expect(wrapper.text()).toContain('分钟')
    expect(wrapper.find('.el-progress').exists()).toBe(true)
    expect(wrapper.findAll('button').some((b) => b.text().includes('查看结果'))).toBe(true)
    wrapper.unmount()
  })

  it('「进行中」按一组状态筛，和概览卡片的口径一致', async () => {
    const wrapper = await renderCenter()
    const running = wrapper.findAll('.summary-card').find((c) => c.text().includes('进行中'))
    await running.trigger('click')
    await flushPromises()

    lists()[1].resolve({
      items: [
        { id: 1, status: 'pending', create_time: 0 },
        { id: 2, status: 'running', create_time: 0 },
        { id: 3, status: 'completed', create_time: 0 },
      ],
    })
    calls
      .filter((c) => c.url === '/agent/tasks/summary')[1]
      .resolve({
        counts: { running: 1, pending: 1 },
        total: 3,
      })
    await flushPromises()

    expect(wrapper.findAll('.task-card')).toHaveLength(2)
    expect(wrapper.findAll('.task-card .el-tag').map((t) => t.text())).toEqual(['等待中', '运行中'])
    wrapper.unmount()
  })

  it('点概览卡片换筛选时，慢的旧结果不能盖掉新筛选', async () => {
    const wrapper = await renderCenter()
    const running = wrapper.findAll('.summary-card').find((c) => c.text().includes('进行中'))
    expect(running).toBeTruthy()

    await running.trigger('click')
    await flushPromises()
    expect(lists()).toHaveLength(2) // 卡片在 loading 期间可点，叠出第二个请求

    await respond(1, 99, 'running') // 新筛选先回来
    await respond(0, 1, 'running') // 全部列表后回来

    expect(rendered()).toEqual(['任务99'])
    wrapper.unmount()
  })
})
