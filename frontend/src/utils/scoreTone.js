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

/* 分数当**文字**用时不能直接吃 tone 本体：good（蓝）压在深色面板上实测 3.06、risk（红）4.15，
   两档都够不到正文的 4.5。抬的幅度用的是这一族已经量过的那批数（蓝混白 25% → 5.08、
   红混白 20% → 5.48），其余三档本体在深色面上已经过线（high 5.20 / warn 5.86 / unknown 5.07）。
   填色与描边不走这里——那是非文字，门槛是 3:1。 */
const TEXT_TONE = {
  high: 'var(--app-score-high)',
  good: 'color-mix(in srgb, var(--app-score-good), white 25%)',
  warn: 'var(--app-score-warn)',
  risk: 'color-mix(in srgb, var(--app-score-risk), white 20%)',
  unknown: 'var(--app-score-unknown)',
}

export function scoreToneTextColor(value, bands = MATCH_SCORE_BANDS) {
  return TEXT_TONE[scoreTone(value, bands)]
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

/**
 * "顶档"判据的唯一出处（§10.5 拍定：界面上那几处原先自己抄的 80 全部跟随顶档线）。
 * 顶档就是 `bands` 里第一条的 `min`，匹配分与面试分今天都是 **85**，分别对齐后端三处：
 * `match_explainer_service.py:530`（强烈推荐）、`prompts/answer_evaluation.py:22`（优秀）、
 * `resume_workspace_service.py:87`（A 级）。没有分数（null / NaN）不是"0 分"，也不算顶档。
 *
 * 刻意**不包含**的那一把尺：`features/jobs/lib/jobModel.js:342` 的 `finalScore >= 82 ? 优先投递`。
 * 它数的是本页自己合成的投递优先级（技能/经验/薪资/城市/已落库…再加匹配分的 28%），
 * 与后端的匹配分不是同一个量；那张卡上也不显示匹配徽章，所以两者同屏不会打架。
 */
export function isTopTier(value, bands = MATCH_SCORE_BANDS) {
  return scoreToneAtLeast(value, 'high', bands)
}

/* 面试表现分的三个出口。同一个页面里"颜色 / 文案 / 胶囊"必须走同一档位，
   否则会出现芯片是警告黄、旁边文字写"风险偏高"的第 4 种分界。 */
export function interviewScoreTone(value) {
  return scoreTone(value, INTERVIEW_SCORE_BANDS)
}

export function interviewScoreColor(value) {
  return scoreToneColor(value, INTERVIEW_SCORE_BANDS)
}

export function interviewScoreTextColor(value) {
  return scoreToneTextColor(value, INTERVIEW_SCORE_BANDS)
}

export function interviewScoreToneClass(value, prefix = 'score-tone') {
  return scoreToneClass(value, INTERVIEW_SCORE_BANDS, prefix)
}
