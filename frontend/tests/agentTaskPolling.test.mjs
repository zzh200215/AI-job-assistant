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
    },
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
    },
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
