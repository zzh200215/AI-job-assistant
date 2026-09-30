import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElDropdown, ElTable } from 'element-plus'

import PipelineKanban from '@/features/pipeline/views/PipelineKanban.vue'
import { installElement } from '@/plugins/element'
import { updateJobPipelineEntry } from '@/api/targets'
import { ElMessage } from '@/plugins/element-services'

/* D59 钉这页的**写路径**：批量移动、看板拖拽、卡片下拉的标记/删除，加上详情弹窗里的反馈保存。
   修掉三件事：
   ① 三个批量按钮此前**没有任何 in-flight 守卫**（新增与反馈那两个按钮都有 `:loading`），
      于是可以连点、也可以点了「面试」再点「拒绝」：两个循环交叉发请求，卡片最终落在哪一列
      取决于返回顺序，而屏幕上那句"成功将 N 项移至「面试」"讲的是其中一趟的局部结果；
   ② 拖拽和卡片下拉的写会撞进同一趟批量。看板列在列表模式下也在 DOM 里（`v-else` 只挡
      loading/失败），探针实测：卡片 1 的批量请求还没回，拖它发出第二条 [1, 'withdrawn']，
      走下拉「标记拒绝」发出 [1, 'rejected']——两趟都写同一个 id，落点取决于谁先返回；
   ③ `saveFeedback` 只有 `finally` 没有 `catch`，保存失败的 reject 会一路冒出 `@click`
      变成未处理的 Promise 拒绝——控制台报错、界面上什么都没说。
   判据：**这一页对投递记录的写，一次只跑一趟**。守卫按各条路自己的形状给——批量按钮与两个
   下拉吃 `:disabled`（拖拽没有按钮可禁，只能函数内提前返回，见那条变异）。 */

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

const CARDS = [
  { id: 1, title: '岗位一', company: 'A', stage: 'applied', jd_id: 11 },
  { id: 2, title: '岗位二', company: 'B', stage: 'applied', jd_id: 12 },
]

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

async function renderList(cards = CARDS) {
  api.getKanban.mockResolvedValue({ stages: { applied: cards.map((c) => ({ ...c })) } })
  api.getPipelineResumeVersions.mockResolvedValue({ items: [] })
  api.getPipelineResumeVersionStats.mockResolvedValue({ items: [] })
  const router = createRouter({
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
  await wrapper
    .findAll('button')
    .find((b) => b.text().trim() === '列表')
    .trigger('click')
  await flushPromises()
  return wrapper
}

async function selectRows(wrapper, cards) {
  // jsdom 里 el-table 不渲染行，所以勾选只能直接发它自己的 selection-change 事件
  wrapper.findComponent(ElTable).vm.$emit('selection-change', cards)
  await flushPromises()
}

function batchButtons() {
  return [...document.querySelectorAll('.batch-bar button')].filter((b) =>
    b.textContent.includes('批量移至')
  )
}

function clickByText(text) {
  const button = [...document.querySelectorAll('button')].find((b) => b.textContent.includes(text))
  expect(button, `屏幕上没有「${text}」按钮`).toBeTruthy()
  button.click()
}

async function dragBoardCard(wrapper) {
  // 拖拽在 jsdom 里能跑：dragstart 只要 dataTransfer 是个对象，drop 打在列上
  await wrapper.find('.kanban-card').trigger('dragstart', { dataTransfer: {} })
  const cols = wrapper.findAll('.kanban-col')
  await cols[cols.length - 1].trigger('drop', { dataTransfer: {} })
  await flushPromises()
}

function batchBarButtons() {
  // 三个都是写操作：批量移至面试 / 批量移至Offer / 批量标记拒绝（最后一句没有「移至」）
  const buttons = [...document.querySelectorAll('.batch-bar button')].filter((b) =>
    b.textContent.includes('批量')
  )
  expect(buttons.length).toBe(3)
  return buttons
}

describe('整页的写：一次只跑一趟', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('批量在飞时把卡片拖到别的列，不会发出第二发移动', async () => {
    const gate = deferred()
    api.movePipelineStage.mockReturnValue(gate.promise)
    const wrapper = await renderList()
    await selectRows(wrapper, CARDS)
    batchBarButtons()[0].click()
    await flushPromises()

    await dragBoardCard(wrapper)
    expect(api.movePipelineStage.mock.calls).toEqual([[1, 'interview']])

    gate.resolve({ ok: true })
    await flushPromises()
    expect(api.movePipelineStage.mock.calls).toEqual([
      [1, 'interview'],
      [2, 'interview'],
    ])
  })

  it('拖拽在飞时三个批量按钮既禁用、也发不出请求', async () => {
    const gate = deferred()
    api.movePipelineStage.mockReturnValue(gate.promise)
    const wrapper = await renderList()
    await selectRows(wrapper, CARDS)

    await dragBoardCard(wrapper)
    expect(api.movePipelineStage.mock.calls).toEqual([[1, 'withdrawn']]) // 拖拽那一发自己先发出去

    const buttons = batchBarButtons()
    expect(buttons.map((b) => b.disabled)).toEqual([true, true, true])
    buttons[0].click()
    await flushPromises()
    expect(api.movePipelineStage.mock.calls).toEqual([[1, 'withdrawn']])

    gate.resolve({ ok: true })
    await flushPromises()
  })

  it('卡片下拉的写也举同一个标记：命令在飞时批量按钮禁用', async () => {
    const gate = deferred()
    api.movePipelineStage.mockReturnValue(gate.promise)
    const wrapper = await renderList()
    await selectRows(wrapper, CARDS)

    wrapper.findAllComponents(ElDropdown)[0].vm.$emit('command', 'reject')
    await flushPromises()
    expect(api.movePipelineStage.mock.calls).toEqual([[1, 'rejected']])
    expect(batchBarButtons().map((b) => b.disabled)).toEqual([true, true, true])

    gate.resolve({ ok: true })
    await flushPromises()
    expect(batchBarButtons().map((b) => b.disabled)).toEqual([false, false, false]) // 标记释放了
  })

  it('批量在飞时两个卡片下拉被禁用（看板列与列表行各一个）', async () => {
    const gate = deferred()
    api.movePipelineStage.mockReturnValue(gate.promise)
    const wrapper = await renderList()
    await selectRows(wrapper, CARDS)
    batchBarButtons()[0].click()
    await flushPromises()

    const dropdowns = wrapper.findAllComponents(ElDropdown)
    expect(dropdowns.length).toBeGreaterThan(1) // 看板那张卡 + 列表那一行
    expect(dropdowns.map((d) => d.props('disabled'))).toEqual([true, true, true, true])

    gate.resolve({ ok: true })
    await flushPromises()
  })
})

describe('批量移动：一趟只能有一批在飞', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('两项都成功 → 逐条移动、提示 2/2、清选择并重取', async () => {
    api.movePipelineStage.mockResolvedValue({ ok: true })
    const wrapper = await renderList()
    await selectRows(wrapper, CARDS)

    batchButtons()[0].click()
    await flushPromises()

    expect(api.movePipelineStage.mock.calls).toEqual([
      [1, 'interview'],
      [2, 'interview'],
    ])
    expect(ElMessage.success).toHaveBeenCalledWith('成功将 2/2 项移至「面试」')
    expect(document.querySelector('.batch-bar')).toBeNull() // 选择被清空
    expect(api.getKanban.mock.calls.length).toBe(2) // 初始 + 重取
  })

  it('一条失败就说真话：2 项里成功 1 用 warning，而不是报成功', async () => {
    api.movePipelineStage
      .mockResolvedValueOnce({ ok: true })
      .mockRejectedValueOnce(new Error('500'))
    const wrapper = await renderList()
    await selectRows(wrapper, CARDS)

    batchButtons()[0].click()
    await flushPromises()

    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.warning).toHaveBeenCalledWith('成功将 1/2 项移至「面试」')
    // 失败不中断：两条都试过了
    expect(api.movePipelineStage.mock.calls.length).toBe(2)
  })

  it('第一批还在飞时点第二下不会发出第二趟请求', async () => {
    const gate = deferred()
    api.movePipelineStage.mockReturnValue(gate.promise)
    const wrapper = await renderList()
    await selectRows(wrapper, CARDS)

    const [toInterview, ToOffer] = batchButtons()
    toInterview.click()
    await flushPromises()
    ToOffer.click() // 换个目标也不行：另一趟会把卡片拖到另一个阶段，而 toast 只讲自己那一趟
    await flushPromises()
    expect(api.movePipelineStage.mock.calls).toEqual([[1, 'interview']])

    gate.resolve({ ok: true })
    await flushPromises()
    expect(api.movePipelineStage.mock.calls.length).toBe(2) // 第一条完成后继续同一趟的第二条
    expect(ElMessage.success).toHaveBeenCalledWith('成功将 2/2 项移至「面试」')
  })
})

