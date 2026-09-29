import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import JobSearch from '@/features/jobs/views/JobSearch.vue'
import PipelinePane from '@/features/jobs/components/PipelinePane.vue'
import { installElement } from '@/plugins/element'

/* D44 把投递流程面板搬出 JobSearch.vue。数据仍归页面的 useJobPipeline，所以这条链上每一处跨边界的
   写都要走 emit：筛选、保存、切阶段、移除、打开详情、带入分析。
   这里逐条核对"事件确实接到了链上那个函数、参数顺序没写反"——写反不会报错，只会静默改错记录。
   规矩：交互前先断言元素真的存在。`find()` 找不到时返回的是空壳而不是报错，
   于是选错一个 selector 就变成"什么都没测还全绿"（本文件第一版就是这么红了 4 条）。 */

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

const entry = (id, stage, title, over = {}) => ({
  id,
  jd_id: 100 + id,
  title,
  company: '公司' + title,
  location: '北京',
  salary: '30-50K',
  stage,
  note: '',
  resume_name: '简历甲',
  updated_at: '2026-09-29T02:00:00Z',
  stage_history: [{ stage, at: '2026-09-29T02:00:00Z' }],
  ...over,
})

let router

async function renderSearch(entries) {
  api.resume.getResumeList.mockResolvedValue({ items: [{ id: 7, file_name: '简历甲' }] })
  api.resume.getResume.mockResolvedValue({ id: 7, parsed_json: {} })
  api.jobs.getCities.mockResolvedValue({ cities: [] })
  api.jobs.getJobList.mockResolvedValue({ items: [] })
  api.jobs.getJobRecommendations.mockResolvedValue({ recommendations: [] })
  api.jobs.searchExternalJobs.mockResolvedValue({ jobs: [] })
  api.jobs.getJobPipelineList.mockResolvedValue({ items: entries })

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
  const found = wrapper.findComponent(PipelinePane)
  expect(found, '投递流程面板没渲染出来，测试前提不成立').toBeTruthy()
  return found
}

const columnHeads = (wrapper) =>
  wrapper.findAll('.pipeline-column-head strong').map((n) => n.text())
const cardTitles = (wrapper) =>
  wrapper.findAll('.pipeline-card').map((c) => c.find('.pipeline-card-head h3').text())

function card(wrapper, title) {
  const found = wrapper
    .findAll('.pipeline-card')
    .find((c) => c.find('.pipeline-card-head h3').text() === title)
  expect(found, `卡片「${title}」没渲染出来，测试前提不成立`).toBeTruthy()
  return found
}

function buttonIn(scope, text) {
  const found = scope.findAll('button').find((b) => b.text().includes(text))
  expect(found, `「${text}」按钮没渲染出来，测试前提不成立`).toBeTruthy()
  return found
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  api.jobs.updateJobPipelineEntry.mockImplementation((id, body) => Promise.resolve({ id, ...body }))
  api.jobs.deleteJobPipelineEntry.mockResolvedValue({})
  api.jobs.clearRejectedJobPipeline.mockResolvedValue({ removed: 1, items: [] })
  api.jobs.startFullAnalysis.mockResolvedValue({})
})

