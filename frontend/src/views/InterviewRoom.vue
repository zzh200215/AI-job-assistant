<template>
  <div class="page-shell">
    <section class="room-hero">
      <div>
        <p class="eyebrow">Interview Workspace</p>
        <h1>{{ sessionTitle }}</h1>
        <p>{{ sessionSubtitle }}</p>
      </div>
      <div class="hero-actions">
        <el-button text @click="goBack" :disabled="wsConnecting">返回</el-button>
        <el-tag :type="statusTagType" effect="dark">{{ statusLabel }}</el-tag>
      </div>
    </section>

    <section class="room-grid">
      <div class="main-column">
        <div class="panel stage-card">
          <div class="panel-body">
            <div class="stage-header">
              <div>
                <span class="stage-kicker">当前阶段</span>
                <h2>{{ currentPhase.title }}</h2>
                <p>{{ currentPhase.desc }}</p>
              </div>
              <div class="stage-meta">
                <div class="meta-pill">
                  <span>进度</span>
                  <strong>{{ store.currentRound || 0 }} / {{ store.totalQuestions || 0 }}</strong>
                </div>
                <div class="meta-pill" :class="{ danger: store.roundRemaining <= 10 }">
                  <span>单题倒计时</span>
                  <strong>{{ store.formattedRoundRemaining }}</strong>
                </div>
                <div class="meta-pill">
                  <span>总用时</span>
                  <strong>{{ store.formattedTime }}</strong>
                </div>
              </div>
            </div>
            <el-progress
              :percentage="store.progress"
              :show-text="false"
              :stroke-width="10"
              class="stage-progress"
            />
          </div>
        </div>

        <div class="panel question-card">
          <div class="panel-body">
            <div class="interviewer-header">
              <div class="interviewer-avatar">AI</div>
              <div>
                <div class="interviewer-name">{{ interviewerPersona }}</div>
                <div class="interviewer-role">{{ interviewerHint }}</div>
              </div>
            </div>

            <div class="question-meta">
              <span class="question-badge">{{ questionCategory }}</span>
              <span v-if="store.isFollowUp" class="question-badge follow-up">追问</span>
            </div>

            <h3>{{ spotlightQuestion }}</h3>
            <p class="question-helper">{{ questionHelperText }}</p>

            <div class="structure-box">
              <div class="structure-title">建议回答结构</div>
              <div class="structure-tips">
                <span v-for="tip in answerStructure" :key="tip">{{ tip }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel transcript-card">
          <div class="panel-header">
            <div class="transcript-header">
              <span>面试实录</span>
              <span class="transcript-sub">实时显示提问、作答、评分与超时反馈</span>
            </div>
          </div>
          <div class="panel-body">
            <div ref="chatRef" class="transcript-list">
              <div
                v-for="(msg, idx) in store.messages"
                :key="`${idx}-${msg.type}`"
                class="msg-row"
                :class="rowClass(msg)"
              >
                <template v-if="msg.type === 'question'">
                  <div class="msg-shell ai-shell">
                    <div class="msg-head">
                      <span>面试官</span>
                      <span>{{ msg.metadata?.category || '通用问题' }}</span>
                    </div>
                    <div class="msg-body">{{ msg.content }}</div>
                  </div>
                </template>

                <template v-else-if="msg.type === 'answer'">
                  <div class="msg-shell user-shell">
                    <div class="msg-head">
                      <span>我的回答</span>
                    </div>
                    <div class="msg-body">{{ msg.content }}</div>
                  </div>
                </template>

                <template v-else-if="msg.type === 'evaluation'">
                  <div class="score-shell" :class="scoreClass(msg.metadata?.score)">
                    <div class="score-top">
                      <strong>本题评分 {{ msg.metadata?.score || 0 }}</strong>
                      <span>{{ performanceSummary(msg.metadata?.score) }}</span>
                    </div>
                    <div class="score-dims">
                      <span>完整 {{ msg.metadata?.completeness ?? '-' }}</span>
                      <span>准确 {{ msg.metadata?.accuracy ?? '-' }}</span>
                      <span>深度 {{ msg.metadata?.depth ?? '-' }}</span>
                      <span>表达 {{ msg.metadata?.expression ?? '-' }}</span>
                    </div>
                    <p>{{ msg.content }}</p>
                    <p v-if="msg.metadata?.improvement" class="score-improvement">
                      改进建议：{{ msg.metadata.improvement }}
                    </p>
                  </div>
                </template>

                <template v-else-if="msg.type === 'system'">
                  <div class="system-shell">{{ msg.content }}</div>
                </template>

                <template v-else-if="msg.type === 'end'">
                  <div class="end-shell">
                    <strong>面试已结束</strong>
                    <span>{{ msg.content }}</span>
                  </div>
                </template>
              </div>
            </div>

            <div v-if="store.status === 'connecting'" class="state-hint">正在接入面试房间...</div>
            <div v-else-if="store.status === 'evaluating'" class="state-hint">
              面试官正在记录你的回答并决定下一问...
            </div>
          </div>
        </div>

        <div v-if="!store.isCompleted" class="panel answer-card">
          <div class="panel-body">
            <div class="answer-head">
              <div>
                <strong>你的回答</strong>
                <p>建议先给结论，再补充过程、取舍和结果。</p>
              </div>
              <div class="answer-shortcut">`Ctrl + Enter` 发送</div>
            </div>
            <el-input
              ref="inputRef"
              v-model="userInput"
              type="textarea"
              :rows="4"
              resize="none"
              :disabled="store.status !== 'ongoing' || wsConnecting"
              :placeholder="inputPlaceholder"
              @keydown.ctrl.enter="handleSend"
            />
            <div class="voice-toolbar">
              <button
                type="button"
                class="voice-trigger"
                :class="{
                  active: isListening,
                  unsupported: !speechSupported,
                  disabled: !canToggleSpeech,
                }"
                :disabled="!canToggleSpeech"
                @click="toggleSpeechRecognition"
              >
                <span class="voice-trigger-core">
                  <span class="voice-trigger-icon">
                    <el-icon><Microphone /></el-icon>
                  </span>
                  <span class="voice-trigger-copy">
                    <strong>{{ isListening ? '正在听写' : '点击开始语音输入' }}</strong>
                    <span>{{ isListening ? '再次点击可停止录音' : '回答会自动写入输入框' }}</span>
                  </span>
                </span>
                <span class="voice-trigger-signal" :class="{ live: isListening }"></span>
              </button>
              <div class="voice-actions">
                <p
                  class="voice-status"
                  :class="{ active: isListening, unsupported: !speechSupported }"
                >
                  {{ speechStatusText }}
                </p>
                <el-button text :disabled="!userInput.trim()" @click="clearAnswerDraft">
                  清空回答
                </el-button>
              </div>
            </div>
            <p v-if="speechPreview" class="speech-preview">实时听写：{{ speechPreview }}</p>
            <div class="answer-actions">
              <el-button @click="handleSkip" :disabled="store.status !== 'ongoing'"
                >跳过本题</el-button
              >
              <el-button type="danger" plain @click="handleEnd">结束面试</el-button>
              <el-button type="primary" :disabled="!canSend" @click="handleSend"
                >提交回答</el-button
              >
            </div>
          </div>
        </div>

        <div v-else class="completed-actions">
          <el-button type="primary" size="large" @click="viewReport">查看面试报告</el-button>
          <el-button size="large" @click="restartInterview">重新开始</el-button>
        </div>
      </div>

      <aside class="side-column">
        <div class="panel side-panel">
          <div class="panel-header">
            <div class="side-title">岗位聚焦</div>
          </div>
          <div class="panel-body">
            <div class="side-block">
              <strong>{{ store.session?.jd_summary?.title || '目标岗位' }}</strong>
              <p>{{ store.session?.jd_summary?.company || '未填写公司' }}</p>
              <div class="skill-grid">
                <span
                  v-for="skill in (store.session?.jd_summary?.required_skills || []).slice(0, 6)"
                  :key="skill"
                >
                  {{ skill }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel side-panel">
          <div class="panel-header">
            <div class="side-title">表现速览</div>
          </div>
          <div class="panel-body">
            <div class="snapshot-grid">
              <div class="snapshot-item">
                <span>已评分题数</span>
                <strong>{{ answeredCount }}</strong>
              </div>
              <div class="snapshot-item">
                <span>超时次数</span>
                <strong>{{ timeoutCount }}</strong>
              </div>
              <div class="snapshot-item">
                <span>最近得分</span>
                <strong>{{ store.lastScore?.score ?? '--' }}</strong>
              </div>
              <div class="snapshot-item">
                <span>当前判断</span>
                <strong>{{ recentSignal }}</strong>
              </div>
            </div>
            <p v-if="store.lastScore?.improvement" class="snapshot-note">
              最近一题建议：{{ store.lastScore.improvement }}
            </p>
          </div>
        </div>

        <div class="panel side-panel">
          <div class="panel-header">
            <div class="side-title">本题提醒</div>
          </div>
          <div class="panel-body">
            <ul class="hint-list">
              <li v-for="tip in answerStructure" :key="tip">{{ tip }}</li>
            </ul>
          </div>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { Microphone } from '@element-plus/icons-vue'
import { getInterviewDetail } from '@/api/interview'
import { useInterviewStore } from '@/stores/interview'

const route = useRoute()
const router = useRouter()
const store = useInterviewStore()

const userInput = ref('')
const chatRef = ref(null)
const inputRef = ref(null)
const recognitionRef = ref(null)
const speechSupported = ref(false)
const isListening = ref(false)
const speechPreview = ref('')

const wsConnecting = computed(() => store.status === 'connecting')
const canSend = computed(() => {
  return userInput.value.trim().length > 0 && store.status === 'ongoing' && !wsConnecting.value
})
const canToggleSpeech = computed(() => {
  return speechSupported.value && store.status === 'ongoing' && !wsConnecting.value
})
const speechStatusText = computed(() => {
  if (!speechSupported.value) {
    return '当前浏览器不支持语音输入，建议使用最新版 Chrome 或 Edge。'
  }
  if (isListening.value) {
    return '正在听写，识别结果会自动追加到回答框。'
  }
  return '可使用语音输入，提交前仍可手动修改识别文本。'
})

const spotlightQuestion = computed(() => {
  return store.currentQuestion?.content || '正在等待面试官提问...'
})

const questionCategory = computed(() => {
  return store.currentQuestion?.metadata?.category || '通用问题'
})

const sessionTitle = computed(() => {
  return store.session?.jd_summary?.title || 'AI 模拟面试'
})

const sessionSubtitle = computed(() => {
  const company = store.session?.jd_summary?.company || '目标岗位'
  const candidate = store.session?.resume_summary?.name || '当前候选人'
  return `${candidate} · ${company}`
})

const currentPhase = computed(() => {
  const round = store.currentRound || 1
  if (round <= 2) {
    return { title: '开场摸底', desc: '先判断你的表达、基础理解和切题速度。' }
  }
  if (store.isFollowUp) {
    return { title: '追问深挖', desc: '面试官正在确认你是否真正理解刚才提到的内容。' }
  }
  if (round <= 6) {
    return { title: '核心深挖', desc: '进入项目细节、技术原理或行为案例的主体考察。' }
  }
  return { title: '收口判断', desc: '通过场景题和综合题判断稳定性、广度与上限。' }
})

const interviewerPersona = computed(() => {
  const type = store.session?.interview_type
  const mapping = {
    tech: '技术面试官',
    hr: '招聘经理 / HR',
    comprehensive: '综合面试官',
  }
  return mapping[type] || 'AI 面试官'
})

const interviewerHint = computed(() => {
  if (store.isFollowUp) return '你刚才的回答还不够扎实，正在触发追问'
  const category = questionCategory.value
  if (category.includes('项目')) return '重点看你做了什么、为什么这么做、结果如何'
  if (category.includes('技术')) return '重点看原理、边界条件和取舍'
  if (category.includes('场景')) return '重点看判断思路、风险和落地能力'
  return '重点看动机、表达和案例完整性'
})

const answerStructure = computed(() => {
  const category = questionCategory.value
  if (category.includes('项目')) {
    return ['背景', '目标', '动作', '结果', '复盘']
  }
  if (category.includes('技术')) {
    return ['先给结论', '说明原理', '举项目例子', '补充边界和取舍']
  }
  if (category.includes('场景')) {
    return ['先判断', '列方案', '说取舍', '讲风险和落地']
  }
  return ['结论', '案例', '动作', '结果', '反思']
})

const questionHelperText = computed(() => {
  if (store.isFollowUp) {
    return '这类追问通常不是再说一遍，而是要补细节、数据、取舍或具体案例。'
  }
  if (questionCategory.value.includes('技术')) {
    return '避免只背概念，最好带一个真实项目中的使用场景。'
  }
  if (questionCategory.value.includes('项目')) {
    return '优先说你的个人贡献，不要只说团队做了什么。'
  }
  if (questionCategory.value.includes('场景')) {
    return '先给思路框架，再展开关键动作。'
  }
  return '先说结论，再用一段具体经历支撑。'
})

const inputPlaceholder = computed(() => {
  if (store.status === 'evaluating') return '面试官正在评估上一题，请稍等...'
  if (store.roundRemaining <= 10) return '时间不多了，先给结论，再补关键细节...'
  return '输入你的回答...'
})

const answeredCount = computed(() => {
  return store.messages.filter((msg) => msg.type === 'evaluation').length
})

const timeoutCount = computed(() => {
  return store.messages.filter((msg) => msg.type === 'system' && msg.content.includes('超时'))
    .length
})

const recentSignal = computed(() => {
  const score = store.lastScore?.score
  if (score == null) return '待观察'
  if (score >= 85) return '表现强'
  if (score >= 70) return '较稳'
  if (score >= 60) return '可继续'
  return '风险偏高'
})

const statusLabel = computed(() => {
  const mapping = {
    idle: '未开始',
    connecting: '连接中',
    ongoing: '进行中',
    evaluating: '评估中',
    completed: '已完成',
    error: '异常',
  }
  return mapping[store.status] || store.status
})

const statusTagType = computed(() => {
  const mapping = {
    connecting: 'warning',
    ongoing: 'success',
    evaluating: 'warning',
    completed: 'success',
    error: 'danger',
    idle: 'info',
  }
  return mapping[store.status] || 'info'
})

function rowClass(msg) {
  return {
    'row-ai': msg.type === 'question',
    'row-user': msg.type === 'answer',
    'row-system': msg.type === 'system' || msg.type === 'end',
  }
}

function scoreClass(score) {
  if (score >= 85) return 'score-strong'
  if (score >= 70) return 'score-good'
  if (score >= 55) return 'score-warn'
  return 'score-risk'
}

function performanceSummary(score) {
  if (score >= 85) return '回答有说服力'
  if (score >= 70) return '整体不错，但还能再深入'
  if (score >= 55) return '基本覆盖，但说服力一般'
  return '回答偏弱，容易触发追问'
}

function getSpeechRecognitionCtor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

function appendRecognizedText(text) {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) return
  const separator = userInput.value.trim() ? '\n' : ''
  userInput.value = `${userInput.value}${separator}${normalized}`
  focusAnswerInput({ placeCursorAtEnd: true, keepVisible: true })
}