describe('反馈保存：失败要说出来，而不是冒成未处理拒绝', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  async function openDetail(wrapper) {
    // 列表视图的「详情」是一个按钮（下拉菜单里没有 detail 这一项）
    await wrapper
      .find('.list-view')
      .findAll('button')
      .find((b) => b.text() === '详情')
      .trigger('click')
    await flushPromises()
  }

  it('内容与类型都空时一个请求都不发', async () => {
    const wrapper = await renderList([{ id: 5, title: '空反馈卡', company: 'C', stage: 'applied' }])
    await openDetail(wrapper)
    clickByText('保存反馈')
    await flushPromises()
    expect(updateJobPipelineEntry).not.toHaveBeenCalled()
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('保存失败：不弹成功、不重取，也不留下未处理的拒绝', async () => {
    api.updateJobPipelineEntry.mockRejectedValue(new Error('500'))
    const wrapper = await renderList([
      {
        id: 6,
        title: '有内容的卡',
        company: 'D',
        stage: 'applied',
        feedback_type: '面试反馈',
        feedback_score: 3,
        feedback_note: '系统设计答得浅',
      },
    ])
    await openDetail(wrapper)
    const reloads = api.getKanban.mock.calls.length
    clickByText('保存反馈')
    await flushPromises()
    expect(updateJobPipelineEntry).toHaveBeenCalledWith(6, {
      feedback_type: '面试反馈',
      feedback_score: 3,
      feedback_note: '系统设计答得浅',
    })
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(api.getKanban.mock.calls.length).toBe(reloads)
    // 正文在 textarea 的 value 里，不在 textContent 里（同一件事在 pipelineCardCommands 那条也踩过）
    expect(document.querySelector('.el-dialog textarea')?.value).toBe('系统设计答得浅')
    /* 「没有未处理的拒绝」这一条不是由 expect 兜住的：M2（删掉 saveFeedback 的 catch）时
       六个断言照旧全绿，红的是 vitest 的 unhandled-rejection 闸门（进程 exit=1、整轮失败）。
       仪器是运行器不是断言，写在这里免得下一个人误以为这条用例自己就能看见它。 */
  })

  it('保存成功：提示 + 重取', async () => {
    api.updateJobPipelineEntry.mockResolvedValue({ ok: true })
    const wrapper = await renderList([
      {
        id: 7,
        title: '另一张卡',
        company: 'E',
        stage: 'applied',
        feedback_note: '约二面',
      },
    ])
    await openDetail(wrapper)
    clickByText('保存反馈')
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('反馈已保存')
    expect(api.getKanban.mock.calls.length).toBe(2)
  })
})
