/* 投递看板的数据形状层：从 PipelineKanban.vue 搬出来的一组纯函数与常量。
   这一页脚本 441 行里，"把后端返回的分组卡片算成统计/漏斗/跟进提醒"占了 ~120 行，而它们不发请求。

   搬的时候改了**一处**形状：`Date.now()` 原来是函数内部读的，现在由调用方传进来（`now`）。
   理由不是洁癖——跟进提醒的整条判据都挂在"离上次更新几天"上，不传时间就没法写一条
   "8 天前投递应该报 danger"的测试；判据本身的数字（3 天 / 7 天、86400000 毫秒一天）一个字没动。
   其余函数唯一的变化是把隐式读的 `kanban.value` / `counts.value` / `totalCards.value` 改成入参
   （同 D41 的 `city`、D49 的 `result`）。 */

/**
 * 看板列。`accent` 是卡片那颗点的类名后缀（模板里写 `'dot-' + col.accent`），
 * 取值集合就是样式里的 `.dot-*`，不在这里发明新值。
 * @typedef {Object} BoardColumn
 * @property {string} key
 * @property {string} label
 * @property {string} accent
 */

/**
 * 后端按阶段分组返回的一张投递卡片。字段全是后端拼写（snake_case），面板直接读，
 * 这一域**没有本地归一层**（对比 jobs 域的 `normalizeJob`），所以这份 typedef 就是后端契约的抄本。
 * 全部可选，除了 id/title/stage：老数据确实缺 `update_time`，缺了就不进跟进提醒（见 `needsFollowUp`）。
 * @typedef {Object} PipelineCard
 * @property {number} id
 * @property {string} title
 * @property {string} stage
 * @property {string} [company]
 * @property {string} [salary_range]
 * @property {string} [source]
 * @property {number|null} [match_score]
 * @property {string} [resume_version_label]
 * @property {string} [interview_at]
 * @property {string} [create_time]
 * @property {string} [update_time]
 */

/**
 * 后端 `stages` 分组：阶段键 → 卡片数组。缺键当空列，不报错。
 * @typedef {Record<string, PipelineCard[]>} Kanban
 */

/**
 * `stageCounts` 的产物：阶段键 → 条数。
 * @typedef {Record<string, number>} StageCounts
 */

/**
 * 简历版本维度的表现（`stats.items`），给统计面板那张表。字段抄自后端
 * `job_pipeline.py:266-279`（`label` 是后端兜底出来的"版本 #id"，不是前端拼的）。
 * @typedef {Object} VersionPerformance
 * @property {number|string} [resume_version_id]
 * @property {string} [label]
 * @property {number} [total]
 * @property {number} [submitted]
 * @property {number} [interviews]
 * @property {number} [offers]
 * @property {number} [accepted]
 * @property {number} [rejected]
 * @property {number} [interview_rate]
 * @property {number} [offer_rate]
 * @property {string|null} [latest_activity]
 */

/** @type {BoardColumn[]} */
export const columns = [
  { key: 'todo', label: '待投递', accent: 'slate' },
  { key: 'applied', label: '已投递', accent: 'blue' },
  { key: 'written_test', label: '笔试', accent: 'amber' },
  { key: 'interview', label: '面试', accent: 'violet' },
  { key: 'offer', label: 'Offer', accent: 'green' },
  { key: 'accepted', label: '已入职', accent: 'green' },
  { key: 'rejected', label: '已拒绝', accent: 'red' },
  { key: 'withdrawn', label: '已放弃', accent: 'gray' },
]

/**
 * 后端按阶段分组返回；缺键当成空列，不报错。
 * @param {Kanban} [kanban]
 * @returns {StageCounts}
 */
export function stageCounts(kanban) {
  /** @type {StageCounts} */
  const map = {}
  columns.forEach((col) => {
    map[col.key] = (kanban?.[col.key] || []).length
  })
  return map
}

/**
 * @param {Kanban} [kanban]
 * @returns {number}
 */
export function totalCardCount(kanban) {
  return columns.reduce((sum, col) => sum + (kanban?.[col.key] || []).length, 0)
}

/**
 * @param {Kanban} [kanban]
 * @returns {PipelineCard[]}
 */
export function flattenCards(kanban) {
  const all = []
  columns.forEach((col) => {
    ;(kanban?.[col.key] || []).forEach((card) => {
      all.push(card)
    })
  })
  return all
}

