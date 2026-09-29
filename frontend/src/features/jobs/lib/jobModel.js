/* 岗位搜索页的数据形状层：从 JobSearch.vue 搬出来的一组纯函数与常量。
   搬它们是因为这页 1312 行脚本里，光是"把后端返回的 JD 归一成本地形状、把投递记录归一成卡片、
   给状态/来源/优先级配色配文案"就占了 ~150 行，而它们不读任何 ref、不发请求。
   `normalizeJob` / `calculateApplicationPriority` 是 D41 才搬的：前者调后者，后者原本直接读视图上的
   `city.value`（投递优先级里藏着一个 UI 字段）。搬的时候只把那一次读取改成调用方传进来的参数，
   **加分规则一个字没动**——分数与搬之前逐条相同，变的只是"谁去读那个字段"可见了。 */
import { compactDateTime } from '@/utils/format/date'

export const pipelineStages = [
  {
    key: 'todo',
    label: '待投递',
    hint: '准备材料',
    description: '简历、作品集、渠道和联系人都还在准备阶段。',
    emptyText: '还没有待投递岗位',
  },
  {
    key: 'applied',
    label: '已投递',
    hint: '等待反馈',
    description: '已经完成投递，重点是补记录、盯进度和安排跟进。',
    emptyText: '还没有已投递岗位',
  },
  {
    key: 'interview',
    label: '已约面',
    hint: '面试推进',
    description: '进入面试流程后，把面试时间、反馈和风险点沉淀下来。',
    emptyText: '还没有进入面试的岗位',
  },
  {
    key: 'rejected',
    label: '已淘汰',
    hint: '复盘沉淀',
    description: '保留失败原因和复盘结论，方便后续调整投递策略。',
    emptyText: '当前没有淘汰岗位',
  },
]
export const pipelineStageMap = Object.fromEntries(pipelineStages.map((item) => [item.key, item]))

export function sourceText(value) {
  return (
    {
      boss: 'BOSS',
      all: '全平台',
      crawled: '爬取',
      imported: '导入',
      api: '接口',
      manual: '手工',
      local: '本地',
      recommend: '推荐',
    }[value] ||
    value ||
    '未知'
  )
}

export function recommendTagType(value) {
  // 后端推荐类型：高度推荐 / 值得一试 / 谨慎考虑
  const v = value || ''
  if (v.includes('高度')) return 'success'
  if (v.includes('值得')) return 'warning'
  if (v.includes('谨慎')) return 'danger'
  return 'info'
}

export function signalClass(flag) {
  return flag ? 'signal positive' : 'signal neutral'
}

export function salaryMid(value) {
  if (!value) return 0
  // 不按分隔符剥字符：任何非数字都是区间边界，剥掉反而会把 "20·30K" 读成 2030K
  const normalized = String(value).replace(/\s/g, '').toLowerCase()
  const nums = normalized.match(/\d+(\.\d+)?/g)?.map(Number) || []
  if (!nums.length) return 0

  let [min, max] = nums.length >= 2 ? [nums[0], nums[1]] : [nums[0], nums[0]]
  if (normalized.includes('w')) {
    min *= 10
    max *= 10
  }
  return Math.round((min + max) / 2)
}

export function rankMap(list) {
  const map = new Map()
  list.forEach((item) => {
    const key = String(item).trim()
    if (!key) return
    map.set(key, (map.get(key) || 0) + 1)
  })
  return [...map.entries()].sort((a, b) => b[1] - a[1]).map(([label, count]) => ({ label, count }))
}

export function uniqueList(list) {
  return [
    ...new Set(
      (Array.isArray(list) ? list : []).map((item) => String(item).trim()).filter(Boolean)
    ),
  ]
}

export function comparePipelineEntries(a, b) {
  const followUpA = a.followUpAt ? new Date(a.followUpAt).getTime() : Number.MAX_SAFE_INTEGER
  const followUpB = b.followUpAt ? new Date(b.followUpAt).getTime() : Number.MAX_SAFE_INTEGER
  if (followUpA !== followUpB) {
    return followUpA - followUpB
  }
  return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
}

export function defaultNextAction(stage) {
  return (
    {
      todo: '补齐定制简历并确认投递渠道',
      applied: '记录投递时间，并在 3-5 天后安排一次跟进',
      interview: '整理面试重点和追问项，准备复盘记录',
      rejected: '补充淘汰原因，复盘后调整投递策略',
    }[stage] || '继续跟进'
  )
}

export function pipelineStageLabel(stage) {
  return pipelineStageMap[stage]?.label || '投递流程'
}

export function pipelineHistoryText(history) {
  if (!Array.isArray(history) || !history.length) return ''
  return history
    .slice(-3)
    .map((item) => `${pipelineStageLabel(item.stage)} ${compactDateTime(item.at, '--')}`)
    .join(' / ')
}

