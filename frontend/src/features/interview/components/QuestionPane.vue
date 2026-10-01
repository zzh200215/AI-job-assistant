<template>
  <div class="panel question-card">
    <div class="panel-body">
      <div class="interviewer-header">
        <div class="interviewer-avatar">AI</div>
        <div>
          <div class="interviewer-name">{{ persona }}</div>
          <div class="interviewer-role">{{ hint }}</div>
        </div>
      </div>

      <div class="question-meta">
        <span class="question-badge">{{ category }}</span>
        <span v-if="isFollowUp" class="question-badge follow-up">追问</span>
      </div>

      <h3>{{ question }}</h3>
      <p class="question-helper">{{ helperText }}</p>

      <div class="structure-box">
        <div class="structure-title">建议回答结构</div>
        <div class="structure-tips">
          <span v-for="tip in structure" :key="tip">{{ tip }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/* 题卡面板：D66 从 InterviewRoom.vue 搬出来。七个字符串/数组全是页面的 lib 规则算完的成品（`interviewRoomModel` 是 D60 那批），面板不重算一遍——"第 3 轮起换核心深挖"这类门槛只能有一处真相。 */

defineProps({
  persona: { type: String, default: '' },
  hint: { type: String, default: '' },
  category: { type: String, default: '' },
  isFollowUp: { type: Boolean, default: false },
  question: { type: String, default: '' },
  helperText: { type: String, default: '' },
  structure: { type: Array, default: () => [] },
})
</script>

<style scoped>
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
.interview-room-page .question-card {
  border-color: #cfd9ea;
  box-shadow: 0 12px 28px rgba(31, 55, 94, 0.08);
}
.interview-room-page .interviewer-avatar {
  background: linear-gradient(135deg, #2359d9, #22a9d8);
}
.interview-room-page .structure-box {
  border-color: #d6e5fb;
  background: #f5f9ff;
}
.interview-room-page .structure-tips span {
  border-radius: var(--app-radius-xs);
  background: #e7f1ff;
  color: #2461b7;
}
</style>
