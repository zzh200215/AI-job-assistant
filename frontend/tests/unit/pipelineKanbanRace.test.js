import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import PipelineKanban from '@/views/PipelineKanban.vue'
import { installElement } from '@/plugins/element'

/* 投递看板这一页的「刷新」按钮（`:28`）没有 loading 也没有 disabled，而 loadKanban 在
   `await Promise.all(...)` 之后直接写 kanban / versionPerformance：
   - 连点两次刷新，早发起的那一份晚到就把新快照换回去；
   - 更要紧的是拖动：刷新在途时把卡片从「待投递」拖到「面试」，移动请求已经成功、乐观更新也做了，
     随后落地的那份**拖动之前**发起的快照会把卡片放回原列——令牌管不到这个，得让 onDrop 也领一发。
   证否的那条：加载失败时那个「重新加载」按钮（`:169`）在途期间点不出第二次，因为它整块在
   `v-else-if="loadError"` 里，而 `loading` 分支在它前面；这条由下面的对照组直接断言 DOM 里没有它。 */

const api = vi.hoisted(() => ({
  getKanban: vi.fn(),
  movePipelineStage: vi.fn(),
  createJobPipelineEntry: vi.fn(),
  deleteJobPipelineEntry: vi.fn(),
  getPipelineResumeVersions: vi.fn(),
  getPipelineResumeVersionStats: vi.fn(),
  updateJobPipelineEntry: vi.fn(),
}))

vi.mock('@/api/targets', () => api)
vi.mock('@/plugins/element-services', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve('confirm')) },
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

const card = (id, stage) => ({
  id,
  title: `投递-${id}`,
  company: '某公司',
  stage,
  status: 'active',
  jd_id: null,
  create_time: '2026-09-01T00:00:00Z',
})

const board = (stages) => ({ stages: { todo: [], applied: [], interview: [], ...stages } })

let router

async function renderKanban(initial = board({ todo: [card(1, 'todo')] })) {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/pipeline', name: 'pipeline', component: { template: '<div />' } }],
  })
  router.push('/pipeline')
  await router.isReady()
  const wrapper = mount(PipelineKanban, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await settle(lastOf('getKanban'), initial)
  await settle(lastOf('getPipelineResumeVersionStats'), { items: [] })
  await flushPromises()
  return wrapper
}

function refreshButton(wrapper) {
  const found = wrapper.findAll('button').find((b) => b.text().includes('刷新'))
  expect(found, '「刷新」按钮没渲染出来，测试前提不成立').toBeTruthy()
  return found
}

function columnByLabel(label) {
  const col = [...document.querySelectorAll('.kanban-col')].find(
    (n) => n.querySelector('.col-header h3')?.textContent.trim() === label
  )
  expect(col, `列「${label}」没渲染出来，测试前提不成立`).toBeTruthy()
  return col
}

function titlesIn(label) {
  return [...columnByLabel(label).querySelectorAll('.card-title')].map((n) => n.textContent.trim())
}

/** loadKanban 一发 = 两个请求同时飞（Promise.all），所以一轮必须落地两条，
   否则它一直卡在 spinner 分支里，测试会误判成"列没渲染出来"。 */
async function settleRound(index, stages) {
  await settle(nthOf('getKanban', index), board(stages))
  await settle(nthOf('getPipelineResumeVersionStats', index), { items: [] })
}

/** jsdom 没有 DataTransfer：dragstart 用最小事件对象走组件自己的入口，drop 打在真实列元素上 */
function dragCardTo(wrapper, cardObj, label) {
  wrapper.vm.onDragStart({ dataTransfer: { effectAllowed: '' } }, cardObj)
  return columnByLabel(label).dispatchEvent(new Event('drop', { bubbles: true }))
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  for (const key of Object.keys(inflight)) delete inflight[key]

  api.getPipelineResumeVersions.mockResolvedValue({ items: [] })
  api.createJobPipelineEntry.mockResolvedValue({})
  api.deleteJobPipelineEntry.mockResolvedValue({})
  api.updateJobPipelineEntry.mockResolvedValue({})
  hang('getKanban')
  hang('getPipelineResumeVersionStats')
  hang('movePipelineStage')
})

