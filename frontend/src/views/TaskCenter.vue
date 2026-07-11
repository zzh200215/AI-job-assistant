<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>任务中心</h2>
        <div class="page-header-sub">查看所有异步分析任务的进度和结果</div>
      </div>
      <el-button @click="loadTasks" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <div v-if="loading && !tasks.length" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>

    <div v-else-if="!tasks.length" class="empty-state">
      <el-empty :image-size="120" description="暂无任务记录" />
    </div>

    <div v-else class="task-list">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="task-card"
        :class="'status-' + task.status"
      >
        <div class="task-top">
          <div class="task-dot" :class="'dot-' + task.status" />
          <div class="task-info">
            <strong>{{ task.name || task.task_type || '分析任务' }}</strong>
            <span>{{ formatDate(task.create_time) }}</span>
          </div>
          <el-tag :type="statusType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
        </div>

        <!-- 进度条 -->
        <div v-if="task.progress !== undefined" class="task-progress">
          <el-progress
            :percentage="task.progress"
            :status="task.status === 'failed' ? 'exception' : task.status === 'completed' ? 'success' : undefined"
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
          <el-button v-if="task.status === 'completed' && task.result_url" size="small" type="primary" @click="viewResult(task)">
            查看结果
          </el-button>
          <el-button v-if="task.status === 'failed'" size="small" @click="retryTask(task)">
            重试
          </el-button>
          <el-button v-if="['pending', 'running'].includes(task.status)" size="small" @click="cancelTask(task)">
            取消
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import request from '@/api/request'

const router = useRouter()
const loading = ref(false)
const tasks = ref([])
let pollTimer = null

function formatDate(d) {
  if (!d) return ''
  try { return new Date(d).toLocaleString('zh-CN') } catch { return d }
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
  const map = { completed: '已完成', failed: '失败', running: '运行中', pending: '等待中', cancelled: '已取消' }
  return map[s] || s
}

async function loadTasks() {
  loading.value = true
  try {
    const res = await request.get('/agent/tasks', { params: { limit: 50 } })
    tasks.value = res?.items || res || []
  } catch {} finally {
    loading.value = false
  }
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
  } catch {}
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

.task-card {
  background: #fff;
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

.dot-pending { background: var(--app-muted); }
.dot-running { background: var(--app-primary); animation: pulse 1.5s infinite; }
.dot-completed { background: var(--app-success); }
.dot-failed { background: var(--app-danger); }
.dot-cancelled { background: var(--app-muted); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
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
</style>
