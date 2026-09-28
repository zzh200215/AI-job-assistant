import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeUpload from '@/views/ResumeUpload.vue'
import { installElement } from '@/plugins/element'

/* 简历列表页的「AI诊断」是行下拉里的一项，点开弹窗后 `await diagnoseResume(r.id)` 直接写
   currentDiagnosis。弹窗是模态的，但**关掉它并不会取消已经发出的请求**：用户看完没出来、
   关掉再看另一份简历，前一份的分数就会落在后一份的弹窗里——那是一整块评估读数，
   不是"稍微旧一点"，是**给错人打分**。 */

const api = vi.hoisted(() => ({
  uploadResume: vi.fn(),
  parseResume: vi.fn(),
  getResumeList: vi.fn(),
  getResumeVersions: vi.fn(),
  getResumeQuickScore: vi.fn(),
  diagnoseResume: vi.fn(),
  getRewriteSuggestions: vi.fn(),
  applyResumeRewrites: vi.fn(),
  deleteResume: vi.fn(),
  generateOptimized: vi.fn(),
  exportResume: vi.fn(),
  downloadResumeExport: vi.fn(),
}))

vi.mock('@/api/resume', () => api)

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const inflight = []

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const row = (id, name) => ({
  id,
  file_name: name,
  name,
  status: 'ready',
  create_time: '2026-09-01T00:00:00Z',
  parsed: { current_title: '后端工程师' },
})

const diagnosis = (score) => ({
  total_score: score,
  structure_score: score,
  expression_score: score,
  keyword_score: score,
  highlight_score: score,
  ats_score: score,
  completeness_score: score,
  structure_issues: [],
  expression_issues: [],
  missing_keywords: [],
  highlights: [],
  match_analysis: '',
})

let router

async function renderUpload(rows) {
  api.getResumeList.mockResolvedValue({ items: rows, total: rows.length })
  router = createRouter({
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
  return wrapper
}

function nextDiagnosis() {
  const record = { ...deferred() }
  inflight.push(record)
  return record.promise
}

const lastOf = () => [...inflight].pop()

function gaugeScore() {
  return document.querySelector('.gauge-text')?.textContent.trim()
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  inflight.length = 0

  api.getResumeList.mockImplementation(() => Promise.resolve({ items: [], total: 0 }))
  api.getResumeVersions.mockResolvedValue({ versions: [] })
  api.getResumeQuickScore.mockResolvedValue({ score: 60 })
  api.parseResume.mockResolvedValue({ parsed: {} })
  api.deleteResume.mockResolvedValue({})
  api.getRewriteSuggestions.mockResolvedValue({})
  api.applyResumeRewrites.mockResolvedValue({})
  api.generateOptimized.mockResolvedValue({})
  api.exportResume.mockResolvedValue({})
  api.downloadResumeExport.mockResolvedValue(new Blob(['x']))
  api.diagnoseResume.mockImplementation(nextDiagnosis)
})

describe('诊断弹窗：弹窗里必须是刚点开的那一份简历', () => {
  it('关掉弹窗再看另一份，前一份的诊断不能留在新弹窗里', async () => {
    const wrapper = await renderUpload([row(1, '简历甲'), row(2, '简历乙')])

    wrapper.vm.showDiagnosisDialog(row(1, '简历甲'))
    await flushPromises()
    expect(api.diagnoseResume.mock.lastCall[0], '没为简历甲发出诊断请求').toBe(1)
    const first = lastOf()

    wrapper.vm.showDiagnosis = false // 关闭弹窗（× 或遮罩），请求仍在途
    await flushPromises()

    wrapper.vm.showDiagnosisDialog(row(2, '简历乙'))
    await flushPromises()
    expect(api.diagnoseResume.mock.lastCall[0]).toBe(2)
    const second = lastOf()
    expect(second).not.toBe(first)

    await settle(second, diagnosis(88))
    expect(gaugeScore()).toBe('88')

    await settle(first, diagnosis(41))
    expect(gaugeScore(), '弹窗里显示的是上一份简历的分数').toBe('88')
    expect(wrapper.vm.currentDiagnosis.resume_id).toBe(2)
    wrapper.unmount()
  })

  it('对照组：单次诊断照常出分，行上的诊断分也照常回填', async () => {
    const wrapper = await renderUpload([row(1, '简历甲')])
    const r = wrapper.vm.resumes[0]
    wrapper.vm.showDiagnosisDialog(r)
    await flushPromises()
    await settle(lastOf(), diagnosis(73))

    expect(gaugeScore()).toBe('73')
    expect(wrapper.vm.resumes[0]._diagnosisScore).toBe(73)
    wrapper.unmount()
  })

  it('对照组：诊断失败要明说不可用，而不是静默留空', async () => {
    const wrapper = await renderUpload([row(1, '简历甲')])
    wrapper.vm.showDiagnosisDialog(wrapper.vm.resumes[0])
    await flushPromises()
    await settle(lastOf(), null)

    expect(document.body.textContent).toContain('诊断服务暂时不可用')
    wrapper.unmount()
  })
})
