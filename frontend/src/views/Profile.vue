<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="eyebrow">Account</p>
        <h2>个人中心</h2>
        <div class="page-header-sub">统一查看当前账号身份、系统运行模式和交付能力状态。</div>
      </div>
      <div class="hero-badges">
        <span>{{ authStore.roleLabel }}</span>
        <span>{{ status.demo_mode ? 'Demo Mode' : 'Live Mode' }}</span>
      </div>
    </header>

    <section class="grid">
      <div class="panel identity-panel">
        <div class="panel-header">
          <h3>账号信息</h3>
          <el-button text @click="refreshAll" :loading="loading">刷新</el-button>
        </div>
        <div class="panel-body">
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
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3>系统模式</h3>
          <span class="panel-tip">运行时状态</span>
        </div>
        <div class="panel-body">
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
        </div>
      </div>
    </section>

    <div class="panel capability-panel">
      <div class="panel-header">
        <h3>能力状态</h3>
        <span class="panel-tip">按交付闭环检查</span>
      </div>
      <div class="panel-body">
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
      </div>
    </div>

    <!-- 账号安全与隐私 -->
    <div class="panel">
      <div class="panel-header">
        <h3>账号安全与隐私</h3>
      </div>
      <div class="panel-body">
        <div class="settings-list">
          <div class="setting-row">
            <div class="setting-info">
              <strong>邮箱验证</strong>
              <span>验证邮箱以提高账号安全性</span>
            </div>
            <div class="setting-action">
              <el-tag v-if="authStore.user?.email_verified" type="success" size="small">已验证</el-tag>
              <el-button v-else size="small" type="primary" @click="verifyEmail" :loading="verifying">发送验证邮件</el-button>
            </div>
          </div>
          <div class="setting-row">
            <div class="setting-info">
              <strong>修改密码</strong>
              <span>定期更换密码保障账号安全</span>
            </div>
            <div class="setting-action">
              <el-button size="small" @click="$router.push('/reset-password')">修改密码</el-button>
            </div>
          </div>
          <div class="setting-row">
            <div class="setting-info">
              <strong>数据导出</strong>
              <span>导出您的所有数据（简历、投递记录、面试记录等）</span>
            </div>
            <div class="setting-action">
              <el-button size="small" @click="exportData" :loading="exporting">导出数据</el-button>
            </div>
          </div>
          <div class="setting-row">
            <div class="setting-info">
              <strong>隐私设置</strong>
              <span>控制简历和数据的可见范围</span>
            </div>
            <div class="setting-action">
              <el-switch v-model="privacySettings.resumePublic" active-text="简历公开" @change="savePrivacy" />
              <el-switch v-model="privacySettings.allowRecommend" active-text="允许推荐" @change="savePrivacy" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 危险操作 -->
    <div class="panel danger-zone">
      <div class="panel-header">
        <h3>危险操作</h3>
        <span class="panel-tip danger-tip">以下操作不可逆</span>
      </div>
      <div class="panel-body">
        <div class="danger-content">
          <div class="danger-row">
            <div>
              <strong>注销账号</strong>
              <p>永久删除账号和所有数据，此操作不可恢复</p>
            </div>
            <el-button type="danger" plain @click="deleteAccount">注销账号</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { getSystemStatus } from '@/api/system'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'

const authStore = useAuthStore()
const loading = ref(false)
const verifying = ref(false)
const exporting = ref(false)
const privacySettings = reactive({
  resumePublic: true,
  allowRecommend: true,
})
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

async function verifyEmail() {
  verifying.value = true
  try {
    await request.post('/auth/send-verify-email')
    ElMessage.success('验证邮件已发送，请查收')
  } catch {
    ElMessage.error('发送失败')
  } finally {
    verifying.value = false
  }
}

