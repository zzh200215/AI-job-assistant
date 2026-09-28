import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobTargets from '@/views/JobTargets.vue'
import { installElement } from '@/plugins/element'

/* 求职目标的「重新加载」(`:60`) 没有锁，新增/设为默认/删除三个动作的尾巴也各调一次 loadTargets，
   而它在 `await getTargets()` 之后直接写 targets/loadError——形状上也正是这一轮在找的那种。
   但它同样点不出第二次：这一发在途时 `v-if="loading"` 的 spinner 分支（`:52`）把整块错误块和行按钮
   一起换掉了。与 Home、与 D31 的看板同型，所以这里留绊线而不是装令牌：
   谁改掉了"加载期间不渲染列表/错误块"，这条就会红。 */

const api = vi.hoisted(() => ({
  getTargets: vi.fn(),
  createTarget: vi.fn(),
  updateTarget: vi.fn(),
  deleteTarget: vi.fn(),
  setPrimaryTarget: vi.fn(),
}))

vi.mock('@/api/targets', () => api)

function deferred() {
  let resolve
  let reject
  const promise = new Promise((r, j) => {
    resolve = r
    reject = j
  })
  return { resolve, reject, promise }
}

const calls = []

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const target = (id, name, primary = false) => ({
  id,
  target_title: name,
  city: '北京',
  is_primary: primary,
  stage: 'todo',
})

let router

async function renderTargets() {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/targets', name: 'targets', component: { template: '<div />' } }],
  })
  router.push('/targets')
  await router.isReady()
  const wrapper = mount(JobTargets, {
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
  calls.length = 0
  api.getTargets.mockImplementation(() => {
    const record = { ...deferred() }
    calls.push(record)
    return record.promise
  })
  api.createTarget.mockResolvedValue({})
  api.updateTarget.mockResolvedValue({})
  api.deleteTarget.mockResolvedValue({})
  api.setPrimaryTarget.mockResolvedValue({})
})

describe('求职目标：重载入口在途时点不出第二次', () => {
  it('失败后按钮出现，一按下去就随错误块一起消失，直到这一轮落地', async () => {
    const wrapper = await renderTargets()
    calls[0].reject(new Error('列表挂了'))
    await flushPromises()

    expect(reloadButtons(wrapper).length, '失败块里应该有「重新加载」').toBe(1)

    await reloadButtons(wrapper)[0].trigger('click')
    expect(calls.length, '点按钮没发出第二轮').toBe(2)
    expect(
      reloadButtons(wrapper).length,
      '在途期间还能再点一次，那 loadTargets 需要的是令牌而不是这条绊线'
    ).toBe(0)

    await settle(calls[1], { targets: [target(1, '重载后的目标')] })
    expect(wrapper.vm.targets.map((t) => t.target_title)).toEqual(['重载后的目标'])
    expect(wrapper.vm.loading).toBe(false)
    wrapper.unmount()
  })

  it('对照组：单次加载照常出列表', async () => {
    const wrapper = await renderTargets()
    await settle(calls[0], { targets: [target(3, '唯一目标')] })

    expect(wrapper.vm.targets.map((t) => t.target_title)).toEqual(['唯一目标'])
    expect(reloadButtons(wrapper).length).toBe(0)
    wrapper.unmount()
  })
})
