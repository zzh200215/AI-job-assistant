import { computed, ref } from 'vue'
import { userErrorCopy } from '@/utils/requestTracing'
import { getJobRecommendations } from '@/api/jobs'
import { useLatestCall } from '@/composables/useLatestCall'
import { calculateApplicationPriority, uniqueList } from '@/features/jobs/lib/jobModel'

/* 智能推荐那条链：按当前简历要 12 条推荐，再把后端那份子对象归一成卡片形状。
   `city` 是从实时搜索那条链注入的——推荐卡片的优先级里有 8 分是"命中界面上的城市筛选"，
   这条耦合在搬之前就一直存在（且只在推荐这一侧随筛选即时重算，另两页要等下一次取数），
   是否该保留是 §10.18 的决定，这里只把它写成看得见的参数。 */

export function useJobRecommend({ selectedResumeId, city }) {
  const recommendLoading = ref(false)
  const recommendations = ref([])
  // 推荐取不到 ≠ 没有贴合的推荐：清空列表会命中"还没有足够贴合的推荐结果，可以先补充岗位池"
  const recommendError = ref('')
  const recommendFilters = ref({
    location: '',
    industry: '',
  })
  const latestRecommendCall = useLatestCall()

  const normalizedRecommendations = computed(() =>
    recommendations.value.map((item, index) => {
      const normalized = {
        uid: `recommend-${item.jd_id || index}`,
        id: item.jd_id || null,
        title: item.job_title || '推荐岗位',
        company: item.company || '未知公司',
        location: item.location || '',
        salary: item.salary_range || '薪资面议',
        industry: item.industry || '',
        summary: item.match_reason || '',
        rawText: '',
        source: 'recommend',
        sourceUrl: '',
        local: true,
        experience: '',
        education: '',
        skillTags: uniqueList([...(item.skill_overlap || []), ...(item.skill_gap || [])]),
        skillOverlap: item.skill_overlap || [],
        skillGap: item.skill_gap || [],
        matchScore: item.match_score || 0,
        recommendationType: item.recommendation_type || '值得一试',
        matchReason: item.match_reason || '',
        salaryMatch: item.salary_match !== false,
        locationMatch: item.location_match !== false,
        experienceMatch: item.experience_match !== false,
        compareText: item.match_reason || '',
      }
      const priority = calculateApplicationPriority(normalized, city.value)
      return { ...normalized, ...priority }
    })
  )

  async function loadRecommendations() {
    // 令牌在进入时领取：新一次的意图（含"没选简历所以清空"）都应作废仍在途的旧请求
    const isCurrent = latestRecommendCall()
    recommendError.value = ''
    if (!selectedResumeId.value) {
      recommendations.value = []
      // 解 loading 也必须在这里做：旧那一发的 finally 带着 `isCurrent()`，它已经过期了，
      // 这一支又不进 try/finally，不写就会让转圈永久停不下来。
      recommendLoading.value = false
      return
    }
    recommendLoading.value = true
    try {
      const params = {
        resume_id: selectedResumeId.value,
        limit: 12,
      }
      if (recommendFilters.value.location) params.location = recommendFilters.value.location
      if (recommendFilters.value.industry) params.industry = recommendFilters.value.industry

      const data = await getJobRecommendations(params)
      if (!isCurrent()) return
      recommendations.value = data?.recommendations || []
    } catch (e) {
      if (!isCurrent()) return
      recommendations.value = []
      recommendError.value = userErrorCopy(e, '暂时取不到推荐结果，请稍后重试')
    } finally {
      if (isCurrent()) recommendLoading.value = false
    }
  }

  return {
    recommendLoading,
    recommendations,
    recommendError,
    recommendFilters,
    normalizedRecommendations,
    loadRecommendations,
  }
}
