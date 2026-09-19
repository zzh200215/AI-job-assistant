<template>
  <div class="dashboard-page">
    <!-- 顶部欢迎栏 -->
    <section class="welcome-bar">
      <div class="welcome-left">
        <div class="signal-kicker"><span class="signal-dot" /> CAREER SIGNAL / LIVE WORKSPACE</div>
        <h1><span>今天，</span><em>推进一份机会</em></h1>
        <p class="welcome-sub">
          {{ greeting }}，{{ username }}。{{
            overviewLoaded ? `当前有 ${dashSummary.active_applications || 0} 个活跃投递` : '加载中...'
          }}
        </p>
      </div>
      <div class="welcome-actions">
        <el-button type="primary" @click="go('/jobs/pipeline/kanban')">
          <el-icon><Grid /></el-icon> 打开投递看板
        </el-button>
        <el-button @click="go('/smart-analysis')">
          <el-icon><MagicStick /></el-icon> 开始智能分析
        </el-button>
      </div>
      <div class="signal-stats" aria-label="求职关键指标">
        <div>
          <strong>{{ overviewLoaded ? dashSummary.active_applications || 0 : '--' }}</strong>
          <span>活跃投递</span>
        </div>
        <div>
          <strong>{{ overviewLoaded ? overview.weekly_new || 0 : '--' }}</strong>
          <span>本周新增</span>
        </div>
        <div>
          <strong>{{ interviewRate }}</strong>
          <span>面试转化</span>
        </div>
      </div>
    </section>

    <el-alert
      v-if="overviewError"
      class="dashboard-error"
      type="warning"
      :closable="false"
      show-icon
      title="求职概览加载失败"
      description="其他工作台功能仍可使用。请检查网络连接后重新加载概览数据。"
    >
      <template #default>
        <el-button size="small" type="primary" plain @click="loadDashboard">重新加载</el-button>
      </template>
    </el-alert>

    <!-- 核心功能入口 -->
    <section class="core-entrance-row">
      <div class="core-card core-resume" @click="go('/resume-center')">
        <div class="core-icon">
          <el-icon :size="32"><Document /></el-icon>
        </div>
        <div class="core-info">
          <h3>简历中心</h3>
          <p>管理、优化、诊断多份简历</p>
          <span class="core-meta">{{
            overviewLoaded ? (dashSummary.total_resumes || '--') + ' 份简历' : '加载中...'
          }}</span>
        </div>
        <el-icon class="core-arrow"><ArrowRight /></el-icon>
      </div>
      <div class="core-card core-job" @click="go('/jobs/recommend')">
        <div class="core-icon">
          <el-icon :size="32"><Search /></el-icon>
        </div>
        <div class="core-info">
          <h3>岗位推荐</h3>
          <p>智能匹配每日高匹配岗位</p>
          <span class="core-meta">{{
            overviewLoaded ? (dashSummary.bookmarked_jobs || '--') + ' 个收藏岗位' : '加载中...'
          }}</span>
        </div>
        <el-icon class="core-arrow"><ArrowRight /></el-icon>
      </div>
      <div class="core-card core-interview" @click="go('/interview/setup')">
        <div class="core-icon">
          <el-icon :size="32"><Microphone /></el-icon>
        </div>
        <div class="core-info">
          <h3>AI 模拟面试</h3>
          <p>针对性面试训练、能力评估</p>
          <span class="core-meta">{{
            overviewLoaded ? (dashSummary.total_interviews || '--') + ' 次面试' : '加载中...'
          }}</span>
        </div>
        <el-icon class="core-arrow"><ArrowRight /></el-icon>
      </div>
    </section>

    <!-- 今日待办 + 下一步建议 -->
    <section class="top-row">
      <div class="panel today-panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-primary)"><Bell /></el-icon>
            <h3>今日待办</h3>
          </div>
          <el-badge v-if="tasks.high_priority > 0" :value="tasks.high_priority" type="danger" />
        </div>
        <div class="panel-body">
          <div v-if="tasksLoading" class="loading-state">
            <el-icon class="is-loading"><Loading /></el-icon> 加载中...
          </div>
          <div v-else-if="tasksError" class="error-state">
            <p>今日待办加载失败</p>
            <el-button size="small" type="primary" plain @click="loadDashboard">重新加载</el-button>
          </div>
          <div v-else-if="!tasks.tasks?.length" class="empty-state">
            <p>今日暂无待办</p>
            <span>建议浏览推荐岗位或跟进已有投递</span>
            <div class="empty-actions">
              <el-button size="small" type="primary" @click="go('/jobs/recommend')">
                查看推荐岗位
              </el-button>
              <el-button size="small" @click="go('/jobs/pipeline/kanban')">
                查看投递看板
              </el-button>
            </div>
          </div>
          <div v-else class="task-list">
            <div
              v-for="task in tasks.tasks"
              :key="task.title"
              class="task-item"
              :class="'priority-' + task.priority"
              @click="go(task.link)"
            >
              <div class="task-dot" :class="'dot-' + task.priority" />
              <div class="task-info">
                <strong>{{ task.title }}</strong>
                <span>{{ task.subtitle }}</span>
              </div>
              <el-icon class="task-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>

      <div class="panel actions-panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-violet)"><MagicStick /></el-icon>
            <h3>下一步建议</h3>
          </div>
          <el-tag size="small" type="info">智能推荐</el-tag>
        </div>
        <div class="panel-body">
          <div v-if="actionsLoading" class="loading-state">
            <el-icon class="is-loading"><Loading /></el-icon> 分析中...
          </div>
          <div v-else-if="actionsError" class="error-state">
            <p>当前没有明确的下一步动作，说明近期节奏正常。</p>
            <el-button size="small" type="primary" plain @click="loadDashboard">重新加载</el-button>
          </div>
          <div v-else class="suggestion-list">
            <div
              v-for="(sug, idx) in nextActions"
              :key="idx"
              class="suggestion-item"
              @click="go(sug.link)"
            >
              <div class="sug-index">{{ idx + 1 }}</div>
              <div class="sug-body">
                <strong>{{ sug.title }}</strong>
                <p>{{ sug.description }}</p>
              </div>
              <el-icon class="sug-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 求职漏斗 + 关键指标 -->
    <section class="middle-row">
      <div class="panel funnel-panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-primary)"><TrendCharts /></el-icon>
            <h3>求职漏斗</h3>
          </div>
        </div>
        <div class="panel-body">
          <div v-if="overviewLoaded" class="funnel-bar">
            <div
              v-for="stage in funnelStages"
              :key="stage.key"
              class="funnel-step"
              :class="{ 'has-count': stage.count > 0 }"
            >
              <div class="funnel-bar-fill" :style="{ height: funnelBarHeight(stage.count) }" />
              <div class="funnel-count">{{ stage.count }}</div>
              <div class="funnel-label">{{ stage.label }}</div>
            </div>
          </div>
          <div v-else class="loading-state">
            <el-icon class="is-loading"><Loading /></el-icon>
          </div>
        </div>
      </div>

      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-icon blue">
            <el-icon><Document /></el-icon>
          </div>
          <div class="metric-body">
            <span class="metric-label">本周投递</span>
            <strong class="data-value">{{ overviewLoaded ? overview.weekly_new : '-' }}</strong>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon amber">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <div class="metric-body">
            <span class="metric-label">面试率</span>
            <strong class="data-value">{{ interviewRate }}</strong>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon violet">
            <el-icon><Histogram /></el-icon>
          </div>
          <div class="metric-body">
            <span class="metric-label">平均匹配</span>
            <strong class="data-value">{{
              overviewLoaded ? (dashSummary.avg_match_score ?? '--') : '-'
            }}</strong>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon green">
            <el-icon><Trophy /></el-icon>
          </div>
          <div class="metric-body">
            <span class="metric-label">Offer 数</span>
            <strong class="data-value">{{
              overviewLoaded ? dashSummary.pending_offers || 0 : '-'
            }}</strong>
          </div>
        </div>
      </div>
    </section>

    <!-- 投递趋势 + 快捷入口 -->
    <section class="bottom-row">
      <div class="panel trend-panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-success)"><TrendCharts /></el-icon>
            <h3>7日投递趋势</h3>
          </div>
        </div>
        <div class="panel-body">
          <div v-if="overviewLoaded" class="trend-chart">
            <div v-for="(day, idx) in overview.trend" :key="idx" class="trend-bar-col">
              <div class="trend-bar" :style="{ height: trendHeight(day.count) }" />
              <span class="trend-count">{{ day.count }}</span>
              <span class="trend-date">{{ day.date.slice(5) }}</span>
            </div>
          </div>
          <div v-else class="loading-state">
            <el-icon class="is-loading"><Loading /></el-icon>
          </div>
        </div>
      </div>

      <div class="quick-entry-panel">
        <h3>快捷入口</h3>
        <div class="quick-grid">
          <button class="quick-btn" @click="go('/jobs/pipeline/kanban')">
            <div class="quick-icon blue">
              <el-icon><Grid /></el-icon>
            </div>
            <span>投递看板</span>
          </button>
          <button class="quick-btn" @click="go('/jobs/recommend')">
            <div class="quick-icon amber">
              <el-icon><Search /></el-icon>
            </div>
            <span>岗位推荐</span>
          </button>
          <button class="quick-btn" @click="go('/resume-center')">
            <div class="quick-icon violet">
              <el-icon><Document /></el-icon>
            </div>
            <span>简历中心</span>
          </button>
          <button class="quick-btn" @click="go('/interview/setup')">
            <div class="quick-icon green">
              <el-icon><Microphone /></el-icon>
            </div>
            <span>模拟面试</span>
          </button>
          <button class="quick-btn" @click="go('/targets')">
            <div class="quick-icon teal">
              <el-icon><Aim /></el-icon>
            </div>
            <span>求职目标</span>
          </button>
          <button class="quick-btn" @click="go('/salary')">
            <div class="quick-icon red">
              <el-icon><Coin /></el-icon>
            </div>
            <span>薪资洞察</span>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Aim,
  Bell,
  ChatDotRound,
  Coin,
  Document,
  Grid,
  Histogram,
  Loading,
  MagicStick,
  Microphone,
  Search,
  Trophy,
  TrendCharts,
} from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'
import { getDashboardOverview, getTodayTasks, getNextActions } from '@/api/dashboard'

