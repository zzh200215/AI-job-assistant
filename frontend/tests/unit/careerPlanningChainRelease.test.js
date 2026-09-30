import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElInput, ElSelect } from 'element-plus'

import CareerPlanning from '@/features/planning/views/CareerPlanning.vue'
import { installElement } from '@/plugins/element'

/* D54 把这两条链搬出页面的同时修掉两处**同一个形状**的缺陷：提前返回的那一支不释放 loading，
   而它已经把上一发作废了（上一发的 `finally` 带着 `isCurrent()` 于是也不解）。D42 在推荐链上
   记过这一对——"两处必须一起改，只做前一处会把看得见的错换成转圈停不下来"。

   用例一（薪资）：`loadSalaryMarket` 进入就领令牌，然后有一支"没有职称 → 不发请求"的提前返回，
   以前只清值。停在屏幕上的样子是薪资那一栏永久"加载中…"，而它其实什么都不会再来。
   用例二（方向）：以前"简历没了"只清值不领令牌，于是清完还会被在途的旧响应填满——屏幕上重新
   出现一份**已经没有选中简历**的方向推荐。 */

const RESUMES = [
  { id: 7, name: '后端三年', parsed: { current_title: '后端工程师' } },
  { id: 8, name: '只有文件名', parsed: { name: '_resume.pdf' } },
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
const salaryCalls = () => ofType('/salary/overview')

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
    statistics: { p25: 18, p50: 25, p75: 35, p90: 48 },
  }
}

function showsSalaryLoading() {
  return [...document.querySelectorAll('.salary-empty')].some((n) =>
    n.textContent.includes('加载中')
  )
}

function renderedDirections() {
  return [...document.querySelectorAll('.direction-item .direction-top strong')].map((n) =>
    n.textContent.trim()
  )
}

async function mountPlanning() {
  const route = { path: '/career-planning', name: 'career', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/career-planning')
  await router.isReady()
  const wrapper = mount(CareerPlanning, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

async function pickResume(wrapper, id) {
  wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', id)
  await flushPromises()
}

async function typeTargetRole(wrapper, value) {
  const input = wrapper
    .findAllComponents(ElInput)
    .find((w) => (w.props('placeholder') || '').includes('AI 应用工程师'))
  input.vm.$emit('update:modelValue', value)
  await flushPromises()
}

describe('CareerPlanning 的两条链：提前返回要解 loading，作废要真作废', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    calls.length = 0
    localStorage.clear()
    // 全局 setup 会写这两条；上面的 clear() 把它们抹掉了，而简历槽是按登录用户 id 分槽的
    localStorage.setItem('token', 'smoke-test-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'smoke', role: 'candidate' }))
  })

  it('换到一份没有职称的简历时，薪资那一栏不许停在"加载中"', async () => {
    const wrapper = await mountPlanning()
    await settle(ofType('/resume/list')[0], { items: RESUMES })
    await settle(ofType('/jd/list')[0], { items: [] })
    // 简历 7 自动选中 → 方向回来之后才发薪资（职称取自这份简历）
    await settle(byResume(7), pathsPayload(7))
    expect(salaryCalls()[0]?.arg).toEqual({ position: '后端工程师' })

    await typeTargetRole(wrapper, '')
    await pickResume(wrapper, 8)
    await settle(byResume(8), pathsPayload(8))
    expect(salaryCalls().length).toBe(1) // 简历 8 没有职称 → 不该再发一次

    /* S1 此刻才回来：它已经被"没有职称就不发请求"那一支判为过期，
       而那一支当时没把 loading 放下来 —— 修之前这里会停在"加载中…"。 */
    await settle(salaryCalls()[0], salaryPayload('后端工程师'))
    expect(showsSalaryLoading()).toBe(false)
  })

  it('槽里记的简历从列表里消失后，在途的方向响应不能把结论填回来', async () => {
    // 真实路径：在另一个标签页删掉这份简历，再回到本页（onMounted 会刷新一次列表）。
    // 槽键按登录用户 id 分，而 store 的归属是在第一次用到时才写进 lastSelection，
    // 所以两种键都播种一份，别让用例去赌哪一条先被读到。
    localStorage.setItem('recruit.lastResumeId.1', '9')
    localStorage.setItem('recruit.lastResumeId.guest', '9')
    const wrapper = await mountPlanning()
    expect(byResume(9)).toBeTruthy()

    await settle(ofType('/resume/list')[0], { items: [] })
    await settle(ofType('/jd/list')[0], { items: [] })
    expect(wrapper.findComponent(ElSelect).props('modelValue')).toBeNull()
    expect(renderedDirections()).toEqual([])

    await settle(byResume(9), pathsPayload(9))
    expect(renderedDirections()).toEqual([])
  })
})
