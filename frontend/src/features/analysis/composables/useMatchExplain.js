import { ref } from 'vue'

import { explainMatch } from '@/api/analysis'
import { useLatestCall } from '@/composables/useLatestCall'

/* 匹配度解释链：D50 从 SmartAnalysis.vue 搬出来。
   "哪一个简历 + 哪一个 JD"是页面上的跨链知识（记录自带的 id 优先，否则用当前选择），
   所以这里收两个取值函数而不是自己持有 refs —— 规则留在页面唯一一份。 */
export function useMatchExplain({ getResumeId, getJdId }) {
  const explainLoading = ref(false)
  const explainResult = ref(null)
  const latestExplainCall = useLatestCall()

  async function run(mode) {
    if (mode === 'clear') {
      latestExplainCall()
      explainResult.value = null
      // 同上：被作废那一发的 finally 不再解 loading
      explainLoading.value = false
      return
    }
    const resumeId = getResumeId()
    const jdId = getJdId()
    if (!resumeId || !jdId) return
    if (mode === 'lazy' && explainResult.value) return

    const isCurrent = latestExplainCall()
    explainLoading.value = true
    try {
      const data = await explainMatch({ resume_id: resumeId, jd_id: jdId })
      if (!isCurrent()) return
      explainResult.value = data
    } catch (e) {
      if (!isCurrent()) return
      console.error('加载匹配度解释失败:', e)
    } finally {
      if (isCurrent()) explainLoading.value = false
    }
  }

  return {
    explainLoading,
    explainResult,
    loadExplainMatch: (force = false) => run(force ? 'force' : 'lazy'),
    clearExplain: () => run('clear'),
  }
}
