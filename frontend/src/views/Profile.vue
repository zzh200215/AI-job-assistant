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
        <el-tag v-if="subTier === 'pro'" type="success" effect="dark">Pro 会员</el-tag>
        <el-tag v-else-if="subTier === 'enterprise'" type="warning" effect="dark">企业版</el-tag>
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
              <dd>{{ dateTime(authStore.user?.created_at, '--') }}</dd>
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
              <small>{{
                status.demo_mode ? '仍有 mock 依赖，适合演示和联调。' : '核心依赖已切到真实模式。'
              }}</small>
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

    <!-- 求职成就里程碑 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-warning)"><Trophy /></el-icon>
          <h3>求职成就里程碑</h3>
        </div>
        <span class="panel-tip"
          >{{ achievements.filter((a) => a.unlocked).length }}/{{
            achievements.length
          }}
          已解锁</span
        >
      </div>
      <div class="panel-body">
        <div class="achievement-grid">
          <div
            v-for="badge in achievements"
            :key="badge.id"
            class="achievement-card"
            :class="{ unlocked: badge.unlocked, locked: !badge.unlocked }"
          >
            <div class="ach-icon" :class="'ach-' + badge.color">
              <el-icon :size="22"><component :is="badge.icon" /></el-icon>
            </div>
            <div class="ach-info">
              <strong>{{ badge.name }}</strong>
              <span>{{ badge.desc }}</span>
            </div>
            <el-tag v-if="badge.unlocked" size="small" type="success" effect="dark">已达成</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">未解锁</el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- 个人数据看板 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-primary)"><DataAnalysis /></el-icon>
          <h3>个人求职数据</h3>
        </div>
        <span class="panel-tip">基于投递和面试记录统计</span>
      </div>
      <div class="panel-body">
        <div v-if="statsLoading" class="empty-inline">
          <el-icon class="is-loading"><Loading /></el-icon> 加载中...
        </div>
        <div v-else class="stats-dashboard">
          <div class="stats-grid">
            <div class="stat-card-v">
              <span class="stat-label">投递总数</span
              ><strong class="stat-num">{{ userStats.total_applications }}</strong>
            </div>
            <div class="stat-card-v">
              <span class="stat-label">面试次数</span
              ><strong class="stat-num stat-interview">{{ userStats.total_interviews }}</strong>
            </div>
            <div class="stat-card-v">
              <span class="stat-label">Offer数</span
              ><strong class="stat-num stat-offer">{{ userStats.total_offers }}</strong>
            </div>
            <div class="stat-card-v">
              <span class="stat-label">面试转化率</span
              ><strong class="stat-num">{{ userStats.interview_rate }}%</strong>
            </div>
            <div class="stat-card-v">
              <span class="stat-label">Offer率</span
              ><strong class="stat-num stat-offer">{{ userStats.offer_rate }}%</strong>
            </div>
            <div class="stat-card-v">
              <span class="stat-label">简历数</span
              ><strong class="stat-num">{{ userStats.resume_count }}</strong>
            </div>
          </div>
          <div class="stats-footer">
            <span
              >已使用 {{ userStats.days_active }} 天 ·
              {{ userStats.total_sessions }} 次模拟面试</span
            >
          </div>
        </div>
      </div>
    </div>

    <!-- 每日任务 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-success)"><List /></el-icon>
          <h3>今日求职任务</h3>
        </div>
        <el-tag
          size="small"
          :type="
            dailyTasks.filter((t) => t.done).length === dailyTasks.length ? 'success' : 'warning'
          "
        >
          {{ dailyTasks.filter((t) => t.done).length }}/{{ dailyTasks.length }}
        </el-tag>
      </div>
      <div class="panel-body">
        <div class="daily-task-list">
          <div v-for="task in dailyTasks" :key="task.id" class="daily-task-item">
            <el-checkbox v-model="task.done" @change="onTaskChange">
              <span :class="{ 'task-done-text': task.done }">{{ task.text }}</span>
            </el-checkbox>
            <el-tag v-if="task.bonus" size="small" type="warning" effect="plain"
              >+{{ task.bonus }} 积分</el-tag
            >
          </div>
        </div>
      </div>
    </div>

    <!-- 邀请好友 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-warning)"><Share /></el-icon>
          <h3>邀请好友</h3>
        </div>
      </div>
      <div class="panel-body">
        <div class="invite-body">
          <p class="invite-desc">邀请好友使用 Career Signal，双方均可获得额外权益</p>
          <div class="invite-link-row">
            <el-input v-model="inviteLink" readonly>
              <template #append>
                <el-button @click="copyInviteLink">复制邀请链接</el-button>
              </template>
            </el-input>
          </div>
          <div class="invite-stats">
            <div class="invite-stat">
              <strong>{{ inviteCount }}</strong
              ><span>已邀请</span>
            </div>
            <div class="invite-stat">
              <strong>+{{ inviteBonus }}</strong
              ><span>累计奖励</span>
            </div>
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
              <el-tag v-if="authStore.user?.email_verified" type="success" size="small"
                >已验证</el-tag
              >
              <el-button
                v-else
                size="small"
                type="primary"
                @click="verifyEmail"
                :loading="verifying"
                >发送验证邮件</el-button
              >
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
              <el-switch
                v-model="privacySettings.resumePublic"
                active-text="简历公开"
                @change="savePrivacy"
              />
              <el-switch
                v-model="privacySettings.allowRecommend"
                active-text="允许推荐"
                @change="savePrivacy"
              />
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
import { getDashboardOverview } from '@/api/dashboard'
import { getMySubscription } from '@/api/subscription'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'
import {
  DataAnalysis,
  List,
  Share,
  Trophy,
  UploadFilled,
  Aim,
  ChatDotRound,
  Coin,
  Grid,
  Star,
  Microphone,
} from '@element-plus/icons-vue'
import { dateTime } from '@/utils/format/date'

