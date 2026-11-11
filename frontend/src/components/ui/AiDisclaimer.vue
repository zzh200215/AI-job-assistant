<template>
  <p class="ai-disclaimer" :class="`tone-${tone}`">
    <el-icon class="ai-disclaimer-icon"><InfoFilled /></el-icon>
    <span>{{ text }}</span>
  </p>
</template>

<script setup>
/* AI 生成内容的免责说明，一处出处。

   为什么要有它：这个产品里候选人看到的每一句结论——匹配分、改写建议、面试评价、职业规划——
   都是模型生成或按规则算的，而屏幕上原先没有任何一处这么说。整套"区分真实推理与模板"的诚实性
   工作只活在管理员侧，候选人这边一片干净，等于白做。

   为什么是组件而不是各页各写一句：同一句话抄四份，改的时候必然漏哪一份，
   而这一句恰恰是不能出现"有的页面说、有的页面不说"的那一类。 */
import { InfoFilled } from '@element-plus/icons-vue'
import { computed } from 'vue'

const props = defineProps({
  /** `inline` 用于面板内部，`footer` 用于页面/报告末尾 */
  tone: { type: String, default: 'footer' },
  /** 少数场景需要更具体的一句（例如面试报告说的是"本场评价"） */
  custom: { type: String, default: '' },
})

const text = computed(
  () =>
    props.custom ||
    '以上内容由 AI 生成或按规则计算，仅供参考；请结合自身情况判断，不要直接当作结论。'
)
</script>

<style scoped>
.ai-disclaimer {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  line-height: 1.7;
  color: var(--app-muted);
}

.ai-disclaimer-icon {
  flex: none;
  margin-top: 2px;
}

.tone-footer {
  margin-top: 20px;
  padding: 12px 14px;
  font-size: 12px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
}

.tone-inline {
  font-size: 12px;
}
</style>
