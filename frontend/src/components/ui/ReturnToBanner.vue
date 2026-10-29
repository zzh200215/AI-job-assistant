<template>
  <div v-if="target" class="return-banner" role="status">
    <span>从{{ target.label }}跳转而来</span>
    <el-button link type="primary" @click="goBack">返回{{ target.label }}</el-button>
    <el-button link @click="dismiss">知道了</el-button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { clearReturnTo, readReturnTo } from '@/utils/navigationReturn'

const router = useRouter()
const target = ref(readReturnTo())

function goBack() {
  if (!target.value) return
  const path = target.value.path
  clearReturnTo()
  router.push(path)
}

function dismiss() {
  clearReturnTo()
  target.value = null
}
</script>

<style scoped>
.return-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.return-banner :deep(.el-button) {
  font-size: 13px;
}
</style>
