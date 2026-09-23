import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobRecommend from '@/views/JobRecommend.vue'
import { installElement } from '@/plugins/element'

/* 岗位推荐页一次 `loadRecommendations` 里串着**三个** await：推荐列表 → 投递状态 → 收藏状态。
   换简历/改筛选都会重发这一串，而三处都是 await 后直接写：
   - 列表：旧简历的慢响应会把新简历的列表整块换掉；
   - 两个回填更糟——它们遍历的是"此刻屏幕上的那张列表"，所以旧那一轮的投递/收藏标记会盖到
     新简历的卡片上，`已加入看板` 与 `优先投递` 两个数字跟着错。 */
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
      const record = { url, arg: config?.params, ...deferred() }
      calls.push(record)
      return record.promise
    }),
    post: vi.fn(() => {
      const record = { url: 'post', ...deferred() }
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

function jobs(tag) {
  return {
    recommendations: [
      {
        jd_id: tag === 'A' ? 101 : 201,
        job_title: `岗位-${tag}`,
        company: '公司',
        match_score: 86,
      },
    ],
  }
}

/**
 * 一轮 `loadRecommendations` 是三个串联请求，列表要等整串跑完才会显示（loading 期间卡片块是隐藏的），
 * 所以"发完一轮"必须把三条都落地。
 */
async function finishRun(listRecord, tag, pipelineItems = [], bookmarkItems = []) {
  await settle(listRecord, jobs(tag))
  await settle(lastOf('/jobs/pipeline/list'), { items: pipelineItems })
  await settle(lastOf('/jobs/bookmarks/list'), { items: bookmarkItems })
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
  await settle(lastOf('/resume/list'), {
    items: [
      { id: 7, name: '简历甲', parsed: { current_title: '后端工程师' } },
      { id: 8, name: '简历乙', parsed: { current_title: '数据分析师' } },
    ],
  })
  await settle(lastOf('/jobs/feedback/stats'), { by_type: {}, total: 0 })
  await flushPromises()
  return wrapper
}

async function selectResume(wrapper, id) {
  const select = wrapper.findComponent('.el-select')
  select.vm.$emit('update:modelValue', id)
  select.vm.$emit('change', id)
  await flushPromises()
}

function titles() {
  return [...document.querySelectorAll('.job-title')].map((n) => n.textContent.trim())
}

function cardBadges() {
  return [...document.querySelectorAll('.job-title-row .el-tag')].map((n) => n.textContent.trim())
}

function briefNumbers() {
  return [...document.querySelectorAll('.brief-metrics b')].map((n) => n.textContent.trim())
}

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
  localStorage.clear()
})

describe('岗位推荐：旧那一轮的列表与标记都不能盖到新那一轮上', () => {
  it('换简历后，慢回来的旧列表不能把新列表整块换掉', async () => {
    const wrapper = await renderRecommend()
    await selectResume(wrapper, 7)
    const oldList = lastOf('/jobs/recommend')

    await selectResume(wrapper, 8)
    const newList = lastOf('/jobs/recommend')
    expect(newList).toBeTruthy()
    expect(newList).not.toBe(oldList)

    await finishRun(newList, 'B')
    expect(titles()).toEqual(['岗位-B'])

    await finishRun(oldList, 'A')
    expect(titles()).toEqual(['岗位-B'])
    wrapper.unmount()
  })

  it('旧那一轮的投递/收藏回填不能盖到新简历的卡片上', async () => {
    const wrapper = await renderRecommend()

    await selectResume(wrapper, 7)
    const aList = lastOf('/jobs/recommend')
    await settle(aList, jobs('A')) // A 的列表落地，A 的投递状态还挂在天上
    const aPipeline = lastOf('/jobs/pipeline/list')
    expect(aPipeline).toBeTruthy()

    await selectResume(wrapper, 8) // 换人：整串重发，并且 B 这一轮先跑完（无投递、无收藏）
    await finishRun(lastOf('/jobs/recommend'), 'B')
    expect(titles()).toEqual(['岗位-B'])
    expect(cardBadges()).not.toContain('已投递')

    await settle(aPipeline, { items: [{ jd_id: 201 }] }) // A 的投递状态最后才到，内容指向 B 的卡片
    const aBookmarks = lastOf('/jobs/bookmarks/list')
    expect(aBookmarks).toBeTruthy()
    await settle(aBookmarks, { items: [{ jd_id: 201 }] })

    expect(cardBadges()).not.toContain('已投递')
    expect(cardBadges()).not.toContain('已收藏')
    expect(briefNumbers()[2]).toBe('0') // 摘要里的「已加入看板」不能被旧轮次撑起来
    wrapper.unmount()
  })

  it('反证：同一轮的投递状态必须照常打上（令牌不能把回填整个废掉）', async () => {
    const wrapper = await renderRecommend()
    await selectResume(wrapper, 7)
    await finishRun(lastOf('/jobs/recommend'), 'A', [{ jd_id: 101 }], [{ jd_id: 101 }])

    expect(cardBadges()).toContain('已投递')
    expect(cardBadges()).toContain('已收藏')
    expect(briefNumbers()[2]).toBe('1')
    wrapper.unmount()
  })

  it('丢弃旧响应不能把加载状态卡住', async () => {
    const wrapper = await renderRecommend()
    await selectResume(wrapper, 7)
    const oldList = lastOf('/jobs/recommend')

    await selectResume(wrapper, 8)
    await finishRun(lastOf('/jobs/recommend'), 'B')
    expect(wrapper.vm.loading.recommend).toBe(false)

    await settle(oldList, jobs('A')) // 旧的那次随后才回
    expect(wrapper.vm.loading.recommend).toBe(false)
    wrapper.unmount()
  })
})
