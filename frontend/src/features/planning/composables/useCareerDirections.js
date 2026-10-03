import { ref } from 'vue'
import { userErrorCopy } from '@/utils/requestTracing'

import { recommendCareerPaths } from '@/api/jobs'
import { useLatestCall } from '@/composables/useLatestCall'

/* 职业方向链：D54 从 CareerPlanning.vue 搬出来。
   这条链的承诺是"给你**这份**简历的方向"，所以两处都要防：
   - 新一次在飞时先把上一份简历的结论撤下（搬之前就做了）；
   - 作废（换了/没了简历）时把仍在途的那一发判为过期——以前只是清值，于是清完还会被旧响应填回来。
   令牌只有一个领取点（`run` 里面），三个入口（加载 / 作废 / 重试）都从它过：D30 量过两个函数共用
   一个实例的症状是"两条都不写"，而同一函数内多处领取不触发那条不变量。 */
const EMPTY_META = { summary: '', corpus: {}, message: '' }

export function useCareerDirections({ getResumeId }) {
  const careerPaths = ref([])
  const careerPathLoading = ref(false)
  const careerPathError = ref('')
  const careerPathMeta = ref({ ...EMPTY_META })
  const latestPathsCall = useLatestCall()

  async function run(mode) {
    const isCurrent = latestPathsCall()
    careerPathError.value = ''
    if (mode === 'clear' || !getResumeId()) {
      careerPaths.value = []
      careerPathMeta.value = { ...EMPTY_META }
      // 被作废那一发的 finally 带着 isCurrent() 已经不会再解 loading，这里必须自己解
      careerPathLoading.value = false
      return
    }
    careerPathLoading.value = true
    // 新的一次开始，上一份简历的方向先撤下：留着就等于把旧简历的结论挂在新简历下面
    careerPaths.value = []
    careerPathMeta.value = { ...EMPTY_META }
    try {
      const data = await recommendCareerPaths(getResumeId())
      if (!isCurrent()) return
      careerPaths.value = data?.career_paths || []
      careerPathMeta.value = {
        summary: data?.summary || '',
        corpus: data?.corpus || {},
        message: data?.message || '',
      }
    } catch (e) {
      if (!isCurrent()) return
      careerPaths.value = []
      careerPathMeta.value = { ...EMPTY_META }
      careerPathError.value = userErrorCopy(e, '暂时无法基于岗位库给出职业方向')
    } finally {
      if (isCurrent()) careerPathLoading.value = false
    }
  }

  return {
    careerPaths,
    careerPathLoading,
    careerPathError,
    careerPathMeta,
    loadCareerPaths: () => run('load'),
    clearCareerPaths: () => run('clear'),
  }
}
