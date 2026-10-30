<template>
  <div class="empty-block" :class="{ 'is-compact': compact }">
    <div v-if="icon" class="empty-icon">
      <el-icon :size="18"><component :is="icon" /></el-icon>
    </div>
    <strong class="empty-title">{{ title }}</strong>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <div v-if="$slots.action" class="empty-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: [Object, Function], default: null },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.empty-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 36px 20px;
  text-align: center;
}

.empty-block.is-compact {
  padding: 20px 16px;
}

.empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  margin-bottom: 4px;
  border: 1px solid var(--app-line);
  border-radius: 50%;
  background: var(--app-surface-muted);
  color: var(--app-muted);
}

.empty-title {
  color: var(--app-text);
  font-size: 14px;
  font-weight: 600;
}

.empty-desc {
  max-width: 360px;
  margin: 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
}

.empty-action {
  margin-top: 8px;
}
</style>
