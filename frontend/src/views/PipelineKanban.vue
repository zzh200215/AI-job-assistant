<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>投递看板</h2>
        <div class="page-header-sub">拖拽卡片在阶段间移动，追踪每一步投递进展</div>
      </div>
      <div class="header-actions">
        <el-button-group class="view-toggle">
          <el-button :type="viewMode === 'kanban' ? 'primary' : ''" size="small" @click="viewMode = 'kanban'">
            <el-icon><Grid /></el-icon> 看板
          </el-button>
          <el-button :type="viewMode === 'list' ? 'primary' : ''" size="small" @click="viewMode = 'list'">
            <el-icon><List /></el-icon> 列表
          </el-button>
        </el-button-group>
        <el-button @click="showStats = !showStats" size="small">
          <el-icon><TrendCharts /></el-icon> {{ showStats ? '隐藏' : '查看' }}统计
        </el-button>
        <el-button @click="loadKanban">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button type="primary" @click="showAddDialog = true">
          <el-icon><Plus /></el-icon> 新增投递
        </el-button>
      </div>
    </div>

    <!-- 投递统计面板 -->
    <div v-if="showStats && totalCards > 0" class="stats-panel">
      <div class="stats-header">
        <h3>投递转化分析</h3>
      </div>
      <div class="stats-body">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-value">{{ totalCards }}</span>
            <span class="stat-label">总投递</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ conversionRate('applied') }}%</span>
            <span class="stat-label">投递率</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ conversionRate('interview') }}%</span>
            <span class="stat-label">面试率</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ conversionRate('offer') }}%</span>
            <span class="stat-label">Offer率</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ rejectionRate }}%</span>
            <span class="stat-label">拒绝率</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ avgResponseDays }}</span>
            <span class="stat-label">平均响应(天)</span>
          </div>
        </div>
        <div class="stats-funnel">
          <div
            v-for="(stage, idx) in funnelData"
            :key="stage.key"
            class="funnel-bar-wrapper"
          >
            <div class="funnel-label-row">
              <span class="funnel-label">{{ stage.label }}</span>
              <span class="funnel-count">{{ stage.count }}</span>
            </div>
            <div class="funnel-track">
              <div
                class="funnel-fill"
                :style="{ width: funnelPercent(stage.count) + '%' }"
                :class="'fill-' + stage.accent"
              />
            </div>
            <div v-if="idx < funnelData.length - 1" class="funnel-arrow">
              <el-icon><ArrowRight /></el-icon>
              <span class="funnel-rate">{{ stageToRate(stage.key, funnelData[idx + 1]?.key) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 看板列 -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>

    <div v-else class="kanban-board">
      <el-empty v-if="totalCards === 0" :image-size="120" description="还没有任何投递记录">
        <template #description>
          <span>去岗位推荐中一键加入看板，或手动新增投递记录</span>
        </template>
        <el-button type="primary" @click="router.push('/jobs/recommend')">
          <el-icon><Search /></el-icon> 去岗位推荐
        </el-button>
        <el-button @click="showAddDialog = true">手动新增</el-button>
      </el-empty>

      <template v-else>
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
              <!-- 跟进提醒 -->
              <div v-if="needsFollowUp(card)" :class="'card-follow follow-' + followUpLevel(card)">
                <el-icon><WarningFilled /></el-icon> {{ followUpDays(card) }}天未回复
              </div>
              <span class="card-date">{{ formatDate(card.create_time) }}</span>
              <el-tag v-if="card.source" size="small" type="info">{{ card.source }}</el-tag>
            </div>
          </div>

          <div v-if="!(kanban[col.key] || []).length" class="col-empty">
            暂无{{ col.label }}
          </div>
        </div>
      </div>
      </template>
    </div>

    <!-- 列表视图 -->
    <div v-if="viewMode === 'list' && totalCards > 0" class="list-view">
      <!-- 批量操作栏 -->
      <div v-if="selectedCards.size > 0" class="batch-bar">
        <span class="batch-info">已选 <strong>{{ selectedCards.size }}</strong> 项</span>
        <el-button size="small" @click="batchMove('interview')">批量移至面试</el-button>
        <el-button size="small" @click="batchMove('offer')">批量移至Offer</el-button>
        <el-button size="small" @click="batchMove('rejected')" style="color:var(--app-danger)">批量标记拒绝</el-button>
        <el-button size="small" text @click="clearSelection">取消选择</el-button>
      </div>

      <el-table :data="allCards" style="width:100%" @selection-change="onSelectionChange" border stripe size="small">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="title" label="岗位" min-width="160">
          <template #default="{ row }">
            <div class="list-title">{{ row.title || '未命名' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="company" label="公司" width="120" />
        <el-table-column label="阶段" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="stageTagType(row.stage)">{{ stageLabel(row.stage) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="跟进" width="100">
          <template #default="{ row }">
            <span v-if="needsFollowUp(row)" :class="'follow-' + followUpLevel(row)">
              <el-icon><WarningFilled /></el-icon> {{ followUpDays(row) }}天
            </span>
            <span v-else class="follow-ok">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="salary_range" label="薪资" width="100" />
        <el-table-column label="匹配度" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.match_score" :class="'score-level-' + scoreLevel(row.match_score)">{{ Math.round(row.match_score) }}分</span>
            <span v-else class="follow-ok">-</span>
          </template>
        </el-table-column>
        <el-table-column label="面试时间" width="110">
          <template #default="{ row }">
            <span v-if="row.interview_at" class="follow-interview">{{ formatShortDate(row.interview_at) }}</span>
            <span v-else class="follow-ok">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="80" />
        <el-table-column label="创建时间" width="90">
          <template #default="{ row }">{{ formatShortDate(row.create_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="showCardDetail(row)">详情</el-button>
            <el-button text size="small" @click="router.push('/smart-analysis?jd_id=' + (row.jd_id || ''))">AI</el-button>
            <el-dropdown trigger="click" @command="cmd => handleListCmd(cmd, row)">
              <el-button text size="small">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="row.stage === 'interview'" command="interview">模拟面试</el-dropdown-item>
                  <el-dropdown-item command="reject">标记拒绝</el-dropdown-item>
                  <el-dropdown-item command="abandon">放弃</el-dropdown-item>
                  <el-dropdown-item command="delete" divided style="color:var(--app-danger)">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
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

    <!-- 投递详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="投递详情" width="560px" :close-on-click-modal="false">
      <div v-if="detailCard">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="岗位" :span="2">{{ detailCard.title || '-' }}</el-descriptions-item>
          <el-descriptions-item label="公司">{{ detailCard.company || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前阶段">
            <el-tag size="small">{{ stageLabel(detailCard.stage) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="薪资">{{ detailCard.salary_range || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ detailCard.source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="匹配度">{{ detailCard.match_score ? Math.round(detailCard.match_score) + '分' : '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">{{ formatDateTime(detailCard.create_time) }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.notes" label="备注" :span="2">{{ detailCard.notes }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.interview_at" label="面试时间" :span="2">{{ formatDateTime(detailCard.interview_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.url" label="岗位链接" :span="2">
            <el-link :href="detailCard.url" target="_blank" type="primary">{{ detailCard.url }}</el-link>
          </el-descriptions-item>
        </el-descriptions>
        <div class="detail-actions">
          <el-button size="small" @click="router.push({ path: '/smart-analysis', query: { jd_id: String(detailCard.jd_id || '') } })">
            <el-icon><DataAnalysis /></el-icon> AI 分析
          </el-button>
          <el-button size="small" type="primary" @click="router.push({ path: '/interview/setup', query: { jd_id: String(detailCard.jd_id || '') } })">
            <el-icon><Microphone /></el-icon> 模拟面试
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Clock,
  Coin,
  DataAnalysis,
  Grid,
  Histogram,
  List,
  Loading,
  Microphone,
  MoreFilled,
  OfficeBuilding,
  Plus,
  Refresh,
  Search,
  TrendCharts,
  WarningFilled,
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
const viewMode = ref('kanban')
const showStats = ref(false)
const selectedCards = ref(new Set())
const totalCards = computed(() => columns.reduce((sum, col) => sum + ((kanban.value[col.key] || []).length), 0))

// 所有卡片扁平列表
const allCards = computed(() => {
  const all = []
  columns.forEach(col => {
    (kanban.value[col.key] || []).forEach(card => {
      all.push(card)
    })
  })
  return all
})

// 统计计算
const counts = computed(() => {
  const map = {}
  columns.forEach(col => { map[col.key] = (kanban.value[col.key] || []).length })
  return map
})

const funnelData = computed(() =>
  columns.filter(c => c.key !== 'abandoned').map(c => ({
    ...c,
    count: counts.value[c.key] || 0,
  }))
)

function conversionRate(stage) {
  const total = totalCards.value
  if (!total) return 0
  // stages before the target
  const stageOrder = ['todo', 'applied', 'written_test', 'interview', 'offer']
  const idx = stageOrder.indexOf(stage)
  if (idx <= 0) return Math.round((counts.value[stage] || 0) / total * 100)
  const prevTotal = stageOrder.slice(0, idx).reduce((s, k) => s + (counts.value[k] || 0), 0)
  const current = counts.value[stage] || 0
  const base = prevTotal + current
  return base > 0 ? Math.round(current / base * 100) : 0
}

const rejectionRate = computed(() => {
  const total = totalCards.value
  if (!total) return 0
  return Math.round(((counts.value.rejected || 0) + (counts.value.abandoned || 0)) / total * 100)
})

const avgResponseDays = computed(() => {
  const now = Date.now()
  const applied = kanban.value.applied || []
  const days = applied
    .filter(c => c.last_update_time)
    .map(c => Math.round((now - new Date(c.last_update_time).getTime()) / 86400000))
  if (!days.length) return '--'
  const avg = Math.round(days.reduce((s, d) => s + d, 0) / days.length)
  return avg + 'd'
})

function funnelPercent(count) {
  const max = Math.max(1, ...funnelData.value.map(s => s.count))
  return Math.max(2, (count / max) * 100)
}

function stageToRate(from, to) {
  const fromCount = counts.value[from] || 0
  const toCount = counts.value[to] || 0
  if (!fromCount) return '0%'
  return Math.round(toCount / fromCount * 100) + '%'
}

function stageTagType(stage) {
  const map = { todo: 'info', applied: 'primary', written_test: 'warning', interview: 'success', offer: 'success', rejected: 'danger', abandoned: 'info' }
  return map[stage] || 'info'
}

function scoreLevel(score) {
  if (score >= 80) return 'high'
  if (score >= 60) return 'mid'
  return 'low'
}

// 跟进提醒
function needsFollowUp(card) {
  return (card.stage === 'applied' || card.stage === 'written_test') && card.last_update_time
}

function followUpDays(card) {
  if (!card.last_update_time) return 0
  return Math.round((Date.now() - new Date(card.last_update_time).getTime()) / 86400000)
}

function followUpLevel(card) {
  const days = followUpDays(card)
  if (days >= 7) return 'danger'
  if (days >= 3) return 'warn'
  return 'ok'
}

const showAddDialog = ref(false)
const addSubmitting = ref(false)
const addFormRef = ref(null)
const showDetailDialog = ref(false)
const detailCard = ref(null)

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

function formatShortDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return d
  }
}

function formatDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return d
  }
}

function formatDateTime(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return d
  }
}

function stageLabel(stage) {
  const map = { todo: '待投递', applied: '已投递', written_test: '笔试', interview: '面试', offer: 'Offer', rejected: '已拒绝', abandoned: '已放弃' }
  return map[stage] || stage || '-'
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
    detailCard.value = card
    showDetailDialog.value = true
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

// === 列表视图方法 ===
function showCardDetail(card) {
  detailCard.value = card
  showDetailDialog.value = true
}

function handleListCmd(cmd, card) {
  if (cmd === 'interview') {
    router.push(`/interview/setup?jd_id=${card.jd_id || ''}`)
  } else if (cmd === 'reject') {
    movePipelineStage(card.id, 'rejected').then(() => { ElMessage.success('已标记拒绝'); loadKanban() }).catch(() => {})
  } else if (cmd === 'abandon') {
    movePipelineStage(card.id, 'abandoned').then(() => { ElMessage.success('已放弃'); loadKanban() }).catch(() => {})
  } else if (cmd === 'delete') {
    ElMessageBox.confirm('确定删除此投递记录？', '删除确认', { type: 'warning' }).then(() => {
      deleteJobPipelineEntry(card.id).then(() => { ElMessage.success('已删除'); loadKanban() }).catch(() => {})
    }).catch(() => {})
  }
}

function onSelectionChange(rows) {
  selectedCards.value = new Set(rows.map(r => r.id))
}

function clearSelection() {
  selectedCards.value = new Set()
}

async function batchMove(targetStage) {
  const ids = [...selectedCards.value]
  if (!ids.length) return
  let success = 0
  for (const id of ids) {
    try {
      await movePipelineStage(id, targetStage)
      success++
    } catch {}
  }
  ElMessage.success(`成功将 ${success}/${ids.length} 项移至「${stageLabel(targetStage)}」`)
  selectedCards.value = new Set()
  loadKanban()
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

.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 20px;
  justify-content: center;
}

/* 跟进提醒 */
.card-follow {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  margin-bottom: 4px;
}
.follow-danger { background: #fff3f0; color: #d46e6e; }
.follow-warn { background: #fffaf1; color: #dc9c3f; }
.follow-ok { background: #f0faf4; color: #67c23a; }

/* View toggle */
.view-toggle { margin-right: 4px; }

/* 统计面板 */
.stats-panel {
  background: #fff;
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
  overflow: hidden;
}
.stats-header {
  padding: 14px 20px;
  border-bottom: 1px solid var(--app-line);
}
.stats-header h3 { margin: 0; font-size: 15px; font-weight: 700; }
.stats-body { padding: 16px 20px; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.stat-item {
  text-align: center;
  padding: 12px 8px;
  border-radius: 12px;
  background: var(--app-bg);
}
.stat-value {
  display: block;
  font-size: 24px;
  font-weight: 800;
  color: var(--app-primary);
  line-height: 1.2;
}
.stat-label {
  font-size: 12px;
  color: var(--app-muted);
  margin-top: 4px;
}
.stats-funnel {
  display: flex;
  align-items: center;
  gap: 8px;
}
.funnel-bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.funnel-label-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.funnel-label { color: var(--app-muted); }
.funnel-count { font-weight: 700; color: var(--app-text); }
.funnel-track {
  height: 24px;
  background: var(--el-fill-color);
  border-radius: 6px;
  overflow: hidden;
}
.funnel-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.4s ease;
}
.fill-slate { background: #94a3b8; }
.fill-blue { background: var(--app-primary); }
.fill-amber { background: var(--app-warning); }
.fill-violet { background: var(--app-violet); }
.fill-green { background: var(--app-success); }
.fill-red { background: var(--app-danger); }
.funnel-arrow {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: var(--app-muted);
  margin-top: 2px;
}
.funnel-rate { color: var(--app-primary); font-weight: 600; }

/* 列表视图 */
.list-view { background: #fff; border-radius: var(--app-radius-md, 16px); border: 1px solid var(--app-line); overflow: hidden; }
.list-title { font-weight: 600; font-size: 14px; }
.follow-interview { color: var(--app-violet); font-weight: 600; }
.score-level-high { color: var(--app-success); font-weight: 600; }
.score-level-mid { color: var(--app-warning); font-weight: 600; }
.score-level-low { color: var(--app-danger); font-weight: 600; }

/* 批量操作栏 */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--app-primary-light);
  border-bottom: 1px solid var(--app-line);
}
.batch-info {
  font-size: 13px;
  color: var(--app-text);
  margin-right: 8px;
}
.batch-info strong { color: var(--app-primary); }

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
