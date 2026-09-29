import { computed, ref } from 'vue'
import { getJobList } from '@/api/jobs'
import { useLatestCall } from '@/composables/useLatestCall'
import { normalizeJob } from '@/features/jobs/lib/jobModel'

/* 岗位仓库那条链：一次拉 100 条已落库的 JD，再按关键词 / 来源 / 行业三个框筛。
   `city` 与推荐链一样是从实时搜索那条链注入的——归一时算的投递优先级里有 8 分是"命中界面上的
   城市筛选"，而这一侧的分数是取数那一刻存进列表的，换筛选要等下一次刷新（§10.18 记的就是这个不对称）。
   `seedDemoData` 不在这条链里：它补完演示岗位要同时刷仓库与推荐两条链，那是页面级的编排。 */

export function useJobWarehouse({ city }) {
  const localLoading = ref(false)
  const localJobs = ref([])
  // 与"仓库为空"分开：GET 失败不弹提示，只清空列表会让候选人以为岗位库是空的
  const localError = ref('')
  const warehouseFilters = ref({
    keyword: '',
    source: '',
    industry: '',
  })
  const latestLocalJobsCall = useLatestCall()

  const filteredLocalJobs = computed(() => {
    const keywordNeedle = warehouseFilters.value.keyword.trim().toLowerCase()
    return localJobs.value.filter((job) => {
      const text = `${job.title} ${job.company} ${job.location} ${job.summary}`.toLowerCase()
      const sourceOk =
        !warehouseFilters.value.source || job.source === warehouseFilters.value.source
      const industryOk =
        !warehouseFilters.value.industry ||
        (job.industry || '').includes(warehouseFilters.value.industry)
      const keywordOk = !keywordNeedle || text.includes(keywordNeedle)
      return sourceOk && industryOk && keywordOk
    })
  })

  async function loadLocalJobs() {
    const isCurrent = latestLocalJobsCall()
    localLoading.value = true
    localError.value = ''
    try {
      const data = await getJobList({ page: 1, page_size: 100 })
      if (!isCurrent()) return
      localJobs.value = (data?.items || []).map((item, index) =>
        normalizeJob(item, `local-${index}`, city.value)
      )
    } catch (e) {
      if (!isCurrent()) return
      localJobs.value = []
      localError.value = e?.userMessage || e?.message || '本地岗位仓库加载失败，请稍后重试'
    } finally {
      if (isCurrent()) localLoading.value = false
    }
  }

  return {
    localLoading,
    localJobs,
    localError,
    warehouseFilters,
    filteredLocalJobs,
    loadLocalJobs,
  }
}
