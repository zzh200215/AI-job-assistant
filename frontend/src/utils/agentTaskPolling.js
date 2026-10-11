/**
 * 这条链自己挂在 Error 上的三个字段；`code` 是 'task_cancelled' / 'task_failed' 这类
 * 调用方拿来分流的字符串，与 ApiError 那四个字段是两套约定。
 * @typedef {Error & { code?: string, taskStatus?: string | null, task?: any }} PollingError
 */

function createPollingError(message, code, taskData = null) {
  /** @type {PollingError} */
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
    /**
     * D204 量到的那件小事的开关：`stopPolling()` 原来只是清表，**不落地**那个 `await`，
     * 所以调用方（组件卸载时）等下去的 promise 永不 settle，它后面的 `finally` 也就永不跑。
     * 默认 `false`（纯工具层不假设调用方要这个语义）；`useAgentTaskPolling` 在 D207 把它打开，
     * 因为那条链正是把 `stopPolling` 挂在 `onUnmounted` 上的，而 `ResumeUpload.vue` 的改写建议
     * 轮询自己开了一份（D205）。
     */
    rejectOnStop = false,
  } = runtimeOptions

  let pollTimer = null
  let settleReject = null
  let settled = true

  function stopPolling() {
    if (pollTimer) {
      clearTimeoutFn(pollTimer)
      pollTimer = null
    }
    setPollingState(false)
    // 只在"没人已经落地过"且调用方要这个语义时才 reject；否则与改动前完全一致。
    if (rejectOnStop && settleReject && !settled) {
      settled = true
      const reject = settleReject
      settleReject = null
      reject(createPollingError('轮询已停止', 'polling_stopped'))
    }
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
      cancelledMessage = '任务已取消',
      timeoutMessage,
      onProgress,
      onCompleted,
      onFailed,
      onCancelled,
      onTimeout,
    } = options

    /* 开新一趟之前先"接管"上一趟：这一发 stop 只负责清表，不能把上一趟判成 `polling_stopped`。
       上一趟一旦落地就会跑自己的 `finally`，而它写的 `loading` 是与这一趟共用的同一批 refs——
       按钮会在第二趟还在飞的时候被松开。D207 只把"卸载"那一跳打开拒绝。 */
    settled = true
    settleReject = null
    stopPolling()
    setPollingState(true)

    return new Promise((resolve, reject) => {
      settled = false
      settleReject = reject
      let count = 0

      const scheduleNext = (delay) => {
        pollTimer = setTimeoutFn(doPoll, delay)
      }

      const rejectWith = async (error, callback, taskData, steps) => {
        // 先立"已落地"再停表：否则 `rejectOnStop` 会在真正的失败原因之前先把 promise 改成
        // `polling_stopped`，把这次跑失败的真实理由抹掉。
        settled = true
        stopPolling()
        if (callback) {
          await callback(error, taskData, steps)
        }
        reject(error)
      }

      const resolveWith = async (taskData, steps) => {
        // 同一条理由：这一下如果排在 stopPolling 之后，成功的那一发会被自己的停表逻辑改判成拒绝。
        settled = true
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