function stopSpeechRecognition() {
  if (recognitionRef.value && isListening.value) {
    recognitionRef.value.stop()
  }
}

function getAnswerTextarea() {
  return inputRef.value?.textarea || inputRef.value?.$el?.querySelector('textarea') || null
}

function focusAnswerInput(options = {}) {
  const { placeCursorAtEnd = false, keepVisible = false } = options
  nextTick(() => {
    const textarea = getAnswerTextarea()
    if (!textarea) return

    if (keepVisible) {
      textarea.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }

    textarea.focus()

    if (placeCursorAtEnd) {
      const length = textarea.value?.length ?? 0
      textarea.setSelectionRange(length, length)
    }
  })
}

function clearAnswerDraft() {
  stopSpeechRecognition()
  userInput.value = ''
  speechPreview.value = ''
  focusAnswerInput({ placeCursorAtEnd: true, keepVisible: true })
}

function toggleSpeechRecognition() {
  if (!speechSupported.value) {
    ElMessage.warning('当前浏览器不支持语音输入')
    return
  }
  if (isListening.value) {
    stopSpeechRecognition()
    return
  }
  speechPreview.value = ''
  recognitionRef.value?.start()
}

function setupSpeechRecognition() {
  const SpeechRecognitionCtor = getSpeechRecognitionCtor()
  speechSupported.value = Boolean(SpeechRecognitionCtor)
  if (!SpeechRecognitionCtor) return

  const recognition = new SpeechRecognitionCtor()
  recognition.continuous = true
  recognition.interimResults = true
  recognition.lang = 'zh-CN'
  recognition.maxAlternatives = 1

  recognition.onstart = () => {
    isListening.value = true
    speechPreview.value = ''
    focusAnswerInput({ placeCursorAtEnd: true, keepVisible: true })
  }

  recognition.onresult = (event) => {
    let interimTranscript = ''
    for (let idx = event.resultIndex; idx < event.results.length; idx += 1) {
      const result = event.results[idx]
      const transcript = result?.[0]?.transcript || ''
      if (result.isFinal) {
        appendRecognizedText(transcript)
      } else {
        interimTranscript += transcript
      }
    }
    speechPreview.value = interimTranscript.trim()
  }

  recognition.onerror = (event) => {
    isListening.value = false
    speechPreview.value = ''

    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      ElMessage.warning('麦克风权限未开启，无法使用语音输入')
      return
    }
    if (event.error === 'no-speech') {
      ElMessage.warning('没有识别到语音，请重试')
      return
    }
    if (event.error === 'audio-capture') {
      ElMessage.warning('未检测到可用麦克风')
      return
    }

    ElMessage.warning(`语音输入不可用：${event.error}`)
  }

  recognition.onend = () => {
    isListening.value = false
    speechPreview.value = ''
    focusAnswerInput({ placeCursorAtEnd: true, keepVisible: true })
  }

  recognitionRef.value = recognition
}

