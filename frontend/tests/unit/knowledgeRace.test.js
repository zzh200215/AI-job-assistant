import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import KnowledgeBase from '@/views/KnowledgeBase.vue'
import { installElement } from '@/plugins/element'

/* 知识库列表的筛选是 watch 触发的：改类型、再改状态，两次请求可以同时在飞；
   loadList 在 await 之后直接写 list.value，于是**后完成的那次赢**——下拉框显示的是
   新组合，表格里却是旧组合的结果。 */
const calls = []

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const api = vi.hoisted(() => ({
  listKnowledge: vi.fn(),
  getEmbeddingStats: vi.fn(),
  getKnowledgeChunks: vi.fn(),
  deleteKnowledgeDoc: vi.fn(),
  queryRewriteTest: vi.fn(),
  rebuildKnowledge: vi.fn(),
  reprocessKnowledgeDoc: vi.fn(),
  searchKnowledge: vi.fn(),
  uploadKnowledge: vi.fn(),
}))

vi.mock('@/api/knowledge', () => api)

async function renderList() {
  const route = { path: '/knowledge', name: 'knowledge', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/knowledge')
  await router.isReady()
  const wrapper = mount(KnowledgeBase, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function respond(index, title) {
  const call = calls[index]
  if (!call) throw new Error(`request ${index} not issued (${calls.length} so far)`)
  call.resolve({ items: [{ id: index + 1, title, doc_type: 'policy', status: 'done' }], total: 1 })
}

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
  api.listKnowledge.mockImplementation(() => {
    const d = deferred()
    calls.push(d)
    return d.promise
  })
  api.getEmbeddingStats.mockResolvedValue({})
})

describe('知识库：连续改筛选时，旧结果不能盖掉新结果', () => {
  it('两次筛选都发出请求，表格数据留下的是后发起那一次', async () => {
    const wrapper = await renderList()
    expect(calls).toHaveLength(1)

    // 用组件的真实状态改两次筛选（等价于用户连点两个下拉框）
    wrapper.vm.filterType = 'policy'
    await flushPromises()
    wrapper.vm.filterStatus = 'failed'
    await flushPromises()
    expect(calls.length).toBeGreaterThanOrEqual(3)

    // el-table 在 jsdom 里不渲染行，所以断言它绑定的 list（表格显示的就是这份数据）
    respond(calls.length - 1, '新筛选的结果')
    await flushPromises()
    expect(wrapper.vm.list.map((d) => d.title)).toEqual(['新筛选的结果'])

    respond(0, '最早那次的结果')
    await flushPromises()
    expect(wrapper.vm.list.map((d) => d.title)).toEqual(['新筛选的结果'])
    wrapper.unmount()
  })
})