describe('流程面板的跨边界写', () => {
  it('关键词筛选走 emit，父链的过滤照常生效', async () => {
    const wrapper = await renderSearch([
      entry(1, 'todo', '后端工程师'),
      entry(2, 'applied', '数据分析师'),
    ])
    expect(cardTitles(wrapper)).toEqual(['后端工程师', '数据分析师'])

    const search = pane(wrapper).find('.pipeline-search input')
    expect(search, '面板上的搜索框没渲染出来').toBeTruthy()
    await search.setValue('分析')
    await flushPromises()

    expect(wrapper.vm.pipelineFilters.keyword).toBe('分析')
    expect(cardTitles(wrapper)).toEqual(['数据分析师'])
    wrapper.unmount()
  })

  it('阶段药丸：点一枚看那一列，点另一枚是换列，再点当前这枚才回全部', async () => {
    const wrapper = await renderSearch([entry(1, 'todo', '甲岗'), entry(2, 'applied', '乙岗')])
    const pills = () => pane(wrapper).findAll('.pipeline-stage-pill')
    // 药丸那排永远列全四个阶段（它读的是 pipelineStages 常量），筛选只影响下面有几列
    expect(pills().map((x) => x.text())).toEqual(['1待投递', '1已投递', '0已约面', '0已淘汰'])

    await pills()[1].trigger('click')
    await flushPromises()
    expect(wrapper.vm.pipelineFilters.stage).toBe('applied')
    expect(columnHeads(wrapper)).toEqual(['已投递'])

    await pills()[0].trigger('click')
    await flushPromises()
    expect(wrapper.vm.pipelineFilters.stage, '点另一枚应当换成那一列').toBe('todo')

    await pills()[0].trigger('click')
    await flushPromises()
    expect(wrapper.vm.pipelineFilters.stage, '再点当前这枚才回全部').toBe('all')
    expect(columnHeads(wrapper)).toEqual(['待投递', '已投递', '已约面', '已淘汰'])
    wrapper.unmount()
  })

  it('改「下一步动作」要带着这条记录去保存，不能拿错对象', async () => {
    const wrapper = await renderSearch([entry(1, 'todo', '甲岗'), entry(2, 'applied', '乙岗')])

    const input = card(wrapper, '乙岗').find('input')
    expect(input, '卡片上找不到输入框').toBeTruthy()
    await input.setValue('周四前发定制简历')
    await flushPromises()

    expect(api.jobs.updateJobPipelineEntry).toHaveBeenCalledTimes(1)
    const [entryId, body] = api.jobs.updateJobPipelineEntry.mock.calls[0]
    expect(entryId).toBe(2)
    expect(body.title).toBe('乙岗')
    expect(body.next_action).toBe('周四前发定制简历')
    wrapper.unmount()
  })

  it('切阶段传的是 (这条记录, 新阶段)，参数写反就会把别的记录挪走', async () => {
    const wrapper = await renderSearch([entry(1, 'todo', '甲岗')])

    // 从卡片里那枚阶段下拉发 change，让**子组件模板里那句 $emit** 成为被测对象
    // （早先版本是 pane.vm.$emit(...) 直接抛事件，那样连"参数顺序写反"都测不出来——
    //   把一个 (entry, value) 改成 (value, entry) 的变异当时全绿，就是这么暴露的）
    const select = card(wrapper, '甲岗').findComponent({ name: 'ElSelect' })
    expect(select, '卡片上找不到阶段下拉').toBeTruthy()
    select.vm.$emit('change', 'interview')
    await flushPromises()

    expect(wrapper.vm.pipelineEntries[0].stage).toBe('interview')
    expect(api.jobs.updateJobPipelineEntry).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ stage: 'interview' })
    )
    wrapper.unmount()
  })

  it('移除只删这一条，其余留着', async () => {
    const wrapper = await renderSearch([entry(1, 'todo', '甲岗'), entry(2, 'applied', '乙岗')])

    await buttonIn(card(wrapper, '甲岗').find('.pipeline-actions'), '移除').trigger('click')
    await flushPromises()

    expect(api.jobs.deleteJobPipelineEntry).toHaveBeenCalledWith(1)
    expect(wrapper.vm.pipelineEntries.map((e) => e.entryId)).toEqual([2])
    wrapper.unmount()
  })

  it('「清理已淘汰」的禁用条件跟着淘汰数走，点了才打那一条接口', async () => {
    const wrapper = await renderSearch([entry(1, 'todo', '甲岗')])
    expect(buttonIn(pane(wrapper), '清理已淘汰').element.disabled, '一条淘汰都没有却可点').toBe(
      true
    )
    wrapper.unmount()

    const wrapper2 = await renderSearch([entry(3, 'rejected', '丙岗')])
    const clear = buttonIn(pane(wrapper2), '清理已淘汰')
    expect(clear.element.disabled).toBe(false)
    await clear.trigger('click')
    await flushPromises()
    expect(api.jobs.clearRejectedJobPipeline).toHaveBeenCalledTimes(1)
    wrapper2.unmount()
  })

  it('卡片上的「详情」开抽屉，「直接分析」带的是这条记录对应的岗位', async () => {
    const wrapper = await renderSearch([entry(1, 'todo', '甲岗', { jd_id: 55 })])
    const actions = card(wrapper, '甲岗').find('.pipeline-actions')

    await buttonIn(actions, '详情').trigger('click')
    await flushPromises()
    expect(wrapper.vm.detailVisible).toBe(true)

    // 不 spy 设置里的函数（模板调的是 setup 闭包本身，spy 拦不住），改看这条链真正打出去的参数
    await buttonIn(actions, '直接分析').trigger('click')
    await flushPromises()
    expect(
      api.jobs.startFullAnalysis,
      '直接分析要带这条记录的 jd_id 去启动，拿错就是分析另一个岗位'
    ).toHaveBeenCalledWith(7, 55)
    wrapper.unmount()
  })
})
