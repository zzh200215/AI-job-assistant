import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeUpload from '@/features/resume/views/ResumeUpload.vue'
import { installElement } from '@/plugins/element'

/* D200 把改写建议改成"建作业 + 轮询"之后，视图层有一跳谁都没测过：作业还在跑的时候屏幕上
   到底是什么。`resumeRewriteUndo` 那批让第一次轮询就直接返回终态（它要钉的是应用→撤销），
   `rewriteSuggestionJobFlow` 钉的是源码形状。这里补的是中间那段：
   ① pending/running 期间 spinner 必须一直亮、卡片一条都不许提前出现；
   ② 作业失败时屏幕上只许出现我们自己的那句措辞——**载荷里若带着服务端写的失败原因，
      那句可能含模型返回的候选人原文，不许流到屏幕上**（同 `llm_service.py:1097` 的理由）；
   ③ 组件卸载后不许继续打接口；④ 在途时重复点击不许建第二个作业。 */

const api = vi.hoisted(() => ({
  uploadResume: vi.fn(),
  parseResume: vi.fn(),
  getResumeList: vi.fn(),
  getResumeVersions: vi.fn(),
  getResumeQuickScore: vi.fn(),
  diagnoseResume: vi.fn(),
  createRewriteSuggestionJob: vi.fn(),
  getRewriteSuggestionJob: vi.fn(),
  applyResumeRewrites: vi.fn(),
  revertResumeRewrite: vi.fn(),
  deleteResume: vi.fn(),
  generateOptimized: vi.fn(),
  exportResume: vi.fn(),
  downloadResumeExport: vi.fn(),
}))

vi.mock('@/api/resume', () => api)

const row = (id, name) => ({
  id,
  file_name: name,
  name,
  status: 'ready',
  create_time: '2026-09-01T00:00:00Z',
  parsed: { current_title: '后端工程师' },
})

const DIAGNOSIS = {
  total_score: 70,
  structure_score: 70,
  expression_score: 70,
  keyword_score: 70,
  highlight_score: 70,
  ats_score: 70,
  completeness_score: 70,
  structure_issues: [],
  expression_issues: [],
  missing_keywords: [],
  highlights: [],
  match_analysis: '',
}

const SUGGESTION = {
  block_id: 'self_evaluation',
  kind: 'self_evaluation',
  label: '自我评价',
  original: '三年后端开发经验',
  proposed_text: '三年后端开发经验，专注订单链路',
  reason: '把已有事实写清楚',
}

const LEAK_SENTINEL = 'MODEL_RAW_TEXT_should_never_reach_the_screen'

async function mountWithDiagnosis() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/resume/upload', name: 'resume-upload', component: { template: '<div />' } }],
  })
  router.push('/resume/upload')
  await router.isReady()
  const wrapper = mount(ResumeUpload, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  wrapper.vm.showDiagnosisDialog(row(1, '简历甲'))
  await flushPromises()
  wrapper.vm.currentDiagnosis = { ...DIAGNOSIS, resume_id: 1, jd_id: null }
  await flushPromises()
  return wrapper
}

/** 让 `generateRewrites()` 跑起来，并把挂起的 promise 交回给调用方。 */
function start(wrapper) {
  return wrapper.vm.generateRewrites()
}

async function tick(ms) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

beforeEach(() => {
  // 这些 spy 是 hoisted 的，跨用例不清计数就会把上一发的调用算进这一发（第一次跑就是这么
  // 把"只建一个作业"读成"建了 4 个"的）。
  for (const fn of Object.values(api)) fn.mockClear()
  api.getResumeList.mockResolvedValue({ items: [row(1, '简历甲')], total: 1 })
  api.getResumeVersions.mockResolvedValue([])
  api.createRewriteSuggestionJob.mockResolvedValue({ job_id: 77, status: 'pending' })
})

