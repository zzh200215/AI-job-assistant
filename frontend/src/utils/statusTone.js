/**
 * 状态 → el-tag 颜色的唯一出处。
 *
 * 和分数色板同一个问题：同一个后端状态在不同页面被涂成不同颜色。改动前实测
 * （17 个 tag 色表 / 32 个状态键）有两处真矛盾——
 *  - 异步任务 `running`：任务中心是蓝，两个 agent 页是橙（而橙在这几页里已经表示
 *    `partial`＝部分完成，需要看一眼）；
 *  - 面试会话 `ongoing`：房间页是绿，设置页是橙，而绿又同时表示 `completed`。
 * 这里定的口径是：**绿只代表"完成"**，进行中一律 primary，橙留给"部分/需留意"，
 * 红留给失败，灰留给"还没开始 / 已取消 / 不知道"。
 *
 * 另一类同名不同义的键（`type`、`resume_template`、`skill_model` 等）不在此表：
 * 它们在各自页面表达的是不同领域概念，颜色不同不是矛盾。
 */

export const TAG_TYPES = ['primary', 'success', 'info', 'warning', 'danger']

/** 编排/分析任务（AgentRun 与 orchestration 共用的一组状态）。 */
export const TASK_STATUS_TAGS = {
  pending: 'info',
  running: 'primary',
  completed: 'success',
  partial: 'warning',
  failed: 'danger',
  cancelled: 'info',
}

/** 模拟面试会话（含房间内的连接态）。`created` 只有列表侧会拿到。 */
export const INTERVIEW_STATUS_TAGS = {
  idle: 'info',
  created: 'info',
  connecting: 'primary',
  ongoing: 'primary',
  evaluating: 'primary',
  completed: 'success',
  error: 'danger',
}

/** 未知状态返回 info：不能因为后端加了一个新枚举就把任务标成红色失败。 */
export function tagTypeFor(table, status) {
  return table[status] || 'info'
}

/** 投递优先级标签：优先投递 / 值得投递 / 先观察，还要兼容遗留的 强烈/可以/谨慎 两套词。
    用子串匹配而不是查表：标签文案带前后缀（"优先投递 · 82"），历史值又是另一套形容词。 */
export function priorityTagType(value) {
  const v = value || ''
  if (v.includes('优先') || v.includes('强烈')) return 'success'
  if (v.includes('值得') || v.includes('可以')) return 'warning'
  if (v.includes('谨慎')) return 'danger'
  return 'info'
}

/**
 * 中文三档强弱（**高 / 中 / 低**）→ el-tag 颜色的唯一出处（D91）。
 * 它同时服务两个字段名：rubric 的 `severity`（差距严重度）与 `priority`（行动项优先级）——
 * 两处的取值域是同一份（`src/constants/states.js` 的 SEVERITY_LEVELS / PRIORITY_LEVELS），
 * 颜色口径也必须一致，否则"高"在差距列是红、在行动项列成了别的。
 * 迁移前这五个地方各写各的三元式：`SkillsPane`、`History` 详情、`CareerPlanPane`、
 * `ReportSummaryPane`、`MultiAgentAnalysis`。
 * **一件实测出来的事顺带记在这**：迁完之后 `styleDebtRatchet` 的 `statusTagEntries` 预算**一分未动**
 * ——那把尺子数的是 `键: '颜色'` 那种形态，`x === '高' ? 'danger' : …` 三元式不在它的口径里。
 * 所以这一族重复是**守卫看不见的重复**：收它的理由是"颜色只有一个出处"，不是"降某个数字"，
 * 也别以为有门在替我看着这类漂移。
 * 未知值返回 info，与 `tagTypeFor` 同一口径：**不能因为后端多给一个档位就把它涂成失败色**。
 *
 * 刻意不覆盖的两处，别当漏网：`CareerPlanning.vue` 的投递策略标签是**两段式**（高→danger，
 * 其余→warning，没有 info 档），并进这张表会把它的观感改掉；`analysisModel.js` 的
 * `complexityType`（简单/中等/困难）是另一个域，名字不同、颜色也不同。
 */
const LEVEL_TAGS = { 高: 'danger', 中: 'warning', 低: 'info' }

export function levelTagType(value) {
  return LEVEL_TAGS[value] || 'info'
}
