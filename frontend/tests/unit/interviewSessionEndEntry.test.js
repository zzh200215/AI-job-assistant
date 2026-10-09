import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import Interview from '@/features/interview/views/Interview.vue'
import { installElement } from '@/plugins/element'

/* P4 / D172：没答完的面试以前只有一扇门——点进去接着答。而收口那两条路（WS 的 `end` 消息、
   每问 30 秒计时器）都只在连接活着时存在，标签页一关就永远停在"进行中"：开发库现量 14 场里
   4 场是非终态僵尸（2 场只推过第一题、4 个月没动；2 场从未开始）。这一屏钉的是新加的那条
   不需要 WebSocket 的收口，顺带钉三档状态标签——旧代码只有"已完成 / 进行中"两档，
   于是 `created`（从没推过题）也显示成"进行中"。

   写法上有一条是被变异逼出来的：第一版断言"整行文本含未开始"，而夹具的岗位名恰好叫
   "从未开始的岗位"——把 `sessionStatusLabel` 改坏也照样绿。所以现在**只读那条副标题节点**，
   且夹具名一律中性。 */

const api = vi.hoisted(() => ({
  interview: { getInterviewList: vi.fn(), getQuestionBank: vi.fn(), endInterviewSession: vi.fn() },
  analysis: { getAnalysis: vi.fn() },
  jobs: { getJobPipelineList: vi.fn() },
}))

vi.mock('@/api/interview', () => api.interview)
vi.mock('@/api/analysis', () => api.analysis)
vi.mock('@/api/jobs', () => api.jobs)

const row = (id, status, title) => ({
  id,
  status,
  jd_title: title,
  created_at: '2026-06-07T03:22:45',
  overall_score: status === 'completed' ? 82 : 0,
})

async function render(sessions) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/interview', name: 'interview', component: { template: '<div />' } }],
  })
  router.push('/interview')
  await router.isReady()
  api.interview.getInterviewList.mockReset()
  api.interview.getInterviewList.mockResolvedValue({ items: sessions })
  api.interview.getQuestionBank.mockResolvedValue({ items: [] })
  api.analysis.getAnalysis.mockResolvedValue({})
  api.jobs.getJobPipelineList.mockResolvedValue({ items: [] })
  const wrapper = mount(Interview, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

/** 每行 `时间 · 状态` 那条副标题，只取 `·` 之后的状态部分。整行文本会被岗位名污染。 */
function subtitles() {
  return [...document.querySelectorAll('.interview-info span')].map((el) => {
    const text = el.textContent.replace(/\s+/g, ' ').trim()
    return text.slice(text.indexOf('·') + 1).trim()
  })
}
const endButtons = () =>
  [...document.querySelectorAll('.interview-row button')].filter((b) =>
    b.textContent.includes('结束面试')
  )

describe('面试列表上那条不需要 WebSocket 的收口', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    api.interview.endInterviewSession.mockReset()
  })

  it('三档状态标签各就各位，且只有进行中的行给「结束面试」', async () => {
    const wrapper = await render([
      row(1, 'ongoing', '岗位甲'),
      row(2, 'created', '岗位乙'),
      row(3, 'completed', '岗位丙'),
    ])

    expect(wrapper.findAll('.interview-row')).toHaveLength(3)
    expect(subtitles()).toEqual(['进行中', '未开始', '已完成'])
    expect(endButtons()).toHaveLength(1)
  })

  it('点一下只发那一行的 id，成功后重拉列表，行就落到已完成', async () => {
    await render([row(1, 'ongoing', '岗位甲')])
    api.interview.getInterviewList.mockResolvedValue({ items: [row(1, 'completed', '岗位甲')] })
    api.interview.endInterviewSession.mockResolvedValue({ status: 'completed' })

    await endButtons()[0].click()
    await flushPromises()
    await flushPromises()

    expect(api.interview.endInterviewSession.mock.calls).toEqual([[1]])
    expect(api.interview.getInterviewList).toHaveBeenCalledTimes(2)
    expect(subtitles()).toEqual(['已完成'])
    expect(endButtons()).toHaveLength(0)
  })

  it('后端拒绝时不重拉列表，也不把行说成已结束', async () => {
    await render([row(9, 'ongoing', '岗位甲')])
    api.interview.endInterviewSession.mockRejectedValue(
      new Error('Request failed with status code 400')
    )

    await endButtons()[0].click()
    await flushPromises()
    await flushPromises()

    expect(api.interview.getInterviewList).toHaveBeenCalledTimes(1)
    expect(subtitles()).toEqual(['进行中'])
  })
})