const authStore = useAuthStore()
const loading = ref(false)
const verifying = ref(false)
const exporting = ref(false)
// 邀请
const inviteLink = ref('')
const inviteCount = ref(0)
const inviteBonus = ref(0)

function generateInviteLink() {
  const baseUrl = window.location.origin
  const userId = authStore.user?.id || ''
  inviteLink.value = baseUrl + '/register?ref=' + userId
  inviteCount.value = Number(localStorage.getItem('recruit.inviteCount') || 0)
  inviteBonus.value = inviteCount.value * 50
}

async function copyInviteLink() {
  if (!inviteLink.value) generateInviteLink()
  try {
    await navigator.clipboard.writeText(inviteLink.value)
    const count = inviteCount.value + 1
    inviteCount.value = count
    inviteBonus.value = count * 50
    localStorage.setItem('recruit.inviteCount', String(count))
    ElMessage.success('邀请链接已复制！')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

const privacySettings = reactive({
  resumePublic: true,
  allowRecommend: true,
})

// 订阅状态
const subTier = ref('free')
const subQuota = ref([])
const subEndAt = ref(null)

async function loadSubscription() {
  try {
    const data = await getMySubscription()
    if (data) {
      subTier.value = data.tier || 'free'
      subQuota.value = data.quota || []
      subEndAt.value = data.end_at
    }
  } catch {
    // 订阅信息暂不可用时保留免费版默认状态。
  }
}

// 成就系统
const achievements = computed(() => {
  const s = userStats.value
  return [
    {
      id: 'resume',
      name: '简历初成',
      desc: '上传第一份简历',
      icon: UploadFilled,
      color: 'blue',
      unlocked: s.resume_count >= 1,
    },
    {
      id: 'apply',
      name: '初出茅庐',
      desc: '完成首次投递',
      icon: Aim,
      color: 'violet',
      unlocked: s.total_applications >= 1,
    },
    {
      id: 'apply10',
      name: '积极求职',
      desc: '投递10个岗位',
      icon: Grid,
      color: 'amber',
      unlocked: s.total_applications >= 10,
    },
    {
      id: 'interview',
      name: '面试首秀',
      desc: '完成首次面试',
      icon: Microphone,
      color: 'green',
      unlocked: s.total_interviews >= 1,
    },
    {
      id: 'interview5',
      name: '面霸进阶',
      desc: '完成5场面试',
      icon: ChatDotRound,
      color: 'teal',
      unlocked: s.total_interviews >= 5,
    },
    {
      id: 'offer',
      name: '首份Offer',
      desc: '获得首个Offer',
      icon: Coin,
      color: 'success',
      unlocked: s.total_offers >= 1,
    },
    {
      id: 'offer3',
      name: 'Offer收割机',
      desc: '获得3个Offer',
      icon: Trophy,
      color: 'gold',
      unlocked: s.total_offers >= 3,
    },
    {
      id: 'stars',
      name: '面试之星',
      desc: '综合评分超过80',
      icon: Star,
      color: 'red',
      unlocked: s.best_score >= 80,
    },
  ]
})

// 用户统计数据
const statsLoading = ref(false)
const userStats = ref({
  total_applications: 0,
  total_interviews: 0,
  total_offers: 0,
  total_sessions: 0,
  resume_count: 0,
  best_score: 0,
  days_active: 1,
  interview_rate: 0,
  offer_rate: 0,
})

async function loadUserStats() {
  statsLoading.value = true
  try {
    const data = await getDashboardOverview()
    const funnel = data?.funnel || {}
    const totalApps =
      (funnel.todo || 0) +
      (funnel.applied || 0) +
      (funnel.written_test || 0) +
      (funnel.interview || 0) +
      (funnel.offer || 0)
    const totalInt = (funnel.interview || 0) + (funnel.offer || 0)
    const totalOff = funnel.offer || 0
    userStats.value = {
      total_applications: totalApps,
      total_interviews: totalInt,
      total_offers: totalOff,
      total_sessions: data?.total_sessions || data?.sessions || 0,
      resume_count: data?.resume_count || 0,
      best_score: data?.best_score || data?.max_score || 0,
      days_active:
        data?.days_active ||
        Math.ceil((Date.now() - new Date(data?.created_at || Date.now()).getTime()) / 86400000) ||
        1,
      interview_rate: totalApps > 0 ? Math.round((totalInt / totalApps) * 100) : 0,
      offer_rate: totalInt > 0 ? Math.round((totalOff / totalInt) * 100) : 0,
    }
  } catch {
    // 统计信息不可用时保留默认计数。
  } finally {
    statsLoading.value = false
  }
}

// 每日任务
const dailyTasks = ref([
  { id: 1, text: '浏览今日岗位推荐', done: false, bonus: 10, link: '/jobs/recommend' },
  { id: 2, text: '检查投递看板跟进状态', done: false, bonus: 10, link: '/jobs/pipeline/kanban' },
  { id: 3, text: '完成一道面试练习题', done: false, bonus: 20, link: '/interview' },
  { id: 4, text: '查看求职周报数据', done: false, bonus: 5, link: '/weekly-report' },
  { id: 5, text: '检查是否有新消息', done: false, bonus: 5 },
])

const LS_TASKS_KEY = 'recruit.dailyTasks'
const LS_TASKS_DATE = 'recruit.dailyTasksDate'

function loadDailyTasks() {
  const saved = localStorage.getItem(LS_TASKS_KEY)
  const savedDate = localStorage.getItem(LS_TASKS_DATE)
  const today = new Date().toDateString()
  if (saved && savedDate === today) {
    try {
      dailyTasks.value = JSON.parse(saved)
      return
    } catch {
      // 本地任务缓存损坏时重置为当天的默认任务。
    }
  }
  dailyTasks.value.forEach((t) => {
    t.done = false
  })
  localStorage.setItem(LS_TASKS_DATE, today)
}

function onTaskChange() {
  localStorage.setItem(LS_TASKS_KEY, JSON.stringify(dailyTasks.value))
  const done = dailyTasks.value.filter((t) => t.done).length
  if (done === dailyTasks.value.length) {
    ElMessage.success('🎉 今日任务全部完成！')
  }
}
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
    await request.post('/auth/send-verification-email')
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
  } catch {
    // 用户取消注销或请求失败时保持登录状态。
  }
}

