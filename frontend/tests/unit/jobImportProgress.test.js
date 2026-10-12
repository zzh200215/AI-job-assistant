import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobRecommend from '@/features/jobs/views/JobRecommend.vue'
import { installElement } from '@/plugins/element'
import { ElMessage } from '@/plugins/element-services'

/* D226 把批量导入改成"建作业 + 轮询"之后，后端那一侧 12 条用例全绿，但屏幕上到底是什么
   一条都没测。这一文件钉的就是那一跳，六条各自对应一个"改坏了也不会报错"的形状：
   ① running 期间进度必须真的在动（不是一句"导入中"挂到底）；
   ② completed 之后要把推荐重取一次——服务端在作业完成时清了推荐缓存，界面不重取就等于
      "导入了 95 条却一条都不出现在列表里"；
   ③ 载荷里若带上服务端写的失败原因，那句可能含文件原文，不许上屏（同 job_import 模型里
      `to_progress()` 不含 `error_msg` 的理由）；
   ④ 在途时重复选文件不许建第二个作业；
   ⑤ 卸载之后不许继续打接口，也不许弹一句候选人没看到的错（D207 那条口径）；
   ⑥ 「停止」按下去要真的打到取消端点，并把"已入库的不回滚"说出来。 */

const api = vi.hoisted(() => ({
  getJobRecommendations: vi.fn(),
  getJobFeedbackStats: vi.fn(),
  seedMockJobs: vi.fn(),
  batchImportJobs: vi.fn(),
  getJobImportTask: vi.fn(),
  cancelJobImportTask: vi.fn(),
  submitJobFeedback: vi.fn(),
  startFullAnalysis: vi.fn(),
  getJobPipelineList: vi.fn(),
  getJobBookmarks: vi.fn(),
  getSuppressedJobs: vi.fn(),
  restoreSuppressedJob: vi.fn(),
  bookmarkJob: vi.fn(),
  unbookmarkJob: vi.fn(),
}))

vi.mock('@/api/jobs', () => api)
vi.mock('@/api/resume', () => ({
  getResumeList: vi.fn(async () => ({ items: [{ id: 7, name: '我的简历' }], total: 1 })),
}))
vi.mock('@/api/targets', () => ({ createJobPipelineEntry: vi.fn() }))
vi.mock('@/plugins/element-services', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

const LEAK_SENTINEL = 'RAW_FILE_TEXT_should_never_reach_the_screen'

const job = (over = {}) => ({
  job_id: 901,
  file_name: 'jd.csv',
  status: 'pending',
  total: 100,
  done: 0,
  created: 0,
  skipped: 0,
  problems: [],
  create_time: '2026-10-12T00:00:00',
  finished_at: null,
  ...over,
})

let liveWrapper = null

async function renderRecommend() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/jobs/recommend', name: 'job-recommend', component: { template: '<div />' } },
    ],
  })
  router.push('/jobs/recommend?resume_id=7')
  await router.isReady()
  const wrapper = mount(JobRecommend, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  liveWrapper = wrapper
  return wrapper
}

async function tick(ms) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
  await flushPromises()
}

const screen = () => document.body.textContent

function stopButton() {
  return [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '停止')
}

/** el-progress 的完成度是内联在那根内条上的 `width`，不是文本——只查"有没有这一行字"抓不到条没画。 */
function barPercent() {
  const inner = document.querySelector('.el-progress-bar__inner')
  return inner ? Number.parseFloat(inner.style.width) : null
}

beforeEach(() => {
  /* `mockClear()` 只清调用记录，**不清 `mockResolvedValueOnce` 排好的队**（那是 mockReset）。
     第一发用例断言失败就没走到 `tick()`，它队列里那个"completed"于是留给第二发——
     症状是第二发的"导入失败"断言莫名其妙地红，而变异其实只动了进度条。
     卸载也在这里补一刀：断言抛出去的那一发不会跑到自己的 `wrapper.unmount()`。 */
  for (const fn of Object.values(api)) fn.mockReset()
  liveWrapper = null
  api.getJobRecommendations.mockResolvedValue({ total: 0, recommendations: [] })
  api.getJobPipelineList.mockResolvedValue({ items: [] })
  api.getJobBookmarks.mockResolvedValue({ total: 0, items: [] })
  api.getSuppressedJobs.mockResolvedValue({ total: 0, orphaned: 0, items: [] })
  api.getJobFeedbackStats.mockResolvedValue({ total: 0 })
  api.cancelJobImportTask.mockResolvedValue(
    job({ status: 'canceled', done: 40, created: 38, skipped: 2 })
  )
})

afterEach(() => {
  vi.useRealTimers()
  if (liveWrapper) {
    try {
      liveWrapper.unmount()
    } catch {
      // 已经卸载过
    }
  }
  document.body.innerHTML = ''
})

