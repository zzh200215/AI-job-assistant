function createPollingError(message, code, taskData = null) {
  const error = new Error(message)
  error.code = code
  error.taskStatus = taskData?.status || null
  error.task = taskData
  return error
}

export function createAgentTaskPoller(apiClient, runtimeOptions = {}) {
  const {
    setTimeoutFn = setTimeout,
    clearTimeoutFn = clearTimeout,
    setPollingState = () => {},
  } = runtimeOptions

  let pollTimer = null

  function stopPolling() {
    if (pollTimer) {
      clearTimeoutFn(pollTimer)
      pollTimer = null
    }
    setPollingState(false)
  }

  async function pollTask(taskId, options = {}) {
    const {
      maxPollCount = 120,
      intervalMs = 2000,
      errorIntervalMs = 3000,
      successStatuses = ['completed', 'partial'],
      failureStatuses = ['failed'],
      cancelledStatuses = ['cancelled'],
      failedMessage,
      cancelledMessage = 'Agent task was cancelled',
      timeoutMessage,
      onProgress,
      onCompleted,
      onFailed,
      onCancelled,
      onTimeout,
    } = options

    stopPolling()
    setPollingState(true)

    return new Promise((resolve, reject) => {
      let count = 0

      const scheduleNext = (delay) => {
        pollTimer = setTimeoutFn(doPoll, delay)
      }

      const rejectWith = async (error, callback, taskData, steps) => {
        stopPolling()
        if (callback) {
          await callback(error, taskData, steps)
        }
        reject(error)
      }

      const resolveWith = async (taskData, steps) => {
        stopPolling()
        const result = onCompleted ? await onCompleted(taskData, steps) : taskData
        resolve(result)
      }

      const doPoll = async () => {
        count += 1

        try {
          const [taskData, stepData] = await Promise.all([
            apiClient.getAgentTask(taskId),
            apiClient.getAgentSteps(taskId),
          ])

          const steps = stepData?.steps || []
          const status = taskData?.status || 'running'

          if (onProgress) {
            await onProgress(taskData, steps)
          }

          if (successStatuses.includes(status)) {
            await resolveWith(taskData, steps)
            return
          }

          if (cancelledStatuses.includes(status)) {
            await rejectWith(
              createPollingError(cancelledMessage, 'task_cancelled', taskData),
              onCancelled || onFailed,
              taskData,
              steps
            )
            return
          }

          if (failureStatuses.includes(status)) {
            await rejectWith(
              createPollingError(
                taskData?.error_msg || failedMessage || 'Agent task failed',
                'task_failed',
                taskData
              ),
              onFailed,
              taskData,
              steps
            )
            return
          }

          if (count >= maxPollCount) {
            await rejectWith(
              createPollingError(
                timeoutMessage || 'Agent task polling timed out',
                'task_timeout',
                taskData
              ),
              onTimeout,
              taskData,
              steps
            )
            return
          }

          scheduleNext(intervalMs)
        } catch (error) {
          if (count >= maxPollCount) {
            await rejectWith(error, onTimeout)
            return
          }
          scheduleNext(errorIntervalMs)
        }
      }

      doPoll()
    })
  }

  return {
    pollTask,
    stopPolling,
  }
}