describe('投递看板：晚到的旧快照不能把屏幕换回旧状态', () => {
  it('连点两次刷新，早发起的那一份不能盖掉新快照', async () => {
    const wrapper = await renderKanban()
    expect(titlesIn('待投递')).toEqual(['投递-1'])

    await refreshButton(wrapper).trigger('click')
    await refreshButton(wrapper).trigger('click')
    expect(countOf('getKanban'), '刷新按钮今天可以叠出发三次请求').toBe(3)

    await settleRound(2, { interview: [card(1, 'interview')] })
    expect(titlesIn('面试')).toEqual(['投递-1'])

    await settleRound(1, { todo: [card(1, 'todo')] })
    expect(titlesIn('待投递'), '旧快照把卡片放回了待投递').toEqual([])
    expect(titlesIn('面试')).toEqual(['投递-1'])
    wrapper.unmount()
  })

  // 本来还写了第三条"刷新在途时拖卡片，旧快照把卡片放回原列"，跑出来发现这条前提不成立：
  // 重取在途时整块看板被 `v-if="loading"` 的 spinner 取代（`:161`），卡片根本不在屏幕上，
  // 拖不动也就交不上。那是 D27 量的 spinner 分支顺带挡住的，不是设计出来的保护，
  // 所以留一条断言它的对照组（下面第三条），不给一条跑不通的路径加守卫。
})

describe('对照组：这些修法不能把正常路径也废掉', () => {
  it('单次刷新照常把新数据放上屏幕', async () => {
    const wrapper = await renderKanban()
    await refreshButton(wrapper).trigger('click')
    await settleRound(1, { applied: [card(9, 'applied')] })

    expect(titlesIn('已投递')).toEqual(['投递-9'])
    wrapper.unmount()
  })

  it('没有并发刷新时，拖动后的乐观更新照常生效', async () => {
    const wrapper = await renderKanban()
    dragCardTo(wrapper, wrapper.vm.kanban.todo[0], '面试')
    await flushPromises()
    await settle(lastOf('movePipelineStage'), {})

    expect(titlesIn('面试')).toEqual(['投递-1'])
    expect(titlesIn('待投递')).toEqual([])
    wrapper.unmount()
  })

  it('重取在途时看板整块被 spinner 取代——上面那条撤掉的用例靠的就是它', async () => {
    const wrapper = await renderKanban()
    await refreshButton(wrapper).trigger('click')

    expect(document.querySelector('.loading-state'), 'spinner 分支不在，前提不成立').toBeTruthy()
    expect(document.querySelectorAll('.kanban-card').length, '在途期间卡片还挂在屏幕上').toBe(0)

    await settleRound(1, { interview: [card(1, 'interview')] })
    expect(document.querySelectorAll('.kanban-card').length).toBe(1)
    wrapper.unmount()
  })

  it('加载失败时按钮能重试，而在途期间那个重试按钮根本不在屏幕上', async () => {
    const wrapper = await renderKanban()
    const err = new Error('boom')
    err.userMessage = '暂时无法获取投递记录'
    await refreshButton(wrapper).trigger('click')
    nthOf('getKanban', 1).reject(err)
    await flushPromises()

    const retry = wrapper.findAll('button').find((b) => b.text().includes('重新加载'))
    expect(retry, '失败块没出来，测试前提不成立').toBeTruthy()

    await retry.trigger('click')
    expect(
      wrapper.findAll('button').some((b) => b.text().includes('重新加载')),
      '重试在途时失败块还挂着，那它就能被连点'
    ).toBe(false)

    await settle(lastOf('getKanban'), board({ todo: [card(1, 'todo')] }))
    await settle(lastOf('getPipelineResumeVersionStats'), { items: [] })
    expect(titlesIn('待投递')).toEqual(['投递-1'])
    wrapper.unmount()
  })
})
