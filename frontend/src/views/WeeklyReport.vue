<template>
  <div class="page-shell weekly-report-page">
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
      <section class="weekly-focus-strip" aria-label="本周求职重点">
        <div class="weekly-focus-main">
          <span class="weekly-focus-label">本周复盘</span>
          <strong>{{ weeklyFocusTitle }}</strong>
          <p>{{ weeklyFocusDescription }}</p>
        </div>
        <div class="weekly-focus-metrics">
          <div>
            <b>{{ report.applications_this_week || 0 }}</b
            ><span>本周投递</span>
          </div>
          <div>
            <b>{{ interviewRateText }}</b
            ><span>面试率</span>
          </div>
          <div>
            <b>{{ responseRateText }}</b
            ><span>响应率</span>
          </div>
        </div>
        <div class="weekly-focus-action">
          <span class="weekly-focus-label">下周第一步</span>
          <p>{{ nextSuggestion }}</p>
          <el-button size="small" type="primary" @click="$router.push('/jobs/pipeline/kanban')"
            >查看投递节奏</el-button
          >
        </div>
      </section>

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
              <strong class="metric-value">{{
                report.interview_rate ? (report.interview_rate * 100).toFixed(1) + '%' : '-'
              }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">平均匹配分</span>
              <strong class="metric-value">{{
                report.avg_match_score ? Math.round(report.avg_match_score) : '-'
              }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">投递响应率</span>
              <strong class="metric-value">{{
                report.response_rate ? (report.response_rate * 100).toFixed(1) + '%' : '-'
              }}</strong>
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
                <span
                  >{{ stageLabel(app.stage) }} ·
                  {{ formatDate(app.update_time || app.create_time) }}</span
                >
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div v-else-if="loadError" class="load-error">
      <div>
        <strong>周报加载失败</strong>
        <span>{{ loadError }}</span>
      </div>
      <el-button @click="loadReport">重新加载</el-button>
    </div>

    <div v-else class="empty-state">
      <el-empty :image-size="120" description="暂无周报数据，开始投递后自动生成">
        <el-button type="primary" @click="$router.push('/jobs/pipeline/kanban')"
          >去投递看板</el-button
        >
      </el-empty>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
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
const loadError = ref('')

const interviewRateText = computed(() =>
  report.value?.interview_rate ? `${(report.value.interview_rate * 100).toFixed(1)}%` : '--'
)
const responseRateText = computed(() =>
  report.value?.response_rate ? `${(report.value.response_rate * 100).toFixed(1)}%` : '--'
)
const weeklyFocusTitle = computed(() => {
  if ((report.value?.offers_this_week || 0) > 0) return '本周已出现 Offer，优先完成条件核验与取舍。'
  if ((report.value?.interviews_this_week || 0) > 0)
    return '本周有面试进展，优先把准备沉淀为下一轮表现。'
  if ((report.value?.applications_this_week || 0) > 0)
    return '本周投递已启动，重点观察响应并及时跟进。'
  return '本周尚未形成投递数据，先明确一批高匹配目标岗位。'
})
const weeklyFocusDescription = computed(() => {
  if ((report.value?.offers_this_week || 0) > 0)
    return '将薪资、成长性与截止日期放进同一套决策框架。'
  if ((report.value?.interviews_this_week || 0) > 0)
    return '根据反馈复盘高频问题，再安排针对性的模拟练习。'
  if ((report.value?.applications_this_week || 0) > 0)
    return '结合匹配分与响应率调整投递节奏，而不是只增加数量。'
  return '从岗位推荐中加入机会，再用看板建立持续跟进节奏。'
})
const nextSuggestion = computed(() => {
  const suggestion = report.value?.suggestions?.[0]
  return (
    suggestion?.title || suggestion?.description || '挑选高匹配机会并为每个机会安排明确的下一步。'
  )
})

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
  const max = Math.max(...funnelStages.map((s) => report.value?.pipeline_summary?.[s.key] || 0), 1)
  return Math.max(4, (val / max) * 100) + '%'
}

function stageColor(stage) {
  const map = {
    todo: 'dot-blue',
    applied: 'dot-violet',
    interview: 'dot-green',
    offer: 'dot-gold',
    rejected: 'dot-red',
  }
  return map[stage] || 'dot-blue'
}

function stageLabel(stage) {
  const map = {
    todo: '待投递',
    applied: '已投递',
    written_test: '笔试',
    interview: '面试',
    offer: 'Offer',
    rejected: '已拒绝',
    abandoned: '已放弃',
  }
  return map[stage] || stage
}

function formatDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return d
  }
}

