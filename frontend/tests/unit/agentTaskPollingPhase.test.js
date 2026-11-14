/**
 * 轮询器把"排队/执行"这一判断递出去（`utils/taskPhase.js`）。
 *
 * 这里直接驱动 `createAgentTaskPoller`，因为第三个参数是**这条链的契约**：
 * 三个页面（SmartAnalysis / AnalysisResult / 职业规划运行链）都靠它决定"零步骤时说不说排队"。
 * 少递一个参数不会报错，只会让那三屏一起退回"不动的 0%"，所以要在源头钉住。
 */

import { describe, expect, it } from 'vitest'

import { createAgentTaskPoller } from '@/utils/agentTaskPolling'
import { TASK_PHASE } from '@/utils/taskPhase'

/** 每一跳返回一个固定载荷，直到队列里的载荷用完（最后一个一直重复）。 */
function makeClient(payloads) {
  let index = 0
  return {
    async getAgentTask() {
      const payload = payloads[Math.min(index, payloads.length - 1)]
      index += 1
      return payload
    },
    async getAgentSteps() {
      return { steps: [] }
    },
  }
}

async function drain(prompt, { maxPolls = 3 } = {}) {
  const phases = []
  const outcomes = []
  const pending = prompt.pollTask(1, {
    intervalMs: 0,
    maxPollCount: maxPolls,
    onProgress(taskData, steps, phase) {
      phases.push(phase)
    },
    onCompleted(taskData) {
      outcomes.push(`completed:${taskData.status}`)
      return taskData
    },
    onFailed() {
      outcomes.push('failed')
    },
    onTimeout() {
      outcomes.push('timeout')
    },
  })
  await pending.catch(() => {})
  return { phases, outcomes }
}

describe('轮询器把任务阶段递给 onProgress', () => {
  it('零步骤的 running 递 queued；有步骤之后递 running', async () => {
    const poller = createAgentTaskPoller(
      makeClient([{ status: 'running', progress: { step_counts: { total: 0 } } }])
    )
    const { phases, outcomes } = await drain(poller, { maxPolls: 2 })

    expect(phases).toEqual([TASK_PHASE.QUEUED, TASK_PHASE.QUEUED])
    /* 两跳都没结束 → 到 maxPollCount 收口成 timeout（这也是"排队很久"在旧行为里的出口）。 */
    expect(outcomes).toEqual(['timeout'])
  })

  it('每一步都能看到当时的阶段，顺序不改写', async () => {
    const queued = {
      status: 'running',
      progress: { step_counts: { total: 0 }, current_step: null },
    }
    const running = { status: 'running', progress: { step_counts: { total: 1 } } }
    const done = { status: 'completed', progress: { step_counts: { total: 3 } } }
    const poller = createAgentTaskPoller(makeClient([queued, running, done]))

    const { phases, outcomes } = await drain(poller, { maxPolls: 5 })

    /* 终态那一跳算 IDLE：完成/失败由 onCompleted 那一支处理，不该继续报阶段。 */
    expect(phases).toEqual([TASK_PHASE.QUEUED, TASK_PHASE.RUNNING, TASK_PHASE.IDLE])
    expect(outcomes).toEqual(['completed:completed'])
  })
})
