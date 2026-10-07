import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import History from '@/features/shell/views/History.vue'
import { installElement } from '@/plugins/element'

/* `loadList` 此前把响应直接拆成 `list.value = data.items` / `total.value = data.total`。
   全仓 20 个列表消费点都写了默认值（Users.vue:173、Orders.vue:183、EvalReport.vue:303……），
   只有这一处是裸的，所以只要 `data.items` 缺席，`v-if="list.length"` 就在渲染期抛
   `Cannot read properties of undefined` —— Vue 把它记成 "Unhandled error during execution of
   render function at <History>"，页面**不会红**、门也**不会红**，只有 console 里两条 warn。
   探针在 2026-10-07 就是这样撞上它的：`/history` 没有夹具，适配器落空时返回 `{}`。
   这里不靠 console 读数，直接把 Vue 的错误出口当作可断言的探针口。 */
const api = vi.hoisted(() => ({
  listHistory: vi.fn(),
  getHistoryDetail: vi.fn(),
  deleteHistory: vi.fn(),
}))

vi.mock('@/api/history', () => api)

async function renderHistory(payload) {
  const errors = []
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/history', name: 'history', component: { template: '<div />' } }],
  })
  router.push('/history')
  await router.isReady()
  api.listHistory.mockResolvedValue(payload)
  const wrapper = mount(History, {
    attachTo: document.body,
    global: {
      plugins: [installElement, createPinia(), router],
      config: {
        errorHandler: (err, _instance, info) => errors.push(`${info}: ${err.message}`),
      },
    },
  })
  await flushPromises()
  await flushPromises()
  return { wrapper, errors }
}

describe('History 列表对响应形状的假设', () => {
  beforeEach(() => {
    api.listHistory.mockReset()
    api.getHistoryDetail.mockReset()
    api.deleteHistory.mockReset()
  })

  it('一次 items 缺席的响应不再触发渲染期异常', async () => {
    const { wrapper, errors } = await renderHistory({})
    expect(errors, `渲染期抛了异常：${errors.join(' | ')}`).toEqual([])
    expect(wrapper.find('.history-page').exists(), '视图整个没挂上').toBe(true)
    expect(wrapper.text()).toContain('历史记录')
  })

  it('有数据时照常出行，且摘要条按真实条数渲染', async () => {
    const { wrapper, errors } = await renderHistory({
      total: 2,
      items: [
        { id: 1, match_score: 92, resume_name: '简历A', jd_title: '岗位A' },
        { id: 2, match_score: 61, resume_name: '简历B', jd_title: '岗位B' },
      ],
    })
    expect(errors).toEqual([])
    const rows = wrapper.findAll('.el-table__row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('92')
    expect(rows[1].text()).toContain('61')
    expect(wrapper.find('.history-focus-strip').exists(), '摘要条被 v-if 掉了').toBe(true)
  })
})
