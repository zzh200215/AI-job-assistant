<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>投递看板</h2>
        <div class="page-header-sub">拖拽卡片在阶段间移动，追踪每一步投递进展</div>
      </div>
      <div class="header-actions">
        <el-button @click="loadKanban">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button type="primary" @click="showAddDialog = true">
          <el-icon><Plus /></el-icon> 新增投递
        </el-button>
      </div>
    </div>

    <!-- 看板列 -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>

    <div v-else class="kanban-board">
      <div
        v-for="col in columns"
        :key="col.key"
        class="kanban-col"
        :class="col.accent"
        @dragover.prevent
        @drop="onDrop($event, col.key)"
      >
        <div class="col-header">
          <div class="col-dot" :class="'dot-' + col.accent" />
          <h3>{{ col.label }}</h3>
          <span class="col-count">{{ (kanban[col.key] || []).length }}</span>
        </div>

        <div class="col-body">
          <div
            v-for="card in (kanban[col.key] || [])"
            :key="card.id"
            class="kanban-card"
            draggable="true"
            @dragstart="onDragStart($event, card)"
          >
            <div class="card-top">
              <strong class="card-title">{{ card.title || card.company || '未命名岗位' }}</strong>
              <el-dropdown trigger="click" @command="cmd => handleCardCmd(cmd, card)">
                <el-icon class="card-more"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="detail">查看详情</el-dropdown-item>
                    <el-dropdown-item command="analyze">AI分析</el-dropdown-item>
                    <el-dropdown-item v-if="col.key === 'interview'" command="interview">模拟面试</el-dropdown-item>
                    <el-dropdown-item command="reject" divided style="color: var(--app-danger)">标记拒绝</el-dropdown-item>
                    <el-dropdown-item command="abandon" style="color: var(--app-muted)">放弃</el-dropdown-item>
                    <el-dropdown-item command="delete" style="color: var(--app-danger)">删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <div v-if="card.company" class="card-company">
              <el-icon><OfficeBuilding /></el-icon> {{ card.company }}
            </div>

            <div class="card-meta">
              <span v-if="card.salary_range"><el-icon><Coin /></el-icon> {{ card.salary_range }}</span>
              <span v-if="card.match_score" class="card-score">
                <el-icon><Histogram /></el-icon> {{ Math.round(card.match_score) }}分
              </span>
            </div>

            <div v-if="card.interview_at && col.key === 'interview'" class="card-interview">
              <el-icon><Clock /></el-icon>
              {{ formatDate(card.interview_at) }}
            </div>

            <div class="card-footer">
              <span class="card-date">{{ formatDate(card.create_time) }}</span>
              <el-tag v-if="card.source" size="small" type="info">{{ card.source }}</el-tag>
            </div>
          </div>

          <div v-if="!(kanban[col.key] || []).length" class="col-empty">
            暂无{{ col.label }}
          </div>
        </div>
      </div>
    </div>

    <!-- 新增投递对话框 -->
    <el-dialog v-model="showAddDialog" title="新增投递记录" width="500px" :close-on-click-modal="false">
      <el-form ref="addFormRef" :model="addForm" :rules="addRules" label-position="top">
        <el-form-item label="岗位名称" prop="title">
          <el-input v-model="addForm.title" placeholder="如：高级前端工程师" />
        </el-form-item>
        <el-form-item label="公司名称" prop="company">
          <el-input v-model="addForm.company" placeholder="如：字节跳动" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="薪资范围">
            <el-input v-model="addForm.salary_range" placeholder="如：30-50K" />
          </el-form-item>
          <el-form-item label="来源">
            <el-input v-model="addForm.source" placeholder="如：Boss直聘" />
          </el-form-item>
        </div>
        <el-form-item label="备注">
          <el-input v-model="addForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addSubmitting" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Clock,
  Coin,
  Histogram,
  Loading,
  MoreFilled,
  OfficeBuilding,
  Plus,
  Refresh,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { getKanban, movePipelineStage, createJobPipelineEntry, deleteJobPipelineEntry } from '@/api/targets'

const router = useRouter()

const columns = [
  { key: 'todo', label: '待投递', accent: 'slate' },
  { key: 'applied', label: '已投递', accent: 'blue' },
  { key: 'written_test', label: '笔试', accent: 'amber' },
  { key: 'interview', label: '面试', accent: 'violet' },
  { key: 'offer', label: 'Offer', accent: 'green' },
  { key: 'rejected', label: '已拒绝', accent: 'red' },
  { key: 'abandoned', label: '已放弃', accent: 'gray' },
]

const loading = ref(true)
const kanban = ref({})
const dragCard = ref(null)

const showAddDialog = ref(false)
const addSubmitting = ref(false)
const addFormRef = ref(null)

const addForm = ref({
  title: '',
  company: '',
  salary_range: '',
  source: '',
  notes: '',
})

