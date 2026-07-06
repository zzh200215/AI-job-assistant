<template>
  <div class="profile-page">
    <section class="hero-card">
      <div>
        <p class="eyebrow">Account</p>
        <h1>个人中心</h1>
        <p class="hero-copy">统一查看当前账号身份、系统运行模式和交付能力状态。</p>
      </div>
      <div class="hero-badges">
        <span>{{ authStore.roleLabel }}</span>
        <span>{{ status.demo_mode ? 'Demo Mode' : 'Live Mode' }}</span>
      </div>
    </section>

    <section class="grid">
      <article class="panel identity-panel">
        <div class="panel-head">
          <h2>账号信息</h2>
          <el-button text @click="refreshAll" :loading="loading">刷新</el-button>
        </div>
        <div class="identity-card">
          <div class="avatar">{{ avatarText }}</div>
          <div class="identity-copy">
            <strong>{{ authStore.user?.username || '--' }}</strong>
            <span>{{ authStore.user?.email || '--' }}</span>
            <div class="identity-pills">
              <span>{{ authStore.roleLabel }}</span>
              <span v-if="authStore.user?.is_admin">Admin</span>
              <span v-else>Standard</span>
            </div>
          </div>
        </div>
        <dl class="info-list">
          <div class="info-row">
            <dt>用户 ID</dt>
            <dd>{{ authStore.user?.id ?? '--' }}</dd>
          </div>
          <div class="info-row">
            <dt>注册时间</dt>
            <dd>{{ formatDate(authStore.user?.created_at) }}</dd>
          </div>
          <div class="info-row">
            <dt>默认工作台</dt>
            <dd>{{ authStore.homeRoute }}</dd>
          </div>
        </dl>
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2>系统模式</h2>
          <span class="panel-tip">运行时状态</span>
        </div>
        <div class="status-grid">
          <div class="status-card" :class="{ alert: status.demo_mode }">
            <span>当前模式</span>
            <strong>{{ status.demo_mode ? '演示模式' : '正式模式' }}</strong>
            <small>{{ status.demo_mode ? '仍有 mock 依赖，适合演示和联调。' : '核心依赖已切到真实模式。' }}</small>
          </div>
          <div class="status-card">
            <span>LLM</span>
            <strong>{{ formatProvider(status.llm_provider) }}</strong>
            <small>编排引擎：{{ status.orchestration_engine || '--' }}</small>
          </div>
          <div class="status-card">
            <span>Embedding</span>
            <strong>{{ formatProvider(status.embedding_provider) }}</strong>
            <small>编排策略：{{ status.orchestration_strategy || '--' }}</small>
          </div>
          <div class="status-card">
            <span>Reranker</span>
            <strong>{{ formatProvider(status.reranker_provider) }}</strong>
            <small>运行环境：{{ status.app_env || '--' }}</small>
          </div>
        </div>
      </article>
    </section>

    <section class="panel capability-panel">
      <div class="panel-head">
        <h2>能力状态</h2>
        <span class="panel-tip">按交付闭环检查</span>
      </div>
      <div class="capability-list">
        <div class="capability-item" :class="{ done: status.capabilities?.tool_calling }">
          <strong>LLM 工具调用</strong>
          <span>{{ status.capabilities?.tool_calling ? '已开启' : '未开启' }}</span>
        </div>
        <div class="capability-item" :class="{ done: status.capabilities?.ocr_resume_parse }">
          <strong>OCR 简历识别</strong>
          <span>{{ status.capabilities?.ocr_resume_parse ? '已开启' : '未开启' }}</span>
        </div>
        <div class="capability-item" :class="{ done: status.capabilities?.password_reset }">
          <strong>忘记密码</strong>
          <span>{{ status.capabilities?.password_reset ? '已开启' : '未开启' }}</span>
        </div>
        <div class="capability-item" :class="{ done: status.capabilities?.social_login }">
          <strong>第三方登录</strong>
          <span>{{ status.capabilities?.social_login ? '已开启' : '未开启' }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { getSystemStatus } from '@/api/system'
import { ElMessage } from '@/plugins/element-services'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const loading = ref(false)
const status = reactive({
  app_env: '',
  orchestration_strategy: '',
  orchestration_engine: '',
  llm_provider: '',
  embedding_provider: '',
  reranker_provider: '',
  demo_mode: false,
  capabilities: {
    tool_calling: false,
    social_login: false,
    password_reset: false,
    ocr_resume_parse: false,
  },
})

const avatarText = computed(() => {
  const name = String(authStore.user?.username || '').trim()
  return name ? name.slice(0, 1).toUpperCase() : 'U'
})

function formatProvider(value) {
  return value ? String(value).toUpperCase() : '--'
}

function formatDate(value) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

async function refreshAll() {
  loading.value = true
  try {
    await authStore.fetchMe()
    const data = await getSystemStatus()
    Object.assign(status, data || {})
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await refreshAll()
  } catch {
    ElMessage.error('个人中心加载失败')
  }
})
</script>

