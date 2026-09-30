import { describe, expect, it } from 'vitest'

import {
  complexityType,
  confidenceTagType,
  dimensionScore,
  explainRecommendationTag,
  groupInterviewQuestions,
  groupTitle,
  hasStructuredCareerGaps,
  mergeMissingSkills,
  milestoneIcon,
  normalizeConfidence,
  pickMatchedSkills,
  pickMissingSkills,
  scoreTagType,
  statusText,
  stepLabel,
  typeLabel,
} from '@/features/analysis/lib/analysisModel'

/* D49 把一组纯函数从 SmartAnalysis.vue 搬进 lib，唯一改动是把隐式的 `result.value` 读取换成入参。
   下面这些 old* 是**搬家前的原函数**，逐字抄自
   HEAD:frontend/src/features/analysis/views/SmartAnalysis.vue，只把 `result.value` 改成参数
   `result`、把 `careerData.value` 换成它展开后的同一条路径。
   留着它们只服务一个问题：搬完的规则一条都没变。 */

function oldGetDimension(result, key) {
  const value = result?.match_report?.dimension_scores?.[key]
  if (value && typeof value === 'object') return value
  if (typeof value === 'number') return { score: value }
  return { score: 0 }
}

function oldDimensionScore(result, key) {
  return oldGetDimension(result, key).score ?? 0
}

function oldPickNonEmptyArray(...candidates) {
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) return candidate
  }
  return []
}

const oldPickMatchedSkills = (result) =>
  oldPickNonEmptyArray(oldGetDimension(result, 'skills').matched, result?.matched_skills)

const oldPickMissingSkills = (result) =>
  oldPickNonEmptyArray(oldGetDimension(result, 'skills').missing, result?.missing_skills)

const OLD_INTERVIEW_GROUP_DEFS = [
  { key: 'hr_questions', legacy: 'basic', title: 'HR 题' },
  { key: 'tech_questions', legacy: 'tech', title: '技术题' },
  { key: 'project_questions', legacy: 'project', title: '项目题' },
  { key: 'scenario_questions', legacy: 'scenario', title: '场景题' },
]

function oldInterviewGroups(result) {
  const iq = result?.interview_questions || {}
  const groups = {}
  OLD_INTERVIEW_GROUP_DEFS.forEach(({ key, legacy }) => {
    const items =
      Array.isArray(iq[key]) && iq[key].length
        ? iq[key]
        : Array.isArray(iq[legacy])
          ? iq[legacy]
          : []
    if (items.length) groups[key] = items
  })
  return groups
}

const oldGroupTitle = (k) => OLD_INTERVIEW_GROUP_DEFS.find((item) => item.key === k)?.title || k

const oldHasStructuredSkillGaps = (careerData) => {
  const gaps = careerData?.skill_gaps || []
  return gaps.length > 0 && typeof gaps[0] === 'object' && gaps[0] !== null
}

function oldExplainMissingSkills(explainResult) {
  const skillMatch = explainResult?.skill_match || {}
  const required = Array.isArray(skillMatch.missing_required) ? skillMatch.missing_required : []
  const nice = Array.isArray(skillMatch.missing_nice) ? skillMatch.missing_nice : []
  return [...required, ...nice.filter((item) => !required.includes(item))]
}

/* 后端这几代响应里同一件事至少有三种写法（维度分给对象或给裸数字、面试题用新键或 legacy 键、
   技能缺口在维度对象里或在记录顶层），回退顺序就是这一页的全部风险。三条轴各自读互不相干的
   字段，所以逐轴铺满而不是做笛卡尔积。 */
const dimensionShapes = [
  undefined,
  {},
  { skills: 0.72 },
  { skills: {} },
  { skills: { score: null } },
  { skills: { score: 0.4, matched: [], missing: [] } },
  { skills: { score: 0.9, matched: ['Go'], missing: ['K8s'] } },
  { skills: 'oops', experience: 0.3, education: { score: 0.6 }, industry: { score: 0 } },
  { skills: { matched: ['维度'], missing: undefined } },
]
const topSkillShapes = [undefined, [], ['A'], ['B', 'C']]
const interviewShapes = [
  undefined,
  {},
  { hr_questions: ['q1'], basic: ['旧q'] },
  { hr_questions: [], basic: ['旧q'] },
  { tech: ['旧技术'] },
  { hr_questions: 'oops', project: ['p'] },
  { scenario_questions: ['s'], tech_questions: ['t'], hr_questions: ['h'] },
  { basic: [], tech: [], project: [], scenario: [] },
  { tech_questions: [], tech: ['旧t'], project_questions: [{}] },
]
const explainShapes = [
  undefined,
  {},
  { skill_match: {} },
  { skill_match: { matched: ['M'], missing_required: ['A'], missing_nice: ['A', 'B'] } },
  { skill_match: { missing_required: 'x', missing_nice: ['B'] } },
  { skill_match: { missing_nice: ['B', 'B'] } },
  { skill_match: { missing_required: ['A', 'A'], missing_nice: [] } },
]