export function normalizePipelineEntry(item) {
  const stage = pipelineStageMap[item?.stage] ? item.stage : 'todo'
  const createdAt =
    item?.createdAt ||
    item?.create_time ||
    item?.updatedAt ||
    item?.update_time ||
    new Date().toISOString()
  const updatedAt = item?.updatedAt || item?.update_time || createdAt
  const rawHistory = item?.stageHistory || item?.stage_history
  const stageHistory =
    Array.isArray(rawHistory) && rawHistory.length
      ? rawHistory.map((historyItem) => ({
          stage: pipelineStageMap[historyItem?.stage] ? historyItem.stage : stage,
          at: historyItem?.at || updatedAt,
        }))
      : [{ stage, at: updatedAt }]

  return {
    entryId: item?.entryId || item?.id || `pipeline-${item?.jobId || item?.jd_id || createdAt}`,
    uid: item?.uid || `pipeline-${item?.jobId || item?.jd_id || item?.id || createdAt}`,
    jobId: item?.jobId || item?.jd_id || null,
    title: item?.title || '未知岗位',
    company: item?.company || '未知公司',
    location: item?.location || '',
    salary: item?.salary || item?.salary_range || '薪资面议',
    summary: item?.summary || '',
    rawText: item?.rawText || item?.raw_text || '',
    source: item?.source || 'local',
    sourceUrl: item?.sourceUrl || item?.source_url || '',
    experience: item?.experience || item?.experience_requirement || '',
    education: item?.education || item?.education_requirement || '',
    industry: item?.industry || '',
    skillTags: uniqueList(item?.skillTags || item?.skill_tags || []),
    local: item?.local !== undefined ? !!item.local : !!item?.jd_id,
    priorityScore: item?.priorityScore || item?.priority_score || 0,
    priorityLabel: item?.priorityLabel || item?.priority_label || '',
    stage,
    note: item?.note || '',
    nextAction: item?.nextAction || defaultNextAction(stage),
    followUpAt: item?.followUpAt || item?.follow_up_at || '',
    resumeId: item?.resumeId || item?.resume_id || null,
    resumeName: item?.resumeName || item?.resume_name || '',
    createdAt,
    updatedAt,
    stageHistory,
  }
}

export function pipelineEntryToJob(entry) {
  return {
    uid: entry.uid,
    id: entry.jobId,
    title: entry.title,
    company: entry.company,
    location: entry.location,
    salary: entry.salary,
    summary: entry.summary,
    rawText: entry.rawText,
    source: entry.source,
    sourceUrl: entry.sourceUrl,
    experience: entry.experience,
    education: entry.education,
    industry: entry.industry,
    skillTags: entry.skillTags || [],
    local: entry.local,
    priorityScore: entry.priorityScore,
    priorityLabel: entry.priorityLabel,
    priorityReason: entry.note || entry.nextAction || '',
  }
}

/* 投递优先级。`city` 是调用方在取数那一刻传进来的 UI 城市筛选，命中它加 8 分——
   这一条加分是否该存在是产品问题（见 docs/upgrade-plan.md §10），这里只负责让它可见。 */
export function calculateApplicationPriority(job, city) {
  let score = 45
  const reasons = []

  const salaryScore = salaryMid(job.salary)
  if (salaryScore >= 35) {
    score += 16
    reasons.push('薪资带更强')
  } else if (salaryScore >= 25) {
    score += 10
    reasons.push('薪资有竞争力')
  }

  if ((job.skillTags || []).length >= 6) {
    score += 10
    reasons.push('技能画像完整')
  } else if ((job.skillTags || []).length >= 3) {
    score += 6
  }

  if (job.location && city && job.location.includes(city)) {
    score += 8
    reasons.push('城市匹配')
  }

  if (job.local) {
    score += 6
    reasons.push('已落库可直接分析')
  }

  if (typeof job.matchScore === 'number' && job.matchScore > 0) {
    score += Math.round(job.matchScore * 0.28)
    reasons.push('推荐匹配度较高')
  }

  if (job.salaryMatch) score += 4
  if (job.locationMatch) score += 4
  if (job.experienceMatch) score += 4

  const finalScore = Math.max(0, Math.min(100, score))
  const label = finalScore >= 82 ? '优先投递' : finalScore >= 66 ? '值得投递' : '先观察'
  return {
    priorityScore: finalScore,
    priorityLabel: label,
    priorityReason: reasons.slice(0, 3).join(' / ') || '信息尚不完整，建议先观察',
  }
}

/** 后端 JD（搜索 / 仓库 / 详情三种形状）归一成页面上的卡片。`city` 透传给优先级算式。 */
export function normalizeJob(item, seed, city) {
  const salary = item.salary || item.salary_range || '薪资面议'
  const skillTags = uniqueList(item.skill_tags || item.skillTags || [])
  const normalized = {
    uid: `${seed}-${item.id || item.external_id || item.title || 'job'}`,
    id: item.id || null,
    title: item.title || item.job_title || '未知岗位',
    company: item.company || '未知公司',
    location: item.location || '',
    salary,
    experience: item.experience || item.experience_requirement || '',
    education: item.education || item.education_requirement || '',
    industry: item.industry || '',
    skillTags,
    summary: item.jd_summary || item.match_reason || '',
    rawText: item.raw_text || '',
    source: item.source || 'local',
    sourceUrl: item.source_url || '',
    local:
      !!item._local_db || ['local', 'imported', 'api', 'manual', 'crawled'].includes(item.source),
  }
  return { ...normalized, ...calculateApplicationPriority(normalized, city) }
}
