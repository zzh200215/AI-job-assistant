<template>
  <div class="task-center-page">
    <el-card shadow="never" class="hero-card">
      <template #header>
        <span>Task Center</span>
      </template>

      <div class="hero-top">
        <div>
          <p class="eyebrow">Async Workflows</p>
          <h1>Unified Task Status Center</h1>
          <p class="hero-desc">
            Track long-running analysis workflows, inspect progress, and jump back to result pages without repeating input.
          </p>
        </div>

        <div class="hero-actions">
          <el-select v-model="statusFilter" class="filter-select" placeholder="Filter by status" @change="loadTaskData">
            <el-option label="All Statuses" value="" />
            <el-option label="Pending" value="pending" />
            <el-option label="Running" value="running" />
            <el-option label="Completed" value="completed" />
            <el-option label="Failed" value="failed" />
            <el-option label="Partial" value="partial" />
            <el-option label="Cancelled" value="cancelled" />
          </el-select>
          <el-button :loading="loading" @click="loadTaskData">Refresh</el-button>
        </div>
      </div>

      <el-row :gutter="16" class="summary-grid">
        <el-col v-for="item in summaryCards" :key="item.label" :xs="12" :sm="8" :md="4">
          <div class="summary-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="section-header">
          <span>Recent Tasks</span>
          <small>{{ tableHint }}</small>
        </div>
      </template>

      <el-table v-loading="loading" :data="tasks" empty-text="No tasks found">
        <el-table-column label="Task ID" min-width="110">
          <template #default="{ row }">
            <strong>#{{ row.id }}</strong>
          </template>
        </el-table-column>

        <el-table-column label="Status" min-width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="Progress" min-width="220">
          <template #default="{ row }">
            <div class="progress-cell">
              <el-progress :percentage="row.progress?.progress_percent || 0" :stroke-width="10" />
              <small>
                {{ row.progress?.finished_steps || 0 }} / {{ row.progress?.total_steps || 0 }}
                · {{ row.progress?.current_step?.label || 'Waiting to start' }}
              </small>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="Resume / JD" min-width="160">
          <template #default="{ row }">
            <div class="meta-block">
              <span>Resume #{{ row.resume_id }}</span>
              <span>JD #{{ row.jd_id }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="Duration" min-width="110">
          <template #default="{ row }">
            {{ formatDuration(row.progress?.duration_ms) }}
          </template>
        </el-table-column>

        <el-table-column label="LLM Cost" min-width="140">
          <template #default="{ row }">
            <div class="meta-block">
              <span>{{ formatTokens(row.usage?.tokens_used) }} tokens</span>
              <span>{{ formatCost(row.usage?.cost_cents) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="Created At" min-width="180">
          <template #default="{ row }">
            {{ row.create_time || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="Action" width="320" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openTask(row)">Open</el-button>
            <el-button link type="info" @click="openTrace(row)">Trace</el-button>
            <el-button
              v-if="row.analysis_record_id"
              link
              type="success"
              @click="openResult(row)"
            >
              Result
            </el-button>
            <el-button
              v-if="['pending', 'running'].includes(row.status)"
              link
              type="danger"
              @click="handleCancel(row)"
            >
              Cancel
            </el-button>
            <el-button
              v-if="['failed', 'partial', 'cancelled', 'completed'].includes(row.status)"
              link
              type="warning"
              @click="handleRetry(row)"
            >
              Retry
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  cancelAgentTask,
  getAgentTaskSummary,
  getAgentTasks,
  retryAgentTask,
} from '@/api/agent'

const router = useRouter()
const loading = ref(false)
const statusFilter = ref('')
const summary = ref({ counts: {}, total: 0, recent: [] })
const taskList = ref({ items: [], total: 0, limit: 20, offset: 0 })
let refreshTimer = null

const tasks = computed(() => taskList.value.items || [])

const summaryCards = computed(() => {
  const counts = summary.value.counts || {}
  return [
    { label: 'Total', value: summary.value.total || 0 },
    { label: 'Pending', value: counts.pending || 0 },
    { label: 'Running', value: counts.running || 0 },
    { label: 'Completed', value: counts.completed || 0 },
    { label: 'Failed', value: counts.failed || 0 },
    { label: 'Partial', value: counts.partial || 0 },
    { label: 'Cancelled', value: counts.cancelled || 0 },
  ]
})

const tableHint = computed(() => {
  const total = taskList.value.total || 0
  return `${total} task${total === 1 ? '' : 's'}`
})

function statusLabel(status) {
  const map = {
    pending: 'Pending',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    partial: 'Partial',
    cancelled: 'Cancelled',
  }
  return map[status] || status || '-'
}

function statusTagType(status) {
  const map = {
    pending: 'info',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    partial: '',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

function formatDuration(durationMs) {
  if (!durationMs && durationMs !== 0) return '-'
  if (durationMs < 1000) return `${durationMs} ms`
  return `${(durationMs / 1000).toFixed(1)} s`
}

function formatTokens(tokens) {
  const value = Number(tokens || 0)
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(value)
}

function formatCost(costCents) {
  const value = Number(costCents || 0)
  if (!value) return '$0.0000'
  return `$${(value / 100).toFixed(4)}`
}

function openTask(task) {
  router.push(`/agent?task_id=${task.id}`)
}

function openResult(task) {
  if (!task.analysis_record_id) return
  router.push(`/analysis/${task.analysis_record_id}`)
}

function openTrace(task) {
  router.push({
    name: 'prompt-traces',
    query: {
      task_id: String(task.id),
      analysis_record_id: task.analysis_record_id ? String(task.analysis_record_id) : undefined,
    },
  })
}

async function handleCancel(task) {
  await ElMessageBox.confirm(
    `Cancel task #${task.id}? Running work will stop after the current step finishes.`,
    'Cancel Task',
    { type: 'warning' },
  )
  await cancelAgentTask(task.id)
  ElMessage.success(`Task #${task.id} cancelled`)
  await loadTaskData()
}

async function handleRetry(task) {
  await ElMessageBox.confirm(
    `Retry task #${task.id}? A new task will be created immediately.`,
    'Retry Task',
    { type: 'info' },
  )
  const data = await retryAgentTask(task.id)
  const nextTask = data?.data || data
  ElMessage.success(`Retry task started${nextTask?.id ? ` (#${nextTask.id})` : ''}`)
  await loadTaskData()
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
}

function scheduleAutoRefresh() {
  stopAutoRefresh()
  if (tasks.value.some(task => ['pending', 'running'].includes(task.status))) {
    refreshTimer = setTimeout(() => {
      loadTaskData({ silent: true })
    }, 5000)
  }
}

async function loadTaskData({ silent = false } = {}) {
  stopAutoRefresh()
  if (!silent) {
    loading.value = true
  }
  try {
    const [summaryRes, listRes] = await Promise.all([
      getAgentTaskSummary(),
      getAgentTasks({
        status: statusFilter.value || undefined,
        limit: 20,
        offset: 0,
      }),
    ])
    summary.value = summaryRes?.data || summaryRes || { counts: {}, total: 0, recent: [] }
    taskList.value = listRes?.data || listRes || { items: [], total: 0, limit: 20, offset: 0 }
  } finally {
    loading.value = false
    scheduleAutoRefresh()
  }
}

onMounted(() => {
  loadTaskData()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.task-center-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-card,
.table-card {
  border-radius: 26px;
}

.hero-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-top h1 {
  margin: 8px 0 0;
}

.hero-desc {
  margin: 10px 0 0;
  color: var(--app-muted);
  max-width: 720px;
  line-height: 1.8;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.filter-select {
  width: 180px;
}

.summary-grid {
  margin-top: 8px;
}

.summary-card {
  padding: 14px 16px;
  border-radius: 18px;
  background: #f7fbf8;
  border: 1px solid rgba(217, 231, 222, 0.94);
}

.summary-card span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.section-header small {
  color: var(--app-muted);
}

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-cell small {
  color: var(--app-muted);
}

.meta-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #506257;
}

.table-card :deep(.el-table th.el-table__cell) {
  background: #f7fbf8;
}

@media (max-width: 768px) {
  .hero-top {
    flex-direction: column;
  }
}
</style>
