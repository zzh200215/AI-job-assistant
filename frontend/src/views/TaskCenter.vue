<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>任务中心</h2>
        <div class="page-header-sub">查看所有异步分析任务的进度和结果</div>
      </div>
      <el-button :loading="loading" @click="loadTasks">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <section class="task-summary" aria-label="任务概览">
      <button
        v-for="item in summaryCards"
        :key="item.key"
        type="button"
        class="summary-card"
        :class="{ active: statusFilter === item.key, [item.tone]: true }"
        @click="selectStatus(item.key)"
      >
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </button>
    </section>

    <div class="task-toolbar">
      <el-radio-group v-model="statusFilter" size="small" @change="loadTasks">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button label="running">进行中</el-radio-button>
        <el-radio-button label="completed">已完成</el-radio-button>
        <el-radio-button label="failed">需处理</el-radio-button>
      </el-radio-group>
      <span class="task-count">{{
        statusFilter === 'all' ? `最近 ${tasks.length} 条任务` : `筛选结果 ${tasks.length} 条`
      }}</span>
    </div>

    <div v-if="loadError && !tasks.length" class="load-error">
      <div>
        <strong>任务加载失败</strong>
        <span>{{ loadError }}</span>
      </div>
      <el-button size="small" @click="loadTasks">重试</el-button>
    </div>

    <div v-else-if="loading && !tasks.length" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>

    <div v-else-if="!tasks.length" class="empty-state">
      <el-empty :image-size="92" description="这里会显示你发起的分析任务" />
      <div class="empty-actions">
        <el-button type="primary" @click="router.push('/smart-analysis')">开始智能分析</el-button>
        <el-button @click="router.push('/jobs/recommend')">查看岗位推荐</el-button>
      </div>
      <div class="empty-guide">
        <span><b>1</b> 上传或选择简历</span>
        <span><b>2</b> 选择目标岗位</span>
        <span><b>3</b> 在这里追踪分析进度</span>
      </div>
    </div>

    <div v-else class="task-list">
      <div v-for="task in tasks" :key="task.id" class="task-card" :class="'status-' + task.status">
        <div class="task-top">
          <div class="task-dot" :class="'dot-' + task.status" />
          <div class="task-info">
            <strong>{{ task.name || task.task_type || '分析任务' }}</strong>
            <span>{{ formatDate(task.create_time) }}</span>
          </div>
          <el-tag :type="statusType(task.status)" size="small">{{
            statusLabel(task.status)
          }}</el-tag>
        </div>

        <!-- 进度条 -->
        <div v-if="task.progress !== undefined" class="task-progress">
          <el-progress
            :percentage="task.progress"
            :status="
              task.status === 'failed'
                ? 'exception'
                : task.status === 'completed'
                  ? 'success'
                  : undefined
            "
            :stroke-width="8"
          />
        </div>

        <div class="task-meta">
          <span v-if="task.current_step">当前步骤：{{ task.current_step }}</span>
          <span v-if="task.duration_ms">耗时：{{ formatDuration(task.duration_ms) }}</span>
        </div>

        <div v-if="task.error_message" class="task-error">
          <el-alert :title="task.error_message" type="error" :closable="false" show-icon />
        </div>

        <div class="task-actions">
          <el-button
            v-if="task.status === 'completed' && task.result_url"
            size="small"
            type="primary"
            @click="viewResult(task)"
          >
            查看结果
          </el-button>
          <el-button v-if="task.status === 'failed'" size="small" @click="retryTask(task)">
            重试
          </el-button>
          <el-button
            v-if="['pending', 'running'].includes(task.status)"
            size="small"
            @click="cancelTask(task)"
          >
            取消
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import request from '@/api/request'

const router = useRouter()
const loading = ref(false)
const tasks = ref([])
const summary = ref({ counts: {}, total: 0 })
const statusFilter = ref('all')
const loadError = ref('')
let pollTimer = null

const summaryCards = computed(() => {
  const counts = summary.value.counts || {}
  return [
    {
      key: 'all',
      label: '全部任务',
      value: summary.value.total || 0,
      hint: '累计发起的分析',
      tone: 'blue',
    },
    {
      key: 'running',
      label: '进行中',
      value: (counts.running || 0) + (counts.pending || 0),
      hint: '正在生成结果',
      tone: 'violet',
    },
    {
      key: 'completed',
      label: '已完成',
      value: counts.completed || 0,
      hint: '可以查看结果',
      tone: 'green',
    },
    {
      key: 'failed',
      label: '需处理',
      value: (counts.failed || 0) + (counts.partial || 0),
      hint: '可重试或查看原因',
      tone: 'amber',
    },
  ]
})

function formatDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleString('zh-CN')
  } catch {
    // 保留服务端返回的原始时间。
    return d
  }
}

