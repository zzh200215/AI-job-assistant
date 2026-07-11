<template>
  <div class="dashboard-page">
    <!-- 顶部欢迎栏 -->
    <section class="welcome-bar">
      <div class="welcome-left">
        <h1>求职仪表盘</h1>
        <p class="welcome-sub">{{ greeting }}，{{ username }}。{{ overviewLoaded ? `当前有 ${overview.active_applications} 个活跃投递` : '加载中...' }}</p>
      </div>
      <div class="welcome-actions">
        <el-button type="primary" @click="go('/jobs/pipeline/kanban')">
          <el-icon><Grid /></el-icon> 投递看板
        </el-button>
        <el-button @click="go('/smart-analysis')">
          <el-icon><MagicStick /></el-icon> 智能分析
        </el-button>
      </div>
    </section>

    <!-- 今日待办 + AI建议 -->
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
          <div v-else-if="!tasks.tasks?.length" class="empty-state">
            <p>今日暂无待办</p>
            <span>建议浏览推荐岗位或跟进已有投递</span>
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

      <div class="panel ai-panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-violet)"><MagicStick /></el-icon>
            <h3>AI 建议</h3>
          </div>
          <el-tag size="small" type="info">智能推荐</el-tag>
        </div>
        <div class="panel-body">
          <div v-if="aiLoading" class="loading-state">
            <el-icon class="is-loading"><Loading /></el-icon> 分析中...
          </div>
          <div v-else class="suggestion-list">
            <div
              v-for="(sug, idx) in aiSuggestions"
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
          <div class="metric-icon blue"><el-icon><Document /></el-icon></div>
          <div class="metric-body">
            <span class="metric-label">本周投递</span>
            <strong class="data-value">{{ overviewLoaded ? overview.weekly_new : '-' }}</strong>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon amber"><el-icon><ChatDotRound /></el-icon></div>
          <div class="metric-body">
            <span class="metric-label">面试率</span>
            <strong class="data-value">{{ interviewRate }}</strong>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon violet"><el-icon><Histogram /></el-icon></div>
          <div class="metric-body">
            <span class="metric-label">平均匹配</span>
            <strong class="data-value">{{ overviewLoaded ? (overview.avg_match_score ?? '--') : '-' }}</strong>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon green"><el-icon><Trophy /></el-icon></div>
          <div class="metric-body">
            <span class="metric-label">Offer 数</span>
            <strong class="data-value">{{ overviewLoaded ? (overview.pending_offers || 0) : '-' }}</strong>
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
            <div
              v-for="(day, idx) in overview.trend"
              :key="idx"
              class="trend-bar-col"
            >
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
            <div class="quick-icon blue"><el-icon><Grid /></el-icon></div>
            <span>投递看板</span>
          </button>
          <button class="quick-btn" @click="go('/jobs/recommend')">
            <div class="quick-icon amber"><el-icon><Search /></el-icon></div>
            <span>岗位推荐</span>
          </button>
          <button class="quick-btn" @click="go('/resume')">
            <div class="quick-icon violet"><el-icon><Document /></el-icon></div>
            <span>简历管理</span>
          </button>
          <button class="quick-btn" @click="go('/interview/setup')">
            <div class="quick-icon green"><el-icon><Microphone /></el-icon></div>
            <span>模拟面试</span>
          </button>
          <button class="quick-btn" @click="go('/targets')">
            <div class="quick-icon teal"><el-icon><Aim /></el-icon></div>
            <span>求职目标</span>
          </button>
          <button class="quick-btn" @click="go('/salary')">
            <div class="quick-icon red"><el-icon><Coin /></el-icon></div>
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
import { getDashboardOverview, getTodayTasks, getAiSuggestions } from '@/api/dashboard'

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
const tasks = ref({ tasks: [], high_priority: 0 })
const tasksLoading = ref(true)
const aiSuggestions = ref([])
const aiLoading = ref(true)

