import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobRecommend from '@/features/jobs/views/JobRecommend.vue'
import { installElement } from '@/plugins/element'

/* §10.5 落地的第一处屏幕：推荐卡上那颗"优先投递"徽章与顶部那个计数。
   改之前它写的是 `job.match_score >= 80`，而后端给同一张卡的推荐标签在 70–84 这段是"可以投递"
   （`match_explainer_service.py:530-533`）——82 分的卡会同时挂着"优先投递"徽章和"可以投递"标签。
   现在两处都走 `isTopTier`（顶档 85）。这里喂一对 82 / 85 的卡片，量的是徽章只剩一颗、
   hero 那个数字跟着只剩 1，而"匹配岗位"那颗总数不动。 */

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
  await settle(lastOf('/resume/list'), { items: [{ id: 7, name: '简历甲' }] })
  return wrapper
}

async function loadCards() {
  const wrapper = await renderRecommend()
  const select = wrapper.findComponent('.el-select')
  select.vm.$emit('update:modelValue', 7)
  select.vm.$emit('change', 7)
  await flushPromises()
  await settle(lastOf('/jobs/recommend'), {
    recommendations: [
      { jd_id: 101, job_title: '岗位-A', company: '公司', match_score: 82 },
      { jd_id: 102, job_title: '岗位-B', company: '公司', match_score: 85 },
    ],
  })
  await settle(lastOf('/jobs/pipeline/list'), { items: [] })
  await settle(lastOf('/jobs/bookmarks/list'), { items: [] })
  return wrapper
}

function metric(tagText) {
  const cell = [...document.querySelectorAll('.brief-metrics > div')].find((d) =>
    d.querySelector('span')?.textContent.includes(tagText)
  )
  return cell?.querySelector('b')?.textContent.trim() ?? null
}

const badges = () =>
  [...document.querySelectorAll('.el-tag')].filter((t) => t.textContent.includes('优先投递')).length

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
  localStorage.clear()
})

describe('推荐页的优先投递线跟随顶档 85', () => {
  it('82 分那张不再挂徽章，85 分那张挂着；hero 的计数一起跟着', async () => {
    const wrapper = await loadCards()
    expect(metric('匹配岗位'), '两张卡都该画出来').toBe('2')
    expect(badges()).toBe(1)
    expect(metric('优先投递')).toBe('1')
    wrapper.unmount()
  })

  it('反向证据：两张都在顶档之上时，徽章与计数都是二', async () => {
    const wrapper = await renderRecommend()
    const select = wrapper.findComponent('.el-select')
    select.vm.$emit('update:modelValue', 7)
    select.vm.$emit('change', 7)
    await flushPromises()
    await settle(lastOf('/jobs/recommend'), {
      recommendations: [
        { jd_id: 101, job_title: '岗位-A', company: '公司', match_score: 85 },
        { jd_id: 102, job_title: '岗位-B', company: '公司', match_score: 88 },
      ],
    })
    await settle(lastOf('/jobs/pipeline/list'), { items: [] })
    await settle(lastOf('/jobs/bookmarks/list'), { items: [] })
    expect(badges()).toBe(2)
    expect(metric('优先投递')).toBe('2')
    wrapper.unmount()
  })
})
