import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import CareerPlanning from '@/views/CareerPlanning.vue'
import { installElement } from '@/plugins/element'

/* 换简历时 `watch(selectedResumeId)` 会重发两个请求：/career-path/recommend（职业方向，按简历算）
   和 /salary/overview（薪资样本，取的是**这份简历解析出的职称**）。两个 await 之后都是直接写 ref，
   所以谁后回来谁赢——手上慢一点的那份简历的方向与薪资区间，会盖到刚选中的那份简历下面。
   这一页对候选人的承诺恰好是"给你这份简历的方向"。 */
const RESUMES = [
  { id: 7, name: '后端三年', parsed: { current_title: '后端工程师' } },
  { id: 8, name: '数据转岗', parsed: { current_title: '数据分析师' } },
]

const calls = []

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn((url, config) => {
      const record = { url, arg: config?.params, ...deferred() }
      calls.push(record)
      return record.promise
    }),
    post: vi.fn((url, data, config) => {
      const record = { url, arg: config?.params, ...deferred() }
      calls.push(record)
      return record.promise
    }),
  },
}))

const ofType = (url) => calls.filter((c) => c.url === url)
const byResume = (id) => ofType('/career-path/recommend').find((c) => c.arg?.resume_id === id)

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

function pathsPayload(id) {
  return {
    career_paths: [{ direction_key: `k${id}`, label: `方向-${id}`, coverage: 0.5, gap_skills: [] }],
    summary: '',
    corpus: { visible_jds: 10, directions_found: 1 },
    message: '',
  }
}

function salaryPayload(position) {
  return {
    has_data: true,
    sample_size: 42,
    filters: { position },
    statistics: { p25: 1, p50: 2, p75: 3, p90: 4 },
  }
}

async function renderPlanning() {
  const route = { path: '/career-planning', name: 'career', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/career-planning')
  await router.isReady()
  const wrapper = mount(CareerPlanning, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await settle(ofType('/resume/list')[0], { items: RESUMES })
  await settle(ofType('/jd/list')[0], { items: [] })
  await flushPromises()
  return wrapper
}

async function pickResume(wrapper, id) {
  wrapper.findComponent('.el-select').vm.$emit('update:modelValue', id)
  await flushPromises()
}

function renderedDirections() {
  return [...document.querySelectorAll('.direction-item .direction-top strong')].map((n) =>
    n.textContent.trim()
  )
}

function renderedSalaryPosition() {
  return document.querySelector('.salary-current strong')?.textContent.trim() ?? null
}

function showsSalaryLoading() {
  return [...document.querySelectorAll('.salary-empty')].some((n) =>
    n.textContent.includes('加载中')
  )
}

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
  localStorage.clear()
})

describe('职业规划：换简历时旧简历的结果不能顶在新简历下面', () => {
  it('两份简历都在飞时，屏幕留下的是后发起的那一份', async () => {
    const wrapper = await renderPlanning()
    expect(byResume(7)).toBeTruthy()

    await pickResume(wrapper, 8)
    expect(byResume(8)).toBeTruthy()

    await settle(byResume(8), pathsPayload(8)) // 新简历先回来
    expect(renderedDirections()).toEqual(['方向-8'])

    await settle(byResume(7), pathsPayload(7)) // 旧简历的回答最后才到
    expect(renderedDirections()).toEqual(['方向-8'])
    wrapper.unmount()
  })

  it('新简历还在加载时，上一份的方向不能还挂在屏幕上', async () => {
    const wrapper = await renderPlanning()

    await settle(byResume(7), pathsPayload(7))
    expect(renderedDirections()).toEqual(['方向-7'])

    await pickResume(wrapper, 8) // 换人，第二次请求还在飞
    expect(renderedDirections()).toEqual([])
    wrapper.unmount()
  })

  it('薪资区间也一样：后回来的旧答案不能盖掉新的', async () => {
    const wrapper = await renderPlanning()
    // watch 里是 `await loadCareerPaths(); await loadSalaryMarket()`，所以方向不落地薪资根本不发
    await pickResume(wrapper, 8)
    await settle(byResume(7), pathsPayload(7))
    await settle(byResume(8), pathsPayload(8))
    const [first, second] = ofType('/salary/overview')
    expect(second).toBeTruthy()

    await settle(second, salaryPayload('数据分析师'))
    expect(renderedSalaryPosition()).toBe('数据分析师')

    await settle(first, salaryPayload('后端工程师'))
    expect(renderedSalaryPosition()).toBe('数据分析师')
    wrapper.unmount()
  })

  it('丢弃旧响应不能把加载状态卡死', async () => {
    const wrapper = await renderPlanning()
    await pickResume(wrapper, 8)
    await settle(byResume(7), pathsPayload(7))
    await settle(byResume(8), pathsPayload(8))
    const [first, second] = ofType('/salary/overview')

    await settle(second, salaryPayload('数据分析师'))
    expect(showsSalaryLoading()).toBe(false)

    await settle(first, salaryPayload('后端工程师')) // 旧的那次随后才回
    expect(showsSalaryLoading()).toBe(false)
    wrapper.unmount()
  })

  it('反证：同一份简历点"刷新"，新数据必须显示出来', async () => {
    const wrapper = await renderPlanning()
    await settle(byResume(7), pathsPayload(7))
    expect(renderedDirections()).toEqual(['方向-7'])

    await wrapper.find('.direction-card .card-header button').trigger('click')
    expect(ofType('/career-path/recommend')).toHaveLength(2)
    await settle(ofType('/career-path/recommend')[1], pathsPayload('7b'))
    expect(renderedDirections()).toEqual(['方向-7b'])
    wrapper.unmount()
  })
})
