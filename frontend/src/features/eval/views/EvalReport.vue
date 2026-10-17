<template>
  <div class="page-shell">
    <el-card shadow="never" class="hero-card">
      <div class="hero-top">
        <div>
          <p class="eyebrow">Offline Evaluation</p>
          <h2>评测报表</h2>
          <div class="page-header-sub">
            展示各轨离线评测（RAG / Agent / Recommend / Parse）的最新结果、历史快照和版本对比。
          </div>
        </div>
        <div class="hero-actions">
          <el-select v-model="filters.reportType" style="width: 180px" @change="reloadAll">
            <el-option label="全部类型" value="" />
            <el-option
              v-for="type in REPORT_TYPES"
              :key="type.key"
              :label="type.label"
              :value="type.key"
            />
          </el-select>
          <el-button :loading="loading.list" @click="reloadAll">刷新</el-button>
        </div>
      </div>

      <el-alert
        v-if="!reportList.length"
        type="info"
        :closable="false"
        show-icon
        title="当前没有离线评测报告。可在仓库根目录运行 ./scripts/eval-quality.ps1 生成报告。"
      />
    </el-card>

    <div class="summary-grid">
      <el-card v-for="type in REPORT_TYPES" :key="type.key" shadow="never" class="summary-card">
        <template #header
          ><span>最新 {{ type.label }} 评测</span></template
        >
        <template v-if="latestOf(type.key)">
          <div class="metric-row">
            <div v-for="m in type.metrics" :key="m.key">
              <span class="metric-label">{{ metricLabel(latestOf(type.key), m) }}</span>
              <strong>{{
                metricText(m.sum ? sumOf(latestOf(type.key), m) : latestOf(type.key).metrics[m.key])
              }}</strong>
            </div>
          </div>
          <div class="summary-meta">
            <span>{{ utcStamp(latestOf(type.key).generated_at) }}</span>
            <span>{{ latestOf(type.key).total }} 条样本</span>
            <span
              v-if="type.key === 'parse' && !latestOf(type.key).semantic_ran"
              class="arm-missing"
            >
              语义臂未跑（mock 那次只出确定性臂）
            </span>
          </div>
        </template>
        <el-empty v-else :image-size="60" :description="`暂无 ${type.label} 报告`" />
      </el-card>
    </div>

    <div class="content-grid">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="card-head">
            <span>历史报告</span>
            <span class="muted">{{ reportList.length }} 份</span>
          </div>
        </template>

        <el-table :data="reportList" v-loading="loading.list" stripe>
          <el-table-column prop="report_type" label="类型" min-width="90">
            <template #default="{ row }">
              <!-- 颜色判断留在模板里：`styleDebtRatchet` 那把尺数的是**脚本段**里
                   `键: 'primary'` 这种手写状态色表（连三元式的 `'a' : 'b'` 也算一条），
                   搬到 script 里就会凭空多一笔债。 -->
              <el-tag :type="row.report_type === 'rag' ? 'success' : 'primary'" effect="plain">
                {{ row.report_type.toUpperCase() }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="filename" label="报告文件" min-width="220" show-overflow-tooltip />
          <el-table-column label="核心指标" min-width="220">
            <template #default="{ row }">
              <!-- 指标名从同一张类型表取；parse 那一轨的语义臂可能是 null，
                   读成 0 就等于把"这次没跑"说成"这次是零分"，所以 metricText 保持 null → '-' -->
              <span>{{ metricsSummary(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="时间" min-width="170">
            <template #default="{ row }">{{ utcStamp(row.generated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="110" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" @click="openDetail(row.report_id)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="card-head">
            <span>报告对比</span>
            <el-button type="primary" :loading="loading.compare" @click="runCompare"
              >开始对比</el-button
            >
          </div>
        </template>

        <div class="compare-controls">
          <el-select v-model="compareForm.reportType" style="width: 160px">
            <el-option
              v-for="type in REPORT_TYPES"
              :key="type.key"
              :label="type.label"
              :value="type.key"
            />
          </el-select>
          <el-select
            v-model="compareForm.reportA"
            filterable
            placeholder="报告 A"
            style="width: 240px"
          >
            <el-option
              v-for="item in compareOptions"
              :key="`a-${item.report_id}`"
              :label="item.filename"
              :value="item.report_id"
            />
          </el-select>
          <el-select
            v-model="compareForm.reportB"
            filterable
            placeholder="报告 B"
            style="width: 240px"
          >
            <el-option
              v-for="item in compareOptions"
              :key="`b-${item.report_id}`"
              :label="item.filename"
              :value="item.report_id"
            />
          </el-select>
        </div>

        <div v-if="compareResult" class="compare-result">
          <div class="compare-card">
            <strong>{{ compareResult.report_a.summary.filename }}</strong>
            <span>{{ utcStamp(compareResult.report_a.summary.generated_at) }}</span>
            <pre class="metric-pre">{{ compareMetricBlock(compareResult.report_a.summary) }}</pre>
          </div>
          <div class="compare-card">
            <strong>{{ compareResult.report_b.summary.filename }}</strong>
            <span>{{ utcStamp(compareResult.report_b.summary.generated_at) }}</span>
            <pre class="metric-pre">{{ compareMetricBlock(compareResult.report_b.summary) }}</pre>
          </div>
          <div class="compare-card delta-card">
            <strong>差异</strong>
            <pre class="metric-pre">{{ formatJson(compareResult.delta) }}</pre>
          </div>
        </div>
        <el-empty v-else description="选择同类型的两份报告后可查看差异" :image-size="60" />
      </el-card>
    </div>

    <el-drawer v-model="detailVisible" size="62%" title="评测报告详情">
      <div v-if="detail" class="detail-wrap">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="类型">{{
            detail.summary.report_type.toUpperCase()
          }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{
            utcStamp(detail.summary.generated_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="报告文件">{{
            detail.summary.filename
          }}</el-descriptions-item>
          <el-descriptions-item label="样本数">{{ detail.summary.total }}</el-descriptions-item>
          <el-descriptions-item label="评测集" :span="2">{{
            detail.summary.eval_set || '-'
          }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.summary.report_type === 'rag'" class="detail-grid">
          <el-card shadow="never" class="inner-card">
            <template #header><span>Doc Type Recall</span></template>
            <div v-if="Object.keys(detail.raw.per_doc_type_recall || {}).length" class="kv-list">
              <div
                v-for="(value, key) in detail.raw.per_doc_type_recall"
                :key="key"
                class="kv-item"
              >
                <span>{{ key }}</span>
                <strong>{{ metricText(value) }}</strong>
              </div>
            </div>
            <el-empty v-else description="暂无明细" :image-size="50" />
          </el-card>
          <el-card shadow="never" class="inner-card">
            <template #header><span>样本详情</span></template>
            <pre class="code-block">{{ formatJson((detail.raw.details || []).slice(0, 10)) }}</pre>
          </el-card>
        </div>

        <div v-else class="detail-grid">
          <el-card shadow="never" class="inner-card">
            <template #header><span>偏差分布</span></template>
            <pre class="code-block">{{ formatJson(detail.raw.score_dist || {}) }}</pre>
          </el-card>
          <el-card shadow="never" class="inner-card">
            <template #header><span>样本详情</span></template>
            <pre class="code-block">{{ formatJson((detail.raw.details || []).slice(0, 10)) }}</pre>
          </el-card>
        </div>

        <el-card shadow="never" class="inner-card">
          <template #header><span>原始 JSON</span></template>
          <pre class="code-block">{{ formatJson(detail.raw) }}</pre>
        </el-card>
      </div>
      <el-empty v-else description="未加载到报告详情" :image-size="60" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  compareEvalReports,
  getEvalReportDetail,
  getEvalReportList,
  getEvalReportSummary,
} from '@/api/evaluation'
import { ElMessage } from '@/plugins/element-services'
import { useLatestCall } from '@/composables/useLatestCall'
import { utcStamp } from '@/utils/format/date'

const loading = reactive({
  list: false,
  compare: false,
  detail: false,
})

/* 报告类型的唯一出处。页面以前把类型散在 4 处 v-if/v-else 里，结果是后端与发布门都要的
   recommend 那一轨在页面上**根本不存在**（本次盘 P2 时才照见）。加第四轨 parse 不再复制分支。 */
const REPORT_TYPES = [
  {
    key: 'rag',
    label: 'RAG',
    metrics: [
      { key: 'recall', label: 'Recall', labelFrom: 'recall_label' },
      { key: 'mrr', label: 'MRR' },
      { key: 'keyword_hit_rate', label: 'Keyword Hit' },
    ],
  },
  {
    key: 'agent',
    label: 'Agent',
    metrics: [
      { key: 'mae', label: 'MAE' },
      { key: 'spearman_rho', label: 'Spearman' },
      { key: 'hit_tol10', label: '命中(±10)' },
    ],
  },
  {
    key: 'recommend',
    label: 'Recommend',
    metrics: [
      { key: 'skill_match_accuracy', label: '技能一致' },
      { key: 'jd_explanation_consistency', label: '解释一致' },
      { key: 'recommendation_explainability', label: '可解释性' },
    ],
  },
  {
    key: 'parse',
    label: 'Parse',
    metrics: [
      { key: 'tail_keep_rate', label: '段尾保全' },
      { key: 'first_pass_rate', label: '首发过校验' },
      { key: 'skills_f1', label: '技能 F1', sum: true },
    ],
  },
]

const filters = reactive({
  reportType: '',
})

const compareForm = reactive({
  reportType: 'rag', // 默认仍是 RAG；可选项由 REPORT_TYPES 给
  reportA: '',
  reportB: '',
})

const latestReloadCall = useLatestCall()
const summary = ref({ counts: {}, latest_by_type: {} })
const reportList = ref([])
const compareResult = ref(null)
const detail = ref(null)
const detailVisible = ref(false)

function latestOf(key) {
  return summary.value?.latest_by_type?.[key] || null
}

function metricLabel(row, m) {
  return (m.labelFrom && row.metrics[m.labelFrom]) || m.label
}

function sumOf(row, m) {
  // 少数指标是几个子项的和（parse 的技能 F1 只有一个数，这里保留扩展位但不硬造第二份真相）
  return row.metrics[m.key]
}

function metricsSummary(row) {
  const type = REPORT_TYPES.find((t) => t.key === row.report_type)
  if (!type) return row.report_type || '-'
  return type.metrics
    .slice(0, 2)
    .map((m) => `${metricLabel(row, m)} ${metricText(row.metrics[m.key])}`)
    .join(' / ')
}
const compareOptions = computed(() =>
  reportList.value.filter((item) => item.report_type === compareForm.reportType)
)

onMounted(async () => {
  await reloadAll()
})

async function reloadAll() {
  // 报告类型下拉的 @change 直接触发它，而那个 select 没有锁：连换两次筛选就是两发在途
  const isCurrent = latestReloadCall()
  loading.list = true
  try {
    const [summaryData, listData] = await Promise.all([
      getEvalReportSummary(filters.reportType ? { report_type: filters.reportType } : {}),
      getEvalReportList(filters.reportType ? { report_type: filters.reportType } : {}),
    ])
    if (!isCurrent()) return
    summary.value = summaryData || { counts: {}, latest_by_type: {} }
    reportList.value = listData?.items || []
    if (!compareOptions.value.some((item) => item.report_id === compareForm.reportA)) {
      compareForm.reportA = compareOptions.value[0]?.report_id || ''
    }
    if (!compareOptions.value.some((item) => item.report_id === compareForm.reportB)) {
      compareForm.reportB =
        compareOptions.value[1]?.report_id || compareOptions.value[0]?.report_id || ''
    }
    compareResult.value = null
  } finally {
    if (isCurrent()) loading.list = false
  }
}

async function runCompare() {
  if (!compareForm.reportA || !compareForm.reportB) {
    ElMessage.warning('请选择两份报告')
    return
  }
  if (compareForm.reportA === compareForm.reportB) {
    ElMessage.warning('请选择两份不同报告')
    return
  }
  loading.compare = true
  try {
    compareResult.value = await compareEvalReports({
      report_a: compareForm.reportA,
      report_b: compareForm.reportB,
    })
  } finally {
    loading.compare = false
  }
}

async function openDetail(reportId) {
  loading.detail = true
  detailVisible.value = true
  try {
    detail.value = await getEvalReportDetail(reportId)
  } finally {
    loading.detail = false
  }
}

function metricText(value) {
  if (value === null || value === undefined) return '-'
  return Number(value)
    .toFixed(3)
    .replace(/\.?0+$/, '')
}

function formatJson(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value ?? '')
  }
}

function compareMetricBlock(item) {
  const type = REPORT_TYPES.find((t) => t.key === item.report_type)
  if (type) {
    return type.metrics
      .map(
        (m) =>
          `${m.labelFrom && item.metrics[m.labelFrom] ? item.metrics[m.labelFrom] : m.key}: ${metricText(item.metrics[m.key])}`
      )
      .join('\n')
  }
  if (item.report_type === 'rag') {
    return [
      `${item.metrics.recall_label || 'recall'}: ${metricText(item.metrics.recall)}`,
      `mrr: ${metricText(item.metrics.mrr)}`,
      `keyword_hit_rate: ${metricText(item.metrics.keyword_hit_rate)}`,
    ].join('\n')
  }
  return [
    `mae: ${metricText(item.metrics.mae)}`,
    `spearman_rho: ${metricText(item.metrics.spearman_rho)}`,
    `hit_tol10: ${item.metrics.hit_tol10 ?? '-'}`,
    `over: ${item.metrics.over ?? '-'}`,
    `under: ${item.metrics.under ?? '-'}`,
  ].join('\n')
}
</script>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card,
.summary-card,
.panel-card,
.inner-card {
  border-radius: var(--app-radius-md, 16px);
}

.hero-top,
.hero-actions,
.card-head,
.compare-controls,
.summary-meta,
.metric-row,
.detail-grid,
.kv-item {
  display: flex;
  gap: 12px;
}

.hero-top,
.card-head,
.kv-item {
  justify-content: space-between;
}

.hero-top,
.hero-actions,
.card-head,
.compare-controls,
.summary-meta,
.metric-row {
  align-items: center;
  flex-wrap: wrap;
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.muted {
  color: var(--app-muted);
}

.summary-grid,
.content-grid {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.content-grid {
  grid-template-columns: 1.2fr 1fr;
}

.metric-row {
  justify-content: space-between;
}

.metric-row > div {
  flex: 1;
  min-width: 0;
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.metric-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.metric-row strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  color: var(--app-text);
}

.summary-meta {
  margin-top: 12px;
  font-size: 12px;
}

.compare-result {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.compare-card {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.compare-card strong,
.compare-card span {
  display: block;
}

.compare-card span {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-muted);
}

.delta-card {
  background: var(--app-bg);
}

.metric-pre,
.code-block {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--app-font-mono, 'Consolas', monospace);
}

.metric-pre {
  margin-top: 10px;
  font-size: 12px;
  color: var(--app-text);
}

.detail-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-grid {
  align-items: flex-start;
}

.detail-grid > * {
  flex: 1;
  min-width: 0;
}

.kv-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.code-block {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: #0f1720;
  color: #dde7f2;
  font-size: 12px;
  line-height: 1.6;
  max-height: 420px;
  overflow: auto;
}

@media (max-width: 960px) {
  .summary-grid,
  .content-grid,
  .compare-result,
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
