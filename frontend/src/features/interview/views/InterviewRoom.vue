<template>
  <div class="page-shell interview-room-page">
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
        <StagePane
          :phase="currentPhase"
          :round="store.currentRound"
          :total="store.totalQuestions"
          :remaining="store.roundRemaining"
          :formatted-remaining="store.formattedRoundRemaining"
          :formatted-time="store.formattedTime"
          :progress="store.progress"
        />

        <QuestionPane
          :persona="interviewerPersona"
          :hint="interviewerHint"
          :category="questionCategory"
          :is-follow-up="store.isFollowUp"
          :question="spotlightQuestion"
          :helper-text="questionHelperText"
          :structure="answerStructure"
        />

        <TranscriptPane :messages="store.messages" :status="store.status" />

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

      <RoomAside
        :session="store.session"
        :answered-count="answeredCount"
        :timeout-count="timeoutCount"
        :last-score="store.lastScore"
        :recent-signal="recentSignal"
        :structure="answerStructure"
      />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { Microphone } from '@element-plus/icons-vue'
import { getInterviewDetail } from '@/api/interview'
import { useInterviewStore } from '@/stores/interview'
import { INTERVIEW_STATUS_TAGS, tagTypeFor } from '@/utils/statusTone'
import RoomAside from '@/features/interview/components/RoomAside.vue'
import QuestionPane from '@/features/interview/components/QuestionPane.vue'
import StagePane from '@/features/interview/components/StagePane.vue'
import TranscriptPane from '@/features/interview/components/TranscriptPane.vue'
import * as roomModel from '@/features/interview/lib/interviewRoomModel'
import { useAnswerDraft } from '@/features/interview/composables/useAnswerDraft'

const route = useRoute()
const router = useRouter()
const store = useInterviewStore()

/* 回答草稿与语音输入这条链（含 SpeechRecognition 的四个回调、150ms 后聚焦那一下、
   离开页面时的收尾）住在 composables/useAnswerDraft.js。`inputRef` 这个名字不能改：
   模板上的 `ref="inputRef"` 靠它绑定。 */
const {
  userInput,
  answerInputRef: inputRef,
  speechSupported,
  isListening,
  speechPreview,
  setupSpeechRecognition,
  toggleSpeechRecognition,
  stopSpeechRecognition,
  clearAnswerDraft,
} = useAnswerDraft({ getStatus: () => store.status })

const wsConnecting = computed(() => store.status === 'connecting')
/* 显示层的规则全部住在 lib/interviewRoomModel.js（D60）：这一层不读 ref、不碰 store，
   所以"第 3 轮起换核心深挖""没有分数时不能写『回答偏弱』"这些门槛能被逐条钉住。
   下面每个 computed 都只是把 store 的一个字段递进去。
   `canSend` / `canToggleSpeech` 以前还各带一条 `!wsConnecting.value`，而 `wsConnecting` 就是
   `store.status === 'connecting'`：同一个值既等于 'ongoing' 又不等于 'connecting'，那条永不
   成立，搬家时按定义删掉（`wsConnecting` 本身仍在模板的两处 `:disabled` 上承重）。 */
const canSend = computed(() =>
  roomModel.sendEnabled({ text: userInput.value, status: store.status })
)
const canToggleSpeech = computed(() =>
  roomModel.speechEnabled({ supported: speechSupported.value, status: store.status })
)
const speechStatusText = computed(() =>
  roomModel.speechStatusText({ supported: speechSupported.value, listening: isListening.value })
)
const spotlightQuestion = computed(() => roomModel.spotlightQuestion(store.currentQuestion))
const questionCategory = computed(() => roomModel.questionCategory(store.currentQuestion))
const sessionTitle = computed(() => roomModel.sessionTitle(store.session))
const sessionSubtitle = computed(() => roomModel.sessionSubtitle(store.session))
const currentPhase = computed(() =>
  roomModel.phaseOf({ round: store.currentRound || 1, isFollowUp: store.isFollowUp })
)
const interviewerPersona = computed(() => roomModel.interviewerPersona(store.session))
const interviewerHint = computed(() =>
  roomModel.interviewerHint({ isFollowUp: store.isFollowUp, category: questionCategory.value })
)
const answerStructure = computed(() => roomModel.answerStructure(questionCategory.value))
const questionHelperText = computed(() =>
  roomModel.questionHelperText({ isFollowUp: store.isFollowUp, category: questionCategory.value })
)
const inputPlaceholder = computed(() =>
  roomModel.inputPlaceholderOf({ status: store.status, roundRemaining: store.roundRemaining })
)
const answeredCount = computed(() => roomModel.answeredCountOf(store.messages))
const timeoutCount = computed(() => roomModel.timeoutCountOf(store.messages))
const recentSignal = computed(() => roomModel.recentSignalOf(store.lastScore?.score))
const statusLabel = computed(() => roomModel.statusLabelOf(store.status))
const statusTagType = computed(() => tagTypeFor(INTERVIEW_STATUS_TAGS, store.status))

function handleSend() {
  const text = userInput.value.trim()
  if (!text || !canSend.value) return
  stopSpeechRecognition()
  store.submitAnswer(text)
  userInput.value = ''
}

function handleSkip() {
  stopSpeechRecognition()
  store.skipCurrent()
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

/* P1 focus treatment: status stays visible while the question remains dominant. */
.interview-room-page {
  background: #f6f8fc;
}

.interview-room-page .room-hero {
  position: relative;
  overflow: hidden;
  border: 1px solid #252b3a;
  border-radius: var(--app-radius-md);
  background: linear-gradient(115deg, #111522 0%, #18223a 62%, #1a2845 100%);
}

.interview-room-page .room-hero::after {
  position: absolute;
  right: -42px;
  bottom: -94px;
  width: 220px;
  height: 220px;
  border: 1px solid rgba(34, 184, 232, 0.24);
  border-radius: 50%;
  box-shadow: 0 0 0 34px rgba(37, 99, 235, 0.08);
  content: '';
}

.interview-room-page .hero-actions {
  position: relative;
  z-index: 1;
}

.interview-room-page .structure-tips span {
  border-radius: var(--app-radius-xs);
  background: #e7f1ff;
  color: #2461b7;
}

.interview-room-page .transcript-card,
.interview-room-page .answer-card {
  border-color: #d9e0eb;
}

.interview-room-page .voice-trigger {
  border-color: #d8e3f4;
  background: #f7faff;
}

.interview-room-page .voice-trigger.active {
  border-color: rgba(37, 99, 235, 0.42);
  background: #eef5ff;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.1);
}

.interview-room-page .voice-trigger-icon {
  background: linear-gradient(135deg, #2359d9, #2c72d9);
}

.interview-room-page .voice-trigger.active .voice-trigger-icon::after {
  border-color: rgba(37, 99, 235, 0.28);
}

.interview-room-page .voice-trigger-signal.live {
  background: var(--app-primary);
  box-shadow: 0 0 0 6px rgba(37, 99, 235, 0.15);
}

.interview-room-page .voice-status.active,
.interview-room-page .score-improvement,
.interview-room-page .snapshot-note {
  color: #2461b7 !important;
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
