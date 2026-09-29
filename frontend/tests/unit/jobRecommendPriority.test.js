import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useJobRecommend } from '@/features/jobs/composables/useJobRecommend'

/* D42 把推荐链搬进 composable 时，城市筛选从"视图里隐式读一次"变成"父页面显式注入一个 ref"。
   这条耦合没有任何测试，用一个常量替换注入后 180 条全绿——所以下面这两条是这次搬运唯一的证据：
   第一条钉"命中城市确实加 8 分"，第二条钉的是**时机**：推荐卡的分数在 computed 里算，
   所以拖动搜索表单的城市筛选会立刻重算；而搜索页/仓库页的分数是取数那一刻存进列表的，要等下一次
   搜索。这个不对称是搬之前就有的行为，§10.18 正在决定要不要统一。若那边选了"城市不参与优先级"，
   该删的就是这两条。 */

const api = vi.hoisted(() => ({ getJobRecommendations: vi.fn() }))
vi.mock('@/api/jobs', () => api)

let city
let selectedResumeId
let market

const recommendation = (over = {}) => ({
  jd_id: 41,
  job_title: '后端工程师',
  company: '某公司',
  location: '北京',
  // 刻意选一份"离满分很远"的推荐：分数封顶 100，接近满分的卡片量不出那 8 分的差
  salary_range: '15K-20K',
  skill_overlap: ['Python'],
  skill_gap: [],
  ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  city = ref('')
  selectedResumeId = ref(7)
  market = useJobRecommend({ selectedResumeId, city })
})

describe('推荐卡的投递优先级', () => {
  it('命中表单上那个城市筛选就多 8 分，并把它写进理由', async () => {
    api.getJobRecommendations.mockResolvedValue({ recommendations: [recommendation()] })

    await market.loadRecommendations()
    city.value = ''
    const withoutCity = market.normalizedRecommendations.value[0]

    city.value = '北京'
    const withCity = market.normalizedRecommendations.value[0]

    expect(withCity.priorityScore - withoutCity.priorityScore).toBe(8)
    expect(withoutCity.priorityReason).not.toContain('城市匹配')
    expect(withCity.priorityReason).toContain('城市匹配')
  })

  it('分数随筛选即时重算，不需要重新请求（这是它与搜索页/仓库页不同的那一半）', async () => {
    api.getJobRecommendations.mockResolvedValue({ recommendations: [recommendation()] })
    await market.loadRecommendations()
    expect(api.getJobRecommendations).toHaveBeenCalledTimes(1)

    city.value = '北京'
    expect(market.normalizedRecommendations.value[0].priorityReason).toContain('城市匹配')

    city.value = '成都'
    expect(market.normalizedRecommendations.value[0].priorityReason).not.toContain('城市匹配')
    expect(api.getJobRecommendations, '改筛选不该发第二次请求').toHaveBeenCalledTimes(1)
  })

  it('没选简历就清空列表并作废在途的那一发', async () => {
    let resolve
    api.getJobRecommendations.mockReturnValue(
      new Promise((r) => {
        resolve = r
      })
    )
    const inFlight = market.loadRecommendations()
    expect(market.recommendLoading.value).toBe(true)

    selectedResumeId.value = null
    await market.loadRecommendations()
    resolve({ recommendations: [recommendation()] })
    await inFlight

    expect(market.recommendations.value).toEqual([])
    expect(market.normalizedRecommendations.value).toEqual([])
    expect(market.recommendLoading.value).toBe(false)
  })
})
