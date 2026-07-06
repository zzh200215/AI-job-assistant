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
    },
  )

  onUnmounted(poller.stopPolling)

  return {
    isPolling,
    pollTask: poller.pollTask,
    stopPolling: poller.stopPolling,
  }
}
