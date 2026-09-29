import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import SalaryInsight from '@/features/jobs/views/SalaryInsight.vue'
import { installElement } from '@/plugins/element'

/* 薪资洞察的「查询」按钮（`:26`）与两个输入框的 enter（`:17/:24`）都没有锁，而 doSearch 里是
   **两个串联 await、各写一块屏幕**：先 `overview`（合理区间那张卡），再 `cityComparison`（城市对比表）。
   所以交叠的后果不是"整块换回旧的"，而是**卡片来自岗位甲、城市对比表来自岗位乙**——
   同一条市场上写着两个不同岗位的读数，谁也看不出它是拼出来的。
   `checkExpectation`（「评估」`:180`，同样没有锁）是第二个形状：换岗位/换薪资再点一次，
   旧结论会盖在新结论上。 */

const api = vi.hoisted(() => ({
  getSalaryOverview: vi.fn(),
  getSalaryCompare: vi.fn(),
  checkSalaryExpectation: vi.fn(),
}))

vi.mock('@/api/salary', () => api)

function deferred() {
  let resolve
  let reject
  const promise = new Promise((r, j) => {
    resolve = r
    reject = j
  })
  return { resolve, reject, promise }
}

const inflight = {}

function hang(name) {
  inflight[name] = []
  api[name] = vi.fn((...args) => {
    const record = { args, ...deferred() }
    inflight[name].push(record)
    return record.promise
  })
}

const lastOf = (name) => [...inflight[name]].pop()
const nthOf = (name, i) => inflight[name][i]
const countOf = (name) => inflight[name].length

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const overview = (position, p25, p75) => ({
  has_data: true,
  total_jds: 20,
  parsed_count: 18,
  statistics: { p25, p50: p25 + 2, p75 },
  position,
})

const comparison = (city) => ({ comparison: [{ city, median: 30 }] })

const expectation = (median, level = 'reasonable') => ({
  level,
  message: `中位数 ${median}`,
  market: { median },
})

let router

async function renderInsight() {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/salary', name: 'salary', component: { template: '<div />' } }],
  })
  router.push('/salary')
  await router.isReady()
  return mount(SalaryInsight, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
}

function buttonByText(wrapper, text) {
  const found = wrapper.findAll('button').find((b) => b.text().trim() === text)
  expect(found, `找不到文案正好是「${text}」的按钮，测试前提不成立`).toBeTruthy()
  return found
}

function marketRange() {
  return document.querySelector('.market-range strong')?.textContent.trim()
}

function cityCities(wrapper) {
  // 城市对比是 el-table，jsdom 里不渲染行（knowledgeRace.test.js 记过这条），所以断言它绑的数据
  return wrapper.vm.cityComparison.map((row) => row.city)
}

function expectationMedian() {
  return document.querySelector('.expect-details strong')?.textContent.trim()
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  for (const key of Object.keys(inflight)) delete inflight[key]
  hang('getSalaryOverview')
  hang('getSalaryCompare')
  hang('checkSalaryExpectation')
})