describe('改写建议作业在视图层的那一跳', () => {
  it('running 期间 spinner 一直亮、卡片一条都不提前出现，completed 才换状态', async () => {
    vi.useFakeTimers()
    api.getRewriteSuggestionJob
      .mockResolvedValueOnce({ job_id: 77, status: 'running', suggestions: [], rejected: [] })
      .mockResolvedValueOnce({ job_id: 77, status: 'running', suggestions: [], rejected: [] })
      .mockResolvedValueOnce({
        job_id: 77,
        status: 'completed',
        suggestions: [SUGGESTION],
        rejected: [],
        note: null,
      })

    const wrapper = await mountWithDiagnosis()
    const done = start(wrapper)
    await tick(0)
    expect(wrapper.vm.rewrite.loading, '第一发轮询就没在跑，spinner 那一档等于没测').toBe(true)
    expect(wrapper.vm.rewrite.items).toHaveLength(0)

    await tick(2000)
    expect(wrapper.vm.rewrite.loading).toBe(true)
    expect(wrapper.vm.rewrite.items).toHaveLength(0)

    await tick(2000)
    await done
    expect(wrapper.vm.rewrite.loading, '到了终态 spinner 还转着，候选人会以为还在等').toBe(false)
    expect(wrapper.vm.rewrite.items).toHaveLength(1)
    expect(api.getRewriteSuggestionJob).toHaveBeenCalledTimes(3)
    vi.useRealTimers()
  })

  it('作业失败时屏幕上只许出现我们自己的措辞，服务端那句一个字都不许流上来', async () => {
    vi.useFakeTimers()
    // 生产端点确实不给这个键（D200 的载荷形状 + 它的守卫钉着）；这条防的是**下一次有人改那个
    // 形状时**顺带把模型原文推到候选人脸上——共享轮询器读的是 `taskData.error_msg`。
    api.getRewriteSuggestionJob.mockResolvedValue({
      job_id: 77,
      status: 'failed',
      suggestions: [],
      rejected: [],
      error_msg: LEAK_SENTINEL,
    })

    const wrapper = await mountWithDiagnosis()
    const done = start(wrapper)
    await tick(0)
    await expect(done).resolves.toBeUndefined()

    expect(wrapper.vm.rewrite.loading).toBe(false)
    expect(wrapper.vm.rewrite.error).toBeTruthy()
    expect(wrapper.text()).not.toContain(LEAK_SENTINEL)
    expect(String(wrapper.vm.rewrite.error)).not.toContain(LEAK_SENTINEL)
    vi.useRealTimers()
  })

  it('组件卸载后不再打轮询接口', async () => {
    vi.useFakeTimers()
    api.getRewriteSuggestionJob.mockResolvedValue({
      job_id: 77,
      status: 'running',
      suggestions: [],
      rejected: [],
    })

    const wrapper = await mountWithDiagnosis()
    start(wrapper)
    await tick(0)
    const callsWhileMounted = api.getRewriteSuggestionJob.mock.calls.length
    expect(callsWhileMounted).toBeGreaterThan(0)

    wrapper.unmount()
    await tick(20000)
    expect(
      api.getRewriteSuggestionJob.mock.calls.length,
      '卸载之后还在继续打接口：那条轮询器没被停掉'
    ).toBe(callsWhileMounted)
    /* 顺带量到的一件小事，写在这而不是藏起来：`stopPolling()` 既不 resolve 也不 reject，所以
       `generateRewrites()` 里那个 `await` 永不落地、`finally` 里的 `rewrite.loading = false`
       也不会跑。组件已经不在了 ⇒ 候选人看不到任何后果，但它是一个悬着的 promise；要治得改共享
       轮询器的停止语义（别的调用方在用），不在这一条里顺手做。 */
    vi.useRealTimers()
  })

  it('在途时再点一次不建第二个作业——一把锁，同一次改写不重付模型钱', async () => {
    vi.useFakeTimers()
    api.getRewriteSuggestionJob.mockResolvedValue({
      job_id: 77,
      status: 'running',
      suggestions: [],
      rejected: [],
    })

    const wrapper = await mountWithDiagnosis()
    // 故意不接、也不 await 这一发：它挂在轮询上，只有跑到终态才落地（见上一条里那件小事）。
    start(wrapper)
    await tick(0)
    const second = await start(wrapper)
    await tick(4000)
    expect(second, '第二次点击另建了一个作业').toBeUndefined()
    expect(api.createRewriteSuggestionJob).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    vi.useRealTimers()
  })
})