function handleSend() {
  const text = userInput.value.trim()
  if (!text || !canSend.value) return
  stopSpeechRecognition()
  store.submitAnswer(text)
  userInput.value = ''
  scrollToBottom()
}

function handleSkip() {
  stopSpeechRecognition()
  store.skipCurrent()
  scrollToBottom()
}

function handleEnd() {
  ElMessageBox.confirm('确定结束当前面试吗？系统会基于已完成题目生成本次复盘。', '结束面试', {
    confirmButtonText: '结束',
    cancelButtonText: '继续',
    type: 'warning',
  })
    .then(() => {
      stopSpeechRecognition()
      store.end()
      scrollToBottom()
    })
    .catch(() => {})
}

function viewReport() {
  router.push(`/interview/report/${route.params.sessionId}`)
}

function restartInterview() {
  stopSpeechRecognition()
  store.disconnect()
  router.push('/interview/setup')
}

function goBack() {
  if (!store.isCompleted && store.status !== 'idle') {
    ElMessageBox.confirm('离开当前页面会中断这场面试，是否返回？', '提示', {
      confirmButtonText: '返回',
      cancelButtonText: '继续面试',
      type: 'warning',
    })
      .then(() => {
        stopSpeechRecognition()
        store.disconnect()
        router.push('/interview/setup')
      })
      .catch(() => {})
    return
  }
  stopSpeechRecognition()
  store.disconnect()
  router.push('/interview/setup')
}