const scoreRecords = []
for (const dimension_scores of dimensionShapes)
  for (const matched_skills of topSkillShapes)
    for (const missing_skills of topSkillShapes)
      scoreRecords.push({ match_report: { dimension_scores }, matched_skills, missing_skills })

describe('D49 搬家：规则与搬家前逐条相同', () => {
  it(`覆盖 ${scoreRecords.length} 种维度/顶层技能形状，分数与两份技能列表一个不差`, () => {
    for (const result of scoreRecords) {
      for (const key of ['skills', 'experience', 'education', 'industry']) {
        expect(dimensionScore(result, key), `维度 ${key} 的分数变了`).toBe(
          oldDimensionScore(result, key)
        )
      }
      expect(pickMatchedSkills(result)).toEqual(oldPickMatchedSkills(result))
      expect(pickMissingSkills(result)).toEqual(oldPickMissingSkills(result))
    }
  })

  it('面试题分组与标题一个不差（新键空数组要回退到 legacy 键）', () => {
    for (const interview_questions of interviewShapes) {
      const result = { interview_questions }
      const old = oldInterviewGroups(result)
      expect(groupInterviewQuestions(result)).toEqual(old)
      for (const key of [...Object.keys(old), 'unknown_key']) {
        expect(groupTitle(key)).toBe(oldGroupTitle(key))
      }
    }
  })

  it('技能缺口是否结构化一个不差', () => {
    for (const career_planning of [
      undefined,
      null,
      {},
      '字符串',
      { skill_gaps: [] },
      { skill_gaps: ['字符串'] },
      { skill_gaps: [{ skill: 'x' }] },
      { skill_gaps: [null] },
      { skill_gaps: [{}] },
      { skill_gaps: 'oops' },
      { skill_gaps: {} },
    ]) {
      expect(hasStructuredCareerGaps({ career_planning })).toBe(
        oldHasStructuredSkillGaps(career_planning)
      )
    }
  })

  it('解释接口的必需/加分两列合并结果一个不差', () => {
    for (const explain of explainShapes) {
      expect(mergeMissingSkills(explain?.skill_match)).toEqual(oldExplainMissingSkills(explain))
    }
  })
})

