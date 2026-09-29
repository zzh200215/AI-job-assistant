import { computed, ref } from 'vue'
import { ElMessage } from '@/plugins/element-services'
import { getCities, searchExternalJobs } from '@/api/jobs'
import { useLatestCall } from '@/composables/useLatestCall'
import { normalizeJob, salaryMid, sourceText } from '@/features/jobs/lib/jobModel'

/* 实时搜索那条链：表单（关键词 / 城市 / 渠道）、结果列表、结果上的四条口径
   （正在搜 / 没搜过 / 回退本地 / 演示数据），以及"这一屏此刻该说什么"的三段文案。
   它和岗位仓库、智能推荐、投递流程三条链各自独立，所以各自领一把竞态令牌；
   令牌实例不能共用——一个实例的计数器是整个实例共享的，共用会让后发起的那条把前一条在途的
   响应判为过期，连 finally 里的解 loading 都不执行（见 D28）。 */

export function useJobSearch({ pushRecentSearch }) {
  const keyword = ref('Python')
  const city = ref('')
  const source = ref('boss')
  const cities = ref([])

  const searching = ref(false)
  const hasSearched = ref(false)
  const searchHint = ref('正在搜索最新岗位...')
  const searchError = ref('')
  const isDemo = ref(false)
  const resultMode = ref('')
  const savedCount = ref(0)
  const externalJobs = ref([])

  const searchFilters = ref({
    experience: '',
    education: '',
    skill: '',
  })
  const searchSort = ref('default')

  const latestSearchCall = useLatestCall()

  const filteredExternalJobs = computed(() => {
    const skillNeedle = searchFilters.value.skill.trim().toLowerCase()
    const list = externalJobs.value.filter((job) => {
      const exp = job.experience || ''
      const edu = job.education || ''
      const skillText = job.skillTags.join(' ').toLowerCase()
      const expOk =
        !searchFilters.value.experience ||
        exp.includes(searchFilters.value.experience.replace('+', ''))
      const eduOk = !searchFilters.value.education || edu.includes(searchFilters.value.education)
      const skillOk =
        !skillNeedle ||
        skillText.includes(skillNeedle) ||
        (job.summary || '').toLowerCase().includes(skillNeedle)
      return expOk && eduOk && skillOk
    })

    const sorted = [...list]
    if (searchSort.value === 'salary_desc') {
      sorted.sort((a, b) => salaryMid(b.salary) - salaryMid(a.salary))
    } else if (searchSort.value === 'salary_asc') {
      sorted.sort((a, b) => salaryMid(a.salary) - salaryMid(b.salary))
    } else if (searchSort.value === 'skill_desc') {
      sorted.sort((a, b) => b.skillTags.length - a.skillTags.length)
    }
    return sorted
  })

  const searchStateText = computed(() => {
    if (searching.value) return '抓取中'
    if (!hasSearched.value) return '未搜索'
    if (resultMode.value === 'local_fallback') return '本地职位库'
    if (resultMode.value === 'demo_fallback') return '演示数据'
    return isDemo.value ? '演示数据' : '最新结果'
  })

  const sourceBannerTitle = computed(() => {
    if (searching.value) return '正在获取岗位数据'
    if (!hasSearched.value) return '优先展示真实岗位结果'
    if (resultMode.value === 'local_fallback') return '当前展示本地职位库'
    if (resultMode.value === 'demo_fallback' || isDemo.value) return '当前展示演示岗位数据'
    return '当前展示实时搜索结果'
  })

  const sourceBannerDesc = computed(() => {
    if (searching.value) return '系统会优先抓取外部岗位，失败时再回退到本地或演示数据。'
    if (!hasSearched.value) return '点击“搜索最新岗位”后，系统会优先使用外部搜索结果。'
    if (resultMode.value === 'local_fallback')
      return '外部抓取未返回可用结果，已切换到本地职位库，适合继续做分析和筛选。'
    if (resultMode.value === 'demo_fallback' || isDemo.value)
      return '当前结果主要用于演示流程，建议补充真实搜索或导入岗位后再做判断。'
    return '这些岗位来自当前搜索渠道，可直接加入流程、对比或带入分析。'
  })

  const sourceBannerClass = computed(() => {
    if (resultMode.value === 'demo_fallback' || isDemo.value) return 'is-demo'
    if (resultMode.value === 'local_fallback') return 'is-local'
    if (searching.value) return 'is-loading'
    return 'is-live'
  })

  async function loadCities() {
    try {
      const data = await getCities()
      cities.value = data?.cities || []
    } catch {
      cities.value = [
        { name: '北京', code: '101010100' },
        { name: '上海', code: '101020100' },
        { name: '深圳', code: '101280600' },
        { name: '杭州', code: '101210100' },
        { name: '广州', code: '101280100' },
        { name: '全国', code: '' },
      ]
    }
  }

  async function runSearch() {
    if (!keyword.value.trim()) {
      ElMessage.warning('请输入搜索关键词')
      return
    }
    // 快速搜索标签和"刷新当前视图"在搜索期间照样可点（都没有 disabled），两次点击就是两个在途请求
    const isCurrent = latestSearchCall()
    searching.value = true
    hasSearched.value = true
    searchError.value = ''
    isDemo.value = false
    resultMode.value = ''
    searchHint.value = `正在搜索 ${sourceText(source.value)} 的 ${keyword.value} 岗位...`

    try {
      const data = await searchExternalJobs({
        keyword: keyword.value.trim(),
        city: city.value,
        source: source.value,
        page: 1,
      })
      if (!isCurrent()) return
      externalJobs.value = (data?.jobs || []).map((item, index) =>
        normalizeJob(item, `search-${index}`, city.value)
      )
      savedCount.value = data?.saved_count || 0
      searchError.value = data?.error || ''
      isDemo.value = !!data?.is_demo
      resultMode.value = data?.result_mode || 'external'
      pushRecentSearch(keyword.value.trim())
    } catch {
      if (!isCurrent()) return
      externalJobs.value = []
      searchError.value = '搜索失败，请稍后重试'
      resultMode.value = ''
    } finally {
      if (isCurrent()) searching.value = false
    }
  }

  /** 快速标签、改写建议、历史词三条入口都是"换个词再搜一次" */
  function searchWithKeyword(value) {
    keyword.value = value
    runSearch()
  }

  function resetSearchFilters() {
    searchFilters.value = {
      experience: '',
      education: '',
      skill: '',
    }
    searchSort.value = 'default'
  }

  return {
    keyword,
    city,
    source,
    cities,
    searching,
    hasSearched,
    searchHint,
    searchError,
    isDemo,
    resultMode,
    savedCount,
    externalJobs,
    searchFilters,
    searchSort,
    filteredExternalJobs,
    searchStateText,
    sourceBannerTitle,
    sourceBannerDesc,
    sourceBannerClass,
    loadCities,
    runSearch,
    searchWithKeyword,
    resetSearchFilters,
  }
}
