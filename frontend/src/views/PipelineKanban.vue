<template>
  <div class="page-shell pipeline-page">
    <div class="page-header">
      <div>
        <h2>投递看板</h2>
        <div class="page-header-sub">拖拽卡片在阶段间移动，追踪每一步投递进展</div>
      </div>
      <div class="header-actions">
        <el-button-group class="view-toggle">
          <el-button
            :type="viewMode === 'kanban' ? 'primary' : ''"
            size="small"
            @click="viewMode = 'kanban'"
          >
            <el-icon><Grid /></el-icon> 看板
          </el-button>
          <el-button
            :type="viewMode === 'list' ? 'primary' : ''"
            size="small"
            @click="viewMode = 'list'"
          >
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

    <section v-if="totalCards > 0" class="pipeline-focus-strip" aria-label="投递行动摘要">
      <div class="focus-message">
        <span class="focus-label">本周重点</span>
        <strong>{{ pipelineFocusTitle }}</strong>
        <p>{{ pipelineFocusDescription }}</p>
      </div>
      <div class="focus-metrics">
        <div>
          <b>{{ followUpCount }}</b
          ><span>待跟进</span>
        </div>
        <div>
          <b>{{ counts.interview || 0 }}</b
          ><span>面试进行中</span>
        </div>
        <div>
          <b>{{ counts.offer || 0 }}</b
          ><span>待决 Offer</span>
        </div>
      </div>
      <div class="focus-actions">
        <el-button size="small" @click="showStats = !showStats">
          {{ showStats ? '收起转化分析' : '查看转化分析' }}
        </el-button>
        <el-button
          v-if="counts.offer"
          size="small"
          type="primary"
          @click="router.push('/offer/compare')"
        >
          进入 Offer 决策
        </el-button>
      </div>
    </section>

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
          <div v-for="(stage, idx) in funnelData" :key="stage.key" class="funnel-bar-wrapper">
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
              <span class="funnel-rate">{{
                stageToRate(stage.key, funnelData[idx + 1]?.key)
              }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showStats && versionPerformance.length" class="version-performance">
      <div class="version-performance-title">
        <div>
          <span class="section-kicker">Resume attribution</span>
          <h3>简历版本表现</h3>
        </div>
        <span>按已投递记录计算</span>
      </div>
      <div class="version-performance-list">
        <div
          v-for="item in versionPerformance"
          :key="item.resume_version_id"
          class="version-performance-row"
        >
          <div class="version-name">
            <strong>{{ item.label }}</strong>
            <span>{{ item.submitted }} 次投递</span>
          </div>
          <div class="version-metric">
            <strong>{{ item.interview_rate }}%</strong><span>面试率</span>
          </div>
          <div class="version-metric">
            <strong>{{ item.offer_rate }}%</strong><span>Offer 率</span>
          </div>
          <div class="version-outcomes">
            <span>{{ item.interviews }} 面试</span><span>{{ item.offers }} Offer</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 看板列 -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>

    <div v-else-if="loadError" class="load-error">
      <div>
        <strong>投递记录加载失败</strong>
        <span>{{ loadError }}</span>
      </div>
      <el-button @click="loadKanban">重新加载</el-button>
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
              v-for="card in kanban[col.key] || []"
              :key="card.id"
              class="kanban-card"
              draggable="true"
              @dragstart="onDragStart($event, card)"
            >
              <div class="card-top">
                <strong class="card-title">{{ card.title || card.company || '未命名岗位' }}</strong>
                <el-dropdown trigger="click" @command="(cmd) => handleCardCmd(cmd, card)">
                  <el-icon class="card-more"><MoreFilled /></el-icon>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="detail">查看详情</el-dropdown-item>
                      <el-dropdown-item command="analyze">AI分析</el-dropdown-item>
                      <el-dropdown-item v-if="col.key === 'interview'" command="interview"
                        >模拟面试</el-dropdown-item
                      >
                      <el-dropdown-item command="reject" divided style="color: var(--app-danger)"
                        >标记拒绝</el-dropdown-item
                      >
                      <el-dropdown-item command="abandon" style="color: var(--app-muted)"
                        >放弃</el-dropdown-item
                      >
                      <el-dropdown-item command="delete" style="color: var(--app-danger)"
                        >删除</el-dropdown-item
                      >
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>

              <div v-if="card.company" class="card-company">
                <el-icon><OfficeBuilding /></el-icon> {{ card.company }}
              </div>

              <div class="card-meta">
                <span v-if="card.salary_range"
                  ><el-icon><Coin /></el-icon> {{ card.salary_range }}</span
                >
                <span v-if="card.match_score" class="card-score">
                  <el-icon><Histogram /></el-icon> {{ Math.round(card.match_score) }}分
                </span>
              </div>
              <el-tag
                v-if="card.resume_version_label"
                class="resume-version-tag"
                size="small"
                effect="plain"
              >
                {{ card.resume_version_label }}
              </el-tag>

              <div v-if="card.interview_at && col.key === 'interview'" class="card-interview">
                <el-icon><Clock /></el-icon>
                {{ monthDay(card.interview_at) }}
              </div>

              <div class="card-footer">
                <!-- 跟进提醒 -->
                <div
                  v-if="needsFollowUp(card)"
                  :class="'card-follow follow-' + followUpLevel(card)"
                >
                  <el-icon><WarningFilled /></el-icon> {{ followUpDays(card) }}天未回复
                </div>
                <span class="card-date">{{ monthDay(card.create_time) }}</span>
                <el-tag v-if="card.source" size="small" type="info">{{ card.source }}</el-tag>
              </div>
            </div>

            <div v-if="!(kanban[col.key] || []).length" class="col-empty">暂无{{ col.label }}</div>
          </div>
        </div>
      </template>
    </div>

    <!-- 列表视图 -->
    <div v-if="viewMode === 'list' && totalCards > 0" class="list-view">
      <!-- 批量操作栏 -->
      <div v-if="selectedCards.size > 0" class="batch-bar">
        <span class="batch-info"
          >已选 <strong>{{ selectedCards.size }}</strong> 项</span
        >
        <el-button size="small" @click="batchMove('interview')">批量移至面试</el-button>
        <el-button size="small" @click="batchMove('offer')">批量移至Offer</el-button>
        <el-button size="small" @click="batchMove('rejected')" style="color: var(--app-danger)"
          >批量标记拒绝</el-button
        >
        <el-button size="small" text @click="clearSelection">取消选择</el-button>
      </div>

      <el-table
        :data="allCards"
        style="width: 100%"
        @selection-change="onSelectionChange"
        border
        stripe
        size="small"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column prop="title" label="岗位" min-width="160">
          <template #default="{ row }">
            <div class="list-title">{{ row.title || '未命名' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="company" label="公司" width="120" />
        <el-table-column label="简历版本" min-width="130">
          <template #default="{ row }">
            <span v-if="row.resume_version_label" class="version-cell">{{
              row.resume_version_label
            }}</span>
            <span v-else class="follow-ok">未记录</span>
          </template>
        </el-table-column>
        <el-table-column label="阶段" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="stageTagType(row.stage)">{{
              stageLabel(row.stage)
            }}</el-tag>
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
            <span
              v-if="row.match_score"
              :class="scoreToneClass(row.match_score, MATCH_SCORE_BANDS, 'score-level')"
              >{{ Math.round(row.match_score) }}分</span
            >
            <span v-else class="follow-ok">-</span>
          </template>
        </el-table-column>
        <el-table-column label="面试时间" width="110">
          <template #default="{ row }">
            <span v-if="row.interview_at" class="follow-interview">{{
              monthDayTime(row.interview_at)
            }}</span>
            <span v-else class="follow-ok">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="80" />
        <el-table-column label="创建时间" width="90">
          <template #default="{ row }">{{ monthDayTime(row.create_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="showCardDetail(row)">详情</el-button>
            <el-button
              text
              size="small"
              @click="router.push('/smart-analysis?jd_id=' + (row.jd_id || ''))"
              >AI</el-button
            >
            <el-dropdown trigger="click" @command="(cmd) => handleListCmd(cmd, row)">
              <el-button text size="small">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="row.stage === 'interview'" command="interview"
                    >模拟面试</el-dropdown-item
                  >
                  <el-dropdown-item command="reject">标记拒绝</el-dropdown-item>
                  <el-dropdown-item command="abandon">放弃</el-dropdown-item>
                  <el-dropdown-item command="delete" divided style="color: var(--app-danger)"
                    >删除</el-dropdown-item
                  >
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增投递对话框 -->
    <el-dialog
      v-model="showAddDialog"
      title="新增投递记录"
      width="500px"
      :close-on-click-modal="false"
    >
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
          <el-input v-model="addForm.note" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="本次投递使用的简历版本">
          <el-select
            v-model="addForm.resume_version_id"
            clearable
            placeholder="选择已保存的简历版本"
            class="full-width"
          >
            <el-option
              v-for="version in resumeVersions"
              :key="version.id"
              :label="`${version.label} · ${version.resume_name}`"
              :value="version.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addSubmitting" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>

    <!-- 投递详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="投递详情"
      width="560px"
      :close-on-click-modal="false"
    >
      <div v-if="detailCard">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="岗位" :span="2">{{
            detailCard.title || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="公司">{{ detailCard.company || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前阶段">
            <el-tag size="small">{{ stageLabel(detailCard.stage) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="薪资">{{
            detailCard.salary_range || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ detailCard.source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="匹配度">{{
            detailCard.match_score ? Math.round(detailCard.match_score) + '分' : '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="简历版本" :span="2">{{
            detailCard.resume_version_label || '未记录'
          }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">{{
            monthDayTime(detailCard.create_time)
          }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.note" label="备注" :span="2">{{
            detailCard.note
          }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.interview_at" label="面试时间" :span="2">{{
            monthDayTime(detailCard.interview_at)
          }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.source_url" label="岗位链接" :span="2">
            <el-link :href="detailCard.source_url" target="_blank" type="primary">{{
              detailCard.source_url
            }}</el-link>
          </el-descriptions-item>
        </el-descriptions>
        <div class="feedback-entry">
          <strong>投递反馈</strong>
          <div class="feedback-controls">
            <el-select v-model="feedbackForm.feedback_type" placeholder="反馈类型" size="small">
              <el-option label="HR 回复" value="hr_reply" />
              <el-option label="面试反馈" value="interview" />
              <el-option label="拒绝原因" value="rejection" />
              <el-option label="Offer 反馈" value="offer" />
            </el-select>
            <el-rate v-model="feedbackForm.feedback_score" :max="5" />
          </div>
          <el-input
            v-model="feedbackForm.feedback_note"
            type="textarea"
            :rows="2"
            placeholder="记录关键信息、建议或拒绝原因"
          />
          <el-button size="small" type="primary" :loading="feedbackSaving" @click="saveFeedback"
            >保存反馈</el-button
          >
        </div>
        <div class="detail-actions">
          <el-button
            size="small"
            @click="
              router.push({
                path: '/smart-analysis',
                query: { jd_id: String(detailCard.jd_id || '') },
              })
            "
          >
            <el-icon><DataAnalysis /></el-icon> AI 分析
          </el-button>
          <el-button
            size="small"
            type="primary"
            @click="
              router.push({
                path: '/interview/setup',
                query: { jd_id: String(detailCard.jd_id || '') },
              })
            "
          >
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
import { MATCH_SCORE_BANDS, scoreToneClass } from '@/utils/scoreTone'
import {
  getKanban,
  movePipelineStage,
  createJobPipelineEntry,
  deleteJobPipelineEntry,
  getPipelineResumeVersions,
  getPipelineResumeVersionStats,
  updateJobPipelineEntry,
} from '@/api/targets'
import { monthDay, monthDayTime } from '@/utils/format/date'

const router = useRouter()

const columns = [
  { key: 'todo', label: '待投递', accent: 'slate' },
  { key: 'applied', label: '已投递', accent: 'blue' },
  { key: 'written_test', label: '笔试', accent: 'amber' },
  { key: 'interview', label: '面试', accent: 'violet' },
  { key: 'offer', label: 'Offer', accent: 'green' },
  { key: 'accepted', label: '已入职', accent: 'green' },
  { key: 'rejected', label: '已拒绝', accent: 'red' },
  { key: 'withdrawn', label: '已放弃', accent: 'gray' },
]

const loading = ref(true)
const kanban = ref({})
const dragCard = ref(null)
const viewMode = ref('kanban')
const showStats = ref(false)
const selectedCards = ref(new Set())
const resumeVersions = ref([])
const versionPerformance = ref([])
const totalCards = computed(() =>
  columns.reduce((sum, col) => sum + (kanban.value[col.key] || []).length, 0)
)

// 所有卡片扁平列表
const allCards = computed(() => {
  const all = []
  columns.forEach((col) => {
    ;(kanban.value[col.key] || []).forEach((card) => {
      all.push(card)
    })
  })
  return all
})

// 统计计算
const counts = computed(() => {
  const map = {}
  columns.forEach((col) => {
    map[col.key] = (kanban.value[col.key] || []).length
  })
  return map
})

const funnelData = computed(() =>
  columns
    .filter((c) => ['todo', 'applied', 'written_test', 'interview', 'offer'].includes(c.key))
    .map((c) => ({
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
  if (idx <= 0) return Math.round(((counts.value[stage] || 0) / total) * 100)
  const prevTotal = stageOrder.slice(0, idx).reduce((s, k) => s + (counts.value[k] || 0), 0)
  const current = counts.value[stage] || 0
  const base = prevTotal + current
  return base > 0 ? Math.round((current / base) * 100) : 0
}

const rejectionRate = computed(() => {
  const total = totalCards.value
  if (!total) return 0
  return Math.round((((counts.value.rejected || 0) + (counts.value.withdrawn || 0)) / total) * 100)
})

const avgResponseDays = computed(() => {
  const now = Date.now()
  const applied = kanban.value.applied || []
  const days = applied
    .filter((c) => c.update_time)
    .map((c) => Math.round((now - new Date(c.update_time).getTime()) / 86400000))
  if (!days.length) return '--'
  const avg = Math.round(days.reduce((s, d) => s + d, 0) / days.length)
  return avg + 'd'
})

const followUpCount = computed(
  () => allCards.value.filter((card) => needsFollowUp(card) && followUpDays(card) >= 3).length
)
const pipelineFocusTitle = computed(() => {
  if (counts.value.offer) return '优先完成 Offer 取舍与确认。'
  if (counts.value.interview) return '把面试机会转化为可执行的准备计划。'
  if (followUpCount.value) return '有投递记录等待跟进，先处理超 3 天未回复的机会。'
  return '继续补充高匹配岗位，让投递保持稳定节奏。'
})
const pipelineFocusDescription = computed(() => {
  if (counts.value.offer) return 'Offer 已进入决策阶段，比较整体回报、成长空间与截止日期。'
  if (counts.value.interview) return '从看板直接发起模拟面试，并把准备情况沉淀在对应机会中。'
  if (followUpCount.value) return '优先处理等待时间较长的投递，避免遗漏有效机会。'
  return '从岗位推荐中挑选高匹配机会，加入看板后持续追踪。'
})

function funnelPercent(count) {
  const max = Math.max(1, ...funnelData.value.map((s) => s.count))
  return Math.max(2, (count / max) * 100)
}

function stageToRate(from, to) {
  const fromCount = counts.value[from] || 0
  const toCount = counts.value[to] || 0
  if (!fromCount) return '0%'
  return Math.round((toCount / fromCount) * 100) + '%'
}

function stageTagType(stage) {
  const map = {
    todo: 'info',
    applied: 'primary',
    written_test: 'warning',
    interview: 'success',
    offer: 'success',
    rejected: 'danger',
    withdrawn: 'info',
  }
  return map[stage] || 'info'
}

// 跟进提醒
function needsFollowUp(card) {
  return (card.stage === 'applied' || card.stage === 'written_test') && card.update_time
}

function followUpDays(card) {
  if (!card.update_time) return 0
  return Math.round((Date.now() - new Date(card.update_time).getTime()) / 86400000)
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
const feedbackSaving = ref(false)
const feedbackForm = ref({ feedback_type: '', feedback_score: 0, feedback_note: '' })
const loadError = ref('')

const addForm = ref({
  title: '',
  company: '',
  salary_range: '',
  source: '',
  note: '',
  resume_version_id: null,
})

const addRules = {
  title: [{ required: true, message: '请输入岗位名称', trigger: 'blur' }],
}

function stageLabel(stage) {
  const map = {
    todo: '待投递',
    applied: '已投递',
    written_test: '笔试',
    interview: '面试',
    offer: 'Offer',
    accepted: '已入职',
    rejected: '已拒绝',
    withdrawn: '已放弃',
  }
  return map[stage] || stage || '-'
}

async function loadKanban() {
  loading.value = true
  try {
    const [data, stats] = await Promise.all([getKanban(), getPipelineResumeVersionStats()])
    kanban.value = data?.stages || data || {}
    versionPerformance.value = stats?.items || []
    loadError.value = ''
  } catch (error) {
    kanban.value = {}
    loadError.value = error?.userMessage || '暂时无法获取投递记录，请检查网络后重试。'
  } finally {
    loading.value = false
  }
}

async function loadResumeVersions() {
  try {
    const data = await getPipelineResumeVersions()
    resumeVersions.value = data?.items || []
  } catch {
    resumeVersions.value = []
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
    const idx = fromList.findIndex((c) => c.id === card.id)
    if (idx >= 0) {
      fromList.splice(idx, 1)
      card.stage = targetStage
      toList.unshift(card)
    }
    ElMessage.success(`已移至「${columns.find((c) => c.key === targetStage)?.label}」`)
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
      resume_id:
        resumeVersions.value.find((version) => version.id === addForm.value.resume_version_id)
          ?.resume_id || null,
    })
    ElMessage.success('投递记录已添加')
    showAddDialog.value = false
    addForm.value = {
      title: '',
      company: '',
      salary_range: '',
      source: '',
      note: '',
      resume_version_id: null,
    }
    loadKanban()
  } catch {
    // 失败消息由统一请求层提示。
  } finally {
    addSubmitting.value = false
  }
}

async function handleCardCmd(cmd, card) {
  if (cmd === 'detail') {
    detailCard.value = card
    feedbackForm.value = {
      feedback_type: card.feedback_type || '',
      feedback_score: card.feedback_score || 0,
      feedback_note: card.feedback_note || '',
    }
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
    } catch {
      // 失败消息由统一请求层提示。
    }
  } else if (cmd === 'abandon') {
    try {
      await movePipelineStage(card.id, 'withdrawn')
      ElMessage.success('已放弃')
      loadKanban()
    } catch {
      // 失败消息由统一请求层提示。
    }
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm('确定删除此投递记录？', '删除确认', { type: 'warning' })
      await deleteJobPipelineEntry(card.id)
      ElMessage.success('已删除')
      loadKanban()
    } catch {
      // 用户取消删除或请求失败时保持当前看板。
    }
  }
}

// === 列表视图方法 ===
function showCardDetail(card) {
  detailCard.value = card
  feedbackForm.value = {
    feedback_type: card.feedback_type || '',
    feedback_score: card.feedback_score || 0,
    feedback_note: card.feedback_note || '',
  }
  showDetailDialog.value = true
}

async function saveFeedback() {
  if (!detailCard.value || (!feedbackForm.value.feedback_type && !feedbackForm.value.feedback_note))
    return
  feedbackSaving.value = true
  try {
    await updateJobPipelineEntry(detailCard.value.id, feedbackForm.value)
    ElMessage.success('反馈已保存')
    await loadKanban()
  } finally {
    feedbackSaving.value = false
  }
}

function handleListCmd(cmd, card) {
  if (cmd === 'interview') {
    router.push(`/interview/setup?jd_id=${card.jd_id || ''}`)
  } else if (cmd === 'reject') {
    movePipelineStage(card.id, 'rejected')
      .then(() => {
        ElMessage.success('已标记拒绝')
        loadKanban()
      })
      .catch(() => {})
  } else if (cmd === 'abandon') {
    movePipelineStage(card.id, 'withdrawn')
      .then(() => {
        ElMessage.success('已放弃')
        loadKanban()
      })
      .catch(() => {})
  } else if (cmd === 'delete') {
    ElMessageBox.confirm('确定删除此投递记录？', '删除确认', { type: 'warning' })
      .then(() => {
        deleteJobPipelineEntry(card.id)
          .then(() => {
            ElMessage.success('已删除')
            loadKanban()
          })
          .catch(() => {})
      })
      .catch(() => {})
  }
}

function onSelectionChange(rows) {
  selectedCards.value = new Set(rows.map((r) => r.id))
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
    } catch {
      // 继续处理剩余投递，并在结束后汇总结果。
    }
  }
  const message = `成功将 ${success}/${ids.length} 项移至「${stageLabel(targetStage)}」`
  if (success === ids.length) ElMessage.success(message)
  else ElMessage.warning(message)
  selectedCards.value = new Set()
  loadKanban()
}

onMounted(() => {
  loadKanban()
  loadResumeVersions()
})
</script>

<style scoped>
.page-shell {
  color: var(--app-text);
}

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

.header-actions {
  display: flex;
  gap: 8px;
}

.pipeline-focus-strip {
  display: grid;
  grid-template-columns: minmax(260px, 1.4fr) minmax(240px, 0.9fr) auto;
  gap: 20px;
  align-items: center;
  margin-bottom: 16px;
  padding: 18px 20px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.focus-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.focus-message strong {
  display: block;
  margin-top: 6px;
  color: var(--app-text);
  font-size: 17px;
}

.focus-message p {
  margin: 6px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}

.focus-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-right: 1px solid var(--app-line);
  border-left: 1px solid var(--app-line);
}

.focus-metrics div {
  display: grid;
  gap: 4px;
  padding: 2px 14px;
  text-align: center;
}

.focus-metrics div + div {
  border-left: 1px solid var(--app-line);
}

.focus-metrics b {
  color: var(--app-primary-dark);
  font-size: 23px;
  line-height: 1;
}

.focus-metrics span {
  color: var(--app-muted);
  font-size: 12px;
}

.focus-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.version-performance {
  margin-bottom: 16px;
  border: 1px solid var(--app-line);
  border-top: 3px solid var(--app-primary);
  border-radius: 8px;
  background: var(--app-surface-strong);
}

.version-performance-title {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--app-line);
}

.version-performance-title h3 {
  margin: 2px 0 0;
  font-size: 15px;
}

.version-performance-title > span,
.version-name span,
.version-metric span,
.version-outcomes {
  color: var(--app-muted);
  font-size: 12px;
}

.section-kicker {
  color: var(--app-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.version-performance-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.version-performance-row {
  display: grid;
  grid-template-columns: minmax(105px, 1fr) auto auto;
  gap: 14px;
  align-items: center;
  padding: 14px 16px;
  border-right: 1px solid var(--app-line);
  border-bottom: 1px solid var(--app-line);
}

.version-name,
.version-metric {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.version-name strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-metric {
  align-items: flex-end;
}

.version-metric strong {
  color: var(--app-primary);
  font-size: 17px;
}

.version-outcomes {
  grid-column: 1 / -1;
  display: flex;
  gap: 10px;
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
  border-radius: var(--app-radius-sm, 8px);
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
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-sm, 8px) var(--app-radius-sm, 8px) 0 0;
}

.col-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-slate {
  background: #94a3b8;
}
.dot-blue {
  background: var(--app-primary);
}
.dot-amber {
  background: var(--app-warning);
}
.dot-violet {
  background: var(--app-violet);
}
.dot-green {
  background: var(--app-success);
}
.dot-red {
  background: var(--app-danger);
}
.dot-gray {
  background: #9ca3af;
}

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
  border-radius: var(--app-radius-xs, 6px);
  background: var(--app-surface-strong);
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

.resume-version-tag {
  max-width: 100%;
  margin-top: 8px;
  color: #365c8d;
}

.version-cell {
  display: inline-block;
  max-width: 120px;
  overflow: hidden;
  color: #365c8d;
  text-overflow: ellipsis;
  vertical-align: bottom;
  white-space: nowrap;
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

.full-width {
  width: 100%;
}

.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 20px;
  justify-content: center;
}

.feedback-entry {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--app-line);
  font-size: 13px;
}

.feedback-controls {
  display: flex;
  align-items: center;
  gap: 12px;
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
.follow-danger {
  background: #fff3f0;
  color: #d46e6e;
}
.follow-warn {
  background: #fffaf1;
  color: #dc9c3f;
}
.follow-ok {
  background: #f0faf4;
  color: #67c23a;
}

/* View toggle */
.view-toggle {
  margin-right: 4px;
}

/* 统计面板 */
.stats-panel {
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
  overflow: hidden;
}
.stats-header {
  padding: 14px 20px;
  border-bottom: 1px solid var(--app-line);
}
.stats-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}
.stats-body {
  padding: 16px 20px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.stat-item {
  text-align: center;
  padding: 12px 8px;
  border-radius: 6px;
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
.funnel-label {
  color: var(--app-muted);
}
.funnel-count {
  font-weight: 700;
  color: var(--app-text);
}
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
.fill-slate {
  background: #94a3b8;
}
.fill-blue {
  background: var(--app-primary);
}
.fill-amber {
  background: var(--app-warning);
}
.fill-violet {
  background: var(--app-violet);
}
.fill-green {
  background: var(--app-success);
}
.fill-red {
  background: var(--app-danger);
}
.funnel-arrow {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: var(--app-muted);
  margin-top: 2px;
}
.funnel-rate {
  color: var(--app-primary);
  font-weight: 600;
}

/* 列表视图 */
.list-view {
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--app-line);
  overflow: hidden;
}
.list-title {
  font-weight: 600;
  font-size: 14px;
}
.follow-interview {
  color: var(--app-violet);
  font-weight: 600;
}
.score-level {
  font-weight: 600;
}
.score-level--high {
  color: var(--app-score-high);
}
.score-level--good {
  color: var(--app-score-good);
}
.score-level--warn {
  color: var(--app-score-warn);
}
.score-level--risk {
  color: var(--app-score-risk);
}
.score-level--unknown {
  color: var(--app-score-unknown);
}

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
.batch-info strong {
  color: var(--app-primary);
}

@media (max-width: 1024px) {
  .pipeline-focus-strip {
    grid-template-columns: 1fr 1fr;
  }

  .focus-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
    padding-top: 12px;
    border-top: 1px solid var(--app-line);
  }

  .kanban-board {
    flex-wrap: wrap;
  }
  .kanban-col {
    max-width: none;
    min-width: 200px;
  }
}

@media (max-width: 768px) {
  .pipeline-focus-strip,
  .focus-metrics {
    grid-template-columns: 1fr;
  }

  .focus-metrics {
    gap: 8px;
    border: 0;
  }

  .focus-metrics div,
  .focus-metrics div + div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
    text-align: left;
  }

  .load-error {
    align-items: flex-start;
    flex-direction: column;
  }
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
