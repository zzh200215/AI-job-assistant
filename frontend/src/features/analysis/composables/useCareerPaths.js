import { ref } from 'vue'

import { useLatestCall } from '@/composables/useLatestCall'

/* 职业方向链：D50 从 SmartAnalysis.vue 搬出来。这一条**每次点标签页都会发请求**（原代码没有
   任何"已经取过就跳过"的守卫），搬的时候把这个行为原样保留 —— 它只多打一次接口，
   不是这次要改的东西。
   `@/api/jobs` 仍是动态 import：这条链只在点开那一页时才需要 jobs 那一个 chunk。 */
export function useCareerPaths({ getResumeId }) {
  const careerPaths = ref([])
  const careerPathsLoading = ref(false)
  const careerPathSummary = ref('')
  const latestCareerPathsCall = useLatestCall()

  async function run(mode) {
    if (mode === 'clear') {
      latestCareerPathsCall()
      careerPaths.value = []
      careerPathSummary.value = ''
      careerPathsLoading.value = false
      return
    }
    const resumeId = getResumeId()
    if (!resumeId) return

    const isCurrent = latestCareerPathsCall()
    careerPathsLoading.value = true
    try {
      const { recommendCareerPaths } = await import('@/api/jobs')
      const data = await recommendCareerPaths(resumeId)
      if (!isCurrent()) return
      careerPaths.value = data?.career_paths || []
      careerPathSummary.value = data?.summary || ''
    } catch (e) {
      if (!isCurrent()) return
      console.error('加载职业方向失败:', e)
    } finally {
      if (isCurrent()) careerPathsLoading.value = false
    }
  }

  return {
    careerPaths,
    careerPathsLoading,
    careerPathSummary,
    loadCareerPaths: () => run('load'),
    clearCareerPaths: () => run('clear'),
  }
}
