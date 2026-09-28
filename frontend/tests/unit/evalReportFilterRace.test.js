import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import EvalReport from '@/views/EvalReport.vue'
import { installElement } from '@/plugins/element'

/* 评测报告页的报告类型下拉（`:13`）绑的是 `@change="reloadAll"`，那个 select 没有任何锁；
   「刷新」按钮有 `:loading`，但下拉没有。连换两次筛选就是两发带**不同参数**的在途请求，
   旧筛选那一发晚到时，屏幕上的数字属于上一个类型，而下拉框写着新选的类型。 */

const api = vi.hoisted(() => ({
  getEvalReportSummary: vi.fn(),
  getEvalReportList: vi.fn(),
  getEvalReportDetail: vi.fn(),
  compareEvalReports: vi.fn(),
}))

vi.mock('@/api/evaluation', () => api)

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const summaryCalls = []
const listCalls = []

async function settleRound(index, counts, items) {
  summaryCalls[index].resolve({ counts, latest_by_type: {} })
  listCalls[index].resolve({ items })
  await flushPromises()
}

const row = (id, type) => ({
  report_id: id,
  report_type: type,
  filename: `${id}.md`,
  metrics: { recall: 0.5, precision: 0.4, hit_rate: 0.3, mrr: 0.2 },
  generated_at: '2026-09-01T00:00:00Z',
})

let router

async function renderReport() {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/eval/report', name: 'eval-report', component: { template: '<div />' } }],
  })
  router.push('/eval/report')
  await router.isReady()
  const wrapper = mount(EvalReport, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function pickType(wrapper, value) {
  const select = wrapper.findComponent('.el-select')
  expect(select, '类型下拉没渲染出来，测试前提不成立').toBeTruthy()
  select.vm.$emit('update:modelValue', value)
  select.vm.$emit('change', value)
  return flushPromises()
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  summaryCalls.length = 0
  listCalls.length = 0
  api.getEvalReportSummary.mockImplementation(() => {
    const record = { ...deferred() }
    summaryCalls.push(record)
    return record.promise
  })
  api.getEvalReportList.mockImplementation(() => {
    const record = { ...deferred() }
    listCalls.push(record)
    return record.promise
  })
  api.getEvalReportDetail.mockResolvedValue({})
  api.compareEvalReports.mockResolvedValue({})
})

describe('评测报告：换筛选后的数字必须属于新筛选', () => {
  it('旧筛选那一发晚到时不能把新筛选的计数盖掉', async () => {
    const wrapper = await renderReport()
    expect(summaryCalls.length, '挂载没有发请求，测试前提不成立').toBe(1)

    await pickType(wrapper, 'rag')
    expect(summaryCalls.length, '换筛选没发第二轮请求').toBe(2)

    await settleRound(1, { rag: 7 }, [row('r2', 'rag')])
    expect(wrapper.vm.summary.counts.rag).toBe(7)

    await settleRound(0, { agent: 2 }, [row('r1', 'agent')])
    expect(wrapper.vm.summary.counts, '屏幕上留下的是上一个筛选的计数').toEqual({ rag: 7 })
    expect(wrapper.vm.reportList.map((r) => r.report_id)).toEqual(['r2'])
    wrapper.unmount()
  })

  it('对照组：换一次筛选照常把数字与列表都写上', async () => {
    const wrapper = await renderReport()
    await settleRound(0, { all: 3 }, [row('r0', 'rag')])
    expect(wrapper.vm.summary.counts.all).toBe(3)

    await pickType(wrapper, 'agent')
    await settleRound(1, { agent: 5 }, [row('r9', 'agent')])
    expect(wrapper.vm.summary.counts.agent).toBe(5)
    expect(wrapper.vm.reportList.map((r) => r.report_id)).toEqual(['r9'])
    expect(wrapper.vm.loading.list).toBe(false)
    wrapper.unmount()
  })
})
