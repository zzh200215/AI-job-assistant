import { computed, ref } from 'vue'

import { getJDList } from '@/api/jd'
import { getResumeList } from '@/api/resume'
import { useSelectionStore } from '@/stores/selection'

/* 选项链：D55 从 CareerPlanning.vue 搬出来，它是这一页"选哪份简历 / 哪个 JD"的唯一持有者。
   规则原样搬，一条没改：
   - 只把**已解析**的简历放进选择列表（`parsed` 非空）；
   - 刷新回来后，选中的项如果已经不在列表里就置空（简历在别处被删掉了）；
   - 谁都没选中过时，取第一份简历；JD 不自动取（不选中就是"按目标岗位新建"）。

   **这一条链我没有加竞态令牌**，理由写在这里而不是留给下一个人重新发现：它有两个入口
   （错误横幅上的"重试"与"刷新数据"按钮），但两个入口打的是同一条 URL、同一套参数，
   两份响应的内容相同，所以"旧的盖住新的"在这一维拿不出可见差异；而置空/自动取那两条规则
   读的是 `selectedResumeId` 当前值与刚回来的列表，两次同样内容的刷新做完是同一个结果。
   D52 刚记过一次"加了一条自己证不了承重的守卫"，这次先不加。 */
export function usePlanningOptions() {
  const selection = useSelectionStore()
  const resumeOptions = ref([])
  const jdOptions = ref([])
  const selectedResumeId = ref(null)
  const selectedJDId = ref(null)
  const optionsLoading = ref(false)
  const baseOptionsError = ref(false)

  const selectedResume = computed(
    () => resumeOptions.value.find((item) => item.id === selectedResumeId.value) || null
  )
  const selectedJD = computed(
    () => jdOptions.value.find((item) => item.id === selectedJDId.value) || null
  )

  /** 槽里记的上一次选择（按登录用户分槽，规则住在 utils/lastSelection）。 */
  function restoreSelections() {
    const resumeId = selection.resumeId()
    const jdId = selection.jdId()
    if (resumeId) selectedResumeId.value = resumeId
    if (jdId) selectedJDId.value = jdId
  }

  async function refreshBaseOptions() {
    optionsLoading.value = true
    baseOptionsError.value = false
    try {
      const [resumeData, jdData] = await Promise.all([
        getResumeList({ page_size: 50 }),
        getJDList({ page_size: 50 }),
      ])
      resumeOptions.value = (resumeData?.items || []).filter(
        (item) => item.parsed && Object.keys(item.parsed).length
      )
      jdOptions.value = jdData?.items || []

      if (
        selectedResumeId.value &&
        !resumeOptions.value.some((item) => item.id === selectedResumeId.value)
      ) {
        selectedResumeId.value = null
      }
      if (selectedJDId.value && !jdOptions.value.some((item) => item.id === selectedJDId.value)) {
        selectedJDId.value = null
      }

      if (!selectedResumeId.value && resumeOptions.value.length) {
        selectedResumeId.value = resumeOptions.value[0].id
      }
    } catch {
      resumeOptions.value = []
      jdOptions.value = []
      baseOptionsError.value = true
    } finally {
      optionsLoading.value = false
    }
  }

  /** 刚创建的目标 JD 要能立刻被选中，所以由列表的持有者自己插到最前，且同一 id 不重复插。 */
  function adoptJD(jd) {
    if (jdOptions.value.some((item) => item.id === jd.id)) return
    jdOptions.value.unshift({ id: jd.id, title: jd.title, company: jd.company })
  }

  return {
    resumeOptions,
    jdOptions,
    selectedResumeId,
    selectedJDId,
    selectedResume,
    selectedJD,
    optionsLoading,
    baseOptionsError,
    restoreSelections,
    refreshBaseOptions,
    adoptJD,
  }
}
