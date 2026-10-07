import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import KnowledgeBase from '@/features/knowledge/views/KnowledgeBase.vue'
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

/* 账上那条"未收"（D59 批次记的 `doUpload`：上传失败后对话框与拖拽区都还在，此时再投一个文件，
   `uploadProgress`/`uploadStatus`/`uploadError` 会互相串）在这一版收掉了。
   注意它和上面那条**不是同一种病**：上面是"后到的响应盖掉新结果"，这里是**两次会话共写同一组状态**——
   第一发的进度回调和它的 catch/finally 在第二发开始之后仍然会跑完。所以判据不是"谁的结果留下"，
   而是"不属于当前会话的回调一个字都不许写"。 */
describe('知识库：两次上传会话不能共写一组进度状态', () => {
  function deferredPair() {
    let resolve
    let reject
    const promise = new Promise((res, rej) => {
      resolve = res
      reject = rej
    })
    return { promise, resolve, reject, onProgress: null }
  }

  let runs

  beforeEach(() => {
    runs = []
    api.uploadKnowledge.mockImplementation((formData, onProgress) => {
      const d = deferredPair()
      d.onProgress = onProgress
      runs.push(d)
      return d.promise
    })
    api.listKnowledge.mockResolvedValue({ items: [], total: 0 })
  })

  it('第一发在第二发开始之后回来：进度不动、错误不上屏、忙碌条不许解除', async () => {
    const wrapper = await renderList()

    wrapper.vm.uploadForm.title = '第一份'
    const first = wrapper.vm.doUpload({ file: { size: 1000 } })
    await flushPromises()
    expect(runs).toHaveLength(1)

    wrapper.vm.uploadForm.title = '第二份'
    const second = wrapper.vm.doUpload({ file: { size: 2000 } })
    await flushPromises()
    expect(runs).toHaveLength(2)
    expect(wrapper.vm.uploadProgress).toBe(0)

    // 第一发的进度回调迟到了：它汇报 90%，屏幕上此刻只能是第二发的世界
    runs[0].onProgress({ loaded: 900, total: 1000 })
    expect(wrapper.vm.uploadProgress, '被作废的会话写了进度').toBe(0)

    // 第二发的进度正常落地（500/2000 = 25%）
    runs[1].onProgress({ loaded: 500, total: 2000 })
    expect(wrapper.vm.uploadProgress).toBe(25)

    // 第一发失败回来：既不能把错误文案挂到屏幕上，也不能把忙碌条解除
    runs[0].reject(new Error('第一发网络错误'))
    await first
    await flushPromises()
    expect(wrapper.vm.uploadError, '被作废的会话把失败文案写给了新会话').toBe('')
    expect(wrapper.vm.uploading, '被作废的会话解除了新会话的忙碌状态').toBe(true)

    runs[1].resolve({})
    await second
    await flushPromises()
    expect(wrapper.vm.uploadError).toBe('')
    expect(wrapper.vm.uploadProgress).toBe(100)
    expect(wrapper.vm.uploading).toBe(false)
    wrapper.unmount()
  })

  it('只有一发时照常工作：守卫不会把正常的失败也一起吞掉', async () => {
    const wrapper = await renderList()
    wrapper.vm.uploadForm.title = '唯一一份'
    const only = wrapper.vm.doUpload({ file: { size: 400 } })
    await flushPromises()

    runs[0].onProgress({ loaded: 100, total: 400 })
    expect(wrapper.vm.uploadProgress).toBe(25)

    runs[0].reject(new Error('网络错误'))
    await only
    await flushPromises()
    expect(wrapper.vm.uploadError).not.toBe('')
    expect(wrapper.vm.uploading).toBe(false)
    wrapper.unmount()
  })
})