describe('批量导入作业在视图层的那一跳', () => {
  it('running 期间进度在动，completed 之后换成结算并重取推荐', async () => {
    vi.useFakeTimers()
    api.batchImportJobs.mockResolvedValue(job())
    api.getJobImportTask
      .mockResolvedValueOnce(job({ status: 'running', done: 40, created: 38, skipped: 2 }))
      .mockResolvedValueOnce(job({ status: 'completed', done: 100, created: 95, skipped: 5 }))

    const wrapper = await renderRecommend()
    const callsAtMount = api.getJobRecommendations.mock.calls.length
    await wrapper.vm.handleImport({ name: 'jd.csv' })
    await flushPromises()

    expect(screen()).toContain('正在导入：已处理 40/100，入库 38 条，跳过 2 条')
    expect(barPercent(), '进度条没画出来，"进度"就只剩一行会变的字').toBe(40)
    expect(stopButton(), '在途时没有「停止」，这一发就只能等它跑完').toBeTruthy()
    expect(api.getJobRecommendations.mock.calls).toHaveLength(callsAtMount)

    await tick(2000)
    expect(screen()).toContain('导入完成：95 条入库，跳过 5 条')
    expect(barPercent(), '已经终态了还画着一根进度条').toBeNull()
    expect(stopButton()).toBeFalsy()
    expect(api.getJobRecommendations.mock.calls).toHaveLength(callsAtMount + 1)
    wrapper.unmount()
  })

  it('服务端那句失败原因不上屏，屏上只有我们自己的措辞', async () => {
    vi.useFakeTimers()
    api.batchImportJobs.mockResolvedValue(job())
    // 真端点不给 error_msg（to_progress 里没有这个键）；这里偏要喂一发，钉的是视图只按白名单取字段
    api.getJobImportTask.mockResolvedValue(
      job({
        status: 'failed',
        done: 60,
        created: 55,
        skipped: 5,
        error_msg: LEAK_SENTINEL,
        error: 1,
      })
    )

    const wrapper = await renderRecommend()
    await wrapper.vm.handleImport({ name: 'jd.csv' })
    await flushPromises()

    expect(screen()).toContain('导入失败：已处理 60/100，入库 55 条')
    expect(screen()).not.toContain(LEAK_SENTINEL)
    wrapper.unmount()
  })

  it('跳过的那几十行要说清为什么：载荷给前几条，界面把行数与原因一起念出来', async () => {
    vi.useFakeTimers()
    // 原因只可能从轮询里来：POST 那一刻作业刚建，库里 problems 还是空表
    api.batchImportJobs.mockResolvedValue(job())
    api.getJobImportTask.mockResolvedValue(
      job({
        status: 'running',
        done: 50,
        created: 38,
        skipped: 12,
        problems: [{ row: 3, reason: '缺 title 或 JD 文本' }],
      })
    )

    const wrapper = await renderRecommend()
    await wrapper.vm.handleImport({ name: 'jd.csv' })
    await flushPromises()

    expect(screen()).toContain('跳过原因：第 3 行：缺 title 或 JD 文本 等共 12 条')
    wrapper.unmount()
  })

  it('在途时重复选文件不建第二个作业', async () => {
    vi.useFakeTimers()
    api.batchImportJobs.mockResolvedValue(job())
    api.getJobImportTask.mockResolvedValue(job({ status: 'running', done: 10 }))

    const wrapper = await renderRecommend()
    await wrapper.vm.handleImport({ name: 'jd.csv' })
    await flushPromises()
    await wrapper.vm.handleImport({ name: 'jd-again.csv' })
    await flushPromises()

    expect(api.batchImportJobs).toHaveBeenCalledTimes(1)
    expect(api.cancelJobImportTask).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('卸载之后不再打进度接口，也不弹一句候选人没看到的错', async () => {
    vi.useFakeTimers()
    api.batchImportJobs.mockResolvedValue(job())
    api.getJobImportTask.mockResolvedValue(job({ status: 'running', done: 10 }))

    const wrapper = await renderRecommend()
    await wrapper.vm.handleImport({ name: 'jd.csv' })
    await flushPromises()
    const polls = api.getJobImportTask.mock.calls.length

    wrapper.unmount()
    await tick(10000)

    expect(api.getJobImportTask.mock.calls).toHaveLength(polls)
    expect(api.batchImportJobs).toHaveBeenCalledTimes(1)
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('「停止」打到取消端点，并把"已入库的不回滚"说出来', async () => {
    vi.useFakeTimers()
    api.batchImportJobs.mockResolvedValue(job())
    api.getJobImportTask.mockResolvedValue(
      job({ status: 'running', done: 40, created: 38, skipped: 2 })
    )

    const wrapper = await renderRecommend()
    await wrapper.vm.handleImport({ name: 'jd.csv' })
    await flushPromises()

    await stopButton().click()
    await flushPromises()

    expect(api.cancelJobImportTask).toHaveBeenCalledWith(901)
    expect(screen()).toContain('导入已停止：停止前入库 38 条')
    expect(screen()).toContain('已入库的不回滚')
    wrapper.unmount()
  })
})
