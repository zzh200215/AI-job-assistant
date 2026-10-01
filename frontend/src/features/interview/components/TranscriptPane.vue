<template>
  <div class="panel transcript-card">
    <div class="panel-header">
      <div class="transcript-header">
        <span>面试实录</span>
        <span class="transcript-sub">实时显示提问、作答、评分与超时反馈</span>
      </div>
    </div>
    <div class="panel-body">
      <div ref="listRef" class="transcript-list">
        <div
          v-for="(msg, idx) in messages"
          :key="`${idx}-${msg.type}`"
          class="msg-row"
          :class="roomModel.messageRowClass(msg)"
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
            <div
              class="score-shell"
              :class="interviewScoreToneClass(msg.metadata?.score, 'score-chip')"
            >
              <div class="score-top">
                <strong>本题评分 {{ msg.metadata?.score || 0 }}</strong>
                <span>{{ roomModel.performanceSummaryOf(msg.metadata?.score) }}</span>
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

      <div v-if="status === 'connecting'" class="state-hint">正在接入面试房间...</div>
      <div v-else-if="status === 'evaluating'" class="state-hint">
        面试官正在记录你的回答并决定下一问...
      </div>
    </div>
  </div>
</template>

<script setup>
/* 面试实录面板：D66 从 InterviewRoom.vue 搬出来，是这页最大的一块（含五种消息行的分支）。消息行的归类与"没有分数时不能写回答偏弱"仍住在 lib 与 utils（面板 import 它们，因为它们是规则不是状态）。 */

import { nextTick, ref, watch } from 'vue'

import { interviewScoreToneClass } from '@/utils/scoreTone'
import * as roomModel from '@/features/interview/lib/interviewRoomModel'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  status: { type: String, default: 'idle' },
})

/* 滚动跟着这块 DOM 走：页面此前用 chatRef + scrollToBottom 从三个动作后面各推一次，
   实测那三条路的其中两条（提交、跳过）本来就会往 messages 里塞一条，第三条（结束）改的是
   status 而下面那块状态提示就在本面板里，所以两个 watcher 覆盖同样的时机。 */
const listRef = ref(null)

function scrollToEnd() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

watch([() => props.messages.length, () => props.status], scrollToEnd)
</script>

<style scoped>
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
.score-chip--high {
  background: var(--app-score-high-soft);
  border: 1px solid var(--app-score-high-soft-line);
}
.score-chip--good {
  background: var(--app-score-good-soft);
  border: 1px solid var(--app-score-good-soft-line);
}
.score-chip--warn {
  background: var(--app-score-warn-soft);
  border: 1px solid var(--app-score-warn-soft-line);
}
.score-chip--risk {
  background: var(--app-score-risk-soft);
  border: 1px solid var(--app-score-risk-soft-line);
}
.score-chip--unknown {
  background: var(--app-score-unknown-soft);
  border: 1px solid var(--app-score-unknown-soft-line);
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
/* D68 补回：D66 抄这条时丢了选择器列表的前半截（页面里是 `.system-shell,` 换行 `.end-shell {…}`，
   抽取脚本按"选择器行以 { 结尾"找起点，只收进后半截），system 消息因此失去药丸形状——
   实测 padding 0px / radius 0px，而同一条规则里的 .end-shell 是 10px 16px / 999px。 */
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
.interview-room-page .user-shell {
  background: linear-gradient(135deg, #2359d9, #2c72d9);
}

@media (max-width: 720px) {
  .msg-shell {
    max-width: 100%;
  }
}
</style>
