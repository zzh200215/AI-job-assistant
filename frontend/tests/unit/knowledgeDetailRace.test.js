import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import KnowledgeBase from '@/views/KnowledgeBase.vue'
import { installElement } from '@/plugins/element'

/* 知识库这一页的列表已经有令牌（D3 那次接的），这轮查的是它没管到的三处：
   - refreshDetail：行上的「详情」按钮没有 disabled，抽屉关掉并不会取消已经发出的 GET，
     两次交叠会让抽屉装着上一个文档的切片，而"重新处理文档"按钮拿的就是这份错文档的 id；
   - onReprocess：`:disabled="reprocessingId === row.id"` 是按行的，点第二行时 `reprocessingId`
     变成第二行，第一行的 finally 又把它整个清掉 —— 第二行还在途就解锁了；
   - onRebuild：「重建索引」按钮没有任何锁，确认两次就是两次全量重处理。
   el-table 在 jsdom 里不渲染行（knowledgeRace.test.js 已经记过这条），所以前两条直接调
   `wrapper.vm` 上的入口函数，"用户能不能点"由 `:208/:213/:137` 的模板绑定证明。 */

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

const inflight = {}

function hang(name) {
  inflight[name] = []
  api[name] = vi.fn((...args) => {
    const record = { args, ...deferred() }
    inflight[name].push(record)
    return record.promise
  })
}

const lastOf = (name) => [...inflight[name]].pop()
const nthOf = (name, i) => inflight[name][i]
const countOf = (name) => inflight[name].length

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const doc = (id, title) => ({
  id,
  title,
  doc_type: 'general',
  status: 'ready',
  chunk_count: 1,
  file_name: `${title}.md`,
  create_time: '2026-09-01T00:00:00Z',
  update_time: '2026-09-02T00:00:00Z',
})

const chunksFor = (title) => ({
  document: doc(title === '甲文档' ? 1 : 2, title),
  chunks: [{ chunk_id: `c-${title}`, chunk_index: 0, text: `正文来自${title}` }],
})

let router

async function renderKb(docs = [doc(1, '甲文档'), doc(2, '乙文档')]) {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/knowledge', name: 'knowledge', component: { template: '<div />' } }],
  })
  router.push('/knowledge')
  await router.isReady()
  const wrapper = mount(KnowledgeBase, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await settle(lastOf('listKnowledge'), { items: docs, total: docs.length })
  return wrapper
}

function rebuildButton(wrapper) {
  const found = wrapper.findAll('button').find((b) => b.text().includes('重建索引'))
  expect(found, '「重建索引」按钮没渲染出来，测试前提不成立').toBeTruthy()
  return found
}

function chunkTexts() {
  return [...document.querySelectorAll('.chunk-card p')].map((n) => n.textContent.trim())
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  for (const key of Object.keys(inflight)) delete inflight[key]

  api.getEmbeddingStats.mockResolvedValue({})
  api.queryRewriteTest.mockResolvedValue({})
  api.searchKnowledge.mockResolvedValue({})
  api.deleteKnowledgeDoc.mockResolvedValue({})
  hang('listKnowledge')
  hang('getKnowledgeChunks')
  hang('reprocessKnowledgeDoc')
  hang('rebuildKnowledge')
})

describe('知识库：抽屉与重处理不能拿旧那一轮的结果当事实', () => {
  it('先看甲文档再看乙文档时，甲的响应不能把抽屉换回甲', async () => {
    const wrapper = await renderKb()

    wrapper.vm.openDetail(doc(1, '甲文档'))
    await flushPromises()
    expect(lastOf('getKnowledgeChunks').args[0]).toBe(1)

    wrapper.vm.openDetail(doc(2, '乙文档'))
    await flushPromises()
    expect(lastOf('getKnowledgeChunks').args[0]).toBe(2)

    await settle(lastOf('getKnowledgeChunks'), chunksFor('乙文档'))
    expect(chunkTexts()).toEqual(['正文来自乙文档'])

    await settle(nthOf('getKnowledgeChunks', 0), chunksFor('甲文档'))
    expect(chunkTexts(), '抽屉里装着先发起那份文档的切片').toEqual(['正文来自乙文档'])
    expect(wrapper.vm.detailDoc.id, '「重新处理文档」按钮会拿这个 id 去重处理').toBe(2)
    wrapper.unmount()
  })

  it('第二行重处理还在途时，第一行收尾不能把它解锁', async () => {
    const wrapper = await renderKb()

    wrapper.vm.onReprocess(doc(1, '甲文档'))
    await flushPromises()
    wrapper.vm.onReprocess(doc(2, '乙文档'))
    await flushPromises()
    expect(countOf('reprocessKnowledgeDoc')).toBe(2)
    expect(wrapper.vm.reprocessingId).toBe(2)

    await settle(nthOf('reprocessKnowledgeDoc', 0), {})
    await settle(lastOf('listKnowledge'), { items: [], total: 0 })
    expect(
      wrapper.vm.reprocessingId,
      '乙文档的重处理还在飞，reprocessingId 已经被甲那一次的 finally 清成 null'
    ).toBe(2)

    await settle(nthOf('reprocessKnowledgeDoc', 1), {})
    await settle(lastOf('listKnowledge'), { items: [], total: 0 })
    expect(wrapper.vm.reprocessingId).toBe(null)
    wrapper.unmount()
  })

  it('重建索引提交之后要先锁住按钮，否则确认两次就是两次全量重处理', async () => {
    const wrapper = await renderKb()

    await rebuildButton(wrapper).trigger('click')
    expect(countOf('rebuildKnowledge'), '点一次没发出重建请求').toBe(1)
    expect(rebuildButton(wrapper).element.disabled, '重建请求还在途，按钮却还能再点一次').toBe(true)

    await settle(lastOf('rebuildKnowledge'), {})
    await settle(lastOf('listKnowledge'), { items: [doc(1, '甲文档')], total: 1 })
    expect(countOf('rebuildKnowledge')).toBe(1)

    await rebuildButton(wrapper).trigger('click')
    expect(countOf('rebuildKnowledge'), '重建完成后按钮应恢复可点').toBe(2)
    wrapper.unmount()
  })
})

describe('对照组：单次触发必须照常生效', () => {
  it('只看一份文档时它的切片照常显示', async () => {
    const wrapper = await renderKb()
    wrapper.vm.openDetail(doc(1, '甲文档'))
    await flushPromises()
    await settle(lastOf('getKnowledgeChunks'), chunksFor('甲文档'))

    expect(chunkTexts()).toEqual(['正文来自甲文档'])
    wrapper.unmount()
  })

  it('单独重处理一份文档结束后按钮必须解锁', async () => {
    const wrapper = await renderKb()
    wrapper.vm.onReprocess(doc(1, '甲文档'))
    await flushPromises()
    await settle(lastOf('reprocessKnowledgeDoc'), {})
    await settle(lastOf('listKnowledge'), { items: [], total: 0 })

    expect(wrapper.vm.reprocessingId).toBe(null)
    wrapper.unmount()
  })

  it('重建完成后列表照常刷新', async () => {
    const wrapper = await renderKb()
    await rebuildButton(wrapper).trigger('click')
    await settle(lastOf('rebuildKnowledge'), {})
    const reload = lastOf('listKnowledge')
    await settle(reload, { items: [doc(7, '重建后的文档')], total: 1 })

    expect(reload).toBeTruthy()
    expect(wrapper.vm.list.map((d) => d.title)).toEqual(['重建后的文档'])
    wrapper.unmount()
  })
})
