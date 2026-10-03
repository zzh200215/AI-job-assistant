/* 投递流程这一簇从 JobSearch.vue 搬出来：19 个成员、~210 行，只管"我的投递记录"这一件事。
   它需要父页面的三样东西（当前标签页、选中的简历、打开详情的动作），所以由调用方注入，
   而不是在模块里再去读路由或 store——那会让这页唯一一份状态来源变成两处。 */
import { computed, ref } from 'vue'
import { userErrorCopy } from '@/utils/requestTracing'
import { ElMessage } from '@/plugins/element-services'
import {
  clearRejectedJobPipeline,
  createJobPipelineEntry,
  deleteJobPipelineEntry,
  getJobPipelineList,
  updateJobPipelineEntry,
} from '@/api/jobs'
import {
  comparePipelineEntries,
  defaultNextAction,
  normalizePipelineEntry,
  pipelineEntryToJob,
  pipelineStageLabel,
  pipelineStageMap,
  pipelineStages,
} from '@/features/jobs/lib/jobModel'

export function useJobPipeline({ activeTab, selectedResumeId, selectedResumeName, openJobDetail }) {
  const pipelineError = ref('')

  const pipelineEntries = ref([])

  const pipelineFilters = ref({
    keyword: '',
    stage: 'all',
  })

  const pipelineStats = computed(() =>
    pipelineStages.reduce((acc, stage) => {
      acc[stage.key] = pipelineEntries.value.filter((item) => item.stage === stage.key).length
      return acc
    }, {})
  )

  const pipelineActiveCount = computed(
    () => pipelineEntries.value.filter((item) => item.stage !== 'rejected').length
  )

  const filteredPipelineEntries = computed(() => {
    const keywordNeedle = pipelineFilters.value.keyword.trim().toLowerCase()
    return [...pipelineEntries.value]
      .filter(
        (entry) =>
          pipelineFilters.value.stage === 'all' || entry.stage === pipelineFilters.value.stage
      )
      .filter((entry) => {
        if (!keywordNeedle) return true
        const text = [
          entry.title,
          entry.company,
          entry.location,
          entry.note,
          entry.nextAction,
          entry.resumeName,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        return text.includes(keywordNeedle)
      })
      .sort(comparePipelineEntries)
  })

  const visiblePipelineStages = computed(() =>
    pipelineFilters.value.stage === 'all'
      ? pipelineStages
      : pipelineStages.filter((item) => item.key === pipelineFilters.value.stage)
  )

  const pipelineByStage = computed(() => {
    const grouped = Object.fromEntries(pipelineStages.map((item) => [item.key, []]))
    filteredPipelineEntries.value.forEach((entry) => {
      if (grouped[entry.stage]) {
        grouped[entry.stage].push(entry)
      }
    })
    return grouped
  })

  const pipelineFocusList = computed(() =>
    [...pipelineEntries.value]
      .filter((entry) => entry.stage !== 'rejected')
      .sort(comparePipelineEntries)
      .slice(0, 5)
  )

  async function loadPipelineEntries() {
    pipelineError.value = ''
    try {
      const data = await getJobPipelineList()
      pipelineEntries.value = (data?.items || []).map((item) => normalizePipelineEntry(item))
    } catch (e) {
      pipelineEntries.value = []
      pipelineError.value = userErrorCopy(e, '暂时无法读取你的跟进记录')
    }
  }

  async function handlePipelineAction(job) {
    const existing = findPipelineEntry(job)
    if (existing) {
      activeTab.value = 'pipeline'
      pipelineFilters.value.stage = existing.stage
      pipelineFilters.value.keyword = ''
      ElMessage.info(`该岗位已在 ${pipelineStageLabel(existing.stage)} 阶段`)
      return
    }

    try {
      const created = await createJobPipelineEntry(createPipelineEntryPayload(job))
      pipelineEntries.value = [normalizePipelineEntry(created), ...pipelineEntries.value]
      activeTab.value = 'pipeline'
      pipelineFilters.value.stage = 'todo'
      pipelineFilters.value.keyword = ''
      ElMessage.success('已加入投递流程')
    } catch {
      // request interceptor already surfaced the error
    }
  }

  function createPipelineEntryPayload(job, stage = 'todo') {
    const now = new Date().toISOString()
    return {
      resume_id: selectedResumeId.value || null,
      jd_id: job.id || null,
      title: job.title,
      company: job.company,
      location: job.location,
      salary_range: job.salary,
      summary: job.summary,
      raw_text: job.rawText,
      source: job.source,
      source_url: job.sourceUrl,
      experience_requirement: job.experience || '',
      education_requirement: job.education || '',
      industry: job.industry || '',
      skill_tags: job.skillTags || [],
      priority_score: job.priorityScore || 0,
      priority_label: job.priorityLabel || '',
      stage,
      note: '',
      next_action: defaultNextAction(stage),
      follow_up_at: null,
      resume_name: selectedResumeName.value || '',
      stage_history: [{ stage, at: now }],
    }
  }

  function findPipelineEntry(job) {
    if (!job) return null
    return (
      pipelineEntries.value.find((item) => {
        if (
          job.id &&
          item.jobId &&
          item.jobId === job.id &&
          (!selectedResumeId.value || !item.resumeId || item.resumeId === selectedResumeId.value)
        ) {
          return true
        }
        return item.uid === job.uid
      }) || null
    )
  }

  function pipelineStatusText(job) {
    const entry = findPipelineEntry(job)
    return entry ? pipelineStageLabel(entry.stage) : ''
  }

  function openPipelineJob(entry) {
    openJobDetail(pipelineEntryToJob(entry), 'pipeline')
  }

  async function touchPipelineEntry(entry) {
    const index = pipelineEntries.value.findIndex((item) => item.entryId === entry.entryId)
    if (index < 0) return
    try {
      const updated = await updateJobPipelineEntry(entry.entryId, {
        resume_id: entry.resumeId,
        jd_id: entry.jobId,
        title: entry.title,
        company: entry.company,
        location: entry.location,
        salary_range: entry.salary,
        source: entry.source,
        source_url: entry.sourceUrl,
        summary: entry.summary,
        raw_text: entry.rawText,
        experience_requirement: entry.experience,
        education_requirement: entry.education,
        industry: entry.industry,
        skill_tags: entry.skillTags || [],
        priority_score: entry.priorityScore || 0,
        priority_label: entry.priorityLabel || '',
        stage: entry.stage,
        note: entry.note || '',
        next_action: entry.nextAction || '',
        follow_up_at: entry.followUpAt || null,
        resume_name: entry.resumeName || '',
        stage_history: entry.stageHistory || [],
      })
      pipelineEntries.value[index] = normalizePipelineEntry(updated)
    } catch {
      await loadPipelineEntries()
    }
  }

  async function updatePipelineStage(entry, stage) {
    const index = pipelineEntries.value.findIndex((item) => item.entryId === entry.entryId)
    if (index < 0 || !pipelineStageMap[stage]) return

    const current = pipelineEntries.value[index]
    if (current.stage === stage) {
      await touchPipelineEntry(current)
      return
    }

    const now = new Date().toISOString()
    const nextEntry = normalizePipelineEntry({
      ...current,
      stage,
      nextAction: current.nextAction || defaultNextAction(stage),
      updatedAt: now,
      stageHistory: [...current.stageHistory, { stage, at: now }],
    })
    pipelineEntries.value[index] = nextEntry
    await touchPipelineEntry(nextEntry)
  }

  async function removePipelineEntry(entryId) {
    try {
      await deleteJobPipelineEntry(entryId)
      pipelineEntries.value = pipelineEntries.value.filter((item) => item.entryId !== entryId)
    } catch {
      // request interceptor already surfaced the error
    }
  }

  async function clearRejectedPipeline() {
    try {
      await clearRejectedJobPipeline()
      pipelineEntries.value = pipelineEntries.value.filter((item) => item.stage !== 'rejected')
    } catch {
      // request interceptor already surfaced the error
    }
  }

  return {
    pipelineError,
    pipelineEntries,
    pipelineFilters,
    pipelineStats,
    pipelineActiveCount,
    visiblePipelineStages,
    pipelineByStage,
    pipelineFocusList,
    loadPipelineEntries,
    handlePipelineAction,
    pipelineStatusText,
    openPipelineJob,
    touchPipelineEntry,
    updatePipelineStage,
    removePipelineEntry,
    clearRejectedPipeline,
  }
}
