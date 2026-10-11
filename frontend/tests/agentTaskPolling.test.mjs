import test from 'node:test'
import assert from 'node:assert/strict'

import { createAgentTaskPoller } from '../src/utils/agentTaskPolling.js'

test('pollTask resolves after running task reaches completed state', async () => {
  const pollingStates = []
  let taskCallCount = 0
  let progressCallCount = 0

  const poller = createAgentTaskPoller(
    {
      async getAgentTask() {
        taskCallCount += 1
        return taskCallCount === 1
          ? { id: 12, status: 'running' }
          : { id: 12, status: 'completed', analysis_record_id: 88 }
      },
      async getAgentSteps() {
        return {
          steps: [{ step_index: 1, status: taskCallCount === 1 ? 'running' : 'completed' }],
        }
      },
    },
    {
      setPollingState(value) {
        pollingStates.push(value)
      },
    }
  )

  const result = await poller.pollTask(12, {
    intervalMs: 0,
    onProgress() {
      progressCallCount += 1
    },
  })

  assert.equal(result.status, 'completed')
  assert.equal(result.analysis_record_id, 88)
  assert.equal(progressCallCount, 2)
  assert.deepEqual(pollingStates, [false, true, false])
})

test('pollTask rejects immediately when task is cancelled', async () => {
  let cancelledCallbackCount = 0

  const poller = createAgentTaskPoller({
    async getAgentTask() {
      return { id: 9, status: 'cancelled' }
    },
    async getAgentSteps() {
      return { steps: [] }
    },
  })

  await assert.rejects(
    poller.pollTask(9, {
      intervalMs: 0,
      onCancelled(error, taskData) {
        cancelledCallbackCount += 1
        assert.equal(error.code, 'task_cancelled')
        assert.equal(taskData.status, 'cancelled')
      },
    }),
    (error) => {
      assert.equal(error.code, 'task_cancelled')
      assert.equal(error.taskStatus, 'cancelled')
      return true
    }
  )

  assert.equal(cancelledCallbackCount, 1)
})

test('pollTask retries after a transient polling error and still resolves', async () => {
  let taskCallCount = 0

  const poller = createAgentTaskPoller({
    async getAgentTask() {
      taskCallCount += 1
      if (taskCallCount === 1) {
        throw new Error('temporary network error')
      }
      return { id: 5, status: 'partial' }
    },
    async getAgentSteps() {
      return { steps: [] }
    },
  })

  const result = await poller.pollTask(5, {
    intervalMs: 0,
    errorIntervalMs: 0,
    maxPollCount: 3,
  })

  assert.equal(result.status, 'partial')
  assert.equal(taskCallCount, 2)
})

/* D204 新增的 `rejectOnStop`：两个方向都要钉。默认那一半是**既有三个调用方**
   （AgentAnalysis / MultiAgentAnalysis / TaskCenter）现在的行为，改它等于改它们；
   开了的那一半是改写建议那一发要的"卸载即落地"。 */
function neverEndingPoller() {
  return {
    async getAgentTask() {
      return { id: 9, status: 'running' }
    },
    async getAgentSteps() {
      return { steps: [] }
    },
  }
}

/** 给一个 promise 一小段时间，看它落地了没有（落地 = 'settled'，没落地 = 'pending'）。 */
async function settleState(promise, ms = 30) {
  return Promise.race([
    promise.then(
      () => 'resolved',
      () => 'rejected'
    ),
    new Promise((resolve) => setTimeout(() => resolve('pending'), ms)),
  ])
}

test('stopPolling leaves the awaited promise unsettled by default (existing callers unchanged)', async () => {
  const poller = createAgentTaskPoller(neverEndingPoller())
  const pending = poller.pollTask(9, { intervalMs: 60000 })

  await settleState(pending, 5)
  poller.stopPolling()

  assert.equal(await settleState(pending), 'pending', '默认档不该改变停止时的语义')
})

test('rejectOnStop makes stopPolling settle the awaited promise with a code', async () => {
  const poller = createAgentTaskPoller(neverEndingPoller(), { rejectOnStop: true })
  const pending = poller.pollTask(9, { intervalMs: 60000 })

  await settleState(pending, 5)
  poller.stopPolling()

  assert.equal(await settleState(pending), 'rejected')
  await pending.catch((error) => {
    assert.equal(error.code, 'polling_stopped')
  })
})

test('a completed task still resolves: the stop inside the success path must not reject it first', async () => {
  let calls = 0
  const poller = createAgentTaskPoller(
    {
      async getAgentTask() {
        calls += 1
        return { id: 9, status: 'completed' }
      },
      async getAgentSteps() {
        return { steps: [] }
      },
    },
    { rejectOnStop: true }
  )

  const result = await poller.pollTask(9, { intervalMs: 0 })

  assert.equal(result.status, 'completed')
  assert.equal(calls, 1)
})
