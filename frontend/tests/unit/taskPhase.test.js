/**
 * `taskPhase` 的判据：**什么时候该说"排队中"**。
 *
 * 这一条独立成纯函数，是因为三处消费者（SmartAnalysis / AnalysisResult / 职业规划运行链）
 * 都要用同一句话，而它的边界很容易写错两个方向：
 *   · 太乐观：把"还没开始"说成"执行中"，屏幕上就是个不动的 0%；
 *   · 太悲观：把报告作业那种没有 `progress.step_counts` 的载荷也说成"排队中"。
 */

import { describe, expect, it } from 'vitest'

import { QUEUED_COPY, TASK_PHASE, taskPhase } from '@/utils/taskPhase'

describe('taskPhase', () => {
  it('running 且零步骤 = 排队中（后端建了任务行、worker 还没写第一条 step_log）', () => {
    expect(
      taskPhase({ status: 'running', progress: { step_counts: { total: 0 }, current_step: null } })
    ).toBe(TASK_PHASE.QUEUED)
  })

  it('running 且已有步骤 = 执行中', () => {
    expect(taskPhase({ status: 'running', progress: { step_counts: { total: 1 } } })).toBe(
      TASK_PHASE.RUNNING
    )
    /* 只给了 current_step 也算开始：分层策略先建 running 步骤再并发，两种形状都可能出现。 */
    expect(
      taskPhase({
        status: 'running',
        progress: { step_counts: { total: 0 }, current_step: { name: 'intent_recognition' } },
      })
    ).toBe(TASK_PHASE.RUNNING)
  })

  it('pending 也是排队中：行建了但还没置 running', () => {
    expect(taskPhase({ status: 'pending' })).toBe(TASK_PHASE.QUEUED)
  })

  it('终态一律 IDLE：成功/失败由调用方的分支处理，不该继续报"排队"', () => {
    for (const status of ['completed', 'partial', 'failed', 'cancelled']) {
      expect(taskPhase({ status, progress: { step_counts: { total: 0 } } })).toBe(TASK_PHASE.IDLE)
    }
  })

  it('形状不明就 IDLE，不要乐观地报排队', () => {
    /* 报告作业等其它异步任务复用同一个轮询器，它们没有 `progress.step_counts`：
       硬判成 QUEUED 会让那些页面挂一句"等后台接单"，而它们其实正在跑。 */
    expect(taskPhase({ status: 'running' })).toBe(TASK_PHASE.IDLE)
    expect(taskPhase({ status: 'running', progress: null })).toBe(TASK_PHASE.IDLE)
    expect(taskPhase({ status: 'running', progress: 'weird' })).toBe(TASK_PHASE.IDLE)
    expect(taskPhase(null)).toBe(TASK_PHASE.IDLE)
    expect(taskPhase({})).toBe(TASK_PHASE.IDLE)
  })

  it('状态大小写/空白不影响判定（后端与夹具写过的两种写法都认）', () => {
    expect(taskPhase({ status: ' RUNNING ', progress: { step_counts: { total: 0 } } })).toBe(
      TASK_PHASE.QUEUED
    )
    expect(taskPhase({ status: 'running', progress: { step_counts: { total: 2 } } })).toBe(
      TASK_PHASE.RUNNING
    )
  })

  it('排队那句话两件事都必须写着：会进入进度，以及没有 worker 时会明确失败', () => {
    /* 这两句对应后端的两条真实行为：拿到 task_id 后第一条 step_log 是毫秒级写的；
       `ORCHESTRATION_START_TIMEOUT_MINUTES=2` 的收口只在没有活着的 worker 时生效。
       少写后半句，用户就不知道"等下去会不会永远转圈"。 */
    expect(QUEUED_COPY.title).toContain('排队中')
    expect(QUEUED_COPY.description).toContain('几秒')
    expect(QUEUED_COPY.description).toContain('两分钟')
    expect(QUEUED_COPY.description).toContain('失败')
  })
})
