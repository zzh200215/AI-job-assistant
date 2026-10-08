/**
 * "拼出来的类名"的值域：`dot-high`、`severity-medium`、`confidence-low`、`action-high` 这一族
 * 由模板把后端的一个字段直接拼进 class（`'dot-' + task.priority`、`` `severity-${item.severity}` ``），
 * 所以**样式表里该有哪几条规则，取决于后端能发哪些值**——这件事以前只存在于样式文件的运气里。
 *
 * D76/D77 用静态尺子与浏览器快照都判不了它们：静态看不见后端的值域，而单屏快照只证明
 * "这一屏没渲染到"，不证明"没有值能渲染到"。所以域写在这里，两个方向各有一条守卫：
 *   正向 —— 域里每个值在该有规则的视图里都必须有一条 `.prefix-value`；
 *   反向 —— 视图里每条 `.prefix-*` 规则的值都必须还在域里（多出来的就是死样式）。
 * 每个域都标了它的出处：多数是后端的某个字段，`FOLLOW_UP_LEVELS` 那一个是前端自己的一个纯函数
 * （见那条注释）。后端加一档而这里没跟上，正向那条会红。
 */

/** 今日待办的优先级。出处：`backend/app/api/dashboard.py` 的 today-tasks，实际发出 high/medium/low。 @typedef {'high' | 'medium' | 'low'} PriorityLevel */
export const PRIORITY_LEVELS = Object.freeze(['high', 'medium', 'low'])

/**
 * Agent 任务状态。出处：`backend/app/api/agent.py` 与 `orchestration/langgraph_flow.py:84`
 * （后者判 `task.status == "cancelled"`，所以 cancelled 是可发的）。
 * @typedef {'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled'} AgentTaskStatus
 */
export const AGENT_TASK_STATUSES = Object.freeze([
  'pending',
  'running',
  'completed',
  'partial',
  'failed',
  'cancelled',
])

/**
 * RAG 置信档位。出处：`backend/app/services/rag_confidence_service.py:54-62`，
 * 按 final_score 分三档，label 是中文、level 是这里的三个值。
 * @typedef {'high' | 'medium' | 'low'} ConfidenceLevel
 */
export const CONFIDENCE_LEVELS = Object.freeze(['high', 'medium', 'low'])

/**
 * 建议/风险的严重度。出处：`backend/app/api/job_recommend.py:110-151`（high/medium/low 三档）。
 * 推荐卡的行动色与评估表的风险色共用这一个域，模板各自拼出自己的前缀。
 * @typedef {'high' | 'medium' | 'low'} SeverityLevel
 */
export const SEVERITY_LEVELS = Object.freeze(['high', 'medium', 'low'])

/**
 * 跟进提醒档位。这一族的出处**不是后端**，是 `features/pipeline/lib/pipelineBoard.js:200-205`：
 * `followUpLevel()` 按 `followUpDays()` 的两个阈值（>=7、>=3）返回这三个字面量，所以域由那个
 * 函数的 return 集合决定——守卫直接解析函数体比对这里的手写列表，两个方向各一条，列表一旦和
 * 代码分叉就红。
 * `.follow-interview` **不在**这个域里：它是 ListPane.vue:120 那枚静态胶囊（`v-if="row.interview_at"`），
 * 由那一站的 siblings 记着；BoardPane 的面试时间走 `.card-interview`，不发这个类名。
 * @typedef {'danger' | 'warn' | 'ok'} FollowUpLevel
 */
export const FOLLOW_UP_LEVELS = Object.freeze(['danger', 'warn', 'ok'])

/**
 * 拼 class 用的那一个函数：它**不做兜底**——值域外的值今天就是没样式，
 * 那是正向守卫要报的错，不该在这里被悄悄抹平（抹平等于把"后端加了一档"这件事变成看不见的视觉缺失）。
 * @param {string} prefix
 * @param {string} value
 * @returns {string}
 */
export function stateClass(prefix, value) {
  return value ? `${prefix}-${value}` : ''
}