const interviewRate = computed(() => {
  if (!overviewLoaded.value) return '-'
  const total = overview.value.total_applications || 0
  const interviews = overview.value.stage_counts?.interview || 0
  const offers = overview.value.stage_counts?.offer || 0
  const accepted = overview.value.stage_counts?.accepted || 0
  const hit = interviews + offers + accepted
  return total > 0 ? Math.round(hit / total * 100) + '%' : '--'
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
  return Math.max(1, ...funnelStages.value.map(s => s.count))
})

const maxTrend = computed(() => {
  if (!overviewLoaded.value) return 1
  return Math.max(1, ...(overview.value.trend || []).map(d => d.count))
})

function funnelBarHeight(count) {
  return Math.max(4, (count / maxFunnel.value) * 100) + '%'
}

function trendHeight(count) {
  return Math.max(4, (count / maxTrend.value) * 100) + '%'
}

onMounted(async () => {
  try {
    const [ov, tk, ai] = await Promise.allSettled([
      getDashboardOverview(),
      getTodayTasks(),
      getAiSuggestions(),
    ])
    if (ov.status === 'fulfilled') {
      overview.value = ov.value
      overviewLoaded.value = true
    }
    if (tk.status === 'fulfilled') {
      tasks.value = tk.value
    }
    if (ai.status === 'fulfilled') {
      aiSuggestions.value = ai.value?.suggestions || []
    }
  } finally {
    tasksLoading.value = false
    aiLoading.value = false
  }
})
</script>

<style scoped>
.dashboard-page {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Welcome Bar ===== */
.welcome-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 28px;
  border-radius: 20px;
  background: linear-gradient(135deg, #196bdb 0%, #4a8fe5 100%);
  color: #fff;
}

.welcome-bar h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
}

.welcome-sub {
  margin: 6px 0 0;
  font-size: 14px;
  opacity: 0.9;
}

.welcome-actions {
  display: flex;
  gap: 10px;
}

.welcome-actions .el-button {
  border-radius: 12px;
}

.welcome-actions .el-button--default {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}

.welcome-actions .el-button--default:hover {
  background: rgba(255, 255, 255, 0.25);
}

/* ===== Panels ===== */
/* panel, panel-header, panel-body, panel-title-row defined in panels.css */

.panel + .panel {
  margin-top: 16px;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 20px 0;
  color: var(--app-muted);
  font-size: 14px;
}

.empty-state span {
  display: block;
  margin-top: 4px;
  font-size: 12px;
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

.dot-high { background: var(--app-danger); }
.dot-medium { background: var(--app-warning); }
.dot-low { background: var(--app-success); }

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
  background: #fff;
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

.metric-icon.blue { background: var(--app-primary-light); color: var(--app-primary); }
.metric-icon.amber { background: #fef5e7; color: var(--app-warning); }
.metric-icon.violet { background: var(--app-violet-light); color: var(--app-violet); }
.metric-icon.green { background: #e8f8ee; color: var(--app-success); }

.metric-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
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
  background: #fff;
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
  background: #fff;
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

.quick-icon.blue { background: var(--app-primary-light); color: var(--app-primary); }
.quick-icon.amber { background: #fef5e7; color: var(--app-warning); }
.quick-icon.violet { background: var(--app-violet-light); color: var(--app-violet); }
.quick-icon.green { background: #e8f8ee; color: var(--app-success); }
.quick-icon.teal { background: #e6fffa; color: #0d9488; }
.quick-icon.red { background: var(--app-accent-soft); color: var(--app-accent); }

/* ===== Responsive ===== */
@media (max-width: 1024px) {
  .top-row { grid-template-columns: 1fr; }
  .middle-row { grid-template-columns: 1fr; }
  .bottom-row { grid-template-columns: 1fr; }
}

@media (max-width: 768px) {
  .welcome-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
  }

  .welcome-bar h1 { font-size: 22px; }

  .metrics-grid { grid-template-columns: 1fr 1fr; }
  .quick-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 560px) {
  .metrics-grid { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: 1fr; }
  .funnel-bar { gap: 6px; }
}
</style>
