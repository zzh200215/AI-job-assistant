<template>
  <div class="panel stage-card">
    <div class="panel-body">
      <div class="stage-header">
        <div>
          <span class="stage-kicker">当前阶段</span>
          <h2>{{ phase.title }}</h2>
          <p>{{ phase.desc }}</p>
        </div>
        <div class="stage-meta">
          <div class="meta-pill">
            <span>进度</span>
            <strong>{{ round || 0 }} / {{ total || 0 }}</strong>
          </div>
          <div class="meta-pill" :class="{ danger: remaining <= 10 }">
            <span>单题倒计时</span>
            <strong>{{ formattedRemaining }}</strong>
          </div>
          <div class="meta-pill">
            <span>总用时</span>
            <strong>{{ formattedTime }}</strong>
          </div>
        </div>
      </div>
      <el-progress
        :percentage="progress"
        :show-text="false"
        :stroke-width="10"
        class="stage-progress"
      />
    </div>
  </div>
</template>

<script setup>
/* 当前阶段面板：D66 从 InterviewRoom.vue 搬出来。七个值全部是页面把 store 的字段递进来的（这个仓库里没有一个组件 import store，展示面板也不破例）。`remaining <= 10` 那一道红色门槛跟着搬进来：它只在屏幕上有一处消费者。 */

defineProps({
  phase: { type: Object, required: true },
  round: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  remaining: { type: Number, default: 0 },
  formattedRemaining: { type: String, default: '--' },
  formattedTime: { type: String, default: '--' },
  progress: { type: Number, default: 0 },
})
</script>

<style scoped>
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
.interview-room-page .stage-card {
  border-top: 3px solid var(--app-cyan);
}
</style>
