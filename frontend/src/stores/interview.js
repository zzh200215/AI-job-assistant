import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  connectInterviewWS,
  createInterview,
  disconnectInterviewWS,
  endInterview,
  sendAnswer,
  skipQuestion,
} from '@/api/interview'

const ROUND_SECONDS = 30

export const useInterviewStore = defineStore('interview', () => {
  const session = ref(null)
  const messages = ref([])
  const currentRound = ref(0)
  const totalQuestions = ref(0)
  const status = ref('idle')
  const evaluation = ref(null)
  const errorMsg = ref('')
  const lastScore = ref(null)
  const timeElapsed = ref(0)
  const isFollowUp = ref(false)
  const roundRemaining = ref(ROUND_SECONDS)

  let sessionTimer = null
  let roundTimer = null

  const currentQuestion = computed(() => {
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      if (messages.value[i].type === 'question') {
        return messages.value[i]
      }
    }
    return null
  })

  const isCompleted = computed(() => status.value === 'completed')

  const progress = computed(() => {
    if (!totalQuestions.value) return 0
    return Math.round((currentRound.value / totalQuestions.value) * 100)
  })

  const formattedTime = computed(() => {
    const mins = Math.floor(timeElapsed.value / 60)
    const secs = timeElapsed.value % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  })

  const formattedRoundRemaining = computed(() => {
    const secs = Math.max(roundRemaining.value, 0)
    return `00:${String(secs).padStart(2, '0')}`
  })

  const roundProgress = computed(() => {
    return Math.max(0, Math.min(100, Math.round((roundRemaining.value / ROUND_SECONDS) * 100)))
  })

  function getLatestQuestionRound(items = []) {
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const item = items[i]
      if (item?.type !== 'question') continue
      const round = Number(item?.metadata?.round)
      if (Number.isFinite(round) && round > 0 && !item?.metadata?.is_follow_up) {
        return round
      }
    }
    return 0
  }

  function reset() {
    session.value = null
    messages.value = []
    currentRound.value = 0
    totalQuestions.value = 0
    status.value = 'idle'
    evaluation.value = null
    errorMsg.value = ''
    lastScore.value = null
    timeElapsed.value = 0
    isFollowUp.value = false
    roundRemaining.value = ROUND_SECONDS
    stopSessionTimer()
    stopRoundTimer()
  }

  async function initSession(resumeId, jdId, interviewType) {
    try {
      const data = await createInterview({
        resume_id: resumeId,
        jd_id: jdId,
        interview_type: interviewType,
      })
      session.value = data
      totalQuestions.value = data.total_questions || 0
      return data
    } catch (error) {
      errorMsg.value = `创建面试失败: ${error.message || error}`
      status.value = 'error'
      throw error
    }
  }

  function hydrateSession(detail) {
    session.value = detail
    totalQuestions.value = detail?.total_questions || totalQuestions.value
    if (Array.isArray(detail?.messages)) {
      messages.value = detail.messages
    }
    if (detail?.status === 'completed') {
      status.value = 'completed'
    } else if (status.value === 'idle') {
      status.value = detail?.status || status.value
    }
    evaluation.value = detail?.evaluation || null
    currentRound.value = Math.max(detail?.answered_count || 0, getLatestQuestionRound(detail?.messages || []))
    lastScore.value = [...(detail?.messages || [])].reverse().find(msg => msg?.type === 'evaluation')?.metadata || null
    isFollowUp.value = !!currentQuestion.value?.metadata?.is_follow_up
  }

  function startWS(sessionId) {
    const isSameSession = Number(session.value?.id) === Number(sessionId)
    disconnectInterviewWS()
    stopRoundTimer()
    stopSessionTimer()
    if (!isSameSession) {
      session.value = null
      messages.value = []
      currentRound.value = 0
      totalQuestions.value = 0
      evaluation.value = null
      lastScore.value = null
      timeElapsed.value = 0
      isFollowUp.value = false
      roundRemaining.value = ROUND_SECONDS
    }
    status.value = 'connecting'
    errorMsg.value = ''

    connectInterviewWS(
      sessionId,
      (data) => handleWSMessage(data),
      (err) => {
        errorMsg.value = `连接错误: ${err.message || err}`
        status.value = 'error'
        stopRoundTimer()
      },
      (event) => {
        if (event.code === 1000 || event.code === 4000) {
          status.value = 'completed'
          stopRoundTimer()
        } else if (status.value !== 'completed' && status.value !== 'error') {
          const reasons = {
            4001: '认证失败，请重新登录',
            4003: '无权访问此面试',
            4004: '面试会话不存在',
          }
          errorMsg.value = reasons[event.code] || `连接已断开 (code: ${event.code})`
          status.value = 'error'
          stopRoundTimer()
        }
      },
    )
  }

  function handleWSMessage(data) {
    const type = data.type
    const content = data.content || ''
    const meta = data.metadata || {}

    if (type === 'question') {
      messages.value.push({
        role: 'ai',
        type: 'question',
        content,
        metadata: meta,
        timestamp: new Date().toISOString(),
      })
      currentRound.value = meta.round || currentRound.value + 1
      totalQuestions.value = meta.total || totalQuestions.value
      isFollowUp.value = !!meta.is_follow_up
      status.value = 'ongoing'
      startSessionTimer()
      resetRoundTimer()
      return
    }

    if (type === 'evaluation') {
      messages.value.push({
        role: 'system',
        type: 'evaluation',
        content,
        metadata: meta,
        timestamp: new Date().toISOString(),
      })
      lastScore.value = {
        score: meta.score,
        completeness: meta.completeness,
        accuracy: meta.accuracy,
        depth: meta.depth,
        expression: meta.expression,
        improvement: meta.improvement,
      }
      status.value = 'evaluating'
      stopRoundTimer()
      return
    }

    if (type === 'system') {
      messages.value.push({
        role: 'system',
        type: 'system',
        content,
        metadata: meta,
        timestamp: new Date().toISOString(),
      })
      stopRoundTimer()
      return
    }

    if (type === 'end') {
      messages.value.push({
        role: 'system',
        type: 'end',
        content,
        metadata: meta,
        timestamp: new Date().toISOString(),
      })
      evaluation.value = meta
      status.value = 'completed'
      stopRoundTimer()
      stopSessionTimer()
      return
    }

    if (type === 'error') {
      errorMsg.value = content
      status.value = 'error'
      stopRoundTimer()
    }
  }

  function submitAnswer(content) {
    const text = content?.trim()
    if (!text) return
    messages.value.push({
      role: 'user',
      type: 'answer',
      content: text,
      timestamp: new Date().toISOString(),
    })
    sendAnswer(text)
    status.value = 'evaluating'
    stopRoundTimer()
  }

  function skipCurrent() {
    messages.value.push({
      role: 'system',
      type: 'system',
      content: '已请求跳过当前问题，正在进入下一题。',
      timestamp: new Date().toISOString(),
    })
    skipQuestion()
    stopRoundTimer()
  }

  function end() {
    endInterview()
    status.value = 'evaluating'
    stopRoundTimer()
    stopSessionTimer()
  }

  function disconnect() {
    disconnectInterviewWS()
    stopRoundTimer()
    stopSessionTimer()
  }

  function startSessionTimer() {
    if (sessionTimer) return
    sessionTimer = setInterval(() => {
      timeElapsed.value += 1
    }, 1000)
  }

  function stopSessionTimer() {
    if (sessionTimer) {
      clearInterval(sessionTimer)
      sessionTimer = null
    }
  }

  function resetRoundTimer() {
    stopRoundTimer()
    roundRemaining.value = ROUND_SECONDS
    roundTimer = setInterval(() => {
      if (roundRemaining.value > 0) {
        roundRemaining.value -= 1
      } else {
        stopRoundTimer()
      }
    }, 1000)
  }

  function stopRoundTimer() {
    if (roundTimer) {
      clearInterval(roundTimer)
      roundTimer = null
    }
  }

  return {
    session,
    messages,
    currentRound,
    totalQuestions,
    status,
    evaluation,
    errorMsg,
    lastScore,
    timeElapsed,
    isFollowUp,
    roundRemaining,
    currentQuestion,
    isCompleted,
    progress,
    formattedTime,
    formattedRoundRemaining,
    roundProgress,
    reset,
    initSession,
    hydrateSession,
    startWS,
    submitAnswer,
    skipCurrent,
    end,
    disconnect,
  }
})
