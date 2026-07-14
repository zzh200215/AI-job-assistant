const EN_TEXT_FALLBACKS = {
  'Proceed with further interviews to assess cultural fit and potential for training.':
    '建议继续安排后续面试，重点评估文化匹配度以及培养潜力。',
  'The candidate has strong skills and experience that align well with the job description, but there are some gaps in specific industry knowledge and educational background.':
    '候选人的技能和经验与岗位描述整体较为匹配，但在特定行业知识和教育背景方面仍存在一定差距。',
  'Strong technical skills aligned with the job requirements.': '技术能力与岗位要求高度匹配。',
  'Relevant work experience in similar roles.': '具备相关岗位的对口工作经验。',
  'Good educational background': '教育背景整体较好。',
  'Good communication and problem-solving abilities.': '具备良好的沟通与问题解决能力。',
  'Good communication and collaboration abilities.': '具备良好的沟通与协作能力。',
  'Limited industry-specific knowledge in the target sector.': '对目标行业的特定业务知识仍有不足。',
  'Limited exposure to the specific industry mentioned in the job description.':
    '对岗位描述中提到的目标行业接触还不够深入。',
  'Lack of certain specialized skills required for the role': '仍缺少岗位所要求的部分专项技能。',
  'Some required skills are not explicitly mentioned in the resume.':
    '部分岗位所需技能尚未在简历中被明确体现出来。',
  "Educational background could be more aligned with the job's requirements.":
    '教育背景与岗位要求的贴合度仍可进一步提升。',
  'Possible challenges in meeting educational criteria without further qualifications.':
    '若不进一步补充相关资质，可能较难完全满足学历或教育条件要求。',
  'Possible mismatch in understanding of specialized tools or processes mentioned in the job description.':
    '对于岗位描述中提到的专业工具或流程，当前理解和经验可能仍存在偏差。',
  'Potential need for additional training or onboarding to bridge the industry knowledge gap.':
    '可能需要通过额外培训或入职辅导来补齐行业知识差距。',
  'Consider the candidate for the role with a focus on providing industry-specific training and evaluating their potential for further education.':
    '可以考虑让候选人进入后续流程，但应重点结合行业专项培训，并评估其继续深造或补充资质的潜力。',
}

const DIMENSION_LABELS = {
  skills: '技能',
  experience: '经验',
  education: '学历',
  industry: '行业',
}

export const containsChinese = (text) => /[\u3400-\u9fff]/.test(String(text || ''))

export const localizeRecommendationText = (value) => {
  const text = String(value || '').trim()
  if (!text) return '-'
  if (containsChinese(text)) return text

  const lower = text.toLowerCase()
  if (lower === 'recommended') return '推荐'
  if (lower === 'hold' || lower === 'consider') return '备选'
  if (lower === 'not recommended' || lower === 'reject') return '不推荐'
  return localizeSentence(text) || text
}

export const localizeSentence = (value) => {
  const text = String(value || '').trim()
  if (!text || containsChinese(text)) return text
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (EN_TEXT_FALLBACKS[text]) return EN_TEXT_FALLBACKS[text]
  if (EN_TEXT_FALLBACKS[normalized]) return EN_TEXT_FALLBACKS[normalized]

  const lower = normalized.toLowerCase()
  if (lower.includes('strong skills') && lower.includes('align well with the job description')) {
    return '候选人的核心技能与岗位要求整体匹配，建议继续推进，并重点核实行业背景与能力短板。'
  }
  if (lower.includes('proceed with further interviews')) {
    return '建议继续安排后续面试，结合进一步沟通确认岗位适配度。'
  }
  if (lower.includes('strong technical skills') && lower.includes('job requirements')) {
    return '技术能力与岗位要求高度匹配。'
  }
  if (lower.includes('relevant work experience') && lower.includes('similar roles')) {
    return '具备相关岗位的对口工作经验。'
  }
  if (lower === 'good educational background') {
    return '教育背景整体较好。'
  }
  if (lower.includes('good communication') && lower.includes('problem-solving abilities')) {
    return '具备良好的沟通与问题解决能力。'
  }
  if (lower.includes('good communication') && lower.includes('collaboration abilities')) {
    return '具备良好的沟通与协作能力。'
  }
  if (lower.includes('limited industry-specific knowledge')) {
    return '对目标行业的特定业务知识仍有不足。'
  }
  if (lower.includes('limited exposure to the specific industry')) {
    return '对岗位描述中提到的目标行业接触还不够深入。'
  }
  if (
    lower.includes('lack of certain specialized skills') &&
    lower.includes('required for the role')
  ) {
    return '仍缺少岗位所要求的部分专项技能。'
  }
  if (
    lower.includes('required skills') &&
    lower.includes('explicitly mentioned') &&
    lower.includes('resume')
  ) {
    return '部分岗位所需技能尚未在简历中被明确体现出来。'
  }
  if (lower.includes('educational background') && lower.includes('job')) {
    return '教育背景与岗位要求的贴合度仍可进一步提升。'
  }
  if (lower.includes('educational criteria') && lower.includes('without further qualifications')) {
    return '若不进一步补充相关资质，可能较难完全满足学历或教育条件要求。'
  }
  if (
    lower.includes('mismatch in understanding') &&
    lower.includes('specialized tools or processes')
  ) {
    return '对于岗位描述中提到的专业工具或流程，当前理解和经验可能仍存在偏差。'
  }
  if (lower.includes('additional training') || lower.includes('onboarding')) {
    return '可能需要通过额外培训或入职辅导来补齐行业知识差距。'
  }
  if (
    lower.includes('consider the candidate for the role') &&
    lower.includes('industry-specific training')
  ) {
    return '可以考虑让候选人进入后续流程，但应重点结合行业专项培训，并评估其继续深造或补充资质的潜力。'
  }
  return text
}

export const localizeSeverity = (value) => {
  const text = String(value || '').trim()
  if (!text) return ''
  if (containsChinese(text)) return text

  const lower = text.toLowerCase()
  if (lower === 'high') return '高'
  if (lower === 'medium') return '中'
  if (lower === 'low') return '低'
  return text
}

export const normalizeLocalizedObjectList = (value) => {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (typeof item === 'string') return localizeSentence(item)
    if (!item || typeof item !== 'object') return String(item || '')

    return {
      ...item,
      item: localizeSentence(
        item.item || item.name || item.title || item.skill || item.point || ''
      ),
      impact: localizeSentence(item.impact || ''),
      evidence: localizeSentence(item.evidence || ''),
      action: localizeSentence(item.action || ''),
      severity: localizeSeverity(item.severity || ''),
    }
  })
}

export const normalizeLocalizedTextList = (value) => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (typeof item === 'string') return localizeSentence(item)
      if (item && typeof item === 'object') {
        return localizeSentence(
          item.item || item.name || item.title || item.point || item.text || ''
        )
      }
      return String(item || '')
    })
    .filter(Boolean)
}

export const localizeDimensionLabel = (value) => {
  const text = String(value || '').trim()
  if (!text) return '-'
  if (containsChinese(text)) return text
  return DIMENSION_LABELS[text.toLowerCase()] || text
}
