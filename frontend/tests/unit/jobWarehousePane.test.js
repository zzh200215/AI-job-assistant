import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobSearch from '@/features/jobs/views/JobSearch.vue'
import WarehousePane from '@/features/jobs/components/WarehousePane.vue'
import { installElement } from '@/plugins/element'

/* D44 把岗位仓库面板搬出 JobSearch.vue。风险不在模板，在筛选那条回路换了形状：
   以前是 `v-model="warehouseFilters.keyword"` 直接改父页面那个 ref 的一个字段，
   现在是子组件抛 `update:filters`（整份新对象）→ 父页面把 `warehouseFilters` 整个换掉。
   所以这里测的是"在页面上打字，列表真的跟着变"，以及清空时给的是空串而不是 undefined
   （undefined 会让 `!warehouseFilters.value.keyword` 之外的那些读法变形）。 */

const api = vi.hoisted(() => ({
  jobs: {
    getCities: vi.fn(),
    getJobList: vi.fn(),
    getJobPipelineList: vi.fn(),
    getJobRecommendations: vi.fn(),
    searchExternalJobs: vi.fn(),
    seedDemoJobs: vi.fn(),
    startFullAnalysis: vi.fn(),
    getJobDetail: vi.fn(),
    createJobPipelineEntry: vi.fn(),
    updateJobPipelineEntry: vi.fn(),
    deleteJobPipelineEntry: vi.fn(),
    clearRejectedJobPipeline: vi.fn(),
  },
  resume: { getResumeList: vi.fn(), getResume: vi.fn() },
  analysis: { explainMatch: vi.fn() },
  knowledge: { queryRewriteTest: vi.fn() },
}))

vi.mock('@/api/jobs', () => api.jobs)
vi.mock('@/api/resume', () => api.resume)
vi.mock('@/api/analysis', () => api.analysis)
vi.mock('@/api/knowledge', () => api.knowledge)

const job = (id, title, over = {}) => ({
  id,
  title,
  company: '公司' + title,
  location: '北京',
  salary: '30-50K',
  source: 'local',
  industry: '互联网',
  ...over,
})

let router

async function renderSearch(items) {
  api.resume.getResumeList.mockResolvedValue({ items: [] })
  api.resume.getResume.mockResolvedValue({ id: 7, parsed_json: {} })
  api.jobs.getCities.mockResolvedValue({ cities: [] })
  api.jobs.getJobPipelineList.mockResolvedValue({ entries: [] })
  api.jobs.getJobRecommendations.mockResolvedValue({ recommendations: [] })
  api.jobs.searchExternalJobs.mockResolvedValue({ jobs: [] })
  api.jobs.getJobList.mockResolvedValue({ items })

  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/jobs/search', name: 'job-search', component: { template: '<div />' } }],
  })
  router.push('/jobs/search')
  await router.isReady()
  const wrapper = mount(JobSearch, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

function pane(wrapper) {
  const found = wrapper.findComponent(WarehousePane)
  expect(found, '仓库面板没渲染出来，测试前提不成立').toBeTruthy()
  return found
}

function visibleTitles(wrapper) {
  return pane(wrapper)
    .findAll('.warehouse-title-row h3')
    .map((n) => n.text())
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('仓库面板的筛选回路', () => {
  it('在页面上打字，列表跟着缩，父页面的筛选对象被整份换掉', async () => {
    const wrapper = await renderSearch([
      job(1, '后端工程师'),
      job(2, '数据分析师'),
      job(3, '前端工程师', { source: 'crawled', industry: '金融' }),
    ])
    expect(visibleTitles(wrapper)).toEqual(['后端工程师', '数据分析师', '前端工程师'])

    await pane(wrapper).find('input').setValue('工程师')
    await flushPromises()
    expect(visibleTitles(wrapper)).toEqual(['后端工程师', '前端工程师'])

    // 行业框是第三个控件里的输入；这里直接用面板抛出的负载核对"没被改的那两格保持原值"
    pane(wrapper).vm.$emit('update:filters', { keyword: '工程师', source: 'crawled', industry: '' })
    await flushPromises()
    expect(visibleTitles(wrapper)).toEqual(['前端工程师'])

    pane(wrapper).vm.$emit('update:filters', { keyword: '', source: '', industry: '金融' })
    await flushPromises()
    expect(visibleTitles(wrapper), '仓库筛行业是包含匹配，「金融」要能命中「金融」这条').toEqual([
      '前端工程师',
    ])
    wrapper.unmount()
  })

  it('清空筛选框时抛出的是空串，不是 undefined', async () => {
    const wrapper = await renderSearch([job(1, '后端工程师')])
    const input = pane(wrapper).find('input')

    await input.setValue('后端')
    await flushPromises()
    expect(visibleTitles(wrapper)).toEqual(['后端工程师'])

    await input.setValue('')
    await flushPromises()
    expect(visibleTitles(wrapper), '清空后列表要回到全量').toEqual(['后端工程师'])

    const emitted = pane(wrapper).emitted('update:filters').at(-1)[0]
    expect(emitted.keyword).toBe('')
    expect(Object.keys(emitted).sort()).toEqual(['industry', 'keyword', 'source'])
    wrapper.unmount()
  })

  it('「刷新仓库」仍然打到仓库链自己身上，而不是面板里另起一发', async () => {
    const wrapper = await renderSearch([job(1, '后端工程师')])
    const before = api.jobs.getJobList.mock.calls.length

    const button = pane(wrapper)
      .findAll('button')
      .find((b) => b.text().includes('刷新仓库'))
    expect(button, '刷新按钮没渲染出来').toBeTruthy()
    await button.trigger('click')
    await flushPromises()

    expect(api.jobs.getJobList.mock.calls.length).toBe(before + 1)
    wrapper.unmount()
  })

  it('失败态与空仓库仍是两块不同的屏幕（搬走时最容易合并的一对分支）', async () => {
    const wrapper = await renderSearch([job(1, '后端工程师')])
    expect(pane(wrapper).find('.warehouse-list').exists()).toBe(true)

    api.jobs.getJobList.mockRejectedValue({ userMessage: '岗位库暂时读不到' })
    await pane(wrapper).vm.$emit('refresh')
    await flushPromises()

    expect(pane(wrapper).find('.warehouse-list').exists()).toBe(false)
    expect(pane(wrapper).text()).toContain('本地岗位仓库加载失败')
    expect(pane(wrapper).text()).not.toContain('岗位仓库还是空的')
    wrapper.unmount()
  })
})
