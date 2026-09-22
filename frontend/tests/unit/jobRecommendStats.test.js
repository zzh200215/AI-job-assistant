import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobRecommend from '@/views/JobRecommend.vue'
import { installElement } from '@/plugins/element'

/* `loadFeedbackStats` 一次 `await` 之后直接写 `feedbackStats`，而它是**每次点喜欢/不喜欢之后**
   都重发的：
   - 没有令牌 → 先发起的那次后回来，面板就退回"你点之前"的计数；
   - catch 里只有一句 `= null` → 统计拉不到时整块面板消失，等于对候选人说"你没有反馈数据"。
     GET 失败不弹提示（`request.js` 只对非 GET 通知），所以消失是它唯一的对外表现。 */
const calls = []

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { resolve, reject, promise }
}

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn((url, config) => {
      const record = { url, method: 'get', arg: config?.params, ...deferred() }
      calls.push(record)
      return record.promise
    }),
    post: vi.fn((url, data) => {
      const record = { url, method: 'post', arg: data, ...deferred() }
      calls.push(record)
      return record.promise
    }),
  },
}))

const lastOf = (url) => [...calls].reverse().find((c) => c.url === url)

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

async function failWith(record, message) {
  const error = new Error('boom')
  error.userMessage = message
  record.reject(error)
  await flushPromises()
}

async function renderRecommend() {
  const route = { path: '/jobs/recommend', name: 'recommend', component: { template: '<div />' } }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  router.push('/jobs/recommend')
  await router.isReady()
  const wrapper = mount(JobRecommend, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  // onMounted 是 `await fetchResumes()` 之后才发统计请求，所以简历列表不落地就没有第一次统计
  await settle(lastOf('/resume/list'), { items: [{ id: 7, name: '简历甲' }] })
  return wrapper
}

async function loadOneCard(wrapper) {
  const select = wrapper.findComponent('.el-select')
  select.vm.$emit('update:modelValue', 7)
  select.vm.$emit('change', 7)
  await flushPromises()
  await settle(lastOf('/jobs/recommend'), {
    recommendations: [{ jd_id: 101, job_title: '岗位-A', company: '公司', match_score: 86 }],
  })
  await settle(lastOf('/jobs/pipeline/list'), { items: [] })
  await settle(lastOf('/jobs/bookmarks/list'), { items: [] })
}

function statsTotal() {
  return document.querySelector('.stats-value')?.textContent.trim() ?? null
}

function clickLike(wrapper) {
  return wrapper.find('.feedback-btns button').trigger('click')
}

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
  localStorage.clear()
})

describe('岗位推荐：反馈统计面板', () => {
  it('点完喜欢之后，旧那一轮的统计不能把计数退回去', async () => {
    const wrapper = await renderRecommend()
    const statsBeforeClick = lastOf('/jobs/feedback/stats') // 进页面发的那次，先不让它回来
    expect(statsBeforeClick).toBeTruthy()

    await loadOneCard(wrapper)
    await clickLike(wrapper)
    await settle(lastOf('/jobs/feedback'), { ok: true })
    const statsAfterClick = lastOf('/jobs/feedback/stats')
    expect(statsAfterClick).toBeTruthy()
    expect(statsAfterClick).not.toBe(statsBeforeClick)

    await settle(statsAfterClick, { total: 4 })
    expect(statsTotal()).toBe('4')

    await settle(statsBeforeClick, { total: 3 }) // 旧的那次最后才到
    expect(statsTotal()).toBe('4')
    wrapper.unmount()
  })

  it('统计拉不到时说"加载失败"，而不是让面板消失冒充没有反馈', async () => {
    const wrapper = await renderRecommend()
    await failWith(
      lastOf('/jobs/feedback/stats'),
      '反馈统计暂时读不出来，稍后重试' // 面板消失 = 对候选人说"你没有反馈数据"
    )

    expect(statsTotal()).toBeNull() // 症状：数字整块没了，页面什么都没说
    const error = document.querySelector('.app-load-error')
    expect(error?.textContent).toContain('反馈统计暂时读不出来，稍后重试')

    const before = calls.filter((c) => c.url === '/jobs/feedback/stats').length
    ;[...document.querySelectorAll('.app-load-error button')].at(-1)?.click()
    await flushPromises()
    expect(calls.filter((c) => c.url === '/jobs/feedback/stats').length).toBe(before + 1)
    wrapper.unmount()
  })

  it('反证：成功那一轮照常显示四个数字', async () => {
    const wrapper = await renderRecommend()
    await settle(lastOf('/jobs/feedback/stats'), {
      total: 7,
      like_count: 5,
      dislike_count: 2,
      avg_match_score: 81,
      like_rate: 0.71,
    })
    const values = [...document.querySelectorAll('.stats-value')].map((n) => n.textContent.trim())
    expect(values.slice(0, 3)).toEqual(['7', '5', '2'])
    wrapper.unmount()
  })
})
