import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useJobSearch } from '@/features/jobs/composables/useJobSearch'

/* D41 把「实时搜索」那条链整体搬进 composable：表单、结果列表、结果口径的三段文案、筛选与排序。
   竞态那半边不在这里测——`jobSearchRace.test.js` 是从页面点的，令牌搬过去之后它照样红（连点两个
   快速搜索词那一条就是它的对照组）。这里补的是搬过去之后**没有任何测试**的另一半：归一写入、
   三个筛选器与三种排序、以及"这一屏此刻说什么"。 */

const api = vi.hoisted(() => ({
  getCities: vi.fn(),
  searchExternalJobs: vi.fn(),
}))
const notify = vi.hoisted(() => ({ warning: vi.fn() }))

vi.mock('@/api/jobs', () => api)
vi.mock('@/plugins/element-services', () => ({ ElMessage: notify }))

const raw = (over = {}) => ({
  id: 1,
  title: '后端工程师',
  company: '某公司',
  location: '北京',
  salary_range: '25K-35K',
  experience_requirement: '3-5年',
  education_requirement: '本科',
  skill_tags: ['Python', 'Go', 'K8s'],
  jd_summary: '负责服务端',
  source: 'boss',
  ...over,
})

let market
let pushRecent

beforeEach(() => {
  vi.clearAllMocks()
  api.getCities.mockResolvedValue({ cities: [{ name: '北京', code: '110000' }] })
  pushRecent = vi.fn()
  market = useJobSearch({ pushRecentSearch: pushRecent })
})

describe('搜索链：结果写入', () => {
  it('一次成功搜索把 JD 归一、按返回口径写好四个状态，并把关键词交给历史', async () => {
    api.searchExternalJobs.mockResolvedValue({
      jobs: [raw(), raw({ id: 2, title: '算法工程师', source: 'local' })],
      saved_count: 1,
      result_mode: 'external',
      is_demo: false,
    })

    await market.runSearch()

    expect(api.searchExternalJobs).toHaveBeenCalledWith({
      keyword: 'Python',
      city: '',
      source: 'boss',
      page: 1,
    })
    expect(market.externalJobs.value.length).toBe(2)
    // 归一后的形状：uid 带 search- 前缀、薪资取 salary_range、学历来自 education_requirement、来源可信
    expect(market.externalJobs.value[0]).toMatchObject({
      uid: 'search-0-1',
      salary: '25K-35K',
      education: '本科',
      experience: '3-5年',
      summary: '负责服务端',
      local: false,
    })
    // source=local 的那一条要能被带进分析，所以 local 为真
    expect(market.externalJobs.value[1].local).toBe(true)
    expect(market.savedCount.value).toBe(1)
    expect(market.resultMode.value).toBe('external')
    expect(market.hasSearched.value).toBe(true)
    expect(market.searching.value).toBe(false)
    expect(market.searchError.value).toBe('')
    expect(pushRecent).toHaveBeenCalledWith('Python')
  })

  it('接口返回 error 字段时说出来，而不是留一条空列表装作没事', async () => {
    api.searchExternalJobs.mockResolvedValue({
      jobs: [],
      error: '外部渠道今日限流',
      result_mode: 'local_fallback',
    })

    await market.runSearch()

    expect(market.externalJobs.value).toEqual([])
    expect(market.searchError.value).toBe('外部渠道今日限流')
    expect(market.resultMode.value).toBe('local_fallback')
    expect(market.searchStateText.value).toBe('本地职位库')
    expect(market.sourceBannerTitle.value).toBe('当前展示本地职位库')
    expect(market.sourceBannerClass.value).toBe('is-local')
  })

  it('演示兜底要说成演示，且它压过 result_mode 的口径', async () => {
    api.searchExternalJobs.mockResolvedValue({
      jobs: [raw()],
      result_mode: 'external',
      is_demo: true,
    })

    await market.runSearch()

    expect(market.isDemo.value).toBe(true)
    expect(market.searchStateText.value).toBe('演示数据')
    expect(market.sourceBannerClass.value).toBe('is-demo')
  })

  it('请求抛错时清空结果并给出可行动的失败文案，但不写历史', async () => {
    api.searchExternalJobs.mockResolvedValue({ jobs: [raw()] })
    await market.runSearch()
    expect(market.externalJobs.value.length).toBe(1)

    api.searchExternalJobs.mockRejectedValue(new Error('network down'))
    await market.runSearch()

    expect(market.externalJobs.value).toEqual([])
    expect(market.searchError.value).toBe('搜索失败，请稍后重试')
    expect(market.resultMode.value).toBe('')
    expect(market.searching.value).toBe(false)
    expect(pushRecent).toHaveBeenCalledTimes(1)
  })

  it('关键词为空就不发请求，只提示一次', async () => {
    market.keyword.value = '   '

    await market.runSearch()

    expect(api.searchExternalJobs).not.toHaveBeenCalled()
    expect(notify.warning).toHaveBeenCalledWith('请输入搜索关键词')
    expect(market.hasSearched.value).toBe(false)
  })
})

