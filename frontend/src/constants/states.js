/**
 * "拼出来的类名"的值域：`dot-high`、`severity-medium`、`confidence-low`、`action-high` 这一族
 * 由模板把后端的一个字段直接拼进 class（`'dot-' + task.priority`、`` `severity-${item.severity}` ``），
 * 所以**样式表里该有哪几条规则，取决于后端能发哪些值**——这件事以前只存在于样式文件的运气里。
 *
 * D76/D77 用静态尺子与浏览器快照都判不了它们：静态看不见后端的值域，而单屏快照只证明
 * "这一屏没渲染到"，不证明"没有值能渲染到"。所以域写在这里，两个方向各有一条守卫：
 *   正向 —— 域里每个值在该有规则的视图里都必须有一条 `.prefix-value`；
 *   反向 —— 视图里每条 `.prefix-*` 规则的值都必须还在域里（多出来的就是死样式）。
 * 每个域都标了它的出处：`PRIORITY_LEVELS` / `AGENT_TASK_STATUSES` / `CONFIDENCE_LEVELS` /
 * `SEVERITY_LEVELS` 是后端字段，`FOLLOW_UP_LEVELS` / `STAGE_ACCENTS` / `FUNNEL_ACCENTS` /
 * `WEIGHT_DOT_COLORS` 是**前端自己的代码**（纯函数或本地常量）——后这四个由守卫逐字解析产出它们的
 * 那段代码，抄本与代码分叉就红。后端加一档而这里没跟上，正向那条会红。
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
 * 看板列的强调色。出处：`features/pipeline/lib/pipelineBoard.js:66-73` 每条列定义的那个 `accent`
 * 字段（`pipelineBoard.js:11` 原话："取值集合就是样式里的 `.dot-*`，不在这里发明新值"）。
 * 这一族与 `PRIORITY_LEVELS` / `AGENT_TASK_STATUSES` **共用 `dot-` 这个前缀但语义无关**：
 * Home 拼的是任务优先级、TaskCenter 拼的是任务状态、看板列头与卡片拼的是 accent，
 * 所以守卫按 (前缀, 文件) 一站一站记，不按前缀全局记。
 * `green` 在列里出现两次（offer 与 accepted），集合里去重。
 * @typedef {'slate' | 'blue' | 'amber' | 'violet' | 'green' | 'red' | 'gray'} StageAccent
 */
export const STAGE_ACCENTS = Object.freeze([
  'slate',
  'blue',
  'amber',
  'violet',
  'green',
  'red',
  'gray',
])

/**
 * 漏斗那几条填充真的会发出来的强调色。出处：`pipelineBoard.js:113-120` 的 `funnelRows()`
 * 先把列筛成 todo / applied / written_test / interview / offer 五段，所以 `rejected`（red）与
 * `withdrawn`（gray）**进不了漏斗**。这条域必须是 `STAGE_ACCENTS` 的子集——守卫两条都钉：
 * 筛出的五段映出来的 accent 集合 == 这里，而 `.fill-*` 规则集合也 == 这里（D151 当场照出
 * `.fill-red` 是没人能发出的死规则，已删）。
 * @typedef {'slate' | 'blue' | 'amber' | 'violet' | 'green'} FunnelAccent
 */
export const FUNNEL_ACCENTS = Object.freeze(['slate', 'blue', 'amber', 'violet', 'green'])

/**
 * Offer 权衡表里那颗点色。出处：`features/jobs/views/OfferCompare.vue:459-464` 六条权重各自的
 * `color` 字段（模板 `:class="'dot-' + w.color"`，`OfferCompare.vue:124`）。同样是 `dot-` 前缀的
 * 第四个域，与上面三个互不相干。
 * @typedef {'blue' | 'violet' | 'green' | 'amber' | 'red' | 'teal'} WeightDotColor
 */
export const WEIGHT_DOT_COLORS = Object.freeze(['blue', 'violet', 'green', 'amber', 'red', 'teal'])

/**
 * 应用外壳（侧栏 + 顶栏）自己那两颗状态点的颜色。出处是**模板里的两处字面量**：
 * `DefaultLayout.vue:76` 的演示模式灯 `runtime.demoMode ? 'dot-amber' : 'dot-green'`，
 * 和 `:97` 的通知徽标 `class="badge-dot dot-blue"`。这是 `dot-` 前缀的**第五个**域（D160 普查撞出来的：
 * 这条站点在 (前缀, 文件) 的登记表里一直缺席）。
 * 这一族与前面四个有一件本质不同：它的宿主是**不跟主题走的硬深色面**——`.aside-chip` 与 `.badge` /
 * `.user-chip` 的底都是写在布局里的字面量（`DefaultLayout.vue:513`、`:611`、`:638`），不是 `--app-*` 令牌，
 * 所以摘掉 `.workspace-theme` 之后这两枚点的相邻面对比一字不变（2026-10-08 逐座实测：外壳灯 5.58、
 * 徽标点 7.18，深色与浅色两遍每个数都相同）。它是 `main.css:3` 那句 "dark command surfaces + light
 * reading flows" 里"深色指令面"那一半，不是漏网的浅色面。
 * @typedef {'amber' | 'green' | 'blue'} LayoutChipColor
 */
export const LAYOUT_CHIP_COLORS = Object.freeze(['amber', 'green', 'blue'])

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
