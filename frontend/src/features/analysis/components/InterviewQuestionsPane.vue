<template>
  <el-empty v-if="!hasQuestions" description="暂无面试题" />
  <template v-else>
    <div v-for="(items, key) in groups" :key="key">
      <h4>{{ groupTitle(key) }}</h4>
      <div v-for="(q, i) in items" :key="i" class="q-card">
        <div class="q">
          <b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}
        </div>
        <div class="q-intent">考察点：{{ q.focus || q.intent }}</div>
        <div class="q-answer">
          参考答案：{{ q.suggested_answer || q.expected_answer || q.ref_answer }}
        </div>
        <div v-if="q.preparation_tips" class="q-tip">备考建议：{{ q.preparation_tips }}</div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { computed } from 'vue'

import { groupTitle } from '@/features/analysis/lib/analysisModel'

/* 个性化面试题面板：D65 从 SmartAnalysis.vue 搬出来。
   页面原来那条 `hasInterview = Object.keys(interviewGroups).length > 0` 是**纯从 props 派生**的，
   所以它跟着搬进来改名 `hasQuestions`，页面那条同时删掉——留两处就是两份真相。
   分组合并（新键 hr_questions 与 legacy 键 tech 都认）住在 lib，页面做完再递进来。 */
const props = defineProps({
  groups: { type: Object, default: () => ({}) },
})

/* 空态判据只认这一条：分组对象有没有键。原来这条在页面上叫 `hasInterview`，它纯从 props 派生，所以跟着搬进来。 */
const hasQuestions = computed(() => Object.keys(props.groups).length > 0)
</script>

<style scoped>
/* Query card */
.q-card {
  padding: 14px;
  margin: 8px 0;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
}

.q {
  font-size: 14px;
}
.q-intent {
  color: var(--app-muted);
  font-size: 12px;
  margin: 4px 0;
}
.q-answer {
  color: var(--app-success);
  font-size: 13px;
}
.q-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-warning);
}
/* List */
ul {
  padding-left: 16px;
  margin: 4px 0;
}
h4 {
  margin: 12px 0 6px;
}
h5 {
  margin: 0 0 8px;
}

.mt {
  margin-top: 16px;
}
.mb {
  margin-bottom: 8px;
}
</style>
