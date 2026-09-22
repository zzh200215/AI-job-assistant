<template>
  <div class="app-load-error" role="alert">
    <div>
      <strong>{{ title }}</strong>
      <span v-if="message">{{ message }}</span>
    </div>
    <el-button v-if="retryLabel" size="small" @click="emit('retry')">{{ retryLabel }}</el-button>
  </div>
</template>

<script setup>
/**
 * 加载失败的统一呈现。
 *
 * 存在的理由是一件事实测出来的：`request.js` 只对**非 GET** 弹提示
 * （`notifyError !== false && method !== 'get'`），而许多视图的 catch 只把列表清成
 * `[]`——于是 GET 的 500 会命中页面自己的空态文案，把"服务端出错"说成"你这里没有数据"。
 * 失败必须是一个独立状态，而不是空态的一种写法。
 */
defineProps({
  title: { type: String, default: '加载失败' },
  message: { type: String, default: '' },
  // 传空字符串就不渲染按钮：有些地方没有可重试的动作
  retryLabel: { type: String, default: '重试' },
})

const emit = defineEmits(['retry'])
</script>

<style scoped>
.app-load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--app-danger), white 66%);
  border-radius: 8px;
  background: var(--app-accent-soft);
}

.app-load-error strong,
.app-load-error span {
  display: block;
}

.app-load-error strong {
  color: var(--app-danger);
  font-size: 13px;
}

.app-load-error span {
  margin-top: 2px;
  color: var(--app-muted);
  font-size: 12px;
}
</style>
