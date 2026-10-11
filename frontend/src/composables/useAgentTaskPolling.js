import { onUnmounted, ref } from 'vue'
import { getAgentSteps, getAgentTask } from '../api/agent'
import { createAgentTaskPoller } from '../utils/agentTaskPolling'

export function useAgentTaskPolling() {
  const isPolling = ref(false)
  const poller = createAgentTaskPoller(
    { getAgentTask, getAgentSteps },
    {
      setPollingState(value) {
        isPolling.value = value
      },
      /* D207：这一条把 `stopPolling` 绑在卸载上，所以"卸载"就是要让那个 await 落地——
         不绑的话调用方的 `finally { loading = false }` 永不执行（D204 量到的悬挂 await）。
         落地形式是 reject(`polling_stopped`)：两个视图的外层 catch 本来就静默，运行链那一处
         显式认这个 code 并把它和"真失败"分开，免得给一个没看完任务的人弹一句错。 */
      rejectOnStop: true,
    }
  )

  onUnmounted(poller.stopPolling)

  return {
    isPolling,
    pollTask: poller.pollTask,
    stopPolling: poller.stopPolling,
  }
}
