import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeUpload from '@/features/resume/views/ResumeUpload.vue'
import { installElement } from '@/plugins/element'

/* B1.3 那天起，每次应用行级改写都会先存一份改写前的 `parsed_json`，返回里带着
   `snapshot_version_id`——然后前端把它**丢掉了**：这个键在 `src` 里 0 个消费者，而唯一列版本的
   `ResumeCompare` 按 `format === 'md'` 过滤，json 快照连屏幕都上不去。于是"快照是为了让撤销成为
   可能"这句话只剩一半：候选人改错了字，界面上没有任何一条路能回去。
   这里钉的是那半条：撤销按钮要出现、要带对 id、要跟着撤销返回的新快照翻转成"撤销这次撤销"，
   并且与应用共用同一把锁。 */

const api = vi.hoisted(() => ({
  uploadResume: vi.fn(),
  parseResume: vi.fn(),
  getResumeList: vi.fn(),
  getResumeVersions: vi.fn(),
  getResumeQuickScore: vi.fn(),
  diagnoseResume: vi.fn(),
  getRewriteSuggestions: vi.fn(),
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

const APPLIED = {
  changed: true,
  applied: [
    {
      block_id: 'self_evaluation',
      kind: 'self_evaluation',
      before: '三年后端开发经验',
      after: '三年后端开发经验，专注订单链路',
    },
  ],
  rejected: [],
  snapshot_version_id: 77,
  resume_version: 'hash-after',
  score: { before: { score: 70 }, after: { score: 80 }, delta: 10 },
}

const REVERTED = {
  changed: true,
  reverted: true,
  restored_blocks: ['self_evaluation'],
  restored_from_version_id: 77,
  undo_version_id: 78,
  resume_version: 'hash-before',
  score: { before: { score: 80 }, after: { score: 70 }, delta: -10 },
  score_note: '',
}

async function renderAndApply(applyPayload = APPLIED) {
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

  api.getRewriteSuggestions.mockResolvedValue({ suggestions: [SUGGESTION], rejected: [] })
  await wrapper.vm.generateRewrites()
  expect(wrapper.vm.rewrite.items).toHaveLength(1)

  api.applyResumeRewrites.mockResolvedValue(applyPayload)
  await wrapper.vm.applyRewrites()
  await flushPromises()
  return wrapper
}

function buttons() {
  return [...document.querySelectorAll('.rw-actions button')]
}

function undoButton() {
  return buttons().find((b) => b.textContent.includes('撤销'))
}

const undoText = () => undoButton()?.textContent.trim() ?? null

describe('改写之后的那一屏要能把刚应用的东西撤回去', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    api.getResumeList.mockResolvedValue({ items: [row(1, '简历甲')], total: 1 })
    api.getResumeVersions.mockResolvedValue({ versions: [] })
    api.getResumeQuickScore.mockResolvedValue({ score: 60 })
    api.diagnoseResume.mockResolvedValue(DIAGNOSIS)
    api.revertResumeRewrite.mockResolvedValue(REVERTED)
  })

  it('应用成功就出现撤销按钮，点它带的正是那次应用返回的快照 id', async () => {
    const wrapper = await renderAndApply()

    expect(undoText(), '应用之后没有撤销入口').toBe('撤销这次应用')
    await undoButton().click()
    await flushPromises()

    expect(api.revertResumeRewrite.mock.calls, '撤销没发请求').toEqual([[1, 77]])
    expect(wrapper.vm.rewrite.snapshotId).toBe(78)
    expect(undoText()).toBe('撤销这次撤销')
    wrapper.unmount()
  })

  it('撤销接上的新快照让下一次撤销用新 id，文案仍指向最近那次动作', async () => {
    const wrapper = await renderAndApply()
    await undoButton().click()
    await flushPromises()

    await undoButton().click()
    await flushPromises()

    // 每一次撤销都留下一份"撤销前"的行，所以撤销第二次撤的是第一次撤销本身：
    // id 在往前走（77 → 78），文案停在"撤销这次撤销"，而不是跟着次数翻花。
    expect(api.revertResumeRewrite.mock.calls.map((call) => call[1])).toEqual([77, 78])
    expect(undoText()).toBe('撤销这次撤销')
    wrapper.unmount()
  })

  it('服务端按块拒了这单撤销时，不吃掉候选人的文字也不假装成功', async () => {
    api.revertResumeRewrite.mockResolvedValue({
      changed: false,
      reverted: false,
      stale_blocks: [{ block_id: 'work[0].desc', kind: 'work', reason: 'stale_block' }],
    })
    const wrapper = await renderAndApply()

    await undoButton().click()
    await flushPromises()

    // block_id 是锚点，候选人读不懂，所以文案取的是 kind
    expect(document.body.textContent).toContain('「工作经历」在应用之后又被改过，整单撤销没有执行')
    expect(wrapper.vm.rewrite.snapshotId, '被拒的撤销不该把快照 id 也丢掉').toBe(77)
    expect(undoText()).toBe('撤销这次应用')
    wrapper.unmount()
  })

  it('一处都没应用上时没有撤销按钮——没有东西被覆盖，就没有东西可撤', async () => {
    const wrapper = await renderAndApply({
      changed: false,
      applied: [],
      rejected: [{ block_id: 'self_evaluation', reason: 'stale_anchor' }],
      snapshot_version_id: null,
      score: { before: null, after: null, delta: null },
    })

    expect(undoText()).toBeNull()
    expect(api.revertResumeRewrite).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('撤销在途时按钮禁用：应用与撤销共用同一把锁，第二次点击不发第二条请求', async () => {
    let release
    api.revertResumeRewrite.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve(REVERTED)
        })
    )
    const wrapper = await renderAndApply()

    const first = undoButton()
    first.click()
    await flushPromises()

    const busy = undoButton()
    expect(busy.disabled, '撤销在途时按钮没有禁用').toBe(true)
    busy.click()
    await flushPromises()
    expect(api.revertResumeRewrite.mock.calls).toHaveLength(1)

    release()
    await flushPromises()
    expect(api.revertResumeRewrite.mock.calls).toHaveLength(1)
    wrapper.unmount()
  })

  it('撤销成功后分数那一行跟着改回来的读数', async () => {
    const wrapper = await renderAndApply()
    expect(document.querySelector('.rw-score')?.textContent).toContain('匹配分 70 → 80')

    await undoButton().click()
    await flushPromises()

    expect(document.querySelector('.rw-score')?.textContent, '撤销后仍显示应用时的分差').toContain(
      '匹配分 80 → 70'
    )
    wrapper.unmount()
  })
})
