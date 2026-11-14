import { computed, ref } from 'vue'

import { getAnalysis, runFullAnalysis } from '@/api/analysis'
import { useAgentTaskPolling } from '@/composables/useAgentTaskPolling'
import { stepLabel } from '@/features/planning/lib/planningModel'
import { localizeSentence } from '@/utils/analysisLocalization'
import {
  NEVER_STARTED_FAILURE,
  QUEUED_COPY,
  TASK_PHASE,
  failedBeforeFirstStep,
} from '@/utils/taskPhase'
import { useSelectionStore } from '@/stores/selection'

/* 规划运行链：D56 从 CareerPlanning.vue 搬出来。这一条是"点一次按钮跑一整条 agent 链路"，
   所以它只持有任务生命周期与那份分析记录。**三样东西留在页面**：
   - 表单守卫（没选简历 / 既没填目标岗位又没选 JD 时弹哪句 warning）——那是页面输入的事，
     而且必须在 `running` 置起来**之前**拦；
   - 用哪个 JD（选已有的，还是按目标岗位现建一个再塞进选项列表）——那是选项链与页面输入之间的事；
   - 跑完之后要刷哪两条面板链——方向与薪资是页面的编排知识，不是运行链的职责。
   后两者通过参数注进来（`resolveJdId` / `onAnalysisFinished`），运行链不认得任何别的链。

   **这一条也没有竞态令牌**，理由与 D55 同一类：两个入口（开始按钮与"重新生成"）都绑在
   `:loading="running"` 上，EP 在 running 期间把按钮禁掉，所以同一时刻只会有一趟。
   真要让入口不吃 loading，就得回来补令牌。 */
