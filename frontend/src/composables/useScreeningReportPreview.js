import { SCREENING_DIMENSION_LABELS } from '@/utils/screening'

const SCREENING_PREVIEW_STORAGE_KEY = 'enterprise-screening-preview-draft'

function scoreLevel(score) {
  if (score >= 85) return '强匹配'
  if (score >= 70) return '较匹配'
  if (score >= 55) return '可关注'
  return '需谨慎'
}

function listText(items, fallback) {
  return Array.isArray(items) && items.length ? items.join('、') : fallback
}

export function formatScreeningPreviewTime(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value)
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function buildScreeningPreviewCandidate(item, rank) {
  const score = Number(item?.overall_score || 0)
  const dimensionRows = Object.entries(SCREENING_DIMENSION_LABELS).map(([key, label]) => ({
    key,
    label,
    score: item?.dimension_scores?.[key]?.score ?? 0,
    reason: item?.dimension_scores?.[key]?.reason || item?.dimension_scores?.[key]?.summary || '',
  }))

  return {
    rank,
    resumeId: item?.resume_id ?? rank,
    candidateName: item?.candidate_name || `候选人 #${rank}`,
    fileName: item?.file_name || '',
    yearsExp: Number(item?.years_exp || 0),
    overallScore: score,
    scoreLevel: scoreLevel(score),
    recommendation: item?.recommendation || '待评估',
    overallReason: item?.overall_reason || '',
    skillsText: listText(item?.skills || [], '未提取'),
    matchedSkillsText: listText(item?.matched_skills || [], '暂无明显命中'),
    missingSkillsText: listText(item?.missing_required_skills || [], '无明显硬缺口'),
    riskPoints: Array.isArray(item?.risk_points) ? item.risk_points : [],
    suggestions: Array.isArray(item?.optimization_suggestions) ? item.optimization_suggestions : [],
    dimensionRows,
  }
}

export function buildScreeningPreviewContext({
  result,
  sessionName = '',
  jdTitle = '',
  company = '',
  generatedAt = '',
}) {
  if (!result) return null

  const summary = result.summary || {}
  const candidates = (result.candidates || []).map((item, index) => buildScreeningPreviewCandidate(item, index + 1))
  const totalCandidates = Number(summary.total_candidates || candidates.length || 0)
  const candidateCount = Number(summary.returned_candidates || candidates.length || 0)
  const averageScore = candidates.length
    ? (candidates.reduce((sum, item) => sum + item.overallScore, 0) / candidates.length).toFixed(1)
    : '0.0'
  const recommendationText = Object.entries(summary.recommendation_distribution || {})
    .map(([label, count]) => `${label} ${count}人`)
    .join(' / ') || '暂无'
  const skillGaps = (summary.most_common_skill_gaps || [])
    .filter(item => item?.skill)
    .map(item => ({
      skill: item.skill,
      count: Number(item.count || 0),
      ratio: `${Math.round((Number(item.count || 0) / Math.max(totalCandidates, 1)) * 100)}%`,
    }))

  return {
    reportTitle: sessionName || `${summary.jd_title || jdTitle || '岗位'}候选人对比报告`,
    jdTitle: summary.jd_title || jdTitle || '未命名岗位',
    company: summary.company || company || '未填写公司',
    generatedAt: generatedAt || formatScreeningPreviewTime(),
    totalCandidates,
    candidateCount,
    averageScore,
    recommendationText,
    topCandidate: candidates[0] || null,
    skillGaps,
    candidates,
  }
}

export function persistScreeningPreviewDraft(payload) {
  sessionStorage.setItem(SCREENING_PREVIEW_STORAGE_KEY, JSON.stringify(payload))
}

export function readScreeningPreviewDraft() {
  const raw = sessionStorage.getItem(SCREENING_PREVIEW_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function clearScreeningPreviewDraft() {
  sessionStorage.removeItem(SCREENING_PREVIEW_STORAGE_KEY)
}

export { SCREENING_DIMENSION_LABELS as DIMENSION_LABELS, SCREENING_PREVIEW_STORAGE_KEY }