const router = useRouter()
const authStore = useAuthStore()
const go = (path) => router.push(path)

const username = computed(() => authStore.user?.nickname || authStore.user?.username || '求职者')

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

// ---- 数据 ----
const overview = ref({})
const overviewLoaded = ref(false)
const overviewError = ref(false)
const tasks = ref({ tasks: [], high_priority: 0 })
const tasksLoading = ref(true)
const tasksError = ref(false)
const nextActions = ref([])
const actionsLoading = ref(true)
const actionsError = ref(false)

// 后端关键指标统一放在 data.summary 下（total_resumes/active_applications 等），
// 模板统一经 dashSummary 读取，避免读顶层字段永远 0/--。
const dashSummary = computed(() => overview.value.summary || overview.value)

const interviewRate = computed(() => {
  if (!overviewLoaded.value) return '-'
  const summary = overview.value.summary || overview.value
  const total = summary.total_applications || 0
  const interviews = overview.value.stage_counts?.interview || 0
  const offers = overview.value.stage_counts?.offer || 0
  const accepted = overview.value.stage_counts?.accepted || 0
  const hit = interviews + offers + accepted
  return total > 0 ? Math.round((hit / total) * 100) + '%' : '--'
})

const funnelStages = computed(() => {
  if (!overviewLoaded.value) return []
  const f = overview.value.funnel || {}
  return [
    { key: 'todo', label: '待投递', count: f.todo || 0 },
    { key: 'applied', label: '已投递', count: f.applied || 0 },
    { key: 'written_test', label: '笔试', count: f.written_test || 0 },
    { key: 'interview', label: '面试', count: f.interview || 0 },
    { key: 'offer', label: 'Offer', count: f.offer || 0 },
  ]
})

