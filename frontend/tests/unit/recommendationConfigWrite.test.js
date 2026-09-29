import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import RecommendationConfig from '@/features/eval/views/RecommendationConfig.vue'
import { installElement } from '@/plugins/element'

/* 这一页的「保存配置」与「恢复默认」各自锁自己的 loading 位，于是另一条在途时照样能点；
   两者都会在响应落地后写同一个 `savedConfig` 并跑 `applyConfig(data)` 把表单重刷一遍。
   所以交叠的后果是：**屏幕上留下的权重属于先点的那一次**，而用户最后看到的是"已恢复默认配置"
   或"已保存"的 toast。与 D29 的 loadWorkspace、D30 的重处理锁同一类——修法是互相上锁，不是令牌。 */

const api = vi.hoisted(() => ({
  getJobRecommendConfig: vi.fn(),
  updateJobRecommendConfig: vi.fn(),
  resetJobRecommendConfig: vi.fn(),
  compareJobRecommendConfig: vi.fn(),
}))

vi.mock('@/api/jobs', () => api)

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const inflight = { save: [], reset: [] }

function hang(bucket) {
  return (...args) => {
    const record = { args, ...deferred() }
    inflight[bucket].push(record)
    return record.promise
  }
}

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const config = (vector) => ({
  vector_weight: vector,
  rule_weight: 1 - vector,
  rule_components: { skill: 0.5, experience: 0.2, salary: 0.15, location: 0.15 },
  thresholds: { high: 80, medium: 60 },
})

let router

async function renderConfig() {
  api.getJobRecommendConfig.mockResolvedValue(config(0.6))
  api.compareJobRecommendConfig.mockResolvedValue({})
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/recommend-config', name: 'rc', component: { template: '<div />' } }],
  })
  router.push('/recommend-config')
  await router.isReady()
  const wrapper = mount(RecommendationConfig, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function buttonByText(wrapper, text) {
  const found = wrapper.findAll('button').find((b) => b.text().trim() === text)
  expect(found, `找不到文案正好是「${text}」的按钮，测试前提不成立`).toBeTruthy()
  return found
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  inflight.save.length = 0
  inflight.reset.length = 0
  api.updateJobRecommendConfig.mockImplementation(hang('save'))
  api.resetJobRecommendConfig.mockImplementation(hang('reset'))
})

describe('推荐配置：保存与恢复默认不能同时在途', () => {
  it('保存还在途时，恢复默认必须点不动', async () => {
    const wrapper = await renderConfig()

    await buttonByText(wrapper, '保存配置').trigger('click')
    expect(inflight.save.length, '点保存没发请求').toBe(1)
    expect(buttonByText(wrapper, '恢复默认').element.disabled, '保存还在途，恢复默认却还能点').toBe(
      true
    )

    await settle(inflight.save[0], config(0.9))
    expect(buttonByText(wrapper, '恢复默认').element.disabled).toBe(false)

    await buttonByText(wrapper, '恢复默认').trigger('click')
    expect(inflight.reset.length).toBe(1)
    expect(buttonByText(wrapper, '保存配置').element.disabled, '恢复默认还在途，保存却还能点').toBe(
      true
    )

    await settle(inflight.reset[0], config(0.5))
    expect(buttonByText(wrapper, '保存配置').element.disabled).toBe(false)
    wrapper.unmount()
  })

  it('对照组：串行地点两次，后一次的配置照常落到屏幕上', async () => {
    const wrapper = await renderConfig()

    await buttonByText(wrapper, '保存配置').trigger('click')
    await settle(inflight.save[0], config(0.9))
    expect(wrapper.vm.form.vector_weight).toBeCloseTo(0.9)

    await buttonByText(wrapper, '恢复默认').trigger('click')
    await settle(inflight.reset[0], config(0.6))
    expect(wrapper.vm.form.vector_weight).toBeCloseTo(0.6)
    expect(wrapper.vm.savedConfig.vector_weight).toBeCloseTo(0.6)
    wrapper.unmount()
  })
})
