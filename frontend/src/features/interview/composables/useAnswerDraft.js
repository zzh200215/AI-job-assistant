import { nextTick, onUnmounted, ref, watch } from 'vue'

import { ElMessage } from '@/plugins/element-services'

/* 回答草稿 + 语音输入这条链，D61 从 InterviewRoom.vue 搬出来。
   搬之前这页对浏览器的 SpeechRecognition 一句测试都没有：jsdom 里那个构造器不存在，
   所以 `speechSupported` 永远是 false，onstart/onresult/onerror/onend 四个回调、
   追加文本的换行规则、状态转走后停听写——全部只能读源码相信。
   装一个假的构造器之后这些都能钉住，见 tests/unit/interviewRoomSpeechChain.test.js。

   入参只有 `getStatus`：这条链需要知道面试还在不在进行中（转走就要停听写），
   但"进行中"是 store 的知识，不该由链自己去 import store。 */
export function useAnswerDraft({ getStatus }) {
  const userInput = ref('')
  const answerInputRef = ref(null)
  const recognitionRef = ref(null)
  const speechSupported = ref(false)
  const isListening = ref(false)
  const speechPreview = ref('')

  function getSpeechRecognitionCtor() {
    if (typeof window === 'undefined') return null
    return window.SpeechRecognition || window.webkitSpeechRecognition || null
  }

  function getAnswerTextarea() {
    return (
      answerInputRef.value?.textarea || answerInputRef.value?.$el?.querySelector('textarea') || null
    )
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

  // 面试不再进行中就停掉听写；刚开始则把光标放进回答框（那 150ms 是给页面渲染留的）
  watch(getStatus, (value) => {
    if (value !== 'ongoing' && isListening.value) {
      stopSpeechRecognition()
    }
    if (value === 'ongoing') {
      setTimeout(() => focusAnswerInput({ placeCursorAtEnd: true, keepVisible: true }), 150)
    }
  })

  // 离开房间时链自己收尾，不指望页面记得
  onUnmounted(stopSpeechRecognition)

  return {
    userInput,
    answerInputRef,
    speechSupported,
    isListening,
    speechPreview,
    setupSpeechRecognition,
    toggleSpeechRecognition,
    stopSpeechRecognition,
    clearAnswerDraft,
  }
}