function formatDuration(ms) {
  if (!ms) return '-'
  if (ms < 1000) return ms + 'ms'
  if (ms < 60000) return (ms / 1000).toFixed(1) + 's'
  return (ms / 60000).toFixed(1) + 'min'
}

function statusType(s) {
  const map = { completed: 'success', failed: 'danger', running: 'primary', pending: 'info' }
  return map[s] || 'info'
}

function statusLabel(s) {
  const map = {
    completed: '已完成',
    failed: '失败',
    running: '运行中',
    pending: '等待中',
    cancelled: '已取消',
  }
  return map[s] || s
}

async function loadTasks() {
  loading.value = true
  try {
    const params = { limit: 50 }
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    const [taskData, summaryData] = await Promise.all([
      request.get('/agent/tasks', { params }),
      request.get('/agent/tasks/summary'),
    ])
    tasks.value = taskData?.items || taskData || []
    summary.value = summaryData || { counts: {}, total: 0 }
    loadError.value = ''
  } catch (error) {
    loadError.value = error?.userMessage || '暂时无法获取任务列表，请检查网络后重试。'
  } finally {
    loading.value = false
  }
}

function selectStatus(status) {
  if (statusFilter.value === status) return
  statusFilter.value = status
  loadTasks()
}

function viewResult(task) {
  if (task.result_url) {
    router.push(task.result_url)
  }
}

async function retryTask(task) {
  try {
    await request.post(`/agent/task/${task.id}/retry`)
    ElMessage.success('已重新提交')
    await loadTasks()
  } catch {
    ElMessage.error('重试失败')
  }
}

async function cancelTask(task) {
  try {
    await ElMessageBox.confirm('确定取消此任务？', '取消确认', { type: 'warning' })
    await request.post(`/agent/task/${task.id}/cancel`)
    ElMessage.success('已取消')
    await loadTasks()
  } catch {
    // 用户取消确认或请求失败时不改变任务状态。
  }
}

onMounted(() => {
  loadTasks()
  // Auto refresh every 10s
  pollTimer = setInterval(loadTasks, 10000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.summary-card {
  min-height: 100px;
  padding: 15px 16px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: var(--app-surface-strong);
  color: var(--app-text);
  cursor: pointer;
  text-align: left;
  box-shadow: var(--app-shadow-soft);
  transition:
    border-color 0.18s ease,
    transform 0.18s ease;
}
.summary-card:hover {
  transform: translateY(-1px);
}
.summary-card.active {
  border-color: currentColor;
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 11%, transparent);
}
.summary-card.blue {
  color: var(--app-primary);
}
.summary-card.violet {
  color: var(--app-violet);
}
.summary-card.green {
  color: var(--app-success);
}
.summary-card.amber {
  color: #a56a00;
}
.summary-card span,
.summary-card small {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}
.summary-card strong {
  display: block;
  margin: 3px 0;
  color: var(--app-text);
  font-size: 24px;
}
.summary-card small {
  font-size: 11px;
}
.task-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
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
  font-size: 13px;
}
.load-error span {
  margin-top: 2px;
  color: var(--app-muted);
  font-size: 12px;
}
.task-count {
  color: var(--app-muted);
  font-size: 12px;
}

.task-card {
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
  padding: 18px 20px;
}

.task-card.status-running {
  border-left: 3px solid var(--app-primary);
}

.task-card.status-failed {
  border-left: 3px solid var(--app-danger);
}

.task-card.status-completed {
  border-left: 3px solid var(--app-success);
}

.task-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.task-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-pending {
  background: var(--app-muted);
}
.dot-running {
  background: var(--app-primary);
  animation: pulse 1.5s infinite;
}
.dot-completed {
  background: var(--app-success);
}
.dot-failed {
  background: var(--app-danger);
}
.dot-cancelled {
  background: var(--app-muted);
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

.task-info {
  flex: 1;
}

.task-info strong {
  display: block;
  font-size: 14px;
}

.task-info span {
  font-size: 12px;
  color: var(--app-muted);
}

.task-progress {
  margin-bottom: 8px;
}

.task-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--app-muted);
  margin-bottom: 8px;
}

.task-error {
  margin-bottom: 8px;
}

.task-actions {
  display: flex;
  gap: 8px;
}

.empty-state {
  padding: 42px 0 34px;
  border: 1px dashed var(--app-line-strong);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.65);
  text-align: center;
}
.empty-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 8px;
}
.empty-guide {
  display: flex;
  justify-content: center;
  gap: 24px;
  margin-top: 24px;
  color: var(--app-muted);
  font-size: 12px;
}
.empty-guide span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.empty-guide b {
  display: grid;
  width: 18px;
  height: 18px;
  place-items: center;
  border-radius: 50%;
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-size: 11px;
}
@media (max-width: 760px) {
  .task-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .task-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
  .load-error {
    align-items: flex-start;
    flex-direction: column;
  }
  .empty-guide {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
    text-align: left;
  }
}
</style>