async function exportData() {
  exporting.value = true
  try {
    const res = await request.get('/auth/export-data', { responseType: 'blob' })
    const url = window.URL.createObjectURL(res)
    const a = document.createElement('a')
    a.href = url
    a.download = `my_data_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('数据导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

function savePrivacy() {
  localStorage.setItem('recruit.privacy', JSON.stringify(privacySettings))
  ElMessage.success('隐私设置已保存')
}

async function deleteAccount() {
  try {
    await ElMessageBox.confirm(
      '此操作将永久删除您的账号和所有数据，不可恢复！确定继续？',
      '注销账号',
      { confirmButtonText: '确定注销', cancelButtonText: '取消', type: 'error' }
    )
    await ElMessageBox.prompt('请输入"确认注销"以继续', '最终确认', {
      confirmButtonText: '注销',
      cancelButtonText: '取消',
      inputPattern: /确认注销/,
      inputErrorMessage: '请输入"确认注销"',
    })
    await request.delete('/auth/account')
    ElMessage.success('账号已注销')
    authStore.logout()
  } catch {}
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
.page-shell {
  display: grid;
  gap: 18px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 28px;
  background:
    radial-gradient(circle at top right, rgba(114, 187, 143, 0.18), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(245, 250, 246, 0.94));
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md, 16px);
  box-shadow: 0 16px 32px rgba(145, 176, 193, 0.12);
  backdrop-filter: blur(10px);
}

.eyebrow {
  margin: 0 0 10px;
  color: var(--app-muted);
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.page-header h2 {
  margin: 0;
  color: var(--app-text);
  font-size: 34px;
  line-height: 1.05;
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

.identity-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px;
  border-radius: var(--app-radius-md, 16px);
  background: linear-gradient(135deg, #f4fbf6, #faf7ef);
  border: 1px solid var(--app-line);
}

.avatar {
  width: 58px;
  height: 58px;
  border-radius: var(--app-radius-sm, 12px);
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
  color: var(--app-text);
  font-size: 22px;
}

.identity-copy > span {
  margin-top: 6px;
  color: var(--app-muted);
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
  border-bottom: 1px solid var(--app-line);
}

.info-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.info-row dt {
  color: var(--app-muted);
}

.info-row dd {
  margin: 0;
  color: var(--app-text);
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
  border-radius: var(--app-radius-md, 16px);
  background: #f8fbfe;
  border: 1px solid var(--app-line);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-card.alert {
  background: linear-gradient(135deg, #fff7ed, #fffbf4);
  border-color: var(--app-line);
}

.status-card span {
  color: var(--app-muted);
  font-size: 13px;
}

.status-card strong {
  color: var(--app-text);
  font-size: 22px;
  line-height: 1.15;
}

.status-card small {
  color: var(--app-muted);
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
  border-radius: var(--app-radius-md, 16px);
  background: linear-gradient(135deg, #fff7f7, #fffdfd);
  border: 1px solid var(--app-line);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
}

.capability-item.done {
  background: linear-gradient(135deg, #f1fbf4, #f8fffd);
  border-color: var(--app-line);
}

.capability-item strong {
  color: var(--app-text);
  font-size: 16px;
  line-height: 1.5;
}

.capability-item span {
  color: var(--app-muted);
  font-size: 14px;
}

/* Settings list */
.settings-list {
  display: flex;
  flex-direction: column;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  border-bottom: 1px solid var(--app-line);
  gap: 16px;
}

.setting-row:last-child {
  border-bottom: none;
}

.setting-info strong {
  display: block;
  font-size: 15px;
  color: var(--app-text);
}

.setting-info span {
  font-size: 13px;
  color: var(--app-muted);
}

.setting-action {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

/* Danger zone */
.danger-zone {
  border-color: rgba(238, 180, 180, 0.9) !important;
}

.danger-tip {
  color: var(--app-danger) !important;
}

.danger-content {
  padding: 0;
}

.danger-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.danger-row strong {
  display: block;
  font-size: 15px;
  color: var(--app-danger);
}

.danger-row p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--app-muted);
}

@media (max-width: 1080px) {
  .grid,
  .capability-list,
  .status-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .page-header,
  .panel {
    padding: 20px;
  }

  .page-header {
    flex-direction: column;
  }

  .page-header h2 {
    font-size: 28px;
  }
}
</style>
