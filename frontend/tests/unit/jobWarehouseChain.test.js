import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useJobWarehouse } from '@/features/jobs/composables/useJobWarehouse'

/* D43 把岗位仓库那条链搬进 composable。搬之前它没有任何测试：把"行业包含匹配"改成相等比较，
   185 条全绿——所以这一份不是补充说明，是这条链唯一的覆盖。
   第 4 条钉的是与推荐链相反的那一半：仓库卡的分数是取数那一刻算好存下的，换城市筛选**不会**重算，
   要等下一次刷新。两条对照放在一起，§10.18 那个"要不要统一求值时机"的决定才有代价可看。 */

const api = vi.hoisted(() => ({ getJobList: vi.fn() }))
vi.mock('@/api/jobs', () => api)

let city
let warehouse

const raw = (over = {}) => ({
  id: 1,
  title: '后端工程师',
  company: '某公司',
  location: '北京',
  salary_range: '25K-35K',
  industry: '互联网/AI',
  skill_tags: ['Python', 'Go'],
  jd_summary: '负责服务端',
  source: 'local',
  ...over,
})

async function load(items) {
  api.getJobList.mockResolvedValue({ items })
  await warehouse.loadLocalJobs()
}

beforeEach(() => {
  vi.clearAllMocks()
  city = ref('')
  warehouse = useJobWarehouse({ city })
})

describe('仓库列表的归一', () => {
  it('按请求那一刻的城市算优先级，uid 带 local- 前缀，落库来源都算本地', async () => {
    city.value = '北京'
    await load([raw(), raw({ id: 2, title: '算法', source: 'crawled', _local_db: true })])

    expect(api.getJobList).toHaveBeenCalledWith({ page: 1, page_size: 100 })
    expect(warehouse.localJobs.value[0]).toMatchObject({
      uid: 'local-0-1',
      salary: '25K-35K',
      industry: '互联网/AI',
      summary: '负责服务端',
      local: true,
    })
    // 城市命中加 8 分并写进理由（此刻 city 是"北京"，卡片地点也是北京）
    expect(warehouse.localJobs.value[0].priorityReason).toContain('城市匹配')
    // source=crawled 但带 _local_db 标记，同样可以直接带去分析
    expect(warehouse.localJobs.value[1].local).toBe(true)
    expect(warehouse.localError.value).toBe('')
    expect(warehouse.localLoading.value).toBe(false)
  })

  it('GET 失败要说出来，不能把仓库演成空的', async () => {
    await load([raw()])
    expect(warehouse.localJobs.value.length).toBe(1)

    api.getJobList.mockRejectedValue({ userMessage: '岗位库暂时读不到' })
    await warehouse.loadLocalJobs()

    expect(warehouse.localJobs.value).toEqual([])
    expect(warehouse.localError.value).toBe('岗位库暂时读不到')
    expect(warehouse.localLoading.value).toBe(false)
  })
})

describe('仓库的三个筛选框', () => {
  const cards = [
    raw({ id: 1, title: '后端工程师', company: '甲厂', location: '北京', industry: '互联网/AI' }),
    raw({ id: 2, title: '数据分析师', company: '乙厂', location: '上海', industry: '金融' }),
    raw({ id: 3, title: '前端工程师', company: '丙厂', location: '杭州', industry: '互联网/电商' }),
  ]

  beforeEach(async () => {
    await load(cards)
    expect(warehouse.localJobs.value.length).toBe(3)
  })

  it('关键词同时命中标题、公司、地点与摘要', () => {
    warehouse.warehouseFilters.value.keyword = '后端'
    expect(warehouse.filteredLocalJobs.value.map((j) => j.id)).toEqual([1])

    warehouse.warehouseFilters.value.keyword = '乙厂'
    expect(warehouse.filteredLocalJobs.value.map((j) => j.id)).toEqual([2])

    warehouse.warehouseFilters.value.keyword = '杭州'
    expect(warehouse.filteredLocalJobs.value.map((j) => j.id)).toEqual([3])

    warehouse.warehouseFilters.value.keyword = '服务端'
    expect(
      warehouse.filteredLocalJobs.value.map((j) => j.id).length,
      '摘要里有的词筛不出来，等于"搜了却说没有"'
    ).toBe(3)
  })

  it('来源是精确匹配，行业是包含匹配', () => {
    warehouse.warehouseFilters.value.source = 'local'
    expect(warehouse.filteredLocalJobs.value.length).toBe(3)

    warehouse.warehouseFilters.value.source = 'boss'
    expect(warehouse.filteredLocalJobs.value).toEqual([])

    warehouse.warehouseFilters.value = { keyword: '', source: '', industry: '互联网' }
    expect(warehouse.filteredLocalJobs.value.map((j) => j.id)).toEqual([1, 3])
  })

  it('三个框是且的关系', () => {
    warehouse.warehouseFilters.value = { keyword: '工程师', source: 'local', industry: '互联网' }
    expect(warehouse.filteredLocalJobs.value.map((j) => j.id)).toEqual([1, 3])

    warehouse.warehouseFilters.value.keyword = '前端'
    expect(warehouse.filteredLocalJobs.value.map((j) => j.id)).toEqual([3])
  })
})

describe('仓库卡分数的求值时机（与推荐链对照）', () => {
  it('换城市筛选不重算，要等下一次加载', async () => {
    city.value = ''
    await load([raw({ location: '北京' })])
    const before = warehouse.localJobs.value[0]
    expect(before.priorityReason).not.toContain('城市匹配')

    city.value = '北京'
    expect(
      warehouse.localJobs.value[0].priorityReason,
      '仓库卡的分数若在渲染时随筛选重算，就和推荐链一个样了——§10.18 要统一的是这两条'
    ).not.toContain('城市匹配')

    await load([raw({ location: '北京' })])
    expect(warehouse.localJobs.value[0].priorityReason).toContain('城市匹配')
  })
})
