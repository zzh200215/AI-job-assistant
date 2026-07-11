<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>Offer 决策</h2>
        <div class="page-header-sub">对比 Offer、评估薪资合理性、AI 辅助决策</div>
      </div>
    </div>

    <!-- Offer 列表 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-primary)"><Trophy /></el-icon>
          <h3>我的 Offer</h3>
        </div>
        <el-tag v-if="offers.length" type="success">{{ offers.length }} 个 Offer</el-tag>
      </div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon> 加载中...
        </div>
        <div v-else-if="!offers.length" class="empty-inline">
          暂无 Offer，继续投递加油
        </div>
        <div v-else class="offer-list">
          <div
            v-for="o in offers"
            :key="o.id"
            class="offer-row"
            :class="{ selected: selectedIds.includes(o.id) }"
            @click="toggleSelect(o.id)"
          >
            <el-checkbox
              :model-value="selectedIds.includes(o.id)"
              @click.stop
              @change="toggleSelect(o.id)"
            />
            <div class="offer-info">
              <strong>{{ o.company || '未知公司' }} - {{ o.title || '未知岗位' }}</strong>
              <span>{{ o.salary_range || '薪资未定' }}</span>
            </div>
            <div class="offer-meta">
              <span v-if="o.offer_deadline"><el-icon><Clock /></el-icon> {{ formatDate(o.offer_deadline) }} 到期</span>
              <span v-if="o.match_score"><el-icon><Histogram /></el-icon> 匹配 {{ Math.round(o.match_score) }}分</span>
            </div>
            <el-tag :type="deadlineUrgency(o.offer_deadline)" size="small">
              {{ deadlineLabel(o.offer_deadline) }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- 对比表 -->
    <div v-if="selectedOffers.length >= 2" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-violet)"><DataLine /></el-icon>
          <h3>Offer 对比</h3>
        </div>
      </div>
      <div class="panel-body">
        <div class="compare-table-wrap">
          <table class="compare-table">
            <thead>
              <tr>
                <th class="dim-col">维度</th>
                <th v-for="o in selectedOffers" :key="o.id">{{ o.company || '未知' }}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>岗位</td>
                <td v-for="o in selectedOffers" :key="o.id">{{ o.title || '-' }}</td>
              </tr>
              <tr>
                <td>薪资</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <strong>{{ o.salary_range || '-' }}</strong>
                </td>
              </tr>
              <tr>
                <td>城市</td>
                <td v-for="o in selectedOffers" :key="o.id">{{ o.city || o.location || '-' }}</td>
              </tr>
              <tr>
                <td>匹配分</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <span :class="scoreClass(o.match_score)">{{ o.match_score ? Math.round(o.match_score) : '-' }}</span>
                </td>
              </tr>
              <tr>
                <td>通勤</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.commute" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>成长空间</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.growth" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>稳定性</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.stability" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>技术栈</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.tech" :max="5" size="small" />
                </td>
              </tr>
              <tr class="total-row">
                <td>综合评分</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <strong class="total-score" :class="totalClass(o)">{{ totalScore(o) }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 薪资合理性 -->
    <div v-if="selectedOffers.length >= 1" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-success)"><Coin /></el-icon>
          <h3>薪资合理性评估</h3>
        </div>
        <el-button size="small" @click="loadSalaryInsight" :loading="salaryLoading">查询市场薪资</el-button>
      </div>
      <div class="panel-body">
        <div v-if="!salaryData" class="empty-inline">
          点击"查询市场薪资"查看该岗位的薪资分位数据
        </div>
        <div v-else>
          <div class="salary-stats">
            <div class="stat-card">
              <span class="stat-label">P25</span>
              <strong>{{ formatK(salaryData.p25) }}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">中位数</span>
              <strong>{{ formatK(salaryData.median) }}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">P75</span>
              <strong>{{ formatK(salaryData.p75) }}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">平均</span>
              <strong>{{ formatK(salaryData.avg) }}</strong>
            </div>
          </div>
          <p v-if="salaryData.sample_count" class="salary-note">
            基于 {{ salaryData.sample_count }} 条岗位数据
          </p>
        </div>
      </div>
    </div>

    <!-- AI 建议 -->
    <div v-if="selectedOffers.length >= 2" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-violet)"><MagicStick /></el-icon>
          <h3>AI 决策建议</h3>
        </div>
        <el-button size="small" type="primary" @click="generateAdvice" :loading="adviceLoading">
          生成建议
        </el-button>
      </div>
      <div class="panel-body">
        <div v-if="!adviceText" class="empty-inline">
          选择 2 个以上 Offer 后，点击"生成建议"获取 AI 分析
        </div>
        <div v-else class="advice-content">
          <p v-for="(line, idx) in adviceLines" :key="idx">{{ line }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Trophy,
  Clock,
  Histogram,
  DataLine,
  Coin,
  MagicStick,
  Loading,
} from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import { getJobPipelineList } from '@/api/jobs'
import { getSalaryOverview } from '@/api/salary'

const loading = ref(true)
const offers = ref([])
const selectedIds = ref([])
const salaryLoading = ref(false)
const salaryData = ref(null)
const adviceLoading = ref(false)
const adviceText = ref('')

const selectedOffers = computed(() =>
  offers.value.filter(o => selectedIds.value.includes(o.id))
)

const adviceLines = computed(() =>
  (adviceText.value || '').split('\n').filter(Boolean)
)

function formatDate(d) {
  if (!d) return ''
  try { return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) } catch { return d }
}

function formatK(v) {
  if (!v) return '-'
  return Number(v).toFixed(1) + 'K'
}