onMounted(async () => {
  try {
    await refreshAll()
    await loadUserStats()
    await loadSubscription()
    loadDailyTasks()
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

/* 成就系统 */
.achievement-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.achievement-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  transition: all 0.2s;
}

.achievement-card.unlocked {
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.achievement-card.locked {
  background: #f9fafb;
  border: 1px dashed #d1d5db;
  opacity: 0.6;
}

.ach-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.ach-blue {
  background: var(--app-primary-light);
  color: var(--app-primary);
}
.ach-violet {
  background: var(--app-violet-light);
  color: var(--app-violet);
}
.ach-amber {
  background: #fef5e7;
  color: var(--app-warning);
}
.ach-green {
  background: #e8f8ee;
  color: var(--app-success);
}
.ach-teal {
  background: #e6fffa;
  color: #0d9488;
}
.ach-success {
  background: #d1fae5;
  color: #059669;
}
.ach-gold {
  background: #fef3c7;
  color: #d97706;
}
.ach-red {
  background: #fce4ec;
  color: #e53935;
}

.ach-info {
  flex: 1;
  min-width: 0;
}
.ach-info strong {
  display: block;
  font-size: 14px;
}
.ach-info span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
  margin-top: 2px;
}

/* 数据看板 */
.stats-dashboard {
  padding: 4px 0;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.stat-card-v {
  text-align: center;
  padding: 16px 12px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.stat-num {
  display: block;
  font-size: 28px;
  font-weight: 800;
  color: var(--app-primary);
  margin-top: 6px;
}

.stat-interview {
  color: var(--app-violet) !important;
}
.stat-offer {
  color: var(--app-success) !important;
}

.stats-footer {
  text-align: center;
  margin-top: 16px;
  font-size: 12px;
  color: var(--app-muted);
}

/* 邀请 */
.invite-body {
  padding: 8px 0;
}
.invite-desc {
  font-size: 14px;
  color: var(--app-muted);
  margin: 0 0 14px;
}
.invite-link-row {
  display: flex;
  gap: 8px;
}
.invite-stats {
  display: flex;
  gap: 24px;
  margin-top: 16px;
}
.invite-stat {
  text-align: center;
}
.invite-stat strong {
  display: block;
  font-size: 22px;
  font-weight: 800;
  color: var(--app-primary);
}
.invite-stat span {
  font-size: 12px;
  color: var(--app-muted);
} /* 每日任务 */
.daily-task-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.daily-task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--app-line);
  transition: background 0.15s;
}

.daily-task-item:hover {
  background: var(--app-bg);
}

.task-done-text {
  text-decoration: line-through;
  color: var(--app-muted);
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
