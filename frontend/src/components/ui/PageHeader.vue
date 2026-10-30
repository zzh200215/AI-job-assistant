<template>
  <header class="page-head">
    <div class="page-head-copy">
      <span v-if="eyebrow" class="page-head-eyebrow">{{ eyebrow }}</span>
      <h1 class="page-head-title">{{ title }}</h1>
      <p v-if="subtitle" class="page-head-sub">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="page-head-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
})
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.page-head-copy {
  min-width: 0;
}

.page-head-eyebrow {
  display: block;
  margin-bottom: 6px;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 500;
}

.page-head-title {
  margin: 0;
  color: var(--app-text);
  font-size: 26px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.page-head-sub {
  max-width: 720px;
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 14px;
  line-height: 1.6;
}

.page-head-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .page-head {
    flex-direction: column;
    gap: 14px;
    margin-bottom: 20px;
  }

  .page-head-title {
    font-size: 22px;
  }

  .page-head-actions {
    width: 100%;
  }
}
</style>