/** 漏斗只画"推进"的五段，入职/拒绝/放弃不进漏斗。 */
export function funnelRows(counts) {
  return columns
    .filter((c) => ['todo', 'applied', 'written_test', 'interview', 'offer'].includes(c.key))
    .map((c) => ({
      ...c,
      count: counts[c.key] || 0,
    }))
}

const FUNNEL_ORDER = ['todo', 'applied', 'written_test', 'interview', 'offer']

/** 到某一阶段的转化率：分母是"到这一步为止经过的卡片数"（前面所有段 + 本段）。 */
export function conversionRate(counts, total, stage) {
  if (!total) return 0
  const idx = FUNNEL_ORDER.indexOf(stage)
  if (idx <= 0) return Math.round(((counts[stage] || 0) / total) * 100)
  const prevTotal = FUNNEL_ORDER.slice(0, idx).reduce((s, k) => s + (counts[k] || 0), 0)
  const current = counts[stage] || 0
  const base = prevTotal + current
  return base > 0 ? Math.round((current / base) * 100) : 0
}

export function rejectionRate(counts, total) {
  if (!total) return 0
  return Math.round((((counts.rejected || 0) + (counts.withdrawn || 0)) / total) * 100)
}

/** "平均响应天数"只统计已投递一列，且只认有 `update_time` 的卡片；没有可算的就说没有。 */
export function avgResponseDays(appliedCards, now) {
  const days = (appliedCards || [])
    .filter((c) => c.update_time)
    .map((c) => Math.round((now - new Date(c.update_time).getTime()) / 86400000))
  if (!days.length) return '--'
  const avg = Math.round(days.reduce((s, d) => s + d, 0) / days.length)
  return avg + 'd'
}

export function funnelPercent(count, rows) {
  const max = Math.max(1, ...rows.map((s) => s.count))
  return Math.max(2, (count / max) * 100)
}

export function stageToRate(counts, from, to) {
  const fromCount = counts[from] || 0
  const toCount = counts[to] || 0
  if (!fromCount) return '0%'
  return Math.round((toCount / fromCount) * 100) + '%'
}

export function stageTagType(stage) {
  const map = {
    todo: 'info',
    applied: 'primary',
    written_test: 'warning',
    interview: 'success',
    offer: 'success',
    rejected: 'danger',
    withdrawn: 'info',
  }
  return map[stage] || 'info'
}

export function stageLabel(stage) {
  const map = {
    todo: '待投递',
    applied: '已投递',
    written_test: '笔试',
    interview: '面试',
    offer: 'Offer',
    accepted: '已入职',
    rejected: '已拒绝',
    withdrawn: '已放弃',
  }
  return map[stage] || stage || '-'
}

/* 跟进提醒只针对"投出去在等回音"的两段：笔试与已投递。
   卡片没写更新时间就不算（后端老数据可能没有这个字段）。 */
export function needsFollowUp(card) {
  return (card.stage === 'applied' || card.stage === 'written_test') && card.update_time
}

export function followUpDays(card, now) {
  if (!card.update_time) return 0
  return Math.round((now - new Date(card.update_time).getTime()) / 86400000)
}

export function followUpLevel(card, now) {
  const days = followUpDays(card, now)
  if (days >= 7) return 'danger'
  if (days >= 3) return 'warn'
  return 'ok'
}

/** 需要跟进的卡片数：等满 3 天才计入提醒。 */
export function followUpCount(cards, now) {
  return cards.filter((card) => needsFollowUp(card) && followUpDays(card, now) >= 3).length
}

/** 页面顶部那句"现在该干什么"：Offer > 面试 > 待跟进 > 继续补充。 */
export function pipelineFocusTitle(counts, waiting) {
  if (counts.offer) return '优先完成 Offer 取舍与确认。'
  if (counts.interview) return '把面试机会转化为可执行的准备计划。'
  if (waiting) return '有投递记录等待跟进，先处理超 3 天未回复的机会。'
  return '继续补充高匹配岗位，让投递保持稳定节奏。'
}

export function pipelineFocusDescription(counts, waiting) {
  if (counts.offer) return 'Offer 已进入决策阶段，比较整体回报、成长空间与截止日期。'
  if (counts.interview) return '从看板直接发起模拟面试，并把准备情况沉淀在对应机会中。'
  if (waiting) return '优先处理等待时间较长的投递，避免遗漏有效机会。'
  return '从岗位推荐中挑选高匹配机会，加入看板后持续追踪。'
}
