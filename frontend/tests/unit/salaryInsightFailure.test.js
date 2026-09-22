import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import SalaryInsight from '@/views/SalaryInsight.vue'
import { installElement } from '@/plugins/element'

/* GET 失败请求层不弹提示（request.js 只对非 GET 通知）。这个页面原本的注释写着
   "保留上一次查询/评估结果"，而实际上：查询前已经把 overview 清空（表现为一片空白），
   期望评估则真的保留上一次结论——换个岗位提问，拿到的还是上一个岗位的"合理"。 */
const api = vi.hoisted(() => ({
  getSalaryOverview: vi.fn(),
  getSalaryCompare: vi.fn(),
  checkSalaryExpectation: vi.fn(),
}))

vi.mock('@/api/salary', () => api)

async function renderInsight() {
  const route = { path: '/salary-insight', name: 'salary', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/salary-insight')
  await router.isReady()
  const wrapper = mount(SalaryInsight, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function fail(message) {
  const e = new Error('boom')
  e.userMessage = message
  return Promise.reject(e)
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  api.getSalaryOverview.mockResolvedValue({
    has_data: true,
    position: '后端工程师',
    city: '上海',
    sample_size: 42,
    low_confidence: false,
    percentiles: { p25: 20, p50: 30, p75: 45 },
  })
  api.getSalaryCompare.mockResolvedValue({ comparison: [] })
  api.checkSalaryExpectation.mockResolvedValue({
    level: 'reasonable',
    market: { p25: 20, p50: 30, p75: 45 },
    percentile: 0.5,
  })
})

describe('薪资洞察：失败不能留着旧结论', () => {
  it('查询失败时说"查询失败"，而不是留一片空白', async () => {
    const wrapper = await renderInsight()
    wrapper.vm.searchPosition = '后端工程师'
    await wrapper.vm.doSearch()
    await flushPromises()
    expect(document.body.textContent).toContain('后端工程师')

    api.getSalaryOverview.mockImplementationOnce(() => fail('薪资服务暂时不可用'))
    await wrapper.vm.doSearch()
    await flushPromises()

    const text = document.body.textContent
    expect(text).toContain('薪资行情查询失败')
    expect(text).toContain('薪资服务暂时不可用')
    expect(wrapper.vm.overview).toBe(null)
    wrapper.unmount()
  })

  it('评估失败时撤掉上一次结论，避免新输入配旧答案', async () => {
    const wrapper = await renderInsight()
    wrapper.vm.expectPosition = '算法工程师'
    wrapper.vm.expectSalary = 35
    await wrapper.vm.checkExpectation()
    await flushPromises()
    expect(document.body.textContent).toContain('薪资期望合理')

    api.checkSalaryExpectation.mockImplementationOnce(() => fail('评估服务超时'))
    await wrapper.vm.checkExpectation()
    await flushPromises()

    const text = document.body.textContent
    expect(wrapper.vm.expectResult).toBe(null)
    expect(text).not.toContain('薪资期望合理')
    expect(text).toContain('期望薪资评估失败')
    expect(text).toContain('评估服务超时')
    wrapper.unmount()
  })
})
