import { ref } from 'vue'

import { getAnalysisReferences } from '@/api/analysis'
import { useLatestCall } from '@/composables/useLatestCall'

/* 引用来源链：D50 从 SmartAnalysis.vue 搬出来。三个入口（点标签页 = 没缓存才取、分析完成 = 必取、
   重新分析 = 作废），全部走同一个 `run`，因为令牌只能有一个领取点：
   领两处的话，"命中缓存直接返回"那一支会把仍在途的那一发判为过期，而它的 finally 带着
   `isCurrent()` 不再解 loading —— 转圈就永久停不下来（同 D42 那两处必须一起改的教训）。 */
export function useAnalysisReferences({ getResult }) {
  const references = ref([])
  const referencesLoading = ref(false)
  const refOpenDocs = ref([0])
  const referenceQuery = ref('')
  const referenceConfidence = ref(null)
  const latestReferencesCall = useLatestCall()

  async function run(mode) {
    if (mode === 'clear') {
      latestReferencesCall()
      references.value = []
      referenceQuery.value = ''
      referenceConfidence.value = null
      // 作废之后那一发的 finally 不会再解 loading，这里必须自己解
      referencesLoading.value = false
      return
    }
    const record = getResult()
    if (!record?.id) return
    if (mode === 'lazy' && references.value.length > 0) return

    const isCurrent = latestReferencesCall()
    referencesLoading.value = true
    try {
      const data = await getAnalysisReferences(record.id)
      if (!isCurrent()) return
      references.value = data?.references || []
      referenceQuery.value = data?.query || ''
      if (!record.rag_confidence && data?.rag_confidence) {
        referenceConfidence.value = data.rag_confidence
      }
    } catch (e) {
      if (!isCurrent()) return
      console.error('加载引用来源失败:', e)
    } finally {
      if (isCurrent()) referencesLoading.value = false
    }
  }

  return {
    references,
    referencesLoading,
    refOpenDocs,
    referenceQuery,
    referenceConfidence,
    loadReferences: (force = false) => run(force ? 'force' : 'lazy'),
    clearReferences: () => run('clear'),
  }
}