const maxFunnel = computed(() => {
  return Math.max(1, ...funnelStages.value.map((s) => s.count))
})

const maxTrend = computed(() => {
  if (!overviewLoaded.value) return 1
  return Math.max(1, ...(overview.value.trend || []).map((d) => d.count))
})

function funnelBarHeight(count) {
  return Math.max(4, (count / maxFunnel.value) * 100) + '%'
}

function trendHeight(count) {
  return Math.max(4, (count / maxTrend.value) * 100) + '%'
}

async function loadDashboard() {
  overviewError.value = false
  tasksError.value = false
  actionsError.value = false
  tasksLoading.value = true
  actionsLoading.value = true
  try {
    const [ov, tk, actions] = await Promise.allSettled([
      getDashboardOverview(),
      getTodayTasks(),
      getNextActions(),
    ])
    if (ov.status === 'fulfilled') {
      overview.value = ov.value
      overviewLoaded.value = true
    } else {
      overviewError.value = true
    }
    if (tk.status === 'fulfilled') {
      tasks.value = tk.value
    } else {
      tasksError.value = true
    }
    if (actions.status === 'fulfilled') {
      nextActions.value = actions.value?.suggestions || []
    } else {
      actionsError.value = true
    }
  } finally {
    tasksLoading.value = false
    actionsLoading.value = false
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.dashboard-page {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: calc(100vh - 76px);
  margin: -20px -24px -24px;
  padding: 32px;
  background:
    radial-gradient(circle at 88% 4%, rgba(124, 58, 237, 0.2), transparent 30%),
    radial-gradient(circle at 5% 100%, rgba(34, 184, 232, 0.1), transparent 32%), #0d0e14;
  color: #f4f5f8;
}

/* ===== Welcome Bar ===== */
.welcome-bar {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 196px;
  padding: 30px 32px;
  overflow: hidden;
  border: 1px solid #2b2d3a;
  border-radius: 12px;
  background: linear-gradient(110deg, #151620 0%, #171825 60%, #211842 100%);
  color: #f8f8fb;
}

.welcome-bar::after {
  position: absolute;
  right: -68px;
  bottom: -90px;
  z-index: -1;
  width: 290px;
  height: 290px;
  border: 1px solid rgba(110, 231, 255, 0.19);
  border-radius: 50%;
  box-shadow:
    0 0 0 42px rgba(124, 58, 237, 0.07),
    0 0 0 86px rgba(34, 184, 232, 0.04);
  content: '';
}

.welcome-left {
  position: relative;
  z-index: 1;
  max-width: 560px;
}

.signal-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 11px;
  color: #a7a9ba;
  font-family: var(--app-font-mono);
  font-size: 11px;
  font-weight: 500;
}

.signal-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 12px rgba(34, 197, 94, 0.8);
}

.welcome-bar h1 {
  margin: 0;
  font-size: 35px;
  line-height: 1.16;
  font-weight: 800;
  letter-spacing: 0;
}

.welcome-bar h1 span {
  color: #f3f4f6;
}

.welcome-bar h1 em {
  margin-left: 8px;
  color: #22b8e8;
  font-style: normal;
}

.welcome-sub {
  margin: 10px 0 0;
  color: #a7a9ba;
  font-size: 14px;
}

.welcome-actions {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 10px;
  align-self: flex-end;
}

.welcome-actions .el-button {
  min-height: 40px;
  border-radius: 8px;
  font-size: 13px;
}

.welcome-actions :deep(.el-button--primary) {
  background: #7c3aed;
  box-shadow: 0 8px 20px rgba(124, 58, 237, 0.28);
}

.welcome-actions .el-button--default {
  background: rgba(255, 255, 255, 0.04);
  border-color: #3a3c4b;
  color: #e8e9f0;
}

.welcome-actions .el-button--default:hover {
  background: rgba(255, 255, 255, 0.1);
}

.signal-stats {
  position: absolute;
  right: 32px;
  bottom: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(96px, 1fr));
  overflow: hidden;
  border: 1px solid #303242;
  border-bottom: 0;
  border-radius: 10px 10px 0 0;
  background: rgba(11, 12, 18, 0.6);
}

