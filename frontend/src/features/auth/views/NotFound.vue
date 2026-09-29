<template>
  <div class="not-found-page">
    <div class="not-found-card">
      <el-icon class="icon" :size="80" color="var(--app-violet)">
        <WarningFilled />
      </el-icon>
      <h1 class="code">404</h1>
      <p class="desc">抱歉，您访问的页面不存在</p>
      <el-button type="primary" size="large" @click="$router.push('/home')">
        <el-icon><HomeFilled /></el-icon>
        返回首页
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { WarningFilled, HomeFilled } from '@element-plus/icons-vue'
</script>

<style scoped>
.not-found-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.not-found-card {
  background: var(--app-surface-strong);
  border-radius: 16px;
  padding: 60px 80px;
  text-align: center;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}
.icon {
  margin-bottom: 16px;
}
.code {
  font-size: 72px;
  font-weight: 900;
  color: #303133;
  margin: 0;
  line-height: 1;
}
.desc {
  font-size: 18px;
  color: #909399;
  margin: 20px 0 36px;
}
</style>
