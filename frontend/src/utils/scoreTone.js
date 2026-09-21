/**
 * 分数语义档的唯一出处。
 *
 * 页面过去各自挑颜色和阈值（85/70/55、80/60/40、80/60 三套并存），于是同一张卡片可以
 * 一边写"可以投递"、一边把分数标成警告色：档位与后端 `MatchExplainer._recommendation`
 * （app/services/match_explainer_service.py）的 85/70/50 不一致。这里只认档位，
 * 颜色留给 CSS 变量——JS 里不再出现 hex，棘轮测试也就能真的数得住。
 */

export const MATCH_SCORE_BANDS = [
  { min: 85, tone: 'high' },
  { min: 70, tone: 'good' },
  { min: 50, tone: 'warn' },
  { min: -Infinity, tone: 'risk' },
]

// 面试表现分和岗位匹配度是两个量，档位不必相同；相同的是"只从这里出 tone"。
export const INTERVIEW_SCORE_BANDS = [
  { min: 85, tone: 'high' },
  { min: 70, tone: 'good' },
  { min: 55, tone: 'warn' },
  { min: -Infinity, tone: 'risk' },
]

export function scoreTone(value, bands = MATCH_SCORE_BANDS) {
  // null / '' 是"没有这个分数"，不是 0 分——不能标成红色风险档
  if (value === null || value === undefined || value === '') return 'unknown'
  const n = Number(value)
  if (!Number.isFinite(n)) return 'unknown'
  const band = bands.find((item) => n >= item.min)
  return band ? band.tone : 'unknown'
}

/** 给 class 用的写法：`<span :class="scoreToneClass(row.match_score)">`。 */
export function scoreToneClass(value, bands = MATCH_SCORE_BANDS, prefix = 'score-tone') {
  return `${prefix} ${prefix}--${scoreTone(value, bands)}`
}

/** 给 SVG / el-progress 这类"必须传颜色值"的地方用；仍是同一个变量，不是第二份色值。 */
export function scoreToneColor(value, bands = MATCH_SCORE_BANDS) {
  return `var(--app-score-${scoreTone(value, bands)})`
}

export function scoreToneFillClass(value, bands = MATCH_SCORE_BANDS) {
  return `score-fill--${scoreTone(value, bands)}`
}

/* el-tag 只有五个 type，正好和 tone 一一对上。历史上这里各处手写
   `score >= 80 ? 'success' : ...`，于是同一个 78 分在推荐页是蓝、在历史页是黄。 */
const TAG_TYPE_BY_TONE = {
  high: 'success',
  good: 'primary',
  warn: 'warning',
  risk: 'danger',
  // 没有分数不是"很差"，是"不知道"——灰标签，别涂红
  unknown: 'info',
}

export function scoreToneTagType(value, bands = MATCH_SCORE_BANDS) {
  return TAG_TYPE_BY_TONE[scoreTone(value, bands)]
}

const TONE_ORDER = ['risk', 'warn', 'good', 'high']

/** 只需要两档（"够好/其他"）的地方：是否至少到某个 tone。unknown 不算够好。 */
export function scoreToneAtLeast(value, tone, bands = MATCH_SCORE_BANDS) {
  return TONE_ORDER.indexOf(scoreTone(value, bands)) >= TONE_ORDER.indexOf(tone)
}

/* 面试表现分的三个出口。同一个页面里"颜色 / 文案 / 胶囊"必须走同一档位，
   否则会出现芯片是警告黄、旁边文字写"风险偏高"的第 4 种分界。 */
export function interviewScoreTone(value) {
  return scoreTone(value, INTERVIEW_SCORE_BANDS)
}

export function interviewScoreColor(value) {
  return scoreToneColor(value, INTERVIEW_SCORE_BANDS)
}

export function interviewScoreToneClass(value, prefix = 'score-tone') {
  return scoreToneClass(value, INTERVIEW_SCORE_BANDS, prefix)
}
