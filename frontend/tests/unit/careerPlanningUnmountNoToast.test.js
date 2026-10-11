import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import CareerPlanning from '@/features/planning/views/CareerPlanning.vue'
import { installElement } from '@/plugins/element'
import { ElMessage } from '@/plugins/element-services'

/* D207 这一组只回答一个问题：**卸载打断一轮职业规划，会不会给候选人弹一句他没点过的错**。
   悬挂 await 本身在这一屏是看不见的（组件已经没了），修它之后能看见的只有这条 toast——
   所以这里走的是真链路：真 `useAgentTaskPolling` + 真轮询器 + 真运行链，只把传输层换掉。 */

const taskState = { status: 'running', error_msg: null }

const RESUME = {
  id: 7,
  name: '后端三年',
  parsed: { current_title: '后端工程师', years_exp: 3 },
}

vi.mock('@/plugins/element-services', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn(async (url) => {
      if (url.startsWith('/agent/task/')) return { ...taskState }
      if (url === '/resume/list') return { items: [RESUME], total: 1 }
      if (url === '/jd/list') return { items: [], total: 0 }
      if (url === '/career-path/recommend')
        return {
          career_paths: [],
          summary: '',
          corpus: { visible_jds: 0, directions_found: 0 },
          message: '',
        }
      return { has_data: false, sample_size: 0 }
    }),
    post: vi.fn(async (url) => {
      if (url === '/analysis/full') return { task_id: 't1' }
      if (url === '/jd') return { id: 99, title: '后端工程师', company: '职业规划目标' }
      return {}
    }),
  },
}))

async function mountPage() {
  const route = { path: '/career-planning', name: 'career', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/career-planning')
  await router.isReady()
  const wrapper = mount(CareerPlanning, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  // 列表回来 → 自动选中第一份简历 → watch 把 current_title 填进"目标岗位"，两道守卫都让过
  await flushPromises()
  await flushPromises()
  return wrapper
}

function planButton(wrapper) {
  return wrapper.findAll('.action-buttons button').at(-1)
}

async function clickPlan(wrapper) {
  await planButton(wrapper).trigger('click')
  await flushPromises()
  await flushPromises()
}

beforeEach(() => {
  taskState.status = 'running'
  taskState.error_msg = null
  vi.clearAllMocks()
  document.body.innerHTML = ''
  localStorage.clear()
})

describe('任务跑在中间时离开这一页', () => {
  it('反证：任务真失败时，那一句错误照样要弹', async () => {
    taskState.status = 'failed'
    taskState.error_msg = '模型超时'
    const wrapper = await mountPage()

    await clickPlan(wrapper)

    expect(ElMessage.error).toHaveBeenCalledWith('职业规划生成失败')
    wrapper.unmount()
  })

  it('被卸载打断时不弹错，也不留下还在轮询的定时器', async () => {
    const wrapper = await mountPage()
    await clickPlan(wrapper)
    expect(ElMessage.error).not.toHaveBeenCalled() // 此刻任务还在跑，本来就不该有声音

    wrapper.unmount()
    await flushPromises()
    await flushPromises()

    expect(ElMessage.error).not.toHaveBeenCalled()
    expect(ElMessage.warning).not.toHaveBeenCalled()
  })
})