<style scoped>
.profile-page {
  display: grid;
  gap: 18px;
}

.hero-card,
.panel {
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(203, 221, 230, 0.82);
  border-radius: 24px;
  box-shadow: 0 16px 32px rgba(145, 176, 193, 0.12);
  backdrop-filter: blur(10px);
}

.hero-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 28px;
  background:
    radial-gradient(circle at top right, rgba(114, 187, 143, 0.18), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(245, 250, 246, 0.94));
}

.eyebrow {
  margin: 0 0 10px;
  color: #7a8aa1;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.hero-card h1,
.panel h2 {
  margin: 0;
  color: #1f2b3d;
}

.hero-card h1 {
  font-size: 34px;
  line-height: 1.05;
}

.hero-copy {
  margin: 12px 0 0;
  color: #66758a;
  line-height: 1.75;
}

.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-badges span,
.identity-pills span {
  padding: 8px 12px;
  border-radius: 999px;
  background: #eff9f2;
  color: #1c8c5e;
  font-size: 12px;
  font-weight: 600;
}

.grid {
  display: grid;
  grid-template-columns: 1.1fr 1.4fr;
  gap: 18px;
}

.panel {
  padding: 24px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.panel-tip {
  color: #8a97ac;
  font-size: 13px;
}

.identity-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(135deg, #f4fbf6, #faf7ef);
  border: 1px solid rgba(211, 231, 218, 0.9);
}

.avatar {
  width: 58px;
  height: 58px;
  border-radius: 18px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #1c8c5e, #c66a3d);
  color: #fff;
  font-size: 24px;
  font-weight: 700;
}

.identity-copy {
  min-width: 0;
}

.identity-copy strong,
.identity-copy span {
  display: block;
}

.identity-copy strong {
  color: #1f2b3d;
  font-size: 22px;
}

.identity-copy > span {
  margin-top: 6px;
  color: #6f8096;
}

.identity-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.info-list {
  margin: 18px 0 0;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 1px solid rgba(224, 233, 242, 0.86);
}

.info-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.info-row dt {
  color: #8190a4;
}

.info-row dd {
  margin: 0;
  color: #1f2b3d;
  font-weight: 600;
  text-align: right;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.status-card {
  min-height: 128px;
  padding: 18px;
  border-radius: 20px;
  background: #f8fbfe;
  border: 1px solid rgba(214, 226, 238, 0.9);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-card.alert {
  background: linear-gradient(135deg, #fff7ed, #fffbf4);
  border-color: rgba(246, 197, 125, 0.9);
}

.status-card span {
  color: #7f8da2;
  font-size: 13px;
}

.status-card strong {
  color: #1f2b3d;
  font-size: 22px;
  line-height: 1.15;
}

.status-card small {
  color: #67778d;
  line-height: 1.6;
}

.capability-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.capability-item {
  min-height: 120px;
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(135deg, #fff7f7, #fffdfd);
  border: 1px solid rgba(238, 209, 209, 0.95);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
}

.capability-item.done {
  background: linear-gradient(135deg, #f1fbf4, #f8fffd);
  border-color: rgba(188, 228, 201, 0.95);
}

.capability-item strong {
  color: #1f2b3d;
  font-size: 16px;
  line-height: 1.5;
}

.capability-item span {
  color: #66758a;
  font-size: 14px;
}

@media (max-width: 1080px) {
  .grid,
  .capability-list,
  .status-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .hero-card,
  .panel {
    padding: 20px;
  }

  .hero-card {
    flex-direction: column;
  }

  .hero-card h1 {
    font-size: 28px;
  }
}
</style>
