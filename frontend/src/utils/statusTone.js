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
