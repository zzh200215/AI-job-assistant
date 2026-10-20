<template>
  <el-alert
    v-if="state === 'reconnecting'"
    class="connection-banner"
    type="warning"
    :closable="false"
    show-icon
  >
    <template #title>网络断开，正在重连（第 {{ attempt }}/{{ max }} 次）</template>
    <template #default>
      {{ delaySeconds }} 秒后自动重试；重连成功后会同步到当前题，无需刷新。
    </template>
  </el-alert>

  <el-alert
    v-else-if="state === 'recovered'"
    class="connection-banner"
    type="success"
    :closable="false"
    show-icon
  >
    <template #title>已重新连接</template>
    <template #default>正在同步面试进度，下一题出现后即可继续作答。</template>
  </el-alert>

  <el-alert
    v-else-if="state === 'failed'"
    class="connection-banner"
    type="error"
    :closable="false"
    show-icon
  >
    <template #title>重连失败</template>
    <template #default>请刷新页面重试；这场面试的进度已经保存在服务端。</template>
  </el-alert>
</template>

<script setup>
/* P5(a)：WS 自动重连的状态对候选人可见。这个组件只画状态，计时与尝试次数都在 store / api 层。 */
defineProps({
  state: { type: String, default: 'idle' },
  attempt: { type: Number, default: 0 },
  max: { type: Number, default: 0 },
  delaySeconds: { type: Number, default: 0 },
})
</script>

<style scoped>
.connection-banner {
  margin-bottom: 0;
}
</style>