.signal-stats div {
  display: grid;
  gap: 3px;
  padding: 12px 17px;
  border-right: 1px solid #303242;
}

.signal-stats div:last-child {
  border-right: 0;
}

.signal-stats strong {
  color: #f8f8fb;
  font-family: var(--app-font-mono);
  font-size: 19px;
  line-height: 1;
}

.signal-stats span {
  color: #8d90a1;
  font-size: 11px;
}

/* ===== Core Entrance Row ===== */
.core-entrance-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.core-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 24px;
  border-radius: 10px;
  border: 1px solid #2a2c38;
  background: #171922;
  box-shadow: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.core-card:hover {
  transform: translateY(-2px);
  border-color: #575a70;
  background: #1c1e29;
}

.core-resume:hover {
  border-color: var(--app-violet);
}
.core-job:hover {
  border-color: var(--app-warning);
}
.core-interview:hover {
  border-color: var(--app-success);
}

.core-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.core-resume .core-icon {
  background: var(--app-violet-light);
  color: var(--app-violet);
}
.core-job .core-icon {
  background: #fef5e7;
  color: var(--app-warning);
}
.core-interview .core-icon {
  background: #e8f8ee;
  color: var(--app-success);
}

.core-info {
  flex: 1;
  min-width: 0;
}

.core-info h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #f1f2f6;
}