async function loadReport() {
  loading.value = true
  try {
    const data = await getWeeklyReport()
    report.value = data
    loadError.value = ''
  } catch (error) {
    report.value = null
    loadError.value = error?.userMessage || '暂时无法生成本周周报，请检查网络后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadReport()
})
</script>

<style scoped>
/* Stats row */
.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
  border: 1px solid #f2c5bf;
  border-radius: 8px;
  background: var(--app-accent-soft);
}
.load-error strong,
.load-error span {
  display: block;
}
.load-error strong {
  color: var(--app-danger);
  font-size: 15px;
}
.load-error span {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
}
.stats-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.weekly-focus-strip {
  display: grid;
  grid-template-columns: minmax(260px, 1.25fr) minmax(240px, 0.9fr) minmax(230px, 0.9fr);
  gap: 0;
  margin-bottom: 18px;
  background: #fff;
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.weekly-focus-strip > div {
  min-width: 0;
  padding: 18px 20px;
  border-left: 1px solid var(--app-line);
}

.weekly-focus-strip > div:first-child {
  border-left: 0;
}

.weekly-focus-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.weekly-focus-main strong {
  display: block;
  margin-top: 7px;
  color: var(--app-text);
  font-size: 18px;
  line-height: 1.35;
}

.weekly-focus-strip p {
  margin: 7px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}

.weekly-focus-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.weekly-focus-metrics div {
  display: grid;
  gap: 4px;
  padding: 2px 12px;
  text-align: center;
}

.weekly-focus-metrics div + div {
  border-left: 1px solid var(--app-line);
}
.weekly-focus-metrics b {
  color: var(--app-primary-dark);
  font-size: 23px;
  line-height: 1;
}
.weekly-focus-metrics span {
  color: var(--app-muted);
  font-size: 12px;
}
.weekly-focus-action .el-button {
  margin-top: 12px;
}

.stat-card {
  flex: 1;
  min-width: 120px;
  text-align: center;
  padding: 16px 12px;
  border-radius: var(--app-radius-xs, 6px);
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

.accent-blue strong {
  color: var(--app-primary);
}
.accent-violet strong {
  color: var(--app-violet);
}
.accent-green strong {
  color: var(--app-success);
}
.accent-amber strong {
  color: var(--app-warning);
}

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

.funnel-bar.accent-blue {
  background: var(--app-primary);
}
.funnel-bar.accent-violet {
  background: var(--app-violet);
}
.funnel-bar.accent-amber {
  background: var(--app-warning);
}
.funnel-bar.accent-green {
  background: var(--app-success);
}
.funnel-bar.accent-gold {
  background: #e6a23c;
}
.funnel-bar.accent-red {
  background: var(--app-danger);
}

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
  border-radius: 6px;
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
  border-radius: 6px;
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

.dot-blue {
  background: var(--app-primary);
}
.dot-violet {
  background: var(--app-violet);
}
.dot-green {
  background: var(--app-success);
}
.dot-gold {
  background: #e6a23c;
}
.dot-red {
  background: var(--app-danger);
}

.app-info strong {
  display: block;
  font-size: 14px;
}

.app-info span {
  font-size: 12px;
  color: var(--app-muted);
}

@media (max-width: 768px) {
  .weekly-focus-strip,
  .weekly-focus-metrics {
    grid-template-columns: 1fr;
  }

  .weekly-focus-strip > div,
  .weekly-focus-strip > div:first-child {
    border-top: 1px solid var(--app-line);
    border-left: 0;
  }

  .weekly-focus-strip > div:first-child {
    border-top: 0;
  }

  .weekly-focus-metrics {
    gap: 8px;
  }

  .weekly-focus-metrics div,
  .weekly-focus-metrics div + div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
    text-align: left;
  }

  .weekly-focus-action .el-button {
    width: 100%;
  }

  .load-error {
    align-items: flex-start;
    flex-direction: column;
  }
  .stats-row {
    flex-direction: column;
  }
}
</style>
