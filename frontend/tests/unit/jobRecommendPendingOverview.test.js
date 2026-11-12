import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobRecommend from '@/features/jobs/views/JobRecommend.vue'
import { installElement } from '@/plugins/element'

/* D4 在手机上量到的一幕：375 宽、首屏 2.2 秒时，「匹配概览」那一栏是 **0 / 0 / 0**，
   四个分段也都是 0，而内容区正转着"正在分析你的简历，智能匹配岗位..."。
   三秒后同一块地方变成 1 / 1 / 0，等于这块面板刚刚说了句假话——它不是"暂时没有数字"，
   它写的是"你没有匹配岗位"。

   这和 D3 收的那一族（失败 ≠ 空）是同一件事的两个面：**加载中 ≠ 空**。判据只有一条：
   `loading.recommend && !hasResults`，也就是"这一轮还没有任何结果落过屏"。
   反过来不能因为 loading 就把数抹掉：二次匹配时手里那份旧结果是真数，不是假数
   （所以下面第二条反着钉了一次）。 */
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

/** 选简历会立刻发一发匹配请求——它挂在 deferred 上，所以这一发"在途"由我们来定。 */
async function selectResumeAndStartMatching(wrapper) {
  const select = wrapper.findComponent('.el-select')
  select.vm.$emit('update:modelValue', 7)
  select.vm.$emit('change', 7)
  await flushPromises()
  const request = lastOf('/jobs/recommend')
  expect(request, '选完简历没有发起匹配请求，测试前提不成立').toBeTruthy()
  return request
}

const overviewNumbers = () =>
  [...document.querySelectorAll('.job-overview-stats strong')].map((n) => n.textContent.trim())
const bucketNumbers = () =>
  [...document.querySelectorAll('.job-buckets em')].map((n) => n.textContent.trim())
const toolbarCount = () => document.querySelector('.job-toolbar-count')?.textContent.trim() ?? null

beforeEach(() => {
  document.body.innerHTML = ''
  calls.length = 0
})

describe('匹配还没回来时，概览不许写 0', () => {
  it('在途：三个数与四个分段都显示"—"，工具条说"正在匹配…"', async () => {
    const wrapper = await renderRecommend()
    await selectResumeAndStartMatching(wrapper)

    expect(overviewNumbers(), '在途时这几个位置写的是 0：那就是在说"你没有匹配岗位"').toEqual([
      '—',
      '—',
      '—',
    ])
    expect(bucketNumbers()).toEqual(['—', '—', '—', '—'])
    expect(toolbarCount()).toBe('正在匹配…')
    wrapper.unmount()
  })

  it('结果落地之后换回真数，而且"正在匹配…"退场', async () => {
    const wrapper = await renderRecommend()
    await selectResumeAndStartMatching(wrapper)
    await settle(lastOf('/jobs/recommend'), {
      recommendations: [
        { jd_id: 101, job_title: '岗位-A', company: '公司', match_score: 86 },
        { jd_id: 102, job_title: '岗位-B', company: '公司', match_score: 62 },
      ],
    })
    await settle(lastOf('/jobs/pipeline/list'), { items: [] })
    await settle(lastOf('/jobs/bookmarks/list'), { items: [] })

    expect(overviewNumbers()).toEqual(['2', '1', '0'])
    expect(toolbarCount()).toBe('2 个岗位 · 1 个优先')
    expect(bucketNumbers()).not.toContain('—')
    wrapper.unmount()
  })

  /* 反向的那一半：`loading && !hasResults` 里的 `!hasResults` 不是装饰。
     已经有结果时再匹配一次（重新匹配），旧数照旧显示——把它一起抹成"—"，
     等于每次微调筛选都把已经算出来的结论藏起来一次。 */
  it('手里已有结果时不抹数：二次匹配期间旧结果照旧读得出来', async () => {
    const wrapper = await renderRecommend()
    await selectResumeAndStartMatching(wrapper)
    await settle(lastOf('/jobs/recommend'), {
      recommendations: [{ jd_id: 101, job_title: '岗位-A', company: '公司', match_score: 86 }],
    })
    await settle(lastOf('/jobs/pipeline/list'), { items: [] })
    await settle(lastOf('/jobs/bookmarks/list'), { items: [] })
    expect(overviewNumbers()).toEqual(['1', '1', '0'])

    // 手动再匹配一次：这一发挂在 deferred 上，此刻 recommendations 里仍是上一轮的结果
    const again = await pageEmitRematch(wrapper)
    if (again) {
      expect(overviewNumbers(), '二次匹配把已有的真数也抹成"—"了').toEqual(['1', '1', '0'])
      await settle(again, { recommendations: [] })
    }
    wrapper.unmount()
  })
})

/** 点「重新匹配」（页面上那颗刷新按钮）。没有这一颗就直接跳过——判据本身已经由前两条钉住。 */
async function pageEmitRematch(wrapper) {
  const before = calls.filter((c) => c.url === '/jobs/recommend').length
  const button = wrapper.findAll('button').find((b) => b.text().includes('重新匹配'))
  if (!button) return null
  await button.trigger('click')
  await flushPromises()
  const after = calls.filter((c) => c.url === '/jobs/recommend').length
  return after > before ? lastOf('/jobs/recommend') : null
}