function scrollToBottom() {
  nextTick(() => {
    if (chatRef.value) {
      chatRef.value.scrollTop = chatRef.value.scrollHeight
    }
  })
}

watch(
  () => store.messages.length,
  () => {
    scrollToBottom()
  }
)

watch(
  () => store.status,
  (value) => {
    if (value !== 'ongoing' && isListening.value) {
      stopSpeechRecognition()
    }
    if (value === 'ongoing') {
      setTimeout(() => focusAnswerInput({ placeCursorAtEnd: true, keepVisible: true }), 150)
    }
  }
)

onMounted(async () => {
  setupSpeechRecognition()

  const sessionId = Number(route.params.sessionId)
  if (!sessionId) {
    ElMessage.error('无效的面试会话 ID')
    router.push('/interview/setup')
    return
  }

  try {
    const detail = await getInterviewDetail(sessionId)
    if (detail.status === 'completed') {
      router.replace(`/interview/report/${sessionId}`)
      return
    }

    store.hydrateSession(detail)
    store.startWS(sessionId)
  } catch (error) {
    ElMessage.error(error.message || '加载面试详情失败')
    router.push('/interview/setup')
  }
})

onUnmounted(() => {
  stopSpeechRecognition()
  store.disconnect()
})
</script>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.room-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 28px;
  border-radius: var(--app-radius-md, 16px);
  background:
    radial-gradient(circle at left top, rgba(217, 98, 48, 0.18), transparent 28%),
    linear-gradient(135deg, #16263e, #203756 45%, #304f71);
  color: #fff;
}