describe('搜索链：筛选与排序', () => {
  const cards = [
    raw({
      id: 1,
      salary_range: '50K-80K',
      experience_requirement: '5年以上',
      skill_tags: ['Python'],
    }),
    raw({
      id: 2,
      salary_range: '15K-20K',
      experience_requirement: '1-3年',
      education_requirement: '大专',
      skill_tags: ['Vue', 'TS', 'CSS', 'Node'],
    }),
    raw({ id: 3, salary_range: '30K-45K', experience_requirement: '3-5年', skill_tags: [] }),
  ]

  beforeEach(async () => {
    api.searchExternalJobs.mockResolvedValue({ jobs: cards, result_mode: 'external' })
    await market.runSearch()
    expect(market.externalJobs.value.length).toBe(3)
  })

  it('经验与学历是包含匹配，技能同时看技能标签和摘要', () => {
    market.searchFilters.value.experience = '3-5'
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([3])

    market.searchFilters.value = { experience: '', education: '大专', skill: '' }
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([2])

    market.searchFilters.value = { experience: '', education: '', skill: 'python' }
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([1])

    market.searchFilters.value.skill = '服务端'
    expect(
      market.filteredExternalJobs.value.map((j) => j.id),
      '技能框搜不到摘要里的词，就等于把一个已知条件当成了筛不出的项'
    ).toEqual([1, 2, 3])
  })

  it('排序默认保持返回顺序，薪资两向与技能数量各按自己的口径', () => {
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([1, 2, 3])

    market.searchSort.value = 'salary_desc'
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([1, 3, 2])

    market.searchSort.value = 'salary_asc'
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([2, 3, 1])

    market.searchSort.value = 'skill_desc'
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([2, 1, 3])
  })

  it('清筛选把三个框与排序一起回零', () => {
    market.searchFilters.value = { experience: '3-5', education: '大专', skill: 'python' }
    market.searchSort.value = 'salary_desc'

    market.resetSearchFilters()

    expect(market.searchFilters.value).toEqual({ experience: '', education: '', skill: '' })
    expect(market.searchSort.value).toBe('default')
    expect(market.filteredExternalJobs.value.map((j) => j.id)).toEqual([1, 2, 3])
  })
})

describe('搜索链：表单口径', () => {
  it('未搜索时说的是"未搜索"，而不是把默认关键词当成结果', () => {
    expect(market.searching.value).toBe(false)
    expect(market.searchStateText.value).toBe('未搜索')
    expect(market.sourceBannerTitle.value).toBe('优先展示真实岗位结果')
    expect(market.sourceBannerClass.value).toBe('is-live')
    expect(market.filteredExternalJobs.value).toEqual([])
  })

  it('换个词再搜：关键词写进表单并且真的发了一次请求', async () => {
    api.searchExternalJobs.mockResolvedValue({ jobs: [raw({ title: '前端架构' })] })

    market.searchWithKeyword('前端架构')
    await vi.waitFor(() => expect(market.searching.value).toBe(false))

    expect(market.keyword.value).toBe('前端架构')
    expect(api.searchExternalJobs).toHaveBeenCalledTimes(1)
    expect(api.searchExternalJobs.mock.calls[0][0].keyword).toBe('前端架构')
    expect(market.externalJobs.value[0].title).toBe('前端架构')
  })

  it('城市选项取接口的，接口没给就是空列表（兜底那份写死城市是 loadCities 自己的 catch）', async () => {
    await market.loadCities()
    expect(market.cities.value).toEqual([{ name: '北京', code: '110000' }])

    api.getCities.mockRejectedValue(new Error('boom'))
    await market.loadCities()
    expect(market.cities.value.map((c) => c.name)).toEqual([
      '北京',
      '上海',
      '深圳',
      '杭州',
      '广州',
      '全国',
    ])
  })
})
