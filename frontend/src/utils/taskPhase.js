/**
 * 任务的第三个状态：**已提交，但一步都还没跑**。
 *
 * 为什么要它：`/analysis/full` 从 2026-11-14 起只在**有 worker 消费队列**时才收单
 * （没有就 503，见 `docs/真provider实测.md` §6）。所以"拿到 task_id 之后"其实有两种等待：
 *
 *   · **排队中**：任务已经落库，worker 还没开始跑第一步 —— 步骤数是 0，屏幕上是 0%；
 *   · **执行中**：第一步已经写下 `agent_step_log`，进度有东西可看。
 *
 * 以前这两种在屏幕上长得一模一样（都是一个不动的 0%），看起来像卡死。分开之后，
 * 排队那一屏说的是"已提交，等后台接单"，而不是让人盯着一个不动的进度条。
 *
 * 判据只看任务载荷，**不看时间**：等得久可能是 worker 正忙着跑前面的任务，而前端并不知道
 * 队列长度；按时间判会把"排队"说成"开始"或者反过来。
 */

/** 三个阶段：终态（completed/failed/…）一律算 IDLE —— 那由调用方的成功/失败分支处理。 */
export const TASK_PHASE = {
  IDLE: 'idle',
  QUEUED: 'queued',
  RUNNING: 'running',
}

/**
 * 从 `GET /agent/task/{id}` 的载荷判断阶段。
 *
 * 形状不明时返回 `IDLE`（不下判断），而不是乐观地报"排队中"：
 * 报告作业等其它异步任务也复用同一个轮询器，它们的载荷没有 `progress.step_counts`。
 */
export function taskPhase(taskData) {
  const status = String(taskData?.status || '')
    .trim()
    .toLowerCase()
  if (status === 'pending') return TASK_PHASE.QUEUED
  if (status !== 'running') return TASK_PHASE.IDLE

  const progress = taskData?.progress
  if (!progress || typeof progress !== 'object') return TASK_PHASE.IDLE

  const total = Number(progress?.step_counts?.total || 0)
  if (total > 0 || progress.current_step) return TASK_PHASE.RUNNING
  return TASK_PHASE.QUEUED
}

/**
 * 排队那一屏的两句话。**两处都必须是真话**：
 *
 * - "几秒内进入进度"：worker 空闲时就是毫秒级写下第一条 `agent_step_log`（2026-11-14 实测
 *   起 worker 后 22 秒出现第 1 条步骤，而那 22 秒它排在另一个任务后面）；
 * - "约两分钟内失败"：只在**没有活着的 worker** 时成立（`ORCHESTRATION_START_TIMEOUT_MINUTES=2`
 *   的收口）。worker 忙着的排队不会失败，所以措辞挂在"如果后台没有可用的 worker"这个前提上。
 */
export const QUEUED_COPY = {
  title: '排队中：后台还没开始跑第一步',
  description:
    '分析已提交。正常情况下几秒内就会进入进度；如果后台没有可用的 worker，它会在约两分钟内变成一条写明原因的失败，而不是一直转圈。',
}

/**
 * "没开始就失败"这一档，屏幕该说的话。
 *
 * **为什么不用后端 `error_msg`**：那句话可能是我们写的（"排队 2 分钟…按未启动收口"），
 * 也可能是 `str(exc)[:500]` —— 共享轮询器把 `error_msg` 挂在 `error.message` 上，而全仓
 * 的错误出口只认 `userMessage`，正是为了不让服务端/模型原文流到候选人脸上（三条作业轮询
 * 用例钉着这条）。所以这一档由前端自己说，判据是**可观察的状态**：失败了，而且一条步骤都没跑。
 */
export const NEVER_STARTED_FAILURE =
  '任务还没开始执行就被收口了：后台没有可用的 worker。请稍后重试；如果一直这样，请联系管理员启动编排 worker。'

/**
 * 任务是否"没跑第一步就失败了"。
 *
 * 只在载荷带 `progress` 时下判断：作业类任务没有这个形状，硬猜会让它们的失败也换成这句话。
 */
export function failedBeforeFirstStep(taskData) {
  if (
    String(taskData?.status || '')
      .trim()
      .toLowerCase() !== 'failed'
  ) {
    return false
  }
  const progress = taskData?.progress
  if (!progress || typeof progress !== 'object') return false
  return Number(progress?.step_counts?.total || 0) === 0
}