.eyebrow {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 12px;
  opacity: 0.72;
}

.room-hero h1 {
  margin: 0 0 8px;
  font-size: 30px;
}

.room-hero p {
  margin: 0;
  color: rgba(255, 255, 255, 0.74);
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.room-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) 340px;
  gap: 18px;
  align-items: start;
}

.main-column,
.side-column {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.main-column .panel + .panel,
.side-column .panel + .panel {
  margin-top: 0;
}

.stage-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.stage-kicker {
  color: var(--app-muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.stage-header h2 {
  margin: 6px 0 8px;
  font-size: 28px;
  color: var(--app-text);
}

.stage-header p {
  margin: 0;
  color: var(--app-muted);
  line-height: 1.7;
}

.stage-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(110px, 1fr));
  gap: 10px;
}

.meta-pill {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.meta-pill span {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}

.meta-pill strong {
  display: block;
  margin-top: 8px;
  color: var(--app-text);
}

.meta-pill.danger {
  background: #fff0ea;
}

.stage-progress {
  margin-top: 18px;
}

.interviewer-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.interviewer-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(135deg, #112b47, #d65d2f);
  color: #fff;
  font-weight: 700;
}

.interviewer-name {
  font-weight: 700;
  color: var(--app-text);
}

.interviewer-role {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
}

.question-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 18px 0 10px;
}

.question-badge {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: #edf4ff;
  color: var(--app-primary);
  font-size: 12px;
}

.question-badge.follow-up {
  background: #fff1e7;
  color: #c55a1f;
}

.question-card h3 {
  margin: 0;
  font-size: 28px;
  line-height: 1.45;
  color: var(--app-text);
}

.question-helper {
  margin: 12px 0 0;
  color: var(--app-muted);
  line-height: 1.7;
}

.structure-box {
  margin-top: 18px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(180deg, #fff8f3, #fff);
  border: 1px solid #f2dfd2;
}

.structure-title {
  margin-bottom: 10px;
  font-weight: 600;
  color: var(--app-text);
}

.structure-tips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.structure-tips span {
  padding: 5px 10px;
  border-radius: 999px;
  background: #fceade;
  color: #b54d1f;
  font-size: 12px;
}

.transcript-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}

.transcript-sub {
  font-size: 12px;
  color: var(--app-muted);
  font-weight: 400;
}

.transcript-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 480px;
  overflow-y: auto;
  padding-right: 4px;
}

