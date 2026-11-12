import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElDropdown } from 'element-plus'

import PipelineKanban from '@/features/pipeline/views/PipelineKanban.vue'
import { installElement } from '@/plugins/element'
import { movePipelineStage, deleteJobPipelineEntry, getKanban } from '@/api/targets'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'

/* D58 把看板视图与列表视图各自的命令分发合成一套实现。合并前漂了一处文案
   （同一动作在两个视图里分别提示带"为"的那句与少一个"为"的那句）——D58 **没有替谁统一**，
   措辞是候选人可见的，留给一句决定；§10.21 现在拍了这一句（D92），两个视图共用一份标签，
   于是这个文件钉的是：两条路径发出**同样的请求**、同样的重取、同样的"失败就什么都不做"，
   而提示**逐字相同**。
   注意列表模式下看板列**也还在 DOM 里**（`v-else` 只挡 loading/失败，不挡 viewMode），
   所以每一发命令都要按容器取那一个下拉，否则测的是错的那个视图。 */

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

const CARD = {
  id: 41,
  title: '平台后端',
  company: '示例科技',
  stage: 'applied',
  status: 'active',
  jd_id: 123,
  feedback_type: '面试反馈',
  feedback_score: 4,
  feedback_note: '二面被系统设计问住',
  update_time: '2026-05-01T00:00:00Z',
}

const boardOf = (...cards) => ({ stages: { applied: cards, interview: [], todo: [] } })

async function renderKanban(view = 'kanban', card = { ...CARD }) {
  api.getKanban.mockResolvedValue(boardOf(card))
  api.getPipelineResumeVersions.mockResolvedValue({ items: [] })
  api.getPipelineResumeVersionStats.mockResolvedValue({ items: [] })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/pipeline', name: 'pipeline', component: { template: '<div />' } }],
  })
  const push = vi.spyOn(router, 'push')
  router.push('/pipeline')
  await router.isReady()
  push.mockClear()
  const wrapper = mount(PipelineKanban, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  if (view === 'list') {
    const toggle = wrapper.findAll('button').find((b) => b.text().trim() === '列表')
    await toggle.trigger('click')
    await flushPromises()
  }
  return { wrapper, push }
}

async function fire(view, command) {
  const { wrapper } = view
  const root = wrapper.find(view.name === 'list' ? '.list-view' : '.kanban-board')
  expect(root.exists(), `${view.name} 视图没渲染出来，测试前提不成立`).toBe(true)
  await root.findComponent(ElDropdown).vm.$emit('command', command)
  await flushPromises()
}

function kanbanView(v) {
  return { ...v, name: 'kanban' }
}
function listView(v) {
  return { ...v, name: 'list' }
}

describe('两个视图走的是同一套命令实现', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    api.getKanban.mockResolvedValue(boardOf({ ...CARD }))
    ElMessageBox.confirm.mockResolvedValue('confirm')
  })

  it('标记拒绝：请求与重取相同，两个视图的提示现在逐字一致', async () => {
    api.movePipelineStage.mockResolvedValue({ ok: true })
    const kanban = kanbanView(await renderKanban('kanban'))
    await fire(kanban, 'reject')
    expect(movePipelineStage).toHaveBeenLastCalledWith(41, 'rejected')
    expect(ElMessage.success).toHaveBeenLastCalledWith('已标记为拒绝')
    // 初始一次 + 重取一次
    const afterFirstMount = getKanban.mock.calls.length
    expect(afterFirstMount).toBe(2)

    const list = listView(await renderKanban('list'))
    await fire(list, 'reject')
    expect(movePipelineStage).toHaveBeenLastCalledWith(41, 'rejected')
    // §10.21 拍定的那一句（仓里已有的「已标记为 + 动作」那一式，见 ResumeCompare.vue:565）
    expect(ElMessage.success).toHaveBeenLastCalledWith('已标记为拒绝')
    // 列表视图这一趟同样是"挂载一次 + 移动成功后重取一次"
    expect(getKanban.mock.calls.length).toBe(afterFirstMount + 2)
  })

  it('放弃：两个视图都移到 withdrawn 并提示"已放弃"', async () => {
    api.movePipelineStage.mockResolvedValue({ ok: true })
    for (const make of [kanbanView, listView]) {
      vi.clearAllMocks()
      api.getKanban.mockResolvedValue(boardOf({ ...CARD }))
      const view = make(await renderKanban(make === listView ? 'list' : 'kanban'))
      await fire(view, 'abandon')
      expect(movePipelineStage, view.name).toHaveBeenLastCalledWith(41, 'withdrawn')
      expect(ElMessage.success, view.name).toHaveBeenLastCalledWith('已放弃')
    }
  })

  it('移动失败：不弹成功、也不重取（两边共用同一份实现）', async () => {
    api.movePipelineStage.mockRejectedValue(new Error('500'))
    for (const make of [kanbanView, listView]) {
      vi.clearAllMocks()
      api.getKanban.mockResolvedValue(boardOf({ ...CARD }))
      const view = make(await renderKanban(make === listView ? 'list' : 'kanban'))
      const before = getKanban.mock.calls.length
      await fire(view, 'reject')
      expect(ElMessage.success, view.name).not.toHaveBeenCalled()
      expect(getKanban.mock.calls.length, view.name).toBe(before) // 失败不重取
    }
  })

  it('删除要先确认；取消确认就一个删除请求都不发', async () => {
    deleteJobPipelineEntry.mockResolvedValue({ ok: true })
    await fire(kanbanView(await renderKanban()), 'delete')
    expect(ElMessageBox.confirm).toHaveBeenCalledWith('确定删除此投递记录？', '删除确认', {
      type: 'warning',
    })
    expect(deleteJobPipelineEntry).toHaveBeenCalledWith(41)
    expect(ElMessage.success).toHaveBeenCalledWith('已删除')

    vi.clearAllMocks()
    ElMessageBox.confirm.mockRejectedValueOnce(new Error('cancel'))
    await fire(kanbanView(await renderKanban()), 'delete')
    expect(deleteJobPipelineEntry).not.toHaveBeenCalled()
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('跳转带的是这张卡的 jd_id，没有就留空', async () => {
    const { wrapper, push } = await renderKanban()
    const view = kanbanView({ wrapper, push })
    await fire(view, 'analyze')
    expect(push).toHaveBeenLastCalledWith('/smart-analysis?jd_id=123')
    await fire(view, 'interview')
    expect(push).toHaveBeenLastCalledWith('/interview/setup?jd_id=123')

    const bare = kanbanView(await renderKanban('kanban', { ...CARD, id: 42, jd_id: null }))
    await fire(bare, 'analyze')
    expect(bare.push).toHaveBeenLastCalledWith('/smart-analysis?jd_id=')
  })

  it('查看详情会带出这张卡已有的反馈', async () => {
    await fire(kanbanView(await renderKanban()), 'detail')
    const dialog = document.querySelector('.el-dialog')
    expect(dialog).toBeTruthy()
    expect(dialog.textContent).toContain('平台后端')
    // 反馈正文在 textarea 的 value 里，不在 textContent 里
    expect(dialog.querySelector('textarea')?.value).toBe('二面被系统设计问住')
  })
})

