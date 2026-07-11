<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>求职周报</h2>
        <div class="page-header-sub">每周求职数据复盘与下周建议</div>
      </div>
      <el-button @click="loadReport" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 生成周报中...
    </div>

    <template v-else-if="report">
      <!-- 周报概览 -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-primary)"><Calendar /></el-icon>
            <h3>{{ report.period || '本周' }}概览</h3>
          </div>
        </div>
        <div class="panel-body">
          <div class="stats-row">
            <div class="stat-card accent-blue">
              <strong>{{ report.applications_this_week || 0 }}</strong>
              <span>本周投递</span>
            </div>
            <div class="stat-card accent-violet">
              <strong>{{ report.interviews_this_week || 0 }}</strong>
              <span>面试次数</span>
            </div>
            <div class="stat-card accent-green">
              <strong>{{ report.offers_this_week || 0 }}</strong>
              <span>新增 Offer</span>
            </div>
            <div class="stat-card accent-amber">
              <strong>{{ report.rejections_this_week || 0 }}</strong>
              <span>被拒绝</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 投递漏斗 -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-violet)"><DataLine /></el-icon>
            <h3>投递漏斗</h3>
          </div>
        </div>
        <div class="panel-body">
          <div class="funnel-chart">
            <div v-for="stage in funnelStages" :key="stage.key" class="funnel-row">
              <span class="funnel-label">{{ stage.label }}</span>
              <div class="funnel-bar-wrap">
                <div
                  class="funnel-bar"
                  :class="stage.accent"
                  :style="{ width: funnelWidth(stage.key) }"
                />
              </div>
              <strong class="funnel-count">{{ report.pipeline_summary?.[stage.key] || 0 }}</strong>
            </div>
          </div>
        </div>
      </div>

      <!-- 关键指标变化 -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-success)"><TrendCharts /></el-icon>
            <h3>关键指标</h3>
          </div>
        </div>
        <div class="panel-body">
          <div class="metrics-grid">
            <div class="metric-item">
              <span class="metric-label">面试率</span>
              <strong class="metric-value">{{ report.interview_rate ? (report.interview_rate * 100).toFixed(1) + '%' : '-' }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">平均匹配分</span>
              <strong class="metric-value">{{ report.avg_match_score ? Math.round(report.avg_match_score) : '-' }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">投递响应率</span>
              <strong class="metric-value">{{ report.response_rate ? (report.response_rate * 100).toFixed(1) + '%' : '-' }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">总投递数</span>
              <strong class="metric-value">{{ report.total_applications || 0 }}</strong>
            </div>
          </div>
        </div>
      </div>

      <!-- AI 建议 -->
      <div class="panel" v-if="report.suggestions?.length">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-violet)"><MagicStick /></el-icon>
            <h3>下周建议</h3>
          </div>
        </div>
        <div class="panel-body">
          <div class="suggestion-list">
            <div v-for="(sug, idx) in report.suggestions" :key="idx" class="suggestion-item">
              <div class="sug-index">{{ idx + 1 }}</div>
              <div class="sug-body">
                <strong>{{ sug.title }}</strong>
                <p>{{ sug.description }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 投递详情 -->
      <div class="panel" v-if="report.recent_applications?.length">
        <div class="panel-header">
          <div class="panel-title-row">
            <el-icon :size="18" color="var(--app-primary)"><List /></el-icon>
            <h3>近期投递</h3>
          </div>
        </div>
        <div class="panel-body">
          <div class="app-list">
            <div v-for="app in report.recent_applications" :key="app.id" class="app-row">
              <div class="app-dot" :class="stageColor(app.stage)" />
              <div class="app-info">
                <strong>{{ app.company || '未知' }} - {{ app.title || '未知岗位' }}</strong>
                <span>{{ stageLabel(app.stage) }} · {{ formatDate(app.update_time || app.create_time) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div v-else class="empty-state">
      <el-empty :image-size="120" description="暂无周报数据，开始投递后自动生成">
        <el-button type="primary" @click="$router.push('/jobs/pipeline/kanban')">去投递看板</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  Refresh,
  Calendar,
  DataLine,
  TrendCharts,
  MagicStick,
  List,
  Loading,
} from '@element-plus/icons-vue'
import { getWeeklyReport } from '@/api/dashboard'

const loading = ref(false)
const report = ref(null)

const funnelStages = [
  { key: 'todo', label: '待投递', accent: 'accent-blue' },
  { key: 'applied', label: '已投递', accent: 'accent-violet' },
  { key: 'written_test', label: '笔试', accent: 'accent-amber' },
  { key: 'interview', label: '面试', accent: 'accent-green' },
  { key: 'offer', label: 'Offer', accent: 'accent-gold' },
  { key: 'rejected', label: '拒绝', accent: 'accent-red' },
]

function funnelWidth(key) {
  const val = report.value?.pipeline_summary?.[key] || 0
  const max = Math.max(...funnelStages.map(s => report.value?.pipeline_summary?.[s.key] || 0), 1)
  return Math.max(4, (val / max) * 100) + '%'
}

function stageColor(stage) {
  const map = { todo: 'dot-blue', applied: 'dot-violet', interview: 'dot-green', offer: 'dot-gold', rejected: 'dot-red' }
  return map[stage] || 'dot-blue'
}

function stageLabel(stage) {
  const map = { todo: '待投递', applied: '已投递', written_test: '笔试', interview: '面试', offer: 'Offer', rejected: '已拒绝', abandoned: '已放弃' }
  return map[stage] || stage
}

function formatDate(d) {
  if (!d) return ''
  try { return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) } catch { return d }
}

async function loadReport() {
  loading.value = true
  try {
    const data = await getWeeklyReport()
    report.value = data
  } catch {} finally {
    loading.value = false
  }
}

onMounted(() => {
  loadReport()
})
</script>

<style scoped>
/* Stats row */
.stats-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-card {
  flex: 1;
  min-width: 120px;
  text-align: center;
  padding: 16px 12px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--el-fill-color-lighter);
}

.stat-card strong {
  display: block;
  font-size: 28px;
  font-weight: 800;
}

.stat-card span {
  display: block;
  font-size: 13px;
  color: var(--app-muted);
  margin-top: 4px;
}

.accent-blue strong { color: var(--app-primary); }
.accent-violet strong { color: var(--app-violet); }
.accent-green strong { color: var(--app-success); }
.accent-amber strong { color: var(--app-warning); }

/* Funnel */
.funnel-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.funnel-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.funnel-label {
  width: 60px;
  font-size: 13px;
  text-align: right;
  color: var(--app-muted);
}

.funnel-bar-wrap {
  flex: 1;
  height: 20px;
  border-radius: 4px;
  background: var(--el-fill-color);
  overflow: hidden;
}

.funnel-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s;
}

.funnel-bar.accent-blue { background: var(--app-primary); }
.funnel-bar.accent-violet { background: var(--app-violet); }
.funnel-bar.accent-amber { background: var(--app-warning); }
.funnel-bar.accent-green { background: var(--app-success); }
.funnel-bar.accent-gold { background: #e6a23c; }
.funnel-bar.accent-red { background: var(--app-danger); }

.funnel-count {
  width: 40px;
  text-align: right;
  font-size: 14px;
}

/* Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 16px;
}

.metric-item {
  padding: 12px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--el-fill-color-lighter);
}

.metric-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.metric-value {
  display: block;
  font-size: 22px;
  font-weight: 700;
  margin-top: 4px;
}

/* Suggestions */
.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.suggestion-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--app-line);
}

.sug-index {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--app-violet);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sug-body strong {
  display: block;
  font-size: 14px;
}

.sug-body p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--app-muted);
}

/* App list */
.app-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.app-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--app-radius-xs, 8px);
}

.app-row:hover {
  background: var(--el-fill-color-light);
}

.app-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-blue { background: var(--app-primary); }
.dot-violet { background: var(--app-violet); }
.dot-green { background: var(--app-success); }
.dot-gold { background: #e6a23c; }
.dot-red { background: var(--app-danger); }

.app-info strong {
  display: block;
  font-size: 14px;
}

.app-info span {
  font-size: 12px;
  color: var(--app-muted);
}

@media (max-width: 768px) {
  .stats-row { flex-direction: column; }
}
</style>
