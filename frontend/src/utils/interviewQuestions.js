export const INTERVIEW_GROUP_DEFS = [
  { key: 'hr_questions', legacy: 'basic', title: '\u{1F9D1} HR \u9898' },
  { key: 'tech_questions', legacy: 'tech', title: '\u{1F4BB} \u6280\u672F\u9898' },
  { key: 'project_questions', legacy: 'project', title: '\u{1F4C2} \u9879\u76EE\u9898' },
  { key: 'scenario_questions', legacy: 'scenario', title: '\u{1F9E9} \u573A\u666F\u9898' },
]

export function normalizeInterviewQuestions(interviewQuestions, { dropEmpty = true } = {}) {
  if (!interviewQuestions || typeof interviewQuestions !== 'object') return {}

  const normalized = Object.fromEntries(
    INTERVIEW_GROUP_DEFS.map(({ key, legacy }) => {
      const currentItems = Array.isArray(interviewQuestions[key]) ? interviewQuestions[key] : []
      const legacyItems = Array.isArray(interviewQuestions[legacy])
        ? interviewQuestions[legacy]
        : []
      return [key, currentItems.length ? currentItems : legacyItems]
    })
  )

  if (!dropEmpty) return normalized

  return Object.fromEntries(
    Object.entries(normalized).filter(([, items]) => Array.isArray(items) && items.length > 0)
  )
}

export function hasInterviewQuestions(interviewQuestions) {
  return Object.keys(normalizeInterviewQuestions(interviewQuestions)).length > 0
}

export function getInterviewGroupTitle(key) {
  return INTERVIEW_GROUP_DEFS.find((item) => item.key === key)?.title || key
}