.core-info p {
  margin: 4px 0 0;
  font-size: 13px;
  color: #989baa;
}

.core-meta {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #7f8293;
  opacity: 0.8;
}

.core-arrow {
  color: var(--app-muted);
  flex-shrink: 0;
  font-size: 16px;
}

/* ===== Responsive for core entrance ===== */
@media (max-width: 768px) {
  .core-entrance-row {
    grid-template-columns: 1fr;
  }
}

/* ===== Panels ===== */
/* panel, panel-header, panel-body, panel-title-row defined in panels.css */

.panel + .panel {
  margin-top: 16px;
}

.loading-state,
.empty-state,
.error-state {
  text-align: center;
  padding: 20px 0;
  color: var(--app-muted);
  font-size: 14px;
}

.dashboard-error {
  margin: 0;
}

.error-state p {
  margin: 0 0 10px;
}

.empty-state span {
  display: block;
  margin-top: 4px;
  font-size: 12px;
}

.empty-actions {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

/* ===== Top Row ===== */
.top-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

/* Task list */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}

.task-item:hover {
  background: var(--el-fill-color-light);
}

.task-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-high {
  background: var(--app-danger);
}
.dot-medium {
  background: var(--app-warning);
}
.dot-low {
  background: var(--app-success);
}

.task-info {
  flex: 1;
  min-width: 0;
}

.task-info strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
}

.task-info span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
  margin-top: 2px;
}

.task-arrow {
  color: var(--app-muted);
  flex-shrink: 0;
}

/* AI Suggestions */
.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--app-violet-light);
  cursor: pointer;
  transition: background 0.15s;
}

.suggestion-item:hover {
  background: #e4dbff;
}

.sug-index {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-violet);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.sug-body {
  flex: 1;
  min-width: 0;
}

.sug-body strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
}

.sug-body p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--app-muted);
  line-height: 1.5;
}

.sug-arrow {
  color: var(--app-muted);
  margin-top: 4px;
  flex-shrink: 0;
}

/* ===== Middle Row ===== */
.middle-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}

/* Funnel */
.funnel-bar {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 180px;
  padding: 0 10px;
}

.funnel-step {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  position: relative;
  height: 100%;
}

.funnel-bar-fill {
  width: 100%;
  border-radius: 8px 8px 0 0;
  background: linear-gradient(180deg, var(--app-primary) 0%, #7db0ee 100%);
  transition: height 0.4s ease;
  opacity: 0.3;
}

.funnel-step.has-count .funnel-bar-fill {
  opacity: 1;
}

.funnel-count {
  position: absolute;
  top: -24px;
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text);
  font-family: var(--app-font-mono);
}

.funnel-label {
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-muted);
  white-space: nowrap;
}

/* Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.metric-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 16px;
  border-radius: 14px;
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
}

.metric-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.metric-icon.blue {
  background: var(--app-primary-light);
  color: var(--app-primary);
}
.metric-icon.amber {
  background: #fef5e7;
  color: var(--app-warning);
}
.metric-icon.violet {
  background: var(--app-violet-light);
  color: var(--app-violet);
}
.metric-icon.green {
  background: #e8f8ee;
  color: var(--app-success);
}

.metric-label {
  display: block;
  font-size: 12px;
  color: #86899a;
}

.metric-body strong {
  display: block;
  margin-top: 4px;
  font-size: 22px;
  line-height: 1.1;
}

/* ===== Bottom Row ===== */
.bottom-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}

/* Trend */
.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 140px;
  padding: 0 6px;
}

.trend-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  position: relative;
}

.trend-bar {
  width: 100%;
  max-width: 36px;
  border-radius: 6px 6px 0 0;
  background: linear-gradient(180deg, var(--app-success) 0%, #6ee7a0 100%);
  transition: height 0.4s ease;
}

.trend-count {
  position: absolute;
  top: -20px;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text);
}