.msg-row {
  display: flex;
}

.row-user {
  justify-content: flex-end;
}

.row-system {
  justify-content: center;
}

.msg-shell {
  max-width: 78%;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
}

.ai-shell {
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.user-shell {
  background: linear-gradient(135deg, #234263, #35597c);
  color: #fff;
}

.msg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
  opacity: 0.75;
}

.msg-body {
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.score-shell {
  width: min(100%, 720px);
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
}

.score-strong {
  background: #edf9ef;
  border: 1px solid #cdebd2;
}

.score-good {
  background: #edf4ff;
  border: 1px solid #d4e5ff;
}

.score-warn {
  background: #fff7eb;
  border: 1px solid #f8e2be;
}

.score-risk {
  background: #fff0ee;
  border: 1px solid #f4c8bf;
}

.score-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.score-dims {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}

.score-dims span {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.58);
  font-size: 12px;
}

.score-shell p {
  margin: 0;
  color: var(--app-muted);
  line-height: 1.7;
}

.score-improvement {
  margin-top: 10px !important;
  color: #9a4b1d !important;
}

.system-shell,
.end-shell {
  padding: 10px 16px;
  border-radius: 999px;
  background: var(--app-bg);
  color: var(--app-muted);
  font-size: 13px;
}

.end-shell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.state-hint {
  text-align: center;
  padding: 22px 0;
  color: var(--app-muted);
}

.answer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.answer-head p {
  margin: 6px 0 0;
  color: var(--app-muted);
}

.answer-shortcut {
  color: var(--app-muted);
  font-size: 12px;
}

.voice-toolbar {
  display: flex;
  align-items: stretch;
  gap: 14px;
  margin-top: 12px;
}

.voice-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex: 1;
  padding: 14px 16px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm, 12px);
  background:
    radial-gradient(circle at left top, rgba(214, 93, 47, 0.12), transparent 32%),
    linear-gradient(135deg, var(--app-bg), #eef3f9);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease;
}

