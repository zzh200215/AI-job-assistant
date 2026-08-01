<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'

import { useTenantStore } from '@/stores/tenant'

// 根组件：进入应用即拉取租户品牌并写入 CSS 变量（T2-5），无登录态也能用默认/域名租户
const tenantStore = useTenantStore()
onMounted(() => tenantStore.init())
</script>