.trend-date {
  margin-top: 6px;
  font-size: 11px;
  color: var(--app-muted);
}

/* Quick entry */
.quick-entry-panel {
  background: var(--app-surface-strong);
  border-radius: 16px;
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
  padding: 20px;
}

.quick-entry-panel h3 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 700;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.quick-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 8px;
  border-radius: 12px;
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  cursor: pointer;
  transition: all 0.15s;
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text);
}

.quick-btn:hover {
  box-shadow: var(--app-shadow);
  transform: translateY(-1px);
  border-color: var(--app-primary-light);
}

.quick-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.quick-icon.blue {
  background: var(--app-primary-light);
  color: var(--app-primary);
}
.quick-icon.amber {
  background: #fef5e7;
  color: var(--app-warning);
}
.quick-icon.violet {
  background: var(--app-violet-light);
  color: var(--app-violet);
}
.quick-icon.green {
  background: #e8f8ee;
  color: var(--app-success);
}
.quick-icon.teal {
  background: #e6fffa;
  color: #0d9488;
}
.quick-icon.red {
  background: var(--app-accent-soft);
  color: var(--app-accent);
}

/* ===== Signal Deck Skin ===== */
.dashboard-page .panel,
.quick-entry-panel,
.metric-card {
  border-color: #2a2c38;
  background: #171922;
  box-shadow: none;
}

.dashboard-page .panel-header {
  border-bottom-color: #2a2c38;
}

.dashboard-page .panel-header h3,
.quick-entry-panel h3,
.dashboard-page .task-info strong,
.dashboard-page .sug-body strong {
  color: #f1f2f6;
}

.dashboard-page .panel-tip,
.dashboard-page .task-info span,
.dashboard-page .sug-body p,
.dashboard-page .metric-label,
.dashboard-page .funnel-label,
.dashboard-page .trend-date,
.dashboard-page .loading-state,
.dashboard-page .empty-state,
.dashboard-page .error-state {
  color: #8f92a3;
}

.dashboard-page .metric-body strong,
.dashboard-page .funnel-count,
.dashboard-page .trend-count {
  color: #f5f6fa;
}

.dashboard-page .task-item:hover {
  background: #20222f;
}

.dashboard-page .suggestion-item {
  border: 1px solid #2e3040;
  background: #1d1d2b;
}

.dashboard-page .suggestion-item:hover {
  background: #242237;
}

.dashboard-page .sug-index {
  background: #6d3ce8;
}

.dashboard-page .funnel-bar-fill {
  background: linear-gradient(180deg, #22b8e8 0%, #2563eb 100%);
}

.dashboard-page .trend-bar {
  background: linear-gradient(180deg, #31d39b 0%, #0f9f78 100%);
}

.dashboard-page .quick-btn {
  border-color: #2d2f3d;
  background: #1b1d28;
  color: #e7e8ee;
}

.dashboard-page .quick-btn:hover {
  border-color: #5b4f95;
  background: #222432;
  box-shadow: none;
}

.dashboard-page :deep(.el-tag) {
  border-color: #3a3d4d;
  background: #222430;
  color: #c3c5d1;
}

/* ===== Responsive ===== */
@media (max-width: 1024px) {
  .top-row {
    grid-template-columns: 1fr;
  }
  .middle-row {
    grid-template-columns: 1fr;
  }
  .bottom-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    min-height: 0;
    margin: -12px -16px -16px;
    padding: 20px 16px;
  }

  .welcome-bar {
    min-height: 0;
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
    padding: 24px 20px 104px;
  }

  .welcome-bar h1 {
    font-size: 27px;
  }

  .welcome-actions {
    align-self: flex-start;
    flex-wrap: wrap;
  }

  .signal-stats {
    right: 20px;
    left: 20px;
    grid-template-columns: repeat(3, 1fr);
  }

  .signal-stats div {
    min-width: 0;
    padding: 11px 8px;
    text-align: center;
  }

  .signal-stats strong {
    font-size: 16px;
  }

  .metrics-grid {
    grid-template-columns: 1fr 1fr;
  }
  .quick-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 560px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  .quick-grid {
    grid-template-columns: 1fr;
  }
  .funnel-bar {
    gap: 6px;
  }
}
</style>
