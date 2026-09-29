import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import Privacy from '@/features/legal/views/Privacy.vue'
import { installElement } from '@/plugins/element'

/* 隐私页的三个删除动作（删简历 / 删分析 / 删面试）都在自己那条尾巴上调 loadDataSummary，
   而这三个按钮互不锁：删简历的概览重取还在飞的时候去删分析记录，两次重取拿的是**不同时刻**的
   服务器状态。旧那一份晚到的话，合规面就会报"分析记录还有 5 条"，而它们刚刚已被删除。 */

const request = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn(), post: vi.fn() }))
vi.mock('@/api/request', () => ({ default: request }))
vi.mock('@/plugins/element-services', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve('confirm')) },
}))

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const summaryCalls = []

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

let router

async function renderPrivacy(initial) {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/privacy', name: 'privacy', component: { template: '<div />' } }],
  })
  router.push('/privacy')
  await router.isReady()
  const wrapper = mount(Privacy, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await settle(summaryCalls[0], initial)
  await flushPromises()
  return wrapper
}

function summaryValue(label) {
  const item = [...document.querySelectorAll('.summary-item')].find(
    (n) => n.querySelector('span')?.textContent.trim() === label
  )
  expect(item, `概览里没有「${label}」这一项，测试前提不成立`).toBeTruthy()
  return item.querySelector('strong').textContent.trim()
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  summaryCalls.length = 0

  request.get.mockImplementation(() => {
    const record = { ...deferred() }
    summaryCalls.push(record)
    return record.promise
  })
  request.delete.mockImplementation(() => Promise.resolve({ deleted: 1 }))
  request.post.mockResolvedValue({})
})

describe('数据概览：删完之后不能把旧计数留在合规面上', () => {
  it('两次删除的重取交叠时，屏幕上是后一次的结果', async () => {
    const wrapper = await renderPrivacy({
      resumes: 2,
      resume_versions: 3,
      analyses: 5,
      interviews: 1,
    })
    expect(summaryValue('分析')).toBe('5')

    wrapper.vm.deleteResumes()
    await flushPromises()
    await flushPromises()
    expect(summaryCalls.length, '删除简历后没有重取概览').toBe(2)
    const afterResumes = summaryCalls[1]

    wrapper.vm.deleteAnalyses()
    await flushPromises()
    await flushPromises()
    expect(summaryCalls.length, '删除分析后没有重取概览').toBe(3)
    const afterAnalyses = summaryCalls[2]

    await settle(afterAnalyses, { resumes: 0, resume_versions: 0, analyses: 0, interviews: 1 })
    expect(summaryValue('分析')).toBe('0')

    await settle(afterResumes, { resumes: 0, resume_versions: 0, analyses: 5, interviews: 1 })
    expect(summaryValue('分析'), '旧那一份概览把已删除的分析记录又数回来了').toBe('0')
    wrapper.unmount()
  })

  it('对照组：单次删除后概览照常更新', async () => {
    const wrapper = await renderPrivacy({ resumes: 2, analyses: 5 })
    wrapper.vm.deleteAnalyses()
    await flushPromises()
    await flushPromises()
    await settle(summaryCalls[1], { resumes: 2, analyses: 0 })

    expect(summaryValue('分析')).toBe('0')
    wrapper.unmount()
  })
})
