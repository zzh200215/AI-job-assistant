import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import CareerPlanning from '@/features/planning/views/CareerPlanning.vue'
import { installElement } from '@/plugins/element'

/* §10.11 决定 ①：自动填进"目标岗位"的职称，在候选人没有亲手编辑过之前，跟着当前简历走。
   改之前它是"只在为空时填一次"，于是换了简历，薪资卡继续按**第一份简历**的职称查询——
   标签与数字自洽（那一屏打印的是服务端回显的 `filters.position`），但不再代表当前这份简历。
   这里量的两件事因此分开：发出去的查询条件（`/salary/overview` 的参数），和屏幕上回显的那一句。 */
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

const pathsPayload = (id) => ({
  career_paths: [{ direction_key: `k${id}`, label: `方向-${id}`, coverage: 0.5, gap_skills: [] }],
  summary: '',
  corpus: { visible_jds: 10, directions_found: 1 },
  message: '',
})

const salaryPayload = (position) => ({
  has_data: true,
  sample_size: 42,
  filters: { position },
  statistics: { p25: 1, p50: 2, p75: 3, p90: 4 },
})

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

/* 让"方向"先落地，薪资请求才会发出（watch 里是 `await loadCareerPaths(); await loadSalaryMarket()`）。
   返回这一次 /salary/overview 的记录。 */
async function salaryRequestFor(id) {
  await settle(byResume(id), pathsPayload(id))
  return ofType('/salary/overview').at(-1)
}

const targetInput = (wrapper) => wrapper.find('input[placeholder^="例如"]')
const renderedSalaryPosition = () =>
  document.querySelector('.salary-current strong')?.textContent.trim() ?? null

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
  localStorage.clear()
})

describe('职业规划：目标岗位跟随当前简历（§10.11 ①）', () => {
  it('第一份简历：职称自动填进输入框，并作为查询条件发出去', async () => {
    const wrapper = await renderPlanning()
    expect(targetInput(wrapper).exists()).toBe(true) // 反空转：选择器落在真的输入框上
    const salary = await salaryRequestFor(7)
    expect(salary).toBeTruthy()
    expect(salary.arg).toMatchObject({ position: '后端工程师' })
    expect(targetInput(wrapper).element.value).toBe('后端工程师')
    wrapper.unmount()
  })

  it('换简历：没被编辑过就跟着换，发出去的查询条件与屏幕回显一起变', async () => {
    const wrapper = await renderPlanning()
    await salaryRequestFor(7)

    await pickResume(wrapper, 8)
    const salary = await salaryRequestFor(8)
    // 改之前这一条会红：条件仍是"后端工程师"，屏幕上也就一直写着第一份简历的职称
    expect(salary.arg).toMatchObject({ position: '数据分析师' })
    expect(targetInput(wrapper).element.value).toBe('数据分析师')

    await settle(salary, salaryPayload('数据分析师'))
    expect(renderedSalaryPosition()).toBe('数据分析师')
    wrapper.unmount()
  })

  it('手输过之后：换简历不再覆盖那一格', async () => {
    const wrapper = await renderPlanning()
    await salaryRequestFor(7)

    await targetInput(wrapper).setValue('我想做算法工程师')
    await pickResume(wrapper, 8)
    const salary = await salaryRequestFor(8)
    expect(salary.arg).toMatchObject({ position: '我想做算法工程师' })
    expect(targetInput(wrapper).element.value).toBe('我想做算法工程师')
    wrapper.unmount()
  })

  it('手输后清空：尊重清空，不再把职称自动填回去（薪资条件回落成当前简历职称）', async () => {
    const wrapper = await renderPlanning()
    await salaryRequestFor(7)

    await targetInput(wrapper).setValue('临时改的')
    await targetInput(wrapper).setValue('')
    await pickResume(wrapper, 8)
    const salary = await salaryRequestFor(8)
    expect(targetInput(wrapper).element.value).toBe('')
    // getPosition 的 `|| 当前简历职称` 那半条回落仍在，所以请求不会空着发
    expect(salary.arg).toMatchObject({ position: '数据分析师' })
    wrapper.unmount()
  })
})
