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
