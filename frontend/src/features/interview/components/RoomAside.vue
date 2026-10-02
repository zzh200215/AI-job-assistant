<template>
  <aside class="side-column">
    <div class="panel side-panel">
      <div class="panel-header">
        <div class="side-title">岗位聚焦</div>
      </div>
      <div class="panel-body">
        <div class="side-block">
          <strong>{{ session?.jd_summary?.title || '目标岗位' }}</strong>
          <p>{{ session?.jd_summary?.company || '未填写公司' }}</p>
          <div class="skill-grid">
            <span
              v-for="skill in (session?.jd_summary?.required_skills || []).slice(0, 6)"
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
            <strong>{{ lastScore?.score ?? '--' }}</strong>
          </div>
          <div class="snapshot-item">
            <span>当前判断</span>
            <strong>{{ recentSignal }}</strong>
          </div>
        </div>
        <p v-if="lastScore?.improvement" class="snapshot-note">
          最近一题建议：{{ lastScore.improvement }}
        </p>
      </div>
    </div>

    <div class="panel side-panel">
      <div class="panel-header">
        <div class="side-title">本题提醒</div>
      </div>
      <div class="panel-body">
        <ul class="hint-list">
          <li v-for="tip in structure" :key="tip">{{ tip }}</li>
        </ul>
      </div>
    </div>
  </aside>
</template>

<script setup>
/* 右栏三块（岗位聚焦 / 表现速览 / 本题提醒）：D66 从 InterviewRoom.vue 整列搬出来。合成一个组件而不是三个，是因为这一列的耦合就在列上——`.side-column .panel + .panel` 那条间距规则要的是"相邻的两块面板"，拆成三个组件就得把它复制三份。 */

defineProps({
  session: { type: Object, default: null },
  answeredCount: { type: Number, default: 0 },
  timeoutCount: { type: Number, default: 0 },
  lastScore: { type: Object, default: null },
  recentSignal: { type: String, default: '' },
  structure: {
    type: /** @type {import('vue').PropType<import('../lib/interviewRoomModel').AnswerStructure>} */ (
      Array
    ),
    default: () => [],
  },
})
</script>

<style scoped>
.side-column {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.side-column .panel + .panel {
  margin-top: 0;
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
.interview-room-page .snapshot-note {
  color: #2461b7 !important;
}

@media (max-width: 720px) {
  .snapshot-grid {
    grid-template-columns: 1fr;
  }
}
</style>
