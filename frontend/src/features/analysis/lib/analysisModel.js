/* 智能分析页的数据形状层：从 SmartAnalysis.vue 搬出来的一组纯函数与常量。
   搬它们是因为这页的脚本里，"把一条 AnalysisRecord 读成能渲染的形状"（维度分、技能命中的两路
   回退、面试题的新旧字段分组、步骤名与状态文案、给置信度/复杂度配 el-tag 颜色）占了 110 行，
   而它们不发请求、不写任何状态。
   `getDimension` / `groupInterviewQuestions` 原本直接读视图上的 `result.value`。搬的时候只把那一次
   读取改成调用方传进来的参数，**判定规则一个字没动**——变的只是"谁去读那条记录"可见了（同 D41
   给 `calculateApplicationPriority` 加 `city` 参数那一刀）。 */

/** 维度分：后端可能给对象（`{score, matched, missing}`），也可能只给一个数字。 */
function getDimension(result, key) {
  const value = result?.match_report?.dimension_scores?.[key]
  if (value && typeof value === 'object') return value
  if (typeof value === 'number') return { score: value }
  return { score: 0 }
}

export function dimensionScore(result, key) {
  return getDimension(result, key).score ?? 0
}

function pickNonEmptyArray(...candidates) {
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) return candidate
  }
  return []
}

/** 命中/缺失技能有两个来源：维度对象，或记录顶层的旧字段。维度对象优先，空了才回退。 */
export function pickMatchedSkills(result) {
  return pickNonEmptyArray(getDimension(result, 'skills').matched, result?.matched_skills)
}

export function pickMissingSkills(result) {
  return pickNonEmptyArray(getDimension(result, 'skills').missing, result?.missing_skills)
}

/** 引用页与记录各带一份置信度，但只有"真的有内容"的那份才算数。 */
export function normalizeConfidence(value) {
  if (!value || typeof value !== 'object') return null
  if (typeof value.score === 'number') return value
  if (value.summary) return value
  return null
}

/* 面试题分组：新字段是 `hr_questions` 这一组，旧记录只有 `basic`/`tech`/... 这套 legacy 键。
   两代字段都要认，否则历史记录里的题会整组消失。 */
const INTERVIEW_GROUP_DEFS = [
  { key: 'hr_questions', legacy: 'basic', title: 'HR 题' },
  { key: 'tech_questions', legacy: 'tech', title: '技术题' },
  { key: 'project_questions', legacy: 'project', title: '项目题' },
  { key: 'scenario_questions', legacy: 'scenario', title: '场景题' },
]

export function groupInterviewQuestions(result) {
  const iq = result?.interview_questions || {}
  const groups = {}
  INTERVIEW_GROUP_DEFS.forEach(({ key, legacy }) => {
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

export function groupTitle(key) {
  return INTERVIEW_GROUP_DEFS.find((item) => item.key === key)?.title || key
}

/** 职业规划的技能缺口：第一项是对象才算"结构化"，纯字符串列表要走另一套渲染。 */
export function hasStructuredCareerGaps(result) {
  const gaps = result?.career_planning?.skill_gaps || []
  return gaps.length > 0 && typeof gaps[0] === 'object' && gaps[0] !== null
}

export function milestoneIcon(type) {
  return { skill: '📚', cert: '🎓', project: '🔨', job: '💼' }[type] || '📍'
}

export function complexityType(level) {
  return { 简单: 'success', 中等: 'warning', 困难: 'danger' }[level] || 'info'
}

export function typeLabel(t) {
  return (
    {
      resume_template: '简历模板',
      jd_lib: '岗位描述库',
      interview_q: '面试题库',
      skill_model: '能力模型',
      industry_report: '行业报告',
      general: '通用',
    }[t] ||
    t ||
    '通用'
  )
}

export function scoreTagType(score) {
  return score >= 0.8 ? 'success' : score >= 0.6 ? 'warning' : 'info'
}

export function confidenceTagType(level) {
  return level === 'high' ? 'success' : level === 'medium' ? 'warning' : 'danger'
}

export function explainRecommendationTag(text) {
  return (
    {
      强烈推荐: 'success',
      可以投递: 'primary',
      谨慎投递: 'warning',
      不建议投递: 'danger',
    }[text] || 'info'
  )
}

/* 解释接口把缺口拆成"必需"与"加分项"两列，但同一项技能可能两列都有，所以合并时按必需优先去重。 */
export function mergeMissingSkills(skillMatch) {
  const required = Array.isArray(skillMatch?.missing_required) ? skillMatch.missing_required : []
  const nice = Array.isArray(skillMatch?.missing_nice) ? skillMatch.missing_nice : []
  return [...required, ...nice.filter((item) => !required.includes(item))]
}

/* 步骤名有两套：编排任务用 Agent 类名，分析记录用 canonical key。两张表都留着，
   canonical 优先——同一含义在两代后端响应里键名不同。 */
const STEP_LABELS = {
  IntentAgent: '意图识别',
  ResumeParseAgent: '简历解析',
  JDParseAgent: 'JD 解析',
  MatchAnalysisAgent: '匹配分析',
  ResumeOptimizeAgent: '简历优化',
  InterviewQuestionAgent: '面试题生成',
  SummaryAgent: '汇总报告',
  intent_recognition: '意图识别',
  resume_parse: '简历解析',
  jd_parse: 'JD 解析',
  knowledge_retrieval: '知识检索',
  matching_analysis: '匹配分析',
  resume_optimization: '简历优化',
  interview_question_generation: '面试题生成',
  self_check: '自我校验',
  final_report: '汇总报告',
}

const CANONICAL_STEP_LABELS = {
  intent_recognition: '意图识别',
  resume_parse: '简历解析',
  jd_parse: 'JD 解析',
  knowledge_retrieval: '知识检索',
  match_analysis: '匹配分析',
  resume_optimization: '简历优化',
  interview_questions: '面试题生成',
  career_planning: '职业规划',
  self_check: '自我校验',
  summary_report: '汇总报告',
}

export function stepLabel(name) {
  return CANONICAL_STEP_LABELS[name] || STEP_LABELS[name] || name
}

export function statusText(status) {
  return (
    { pending: '等待中', running: '执行中', completed: '已完成', failed: '失败' }[status] || status
  )
}