function deadlineUrgency(d) {
  if (!d) return 'info'
  const days = (new Date(d) - new Date()) / 86400000
  if (days <= 1) return 'danger'
  if (days <= 3) return 'warning'
  return 'success'
}

function deadlineLabel(d) {
  if (!d) return '无截止日期'
  const days = Math.ceil((new Date(d) - new Date()) / 86400000)
  if (days < 0) return '已过期'
  if (days === 0) return '今天到期'
  if (days <= 3) return `${days}天后到期`
  return `${days}天后到期`
}

function scoreClass(v) {
  if (!v) return ''
  if (v >= 80) return 'score-high'
  if (v >= 60) return 'score-mid'
  return 'score-low'
}

function totalScore(o) {
  const s = o._scores
  return ((s.commute + s.growth + s.stability + s.tech) * 5).toFixed(0)
}

function totalClass(o) {
  const t = Number(totalScore(o))
  if (t >= 80) return 'score-high'
  if (t >= 60) return 'score-mid'
  return 'score-low'
}

function toggleSelect(id) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

async function loadOffers() {
  loading.value = true
  try {
    const data = await getJobPipelineList({ stage: 'offer', limit: 50 })
    const items = data?.items || data || []
    offers.value = items.map(o => ({
      ...o,
      _scores: { commute: 3, growth: 3, stability: 3, tech: 3 },
    }))
    // auto select all if <= 4
    if (items.length <= 4 && items.length >= 2) {
      selectedIds.value = items.map(o => o.id)
    }
  } catch {} finally {
    loading.value = false
  }
}

async function loadSalaryInsight() {
  const offer = selectedOffers.value[0]
  if (!offer) return
  salaryLoading.value = true
  try {
    const position = offer.title || ''
    const city = offer.city || offer.location || ''
    const data = await getSalaryOverview({ position, city })
    salaryData.value = data
  } catch {
    ElMessage.error('薪资数据加载失败')
  } finally {
    salaryLoading.value = false
  }
}

async function generateAdvice() {
  if (selectedOffers.value.length < 2) {
    ElMessage.warning('请至少选择 2 个 Offer')
    return
  }
  adviceLoading.value = true
  try {
    // Build a simple comparison summary
    const lines = selectedOffers.value.map(o => {
      const ts = totalScore(o)
      return `${o.company}(${o.title}): 薪资${o.salary_range || '未知'}, 综合评分${ts}`
    })
    const best = [...selectedOffers.value].sort(
      (a, b) => Number(totalScore(b)) - Number(totalScore(a))
    )[0]

    adviceText.value = [
      `【综合评估】`,
      ...lines.map((l, i) => `${i + 1}. ${l}`),
      ``,
      `【建议】`,
      `从综合评分看，${best.company}(${best.title})得分最高(${totalScore(best)}分)。`,
      ``,
      `【决策参考】`,
      `- 如果看重薪资：选择薪资最高的选项`,
      `- 如果看重成长：选择成长空间评分最高的选项`,
      `- 如果看重稳定：选择稳定性评分最高的选项`,
      `- 如果看重技术：选择技术栈评分最高的选项`,
      ``,
      `提示：请根据个人实际情况调整上方评分，AI 建议仅供参考。`,
    ].join('\n')
  } finally {
    adviceLoading.value = false
  }
}

onMounted(() => {
  loadOffers()
})
</script>

<style scoped>
.panel + .panel {
  margin-top: 16px;
}

.empty-inline {
  text-align: center;
  padding: 16px 0;
  color: var(--app-muted);
  font-size: 14px;
}

/* Offer list */
.offer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.offer-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--app-radius-xs, 8px);
  cursor: pointer;
  transition: background 0.15s;
  border: 2px solid transparent;
}

.offer-row:hover {
  background: var(--el-fill-color-light);
}

.offer-row.selected {
  border-color: var(--app-primary);
  background: var(--app-primary-light);
}

.offer-info {
  flex: 1;
}

.offer-info strong {
  display: block;
  font-size: 14px;
}

.offer-info span {
  font-size: 12px;
  color: var(--app-muted);
}

.offer-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--app-muted);
}

.offer-meta span {
  display: flex;
  align-items: center;
  gap: 3px;
}

/* Compare table */
.compare-table-wrap {
  overflow-x: auto;
}

.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.compare-table th,
.compare-table td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  text-align: center;
}

.compare-table th {
  background: var(--el-fill-color-lighter);
  font-weight: 700;
  white-space: nowrap;
}

.compare-table .dim-col {
  text-align: left;
  font-weight: 600;
  background: var(--el-fill-color-lighter);
  min-width: 100px;
}

.compare-table td {
  min-width: 140px;
}

.total-row {
  background: var(--el-fill-color-lighter);
}

.total-score {
  font-size: 20px;
}

.score-high { color: var(--app-success); }
.score-mid { color: var(--app-warning); }
.score-low { color: var(--app-danger); }

/* Salary stats */
.salary-stats {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-card {
  text-align: center;
  padding: 12px 20px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--el-fill-color-lighter);
  min-width: 80px;
}

.stat-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.stat-card strong {
  font-size: 20px;
  font-weight: 700;
  color: var(--app-primary);
}

.salary-note {
  margin-top: 10px;
  font-size: 12px;
  color: var(--app-muted);
}

/* Advice */
.advice-content {
  line-height: 1.8;
  font-size: 14px;
  white-space: pre-wrap;
}

@media (max-width: 768px) {
  .compare-table th,
  .compare-table td {
    padding: 8px 10px;
    font-size: 13px;
  }
  .offer-meta {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