.voice-trigger:hover:not(.disabled) {
  transform: translateY(-1px);
  border-color: var(--app-line-strong, rgba(185, 190, 197, 0.9));
  box-shadow: 0 12px 26px rgba(26, 46, 71, 0.08);
}

.voice-trigger.active {
  border-color: rgba(197, 90, 31, 0.45);
  background:
    radial-gradient(circle at left top, rgba(214, 93, 47, 0.18), transparent 32%),
    linear-gradient(135deg, #fff3ea, #fff9f5);
  box-shadow: 0 14px 30px rgba(197, 90, 31, 0.12);
}

.voice-trigger.unsupported,
.voice-trigger.disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.voice-trigger-core {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.voice-trigger-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--app-radius-xs, 8px);
  background: linear-gradient(135deg, #17314d, #2f5378);
  color: #fff;
  font-size: 22px;
  flex-shrink: 0;
}

.voice-trigger.active .voice-trigger-icon::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid rgba(197, 90, 31, 0.28);
  animation: voice-pulse 1.6s ease-out infinite;
}

.voice-trigger-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
}

.voice-trigger-copy strong {
  color: var(--app-text);
  font-size: 15px;
}

.voice-trigger-copy span {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.5;
  text-align: left;
}

.voice-trigger-signal {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #b9c3d2;
  flex-shrink: 0;
}

.voice-trigger-signal.live {
  background: #d96230;
  box-shadow: 0 0 0 6px rgba(217, 98, 48, 0.16);
}

.voice-actions {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  gap: 8px;
  min-width: 220px;
}

.voice-status {
  margin: 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
  text-align: right;
}

.voice-status.active {
  color: #c55a1f;
}

.voice-status.unsupported {
  color: var(--app-muted);
}

.speech-preview {
  margin: 10px 0 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.7;
}

.answer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
}

.completed-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 8px 0 0;
}

.side-title {
  font-weight: 600;
}

.side-block strong {
  display: block;
  color: var(--app-text);
}

.side-block p {
  margin: 6px 0 14px;
  color: var(--app-muted);
}

.skill-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.skill-grid span {
  padding: 5px 10px;
  border-radius: 999px;
  background: var(--app-bg);
  color: var(--app-muted);
  font-size: 12px;
}

.snapshot-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.snapshot-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.snapshot-item span {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}

.snapshot-item strong {
  display: block;
  margin-top: 8px;
  color: var(--app-text);
}

.snapshot-note {
  margin: 14px 0 0;
  color: #8c4a1f;
  line-height: 1.7;
}

.hint-list {
  margin: 0;
  padding-left: 18px;
  color: var(--app-muted);
  line-height: 1.9;
}

@keyframes voice-pulse {
  0% {
    opacity: 0.85;
    transform: scale(0.92);
  }
  70% {
    opacity: 0;
    transform: scale(1.08);
  }
  100% {
    opacity: 0;
    transform: scale(1.08);
  }
}

@media (max-width: 1100px) {
  .room-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .room-hero,
  .stage-header,
  .answer-head,
  .transcript-header,
  .voice-toolbar {
    flex-direction: column;
  }

  .stage-meta,
  .snapshot-grid {
    grid-template-columns: 1fr;
  }

  .msg-shell {
    max-width: 100%;
  }

  .answer-actions,
  .completed-actions,
  .voice-actions {
    flex-direction: column;
  }

  .voice-actions {
    align-items: stretch;
    min-width: 0;
  }

  .voice-status {
    text-align: left;
  }

  .voice-trigger {
    width: 100%;
  }
}
</style>