describe('薪资洞察：一次查询的两块屏幕必须来自同一个岗位', () => {
  it('换岗位再查询，旧岗位的区间不能盖掉新岗位的', async () => {
    const wrapper = await renderInsight()

    wrapper.vm.searchPosition = '前端'
    await buttonByText(wrapper, '查询').trigger('click')
    const firstOverview = lastOf('getSalaryOverview')
    expect(firstOverview.args[0].position).toBe('前端')

    wrapper.vm.searchPosition = 'Java'
    await buttonByText(wrapper, '查询').trigger('click')
    const secondOverview = lastOf('getSalaryOverview')
    expect(secondOverview.args[0].position).toBe('Java')

    await settle(secondOverview, overview('Java', 20, 40))
    await settle(lastOf('getSalaryCompare'), comparison('北京'))
    expect(marketRange()).toBe('20K - 40K')

    await settle(firstOverview, overview('前端', 12, 18))
    expect(marketRange(), '卡片回到了先查询那个岗位的区间').toBe('20K - 40K')
    wrapper.unmount()
  })

  it('换期望薪资再评估，旧的结论不能盖住新的', async () => {
    const wrapper = await renderInsight()

    wrapper.vm.expectPosition = '前端'
    wrapper.vm.expectSalary = 18
    await buttonByText(wrapper, '评估').trigger('click')
    const first = lastOf('checkSalaryExpectation')
    expect(first.args[0].salary).toBe(18)

    wrapper.vm.expectSalary = 45
    await buttonByText(wrapper, '评估').trigger('click')
    const second = lastOf('checkSalaryExpectation')
    expect(second.args[0].salary).toBe(45)

    await settle(second, expectation(30, 'high'))
    expect(expectationMedian()).toBe('30K')

    await settle(first, expectation(22, 'reasonable'))
    expect(expectationMedian(), '结论回到了上一次报价的评估').toBe('30K')
    wrapper.unmount()
  })

  it('旧那一轮不许把新那轮的转圈提前停掉', async () => {
    const wrapper = await renderInsight()

    wrapper.vm.searchPosition = '前端'
    await buttonByText(wrapper, '查询').trigger('click')
    const first = lastOf('getSalaryOverview')
    wrapper.vm.searchPosition = 'Java'
    await buttonByText(wrapper, '查询').trigger('click')
    await flushPromises()
    expect(wrapper.vm.loading).toBe(true)

    await settle(first, overview('前端', 12, 18))
    // 作废的那一轮不该再去发它的第二个请求；而新那轮此时还停在第一个请求上
    expect(countOf('getSalaryCompare'), '被作废的那一轮还是发了第二个请求').toBe(0)
    expect(wrapper.vm.loading, '旧的一轮落地就把还在途的查询说成已完成').toBe(true)

    await settle(lastOf('getSalaryOverview'), overview('Java', 20, 40))
    await settle(lastOf('getSalaryCompare'), comparison('上海'))
    expect(wrapper.vm.loading).toBe(false)
    expect(marketRange()).toBe('20K - 40K')
    wrapper.unmount()
  })
})

describe('对照组：单次查询必须照常把两块屏幕都拼上', () => {
  it('只查一次时区间与城市对比都照常出来', async () => {
    const wrapper = await renderInsight()
    wrapper.vm.searchPosition = '前端'
    await buttonByText(wrapper, '查询').trigger('click')
    await settle(lastOf('getSalaryOverview'), overview('前端', 12, 18))
    await settle(lastOf('getSalaryCompare'), comparison('深圳'))

    expect(marketRange()).toBe('12K - 18K')
    expect(cityCities(wrapper)).toEqual(['深圳'])
    expect(wrapper.vm.loading).toBe(false)
    wrapper.unmount()
  })

  it('只评估一次时结论照常出来', async () => {
    const wrapper = await renderInsight()
    wrapper.vm.expectPosition = '前端'
    wrapper.vm.expectSalary = 30
    await buttonByText(wrapper, '评估').trigger('click')
    await settle(lastOf('checkSalaryExpectation'), expectation(26))

    expect(expectationMedian()).toBe('26K')
    wrapper.unmount()
  })

  it('查询失败时按失败说，而不是把旧结果留着当答案', async () => {
    const wrapper = await renderInsight()
    wrapper.vm.searchPosition = '前端'
    await buttonByText(wrapper, '查询').trigger('click')
    await settle(lastOf('getSalaryOverview'), overview('前端', 12, 18))
    await settle(lastOf('getSalaryCompare'), comparison('深圳'))
    expect(marketRange()).toBe('12K - 18K')

    wrapper.vm.searchPosition = '不存在的岗位'
    await buttonByText(wrapper, '查询').trigger('click')
    const err = new Error('boom')
    err.userMessage = '薪资服务超时'
    nthOf('getSalaryOverview', 1).reject(err)
    await flushPromises()

    expect(document.body.textContent).toContain('薪资行情查询失败')
    wrapper.unmount()
  })
})