export function useCareerPlanningRun({ getResumeId, resolveJdId, onAnalysisFinished }) {
  const selection = useSelectionStore()
  const running = ref(false)
  const taskStatus = ref('pending')
  /** 已提交、后台还没开始跑第一步（判据在 `utils/taskPhase.js`）。 */
  const queued = ref(false)
  /** 失败时给页面用的那句话：只有"没跑第一步就失败"这一档由前端自己说，其余留空走原兜底。 */
  const failureCopy = ref('')
  const agentSteps = ref([])
  const analysisRecordId = ref(null)
  const analysisResult = ref(null)
  const { pollTask } = useAgentTaskPolling()

  const careerResult = computed(() => analysisResult.value?.career_planning || null)
  const latestMatchScore = computed(() => Number(analysisResult.value?.match_score || 0))
  const localizedCurrentStatusSummary = computed(() =>
    localizeSentence(careerResult.value?.current_status?.summary || '')
  )
  const localizedOverallAdvice = computed(() =>
    localizeSentence(careerResult.value?.overall_advice || '')
  )

  const completedSteps = computed(
    () => agentSteps.value.filter((item) => item.status === 'completed').length
  )
  const currentStepName = computed(() => {
    const runningStep = agentSteps.value.find((item) => item.status === 'running')
    if (runningStep) return stepLabel(runningStep.step_name)
    const pendingStep = agentSteps.value.find((item) => item.status === 'pending')
    if (pendingStep) return stepLabel(pendingStep.step_name)
    const lastStep = [...agentSteps.value].reverse().find((item) => item.status === 'completed')
    return lastStep ? stepLabel(lastStep.step_name) : '等待启动'
  })
  const taskStatusLabel = computed(() => {
    if (queued.value) return '排队中'
    return (
      {
        pending: '等待中',
        running: '执行中',
        completed: '已完成',
        partial: '部分完成',
        cancelled: '已取消',
        failed: '失败',
      }[taskStatus.value] || taskStatus.value
    )
  })

  const analysisStatusLabel = computed(() => {
    if (running.value) return '分析中'
    if (careerResult.value) return '已生成'
    if (analysisRecordId.value && taskStatus.value === 'partial') return '部分完成'
    if (analysisRecordId.value) return '已完成'
    if (taskStatus.value === 'failed') return '失败'
    if (taskStatus.value === 'cancelled') return '已取消'
    return '待启动'
  })
  const latestMatchLabel = computed(() => {
    if (running.value) return queued.value ? QUEUED_COPY.title : 'Agent 正在生成职业规划'
    if (careerResult.value) return `匹配度 ${latestMatchScore.value}`
    if (analysisRecordId.value) return '完整分析已生成，但职业规划内容为空'
    if (taskStatus.value === 'failed') return '生成失败，请重试'
    if (taskStatus.value === 'cancelled') return '任务已取消'
    return '等待生成职业规划'
  })

  async function startCareerPlanning() {
    running.value = true
    taskStatus.value = 'running'
    queued.value = false
    failureCopy.value = ''
    analysisResult.value = null
    analysisRecordId.value = null
    agentSteps.value = []

    try {
      // 建目标 JD 也在 running 之内：原实现就是先亮转圈再建，保持一致
      const effectiveJdId = await resolveJdId()
      const startRes = await runFullAnalysis({
        resume_id: getResumeId(),
        jd_id: effectiveJdId,
      })
      if (!startRes?.task_id) {
        throw new Error('未拿到 task_id')
      }
      /* 任务号一到手就是"已提交、还没开始跑"：不等第一跳轮询，排队那句话立刻上屏。 */
      queued.value = true
      await pollTask(startRes.task_id, {
        timeoutMessage: '职业规划生成超时，请稍后重试',
        onProgress(taskData, steps, phase) {
          taskStatus.value = taskData?.status || 'running'
          queued.value = phase === TASK_PHASE.QUEUED
          agentSteps.value = steps
        },
        async onCompleted(taskData) {
          queued.value = false
          taskStatus.value = taskData?.status || 'completed'
          analysisRecordId.value = taskData?.analysis_record_id || null
          if (!analysisRecordId.value) {
            throw new Error('分析完成但没有生成记录')
          }
          analysisResult.value = await getAnalysis(analysisRecordId.value)
          selection.rememberRecord(analysisRecordId.value)
        },
        onFailed(error) {
          queued.value = false
          taskStatus.value = 'failed'
          failureCopy.value = failedBeforeFirstStep(error?.task) ? NEVER_STARTED_FAILURE : ''
        },
        onCancelled() {
          queued.value = false
          taskStatus.value = 'cancelled'
        },
        onTimeout() {
          queued.value = false
          taskStatus.value = 'failed'
        },
      })
      // 跑完要刷什么，是页面的编排知识；运行链只负责把"这一趟完成了"递出去
      if (analysisRecordId.value) await onAnalysisFinished()
      return { ok: true }
    } catch (error) {
      if (error?.code === 'polling_stopped') {
        /* 走到这里只可能是页面被卸载（`useAgentTaskPolling` 把 stopPolling 挂在 onUnmounted 上）。
           任务本身既没失败也没取消：不写 taskStatus（写了也没人看，但下一屏读不到这一屏），
           更不把它报成 run-failed——那是页面弹错误 toast 的开关。 */
        return { ok: false, reason: 'polling-stopped', error }
      }
      queued.value = false
      taskStatus.value = error?.code === 'task_cancelled' ? 'cancelled' : 'failed'
      return { ok: false, reason: 'run-failed', error }
    } finally {
      running.value = false
      /* 这条链只在**正在轮询**时才知道任务处于哪个阶段。轮询一结束（完成/失败/卸载打断），
         任何"排队中"的说法都过期了——留着它会让下一次进这一屏的人看到一句没人能保证的话。 */
      queued.value = false
    }
  }

  return {
    running,
    taskStatus,
    queued,
    failureCopy,
    agentSteps,
    analysisRecordId,
    analysisResult,
    careerResult,
    latestMatchScore,
    localizedCurrentStatusSummary,
    localizedOverallAdvice,
    completedSteps,
    currentStepName,
    taskStatusLabel,
    analysisStatusLabel,
    latestMatchLabel,
    startCareerPlanning,
  }
}
