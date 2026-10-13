import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import mockReportJob from '../fixtures/mockReportShape.json'
import ResumeReport from '@/features/resume/views/ResumeReport.vue'
import { installElement } from '@/plugins/element'

/* 六模块那一页对**后端真输出**的比对，夹具不是这里手搓的。
   `frontend/tests/fixtures/mockReportShape.json` 由 `backend/scripts/collect_mock_report_shape.py`
   从一条真跑完的作业上导出（provider=mock，不打任何补丁），后端那边有反向守卫盯着它不过期
   （`backend/tests/test_mock_report_shape_fixture.py`）。

   为什么这一族要单独成立：`resumeReportPage.test.js` 那 24 条用的是本文件里手写的夹具，
   它只能证明"页面按我以为的形状画"，证明不了"页面按后端实际发的形状画"。两棵树各持一份
   形状的想象，键名一漂就是**画少了但不报错**——这一族在抽取搬家的账上记过三次。 */

const api = vi.hoisted(() => ({
  getResumeList: vi.fn(),
  createReportJob: vi.fn(),
  getReportJob: vi.fn(),
  applyReportRedline: vi.fn(),
  downloadReportHtml: vi.fn(),
}))
const services = vi.hoisted(() => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/api/resume', () => api)
vi.mock('@/api/jd', () => ({ getJDList: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/plugins/element-services', () => services)

const RESUME_ROW = { id: 1, name: '示例候选人', file_name: 'mock.pdf', parsed: {} }
const REPORT = mockReportJob.report

async function mountFromBackendBytes() {
  api.getResumeList.mockResolvedValue({ items: [RESUME_ROW], total: 1 })
  // 直接把后端那一份字节交出去，一个字段都不在这里补。
  api.getReportJob.mockResolvedValue(mockReportJob)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/resume/report', name: 'resume-report', component: { template: '<div />' } },
      { path: '/resume-center', name: 'resume-center', component: { template: '<div />' } },
    ],
  })
  await router.push({ name: 'resume-report', query: { resume_id: '1', job_id: '1' } })
  await router.isReady()
  const wrapper = mount(ResumeReport, {
    attachTo: document.body,
    global: { plugins: [installElement, router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  for (const fn of [...Object.values(api), ...Object.values(services.ElMessage)]) fn.mockClear()
  document.body.innerHTML = ''
})

describe('后端真输出的六模块', () => {
  it('六节全上屏：一处"这一节没能生成"的兜底都不该出现', async () => {
    const wrapper = await mountFromBackendBytes()

    for (const anchor of ['m-summary', 'm-score', 'm-fit', 'm-resume', 'm-interview', 'm-boss']) {
      expect(wrapper.find(`#${anchor}`).exists()).toBe(true)
    }
    expect(wrapper.findAll('.rr-missing')).toHaveLength(0)
    expect(wrapper.findAll('.rr-deferred')).toHaveLength(0)
    wrapper.unmount()
  })

  it('七维每维一行，合计取七维之和而不是模型自报的那一个', async () => {
    const wrapper = await mountFromBackendBytes()

    expect(wrapper.findAll('.rr-dim-row')).toHaveLength(REPORT.dimensions.length)
    const score = wrapper.find('#m-score').text()
    expect(score).toContain('65')
    expect(score).toContain('C')
    // 模型自报的 72 是对照证据，住在 `model_reported_total`，出不了候选人的屏。
    expect(score).not.toContain('72')
    wrapper.unmount()
  })

  it('批改稿左栏按 sections 顺序铺开，一段都不许省', async () => {
    const wrapper = await mountFromBackendBytes()

    const blocks = wrapper.findAll('.rr-block')
    expect(blocks).toHaveLength(REPORT.sections.length)
    const labels = blocks.map((b) => b.find('.rr-block-label').text())
    expect(labels).toEqual(REPORT.sections.map((s) => s.label))
    wrapper.unmount()
  })

  it('正文编号与右栏批注一一对应，关键项各带自己的底色', async () => {
    const wrapper = await mountFromBackendBytes()

    expect(wrapper.findAll('.rr-mark')).toHaveLength(REPORT.redline.total)
    expect(wrapper.findAll('.rr-note')).toHaveLength(REPORT.redline.total)
    expect(wrapper.findAll('.rr-note-key')).toHaveLength(REPORT.redline.key_total)
    expect(wrapper.find('.rr-stat').text()).toContain(`共 ${REPORT.redline.total} 处改动`)
    wrapper.unmount()
  })

  it('字段值那一栏的编号只批注不写回：勾选框 disable，并提示自己在简历文件里改', async () => {
    const wrapper = await mountFromBackendBytes()

    const manual = wrapper.findAll('.rr-manual-hint')
    const manualMarks = REPORT.redline.blocks.filter((b) => !b.editable).flatMap((b) => b.edits)
    expect(manual.length).toBeGreaterThanOrEqual(manualMarks.length)

    const boxes = wrapper.findAll('.rr-note input[type="checkbox"]')
    expect(boxes).toHaveLength(REPORT.redline.total)
    // 只有 editable 的编号能发采纳请求：这份报告里 6 处有 1 处打在技术栈那一栏。
    expect(boxes.filter((b) => b.attributes('disabled') !== undefined)).toHaveLength(
      manualMarks.length
    )
    wrapper.unmount()
  })

  it('面试预演的题数、追问数与需补强都按后端数出来的那一份画', async () => {
    const wrapper = await mountFromBackendBytes()
    const dist = REPORT.interview.distribution

    expect(wrapper.findAll('.rr-question')).toHaveLength(dist.total)
    expect(wrapper.findAll('.rr-label-follow')).toHaveLength(dist.total * 3)
    expect(wrapper.findAll('.rr-status-warn')).toHaveLength(dist.weak)
    expect(wrapper.find('#m-interview .rr-hint').text()).toContain(`共 ${dist.total} 题`)
    wrapper.unmount()
  })

  it('投递策略五章逐字引用，两处填空引用报告里已有的话', async () => {
    const wrapper = await mountFromBackendBytes()

    // 五章 + 那一块"本报告的两处填空"
    expect(wrapper.findAll('#m-boss .rr-chapter')).toHaveLength(
      REPORT.apply_strategy.chapters.length + 1
    )
    const boss = wrapper.find('#m-boss').text()
    expect(boss).toContain(REPORT.personalization.one_line_label)
    expect(boss).toContain(REPORT.personalization.opener)
    wrapper.unmount()
  })

  it('页面上不出现任何对内字眼：降级、机制名、拒因计数都不上屏', async () => {
    const wrapper = await mountFromBackendBytes()
    const text = wrapper.text()

    for (const word of [
      '兜底',
      '严格制',
      '软下限',
      '门禁',
      '可面试水位',
      '硬条件',
      '双轴',
      '收敛',
      '档内区分项',
    ]) {
      expect(text).not.toContain(word)
    }
    for (const key of [
      'model_reported_total',
      'stage_errors',
      'redline_rejected',
      'provenance',
      'error_msg',
    ]) {
      expect(text).not.toContain(key)
    }
    wrapper.unmount()
  })
})