/* D4 补的菜单推进（`move:<stage>`）**不是第二条写路径**：从下拉发出后仍然落到 `moveCard`，
   也就是拖拽那一发。这条用例钉的正是"同一发"——同样的请求、同样的乐观更新（不重取）、
   同样的提示措辞。如果哪天有人给菜单另抄一份实现，这三样里至少有两样会当场漂开。 */
describe('菜单推进与拖拽是同一发（D4）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    api.getKanban.mockResolvedValue(boardOf({ ...CARD }))
  })

  it('移到「面试」：一次请求、卡片当场落到面试列、提示与拖拽逐字相同', async () => {
    api.movePipelineStage.mockResolvedValue({ ok: true })
    const view = kanbanView(await renderKanban())
    const before = getKanban.mock.calls.length // 挂载那一次
    await fire(view, 'move:interview')

    expect(movePipelineStage).toHaveBeenLastCalledWith(41, 'interview')
    // 拖拽那条路成功后提示 `已移至「X」`，菜单这条必须一字不差
    expect(ElMessage.success).toHaveBeenLastCalledWith('已移至「面试」')
    // 乐观更新：卡片自己搬过去，不等重取
    expect(getKanban.mock.calls.length, '菜单推进不该重取').toBe(before)
    const col = [...document.querySelectorAll('.kanban-col')].find((el) =>
      el.querySelector('h3')?.textContent.includes('面试')
    )
    expect(col.querySelectorAll('.kanban-card')).toHaveLength(1)
    const appliedCol = [...document.querySelectorAll('.kanban-col')].find((el) =>
      el.querySelector('h3')?.textContent.includes('已投递')
    )
    expect(appliedCol.querySelectorAll('.kanban-card')).toHaveLength(0)
  })

  it('同一阶段发不起来（拖回原列也不发），所以菜单里也就不列它', async () => {
    api.movePipelineStage.mockResolvedValue({ ok: true })
    const view = kanbanView(await renderKanban())
    await fire(view, 'move:applied')
    expect(movePipelineStage).not.toHaveBeenCalled()
    expect(getKanban.mock.calls.length).toBe(1)
  })

  /* 状态机那一半：后端 `VALID_TRANSITIONS` 不认的流转，前端**一发都不发**。
     为什么要拦在前端：后端那句原文是 `不允许从 'applied' 流转到 'todo'，允许的目标: …`
     再挂一串 request id——那是给开发看的话，不是给候选人看的。D4 在真浏览器里就是这么撞上的
     （拖拽能拖到任何一列，菜单当时也把七种目标全列了出来）。 */
  it('后端不允许的流转：不发请求、不乐观更新，说的是中文阶段名', async () => {
    api.movePipelineStage.mockResolvedValue({ ok: true })
    const view = kanbanView(await renderKanban())
    await fire(view, 'move:todo') // CARD.stage 是 applied，applied → todo 是被拒的回头路
    expect(movePipelineStage).not.toHaveBeenCalled()
    expect(getKanban.mock.calls.length).toBe(1)
    expect(ElMessage.warning).toHaveBeenLastCalledWith('不能从「已投递」直接到「待投递」')
    // 卡片没动：还在已投递那列
    const col = [...document.querySelectorAll('.kanban-col')].find((el) =>
      el.querySelector('h3')?.textContent.includes('已投递')
    )
    expect(col.querySelectorAll('.kanban-card')).toHaveLength(1)
  })

  it('终态卡片的「标记拒绝」被同一张表挡住（列表视图那行是无条件画的）', async () => {
    api.movePipelineStage.mockResolvedValue({ ok: true })
    const view = kanbanView(await renderKanban('kanban', { ...CARD, stage: 'rejected' }))
    await fire(view, 'reject')
    expect(movePipelineStage).not.toHaveBeenCalled()
    expect(ElMessage.warning).toHaveBeenLastCalledWith('「已拒绝」已经结束，不能再改阶段')
  })
})