const addRules = {
  title: [{ required: true, message: '请输入岗位名称', trigger: 'blur' }],
}

function formatDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return d
  }
}

async function loadKanban() {
  loading.value = true
  try {
    const data = await getKanban()
    kanban.value = data || {}
  } catch {
    kanban.value = {}
  } finally {
    loading.value = false
  }
}

function onDragStart(e, card) {
  dragCard.value = card
  e.dataTransfer.effectAllowed = 'move'
}

async function onDrop(e, targetStage) {
  if (!dragCard.value) return
  const card = dragCard.value
  if (card.stage === targetStage) {
    dragCard.value = null
    return
  }

  const oldStage = card.stage
  try {
    await movePipelineStage(card.id, targetStage)
    // 乐观更新
    const fromList = kanban.value[oldStage] || []
    const toList = kanban.value[targetStage] || []
    const idx = fromList.findIndex(c => c.id === card.id)
    if (idx >= 0) {
      fromList.splice(idx, 1)
      card.stage = targetStage
      toList.unshift(card)
    }
    ElMessage.success(`已移至「${columns.find(c => c.key === targetStage)?.label}」`)
  } catch {
    loadKanban()
  }
  dragCard.value = null
}

async function handleAdd() {
  try {
    await addFormRef.value?.validate()
  } catch {
    return
  }
  addSubmitting.value = true
  try {
    await createJobPipelineEntry({
      ...addForm.value,
      stage: 'todo',
    })
    ElMessage.success('投递记录已添加')
    showAddDialog.value = false
    addForm.value = { title: '', company: '', salary_range: '', source: '', notes: '' }
    loadKanban()
  } catch {} finally {
    addSubmitting.value = false
  }
}

async function handleCardCmd(cmd, card) {
  if (cmd === 'detail') {
    router.push(`/jobs/pipeline/${card.id}`)
  } else if (cmd === 'analyze') {
    router.push(`/smart-analysis?jd_id=${card.jd_id || ''}`)
  } else if (cmd === 'interview') {
    router.push(`/interview/setup?jd_id=${card.jd_id || ''}`)
  } else if (cmd === 'reject') {
    try {
      await movePipelineStage(card.id, 'rejected')
      ElMessage.success('已标记为拒绝')
      loadKanban()
    } catch {}
  } else if (cmd === 'abandon') {
    try {
      await movePipelineStage(card.id, 'abandoned')
      ElMessage.success('已放弃')
      loadKanban()
    } catch {}
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm('确定删除此投递记录？', '删除确认', { type: 'warning' })
      await deleteJobPipelineEntry(card.id)
      ElMessage.success('已删除')
      loadKanban()
    } catch {}
  }
}

onMounted(loadKanban)
</script>

<style scoped>
.page-shell {
  color: var(--app-text);
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* Board */
.kanban-board {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 16px;
}

.kanban-col {
  min-width: 240px;
  max-width: 300px;
  flex: 1;
  background: var(--app-bg);
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  display: flex;
  flex-direction: column;
}

.col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--app-line);
  background: #fff;
  border-radius: var(--app-radius-md, 16px) var(--app-radius-md, 16px) 0 0;
}

.col-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-slate { background: #94a3b8; }
.dot-blue { background: var(--app-primary); }
.dot-amber { background: var(--app-warning); }
.dot-violet { background: var(--app-violet); }
.dot-green { background: var(--app-success); }
.dot-red { background: var(--app-danger); }
.dot-gray { background: #9ca3af; }

.col-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  flex: 1;
}

.col-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-muted);
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: var(--app-radius-xs, 8px);
}

.col-body {
  padding: 8px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}

.col-empty {
  text-align: center;
  padding: 24px 0;
  color: var(--app-muted);
  font-size: 13px;
}

/* Card */
.kanban-card {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: #fff;
  border: 1px solid var(--app-line);
  cursor: grab;
  transition: all 0.15s;
}

.kanban-card:hover {
  box-shadow: var(--app-shadow);
  transform: translateY(-1px);
}

.kanban-card:active {
  cursor: grabbing;
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-more {
  cursor: pointer;
  color: var(--app-muted);
  padding: 2px;
  border-radius: var(--app-radius-xs, 8px);
  flex-shrink: 0;
}

.card-company {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 13px;
  color: var(--app-muted);
}

.card-meta {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-muted);
}

.card-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-score {
  color: var(--app-primary);
  font-weight: 600;
}

.card-interview {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-violet-light);
  color: var(--app-violet);
  font-size: 12px;
  font-weight: 600;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.card-date {
  font-size: 11px;
  color: var(--app-muted);
}

/* Form */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 1024px) {
  .kanban-board {
    flex-wrap: wrap;
  }
  .kanban-col {
    max-width: none;
    min-width: 200px;
  }
}

@media (max-width: 768px) {
  .page-shell .page-header {
    flex-direction: column;
    gap: 12px;
  }
  .kanban-col {
    min-width: 180px;
  }
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
