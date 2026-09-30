import { ref } from 'vue'

import { getSalaryOverview } from '@/api/salary'
import { useLatestCall } from '@/composables/useLatestCall'

/* 薪资行情链：D54 从 CareerPlanning.vue 搬出来。查的是**一个职称**的样本，不是"这份简历"，
   所以入参是取岗位名的函数——名字来自页面上用户填的目标岗位，没有就退回这份简历解析出的职称。
   这里不做任何推算：此前该卡片用 `yearsExp * 5 + 8` 和一组魔法增长率生成五年薪资曲线，
   看起来像预测，实际与数据无关（E 阶段那次改成了只读 /salary/overview 的真实分位数）。

   修掉的一处：以前"没有职称就不发请求"那一支只清值不解 loading，而它已经把上一发作废了
   （上一发的 finally 带着 `isCurrent()` 于是也不解）——`salaryMarketLoading` 从此停在 true，
   薪资那一栏永久写着"加载中…"。 */
export function useSalaryMarket({ getPosition }) {
  const salaryMarket = ref(null)
  const salaryMarketLoading = ref(false)
  const salaryMarketError = ref('')
  const latestSalaryCall = useLatestCall()

  async function loadSalaryMarket() {
    const isCurrent = latestSalaryCall()
    const position = (getPosition() || '').trim()
    if (!position) {
      salaryMarket.value = null
      salaryMarketLoading.value = false
      return
    }
    salaryMarketLoading.value = true
    salaryMarketError.value = ''
    salaryMarket.value = null // 新的一次在飞时，不拿旧区间的数字顶着
    try {
      const data = await getSalaryOverview({ position }, { notifyError: false })
      if (!isCurrent()) return
      salaryMarket.value = data?.has_data ? data : null
    } catch (e) {
      if (!isCurrent()) return
      salaryMarket.value = null
      salaryMarketError.value = e?.userMessage || e?.message || '暂时无法读取岗位库薪资样本'
    } finally {
      if (isCurrent()) salaryMarketLoading.value = false
    }
  }

  return { salaryMarket, salaryMarketLoading, salaryMarketError, loadSalaryMarket }
}
