<template>
  <span v-for="(part, i) in parts" :key="i" :class="part.pending ? 'todo-text' : ''">{{
    part.text
  }}</span>
</template>

<script setup>
import { computed } from 'vue'

/* `【待补：…】` 上底色，但不走 v-html：这一段文字来自模型，注入面不该为了一点配色打开。
   同一条标记在可下载的独立 HTML 里由 `project_report_html._todo` 上色，两处认的是同一个形状。 */
const props = defineProps({ text: { type: [String, Number], default: '' } })
const SPLIT = /(【待补[^】]*】)/

const parts = computed(() =>
  String(props.text ?? '')
    .split(SPLIT)
    .filter((chunk) => chunk !== '')
    .map((chunk) => ({ text: chunk, pending: SPLIT.test(chunk) }))
)
</script>

<style scoped>
.todo-text {
  color: var(--app-danger);
  font-weight: 600;
}
</style>
