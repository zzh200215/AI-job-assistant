<template>
  <span class="score-ring" :style="{ width: size + 'px', height: size + 'px' }">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" aria-hidden="true">
      <circle
        class="score-ring-track"
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        :stroke-width="strokeWidth"
      />
      <circle
        class="score-ring-value"
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        :stroke="color"
        :stroke-width="strokeWidth"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="offset"
      />
    </svg>
    <b>{{ label }}</b>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { scoreToneColor } from '@/utils/scoreTone'

const props = defineProps({
  score: { type: [Number, String], default: null },
  size: { type: Number, default: 38 },
  strokeWidth: { type: Number, default: 3 },
})

const center = computed(() => props.size / 2)
const radius = computed(() => props.size / 2 - props.strokeWidth / 2 - 1)
const circumference = computed(() => 2 * Math.PI * radius.value)
const safeScore = computed(() => {
  if (props.score === null || props.score === undefined || !Number.isFinite(Number(props.score)))
    return null
  return Math.min(100, Math.max(0, Number(props.score)))
})
const offset = computed(() =>
  safeScore.value === null ? circumference.value : circumference.value * (1 - safeScore.value / 100)
)
const color = computed(() =>
  safeScore.value === null ? 'var(--app-line-strong)' : scoreToneColor(safeScore.value)
)
const label = computed(() => (safeScore.value === null ? '—' : String(Math.round(safeScore.value))))
</script>

<style scoped>
.score-ring {
  position: relative;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
}

.score-ring svg {
  transform: rotate(-90deg);
}

.score-ring-track {
  stroke: var(--app-surface-muted);
}

.score-ring b {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--app-text);
  font-family: var(--app-font-mono);
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
}
</style>