describe('钉死每条规则（搬家只改了参数，没改判据）', () => {
  it('维度分认对象、认裸数字、缺键给 0', () => {
    const result = {
      match_report: {
        dimension_scores: { skills: 0.72, education: { score: 0.6 }, industry: {} },
      },
    }
    expect(dimensionScore(result, 'skills')).toBe(0.72)
    expect(dimensionScore(result, 'education')).toBe(0.6)
    expect(dimensionScore(result, 'industry')).toBe(0)
    expect(dimensionScore(result, 'experience')).toBe(0)
    expect(dimensionScore({}, 'skills')).toBe(0)
    expect(dimensionScore(undefined, 'skills')).toBe(0)
  })

  it('技能列表：维度对象优先，空了才回退到记录顶层', () => {
    const full = {
      match_report: { dimension_scores: { skills: { matched: ['Go'], missing: ['K8s'] } } },
      matched_skills: ['顶层'],
      missing_skills: ['顶层'],
    }
    expect(pickMatchedSkills(full)).toEqual(['Go'])
    expect(pickMissingSkills(full)).toEqual(['K8s'])
    const fallback = {
      match_report: { dimension_scores: { skills: { matched: [], missing: undefined } } },
      matched_skills: ['顶层A', '顶层B'],
      missing_skills: ['顶层C'],
    }
    expect(pickMatchedSkills(fallback)).toEqual(['顶层A', '顶层B'])
    expect(pickMissingSkills(fallback)).toEqual(['顶层C'])
    expect(pickMatchedSkills({})).toEqual([])
  })

  it('面试题：新键是空数组时仍用 legacy 键，非数组一律当没有', () => {
    expect(
      groupInterviewQuestions({ interview_questions: { hr_questions: [], basic: ['旧Q'] } })
    ).toEqual({ hr_questions: ['旧Q'] })
    expect(
      groupInterviewQuestions({ interview_questions: { hr_questions: ['新Q'], basic: ['旧Q'] } })
    ).toEqual({ hr_questions: ['新Q'] })
    expect(groupInterviewQuestions({ interview_questions: { tech_questions: 'oops' } })).toEqual({})
    expect(groupInterviewQuestions({})).toEqual({})
    expect(groupTitle('tech_questions')).toBe('技术题')
    expect(groupTitle('unknown_key')).toBe('unknown_key')
  })

  it('置信度：只有带 score 或带非空 summary 的对象才算数', () => {
    for (const junk of [undefined, null, {}, { summary: '' }, '字符串', 0]) {
      expect(normalizeConfidence(junk), `${JSON.stringify(junk)} 不该被当成置信度`).toBeNull()
    }
    expect(normalizeConfidence({ score: 0 })).toEqual({ score: 0 })
    expect(normalizeConfidence({ summary: '有' })).toEqual({ summary: '有' })
  })

  it('结构化技能缺口：第一项是对象才算，null 与字符串都不算', () => {
    expect(hasStructuredCareerGaps({ career_planning: { skill_gaps: [{ skill: 'x' }] } })).toBe(
      true
    )
    expect(hasStructuredCareerGaps({ career_planning: { skill_gaps: [null] } })).toBe(false)
    expect(hasStructuredCareerGaps({ career_planning: { skill_gaps: ['K8s'] } })).toBe(false)
    expect(hasStructuredCareerGaps({})).toBe(false)
  })

  it('必需优先去重：同一项技能在两列都有时只出现一次，且在必需那一列的位置', () => {
    expect(mergeMissingSkills({ missing_required: ['A'], missing_nice: ['A', 'B'] })).toEqual([
      'A',
      'B',
    ])
    expect(mergeMissingSkills({ missing_nice: ['B', 'B'] })).toEqual(['B', 'B'])
    expect(mergeMissingSkills({ missing_required: 'x', missing_nice: ['B'] })).toEqual(['B'])
    expect(mergeMissingSkills(undefined)).toEqual([])
  })

  it('步骤名两张表都认，状态文案未知就原样透出', () => {
    expect(stepLabel('MatchAnalysisAgent')).toBe('匹配分析')
    expect(stepLabel('match_analysis')).toBe('匹配分析')
    expect(stepLabel('matching_analysis')).toBe('匹配分析')
    expect(stepLabel('career_planning')).toBe('职业规划')
    expect(stepLabel('summary_report')).toBe('汇总报告')
    expect(stepLabel('brand_new_agent')).toBe('brand_new_agent')
    expect(statusText('pending')).toBe('等待中')
    expect(statusText('running')).toBe('执行中')
    expect(statusText('completed')).toBe('已完成')
    expect(statusText('failed')).toBe('失败')
    expect(statusText('weird')).toBe('weird')
  })

  it('四张 el-tag 色表的边界与兜底', () => {
    expect([scoreTagType(0.8), scoreTagType(0.79), scoreTagType(0.6), scoreTagType(0.59)]).toEqual([
      'success',
      'warning',
      'warning',
      'info',
    ])
    expect([
      confidenceTagType('high'),
      confidenceTagType('medium'),
      confidenceTagType('low'),
    ]).toEqual(['success', 'warning', 'danger'])
    expect(explainRecommendationTag('强烈推荐')).toBe('success')
    expect(explainRecommendationTag('可以投递')).toBe('primary')
    expect(explainRecommendationTag('谨慎投递')).toBe('warning')
    expect(explainRecommendationTag('不建议投递')).toBe('danger')
    expect(explainRecommendationTag('')).toBe('info')
    expect(complexityType('简单')).toBe('success')
    expect(complexityType('中等')).toBe('warning')
    expect(complexityType('困难')).toBe('danger')
    expect(complexityType('未见过的词')).toBe('info')
  })

  it('文档类型与里程碑图标：空值有兜底，未知类型透出原文', () => {
    expect(typeLabel('resume_template')).toBe('简历模板')
    expect(typeLabel('jd_lib')).toBe('岗位描述库')
    expect(typeLabel('interview_q')).toBe('面试题库')
    expect(typeLabel('skill_model')).toBe('能力模型')
    expect(typeLabel('industry_report')).toBe('行业报告')
    expect(typeLabel('general')).toBe('通用')
    expect(typeLabel('')).toBe('通用')
    expect(typeLabel(undefined)).toBe('通用')
    expect(typeLabel('new_type')).toBe('new_type')
    expect(milestoneIcon('skill')).toBe('📚')
    expect(milestoneIcon('cert')).toBe('🎓')
    expect(milestoneIcon('project')).toBe('🔨')
    expect(milestoneIcon('job')).toBe('💼')
    expect(milestoneIcon('')).toBe('📍')
  })
})
