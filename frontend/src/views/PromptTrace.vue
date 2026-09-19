<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>Prompt 追踪</h2>
        <div class="page-header-sub">版本对比、实验分组和结果回放</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-body">
        <el-select
          v-model="filters.source"
          clearable
          filterable
          placeholder="按来源筛选"
          style="width: 260px"
          @change="reloadAll"
        >
          <el-option
            v-for="item in summary.sources || []"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
        <el-select
          v-model="filters.prompt_version"
          clearable
          filterable
          placeholder="按版本筛选"
          style="width: 180px"
          @change="reloadAll"
        >
          <el-option
            v-for="item in summary.versions || []"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
        <el-select
          v-model="filters.status"
          clearable
          placeholder="状态"
          style="width: 140px"
          @change="reloadAll"
        >
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-select
          v-model="filters.response_source"
          clearable
          placeholder="应答来源"
          style="width: 160px"
          @change="reloadAll"
        >
          <el-option
            v-for="item in summary.response_sources || []"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
        <el-select
          v-model="filters.degraded"
          clearable
          placeholder="是否降级"
          style="width: 140px"
          @change="reloadAll"
        >
          <el-option label="仅非主模型应答" value="true" />
          <el-option label="仅主模型应答" value="false" />
        </el-select>
        <el-input
          v-model.trim="filters.request_id"
          clearable
          placeholder="Request ID"
          style="width: 220px"
          @change="reloadAll"
        />
        <el-input-number
          v-model="filters.task_id"
          :min="1"
          controls-position="right"
          placeholder="任务 ID"
          style="width: 160px"
          @change="reloadAll"
        />
        <el-input-number
          v-model="filters.analysis_record_id"
          :min="1"
          controls-position="right"
          placeholder="分析记录 ID"
          style="width: 180px"
          @change="reloadAll"
        />
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </div>

    <el-alert
      v-if="scopeHint"
      class="scope-alert"
      type="info"
      :closable="false"
      show-icon
      :title="scopeHint"
    />

    <div class="grid-6">
      <div class="stat-card">
        <div class="stat-value">{{ summary.total || 0 }}</div>
        <div class="stat-label">总调用</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ percentText(summary.success_rate || 0) }}</div>
        <div class="stat-label">成功率</div>
      </div>
      <div class="stat-card" :class="{ 'stat-card-alert': degradedCount > 0 }">
        <div class="stat-value">{{ percentText(summary.degraded_rate || 0) }}</div>
        <div class="stat-label">
          非主模型应答 {{ degradedCount }} 次<span v-if="degradedBreakdown">（{{ degradedBreakdown }}）</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.avg_duration_ms ?? '-' }}</div>
        <div class="stat-label">平均耗时(ms)</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.avg_total_tokens ?? '-' }}</div>
        <div class="stat-label">平均 Tokens</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.avg_cost_cents ?? '-' }}</div>
        <div class="stat-label">平均成本(cents)</div>
      </div>
    </div>

    <div class="dual-grid">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <h3>版本对比</h3>
          </div>
          <el-button type="primary" size="small" :loading="loading.compare" @click="runCompare"
            >开始对比</el-button
          >
        </div>
        <div class="panel-body">
          <div class="compare-controls">
            <el-select
              v-model="compareForm.source"
              clearable
              filterable
              placeholder="选择来源"
              style="width: 260px"
            >
              <el-option
                v-for="item in summary.sources || []"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
            <el-select
              v-model="compareForm.versionA"
              filterable
              placeholder="版本 A"
              style="width: 180px"
            >
              <el-option
                v-for="item in compareVersionOptions"
                :key="`a-${item}`"
                :label="item"
                :value="item"
              />
            </el-select>
            <el-select
              v-model="compareForm.versionB"
              filterable
              placeholder="版本 B"
              style="width: 180px"
            >
              <el-option
                v-for="item in compareVersionOptions"
                :key="`b-${item}`"
                :label="item"
                :value="item"
              />
            </el-select>
          </div>

          <div v-if="compareResult" class="compare-grid">
            <div class="compare-col">
              <div class="compare-title">{{ compareResult.version_a.prompt_version }}</div>
              <div class="compare-metrics">
                <div>调用数：{{ compareResult.version_a.metrics.total }}</div>
                <div>
                  成功率：{{ percentText(compareResult.version_a.metrics.success_rate || 0) }}
                </div>
                <div>平均耗时：{{ compareResult.version_a.metrics.avg_duration_ms ?? '-' }}</div>
                <div>
                  平均 Tokens：{{ compareResult.version_a.metrics.avg_total_tokens ?? '-' }}
                </div>
                <div>平均成本：{{ compareResult.version_a.metrics.avg_cost_cents ?? '-' }}</div>
              </div>
            </div>
            <div class="compare-col">
              <div class="compare-title">{{ compareResult.version_b.prompt_version }}</div>
              <div class="compare-metrics">
                <div>调用数：{{ compareResult.version_b.metrics.total }}</div>
                <div>
                  成功率：{{ percentText(compareResult.version_b.metrics.success_rate || 0) }}
                </div>
                <div>平均耗时：{{ compareResult.version_b.metrics.avg_duration_ms ?? '-' }}</div>
                <div>
                  平均 Tokens：{{ compareResult.version_b.metrics.avg_total_tokens ?? '-' }}
                </div>
                <div>平均成本：{{ compareResult.version_b.metrics.avg_cost_cents ?? '-' }}</div>
              </div>
            </div>
            <div class="compare-col delta-col">
              <div class="compare-title">差异</div>
              <div class="compare-metrics">
                <div>成功率差：{{ signed(compareResult.delta.success_rate, true) }}</div>
                <div>耗时差：{{ signed(compareResult.delta.avg_duration_ms) }}</div>
                <div>Tokens 差：{{ signed(compareResult.delta.avg_total_tokens) }}</div>
                <div>成本差：{{ signed(compareResult.delta.avg_cost_cents) }}</div>
              </div>
            </div>
          </div>
          <el-empty v-else :image-size="72" description="选择两个版本后可查看对比结果" />
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title-row">
            <h3>实验分组</h3>
          </div>
          <span class="muted">按 source + prompt_version 聚合</span>
        </div>
        <div class="panel-body">
          <div v-if="summary.version_groups?.length" class="group-list">
            <div
              v-for="item in summary.version_groups"
              :key="`${item.source}-${item.prompt_version}`"
              class="group-item"
            >
              <div class="group-top">
                <strong>{{ item.prompt_version }}</strong>
                <span>{{ item.source }}</span>
              </div>
              <div class="group-meta">
                <span>{{ item.total }} 次</span>
                <span>成功率 {{ percentText(item.success_rate || 0) }}</span>
                <span>均耗时 {{ item.avg_duration_ms ?? '-' }}</span>
              </div>
            </div>
          </div>
          <el-empty v-else :image-size="72" description="暂无版本样本" />
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>调用明细</h3>
        </div>
        <span class="muted">点击查看完整 Prompt 与输出回放</span>
      </div>
      <div class="panel-body">
        <el-table :data="traceList.items" v-loading="loading.list" stripe class="trace-table">
          <el-table-column prop="created_at" label="时间" min-width="168">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="source" label="来源" min-width="220" show-overflow-tooltip />
          <el-table-column prop="prompt_version" label="版本" min-width="120" />
          <el-table-column prop="model" label="模型" min-width="140" />
          <el-table-column prop="response_source" label="应答来源" min-width="120">
            <template #default="{ row }">
              <el-tag :type="sourceTagType(row)" effect="plain">
                {{ sourceLabel(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" min-width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'success' ? 'success' : 'danger'" effect="plain">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="duration_ms" label="耗时" min-width="90" />
          <el-table-column prop="total_tokens" label="Tokens" min-width="90" />
          <el-table-column prop="cost_cents" label="成本" min-width="110" />
          <el-table-column label="操作" fixed="right" min-width="100">
            <template #default="{ row }">
              <el-button text type="primary" @click="openDetail(row.id)">回放</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pager-row">
          <el-pagination
            background
            layout="prev, pager, next, total"
            :current-page="pagination.page"
            :page-size="pagination.page_size"
            :total="traceList.total || 0"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </div>

    <el-drawer v-model="detailVisible" size="58%" title="Prompt 结果回放">
      <div v-if="detail" class="detail-wrap">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="来源">{{ detail.source }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ detail.prompt_version }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ detail.model }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
          <el-descriptions-item label="Request ID">{{
            detail.request_id || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="任务 ID">{{ detail.task_id ?? '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-tabs class="detail-tabs">
          <el-tab-pane label="Prompt">
            <pre class="code-block">{{ detail.prompt_text || '暂无 Prompt 文本' }}</pre>
          </el-tab-pane>
          <el-tab-pane label="Response JSON">
            <pre class="code-block">{{ responseJsonText }}</pre>
          </el-tab-pane>
          <el-tab-pane label="Response Text">
            <pre class="code-block">{{ detail.response_text || '暂无原始文本输出' }}</pre>
          </el-tab-pane>
          <el-tab-pane label="Error">
            <pre class="code-block">{{ detail.error_message || '无错误信息' }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>
      <el-empty v-else :image-size="72" description="未加载到回放详情" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ElMessage } from '@/plugins/element-services'
import {
  comparePromptTraceVersions,
  getPromptTraceDetail,
  getPromptTraceList,
  getPromptTraceSummary,
} from '@/api/promptTrace'

const loading = reactive({
  summary: false,
  list: false,
  compare: false,
  detail: false,
})

const route = useRoute()
const router = useRouter()

const filters = reactive({
  source: '',
  prompt_version: '',
  status: '',
  response_source: '',
  degraded: '',
  request_id: '',
  task_id: null,
  analysis_record_id: null,
})

const pagination = reactive({
  page: 1,
  page_size: 20,
})

const compareForm = reactive({
  source: '',
  versionA: '',
  versionB: '',
})

const summary = reactive({
  total: 0,
  success_rate: 0,
  avg_duration_ms: null,
  avg_total_tokens: null,
  avg_cost_cents: null,
  sources: [],
  versions: [],
  version_groups: [],
})

const traceList = reactive({
  items: [],
  total: 0,
})

const compareResult = ref(null)
const detail = ref(null)
const detailVisible = ref(false)
const scopeHint = computed(() => {
  if (filters.task_id && filters.analysis_record_id) {
    return `当前按任务 #${filters.task_id} 和分析记录 #${filters.analysis_record_id} 查看全链路追踪`
  }
  if (filters.task_id) {
    return `当前按任务 #${filters.task_id} 查看全链路追踪`
  }
  if (filters.analysis_record_id) {
    return `当前按分析记录 #${filters.analysis_record_id} 查看追踪`
  }
  return ''
})

const RESPONSE_SOURCES = {
  real: { label: '主模型', type: 'success' },
  fallback_model: { label: '备用模型', type: 'warning' },
  truncated: { label: '截断提示', type: 'warning' },
  mock: { label: 'Mock 模板', type: 'danger' },
  tool_output: { label: '工具输出', type: 'warning' },
  unknown: { label: '未知', type: 'info' },
}

function sourceMeta(row) {
  return RESPONSE_SOURCES[row?.response_source] || { label: row?.response_source || '未知', type: 'info' }
}

function sourceLabel(row) {
  return sourceMeta(row).label
}

function sourceTagType(row) {
  // A row written before response provenance existed reports `unknown`; only
  // flag it when the degraded column itself says so.
  if (row?.degraded && row?.response_source !== 'unknown') return sourceMeta(row).type
  if (row?.degraded) return 'warning'
  return sourceMeta(row).type
}

const degradedCount = computed(() => summary.degraded_count || 0)

const degradedBreakdown = computed(() => {
  const bySource = summary.degraded_by_source || {}
  return Object.entries(bySource)
    .map(([key, count]) => `${(RESPONSE_SOURCES[key] || { label: key }).label} ${count}`)
    .join(' / ')
})

const compareVersionOptions = computed(() => {
  const groups = summary.version_groups || []
  const filtered = compareForm.source
    ? groups.filter((item) => item.source === compareForm.source)
    : groups
  return [...new Set(filtered.map((item) => item.prompt_version).filter(Boolean))]
})

const responseJsonText = computed(() => {
  if (!detail.value?.response_json) return '暂无结构化输出'
  try {
    return JSON.stringify(detail.value.response_json, null, 2)
  } catch {
    return String(detail.value.response_json)
  }
})

onMounted(async () => {
  hydrateFiltersFromRoute()
  await reloadAll()
})

async function reloadAll() {
  pagination.page = 1
  syncRouteQuery()
  await Promise.all([loadSummary(), loadList()])
}

async function loadSummary() {
  loading.summary = true
  try {
    const data = await getPromptTraceSummary(buildFilterParams())
    Object.assign(summary, {
      total: data?.total || 0,
      success_rate: data?.success_rate || 0,
      avg_duration_ms: data?.avg_duration_ms ?? null,
      avg_total_tokens: data?.avg_total_tokens ?? null,
      avg_cost_cents: data?.avg_cost_cents ?? null,
      sources: data?.sources || [],
      versions: data?.versions || [],
      version_groups: data?.version_groups || [],
    })
    if (!compareForm.source || !summary.sources.includes(compareForm.source)) {
      compareForm.source = filters.source || summary.sources[0] || ''
    }
  } finally {
    loading.summary = false
  }
}

async function loadList() {
  loading.list = true
  try {
    const data = await getPromptTraceList({
      ...buildFilterParams(),
      page: pagination.page,
      page_size: pagination.page_size,
    })
    traceList.items = data?.items || []
    traceList.total = data?.total || 0
  } finally {
    loading.list = false
  }
}

async function runCompare() {
  if (!compareForm.versionA || !compareForm.versionB) {
    ElMessage.warning('请选择两个版本后再对比')
    return
  }
  if (compareForm.versionA === compareForm.versionB) {
    ElMessage.warning('请选择两个不同版本')
    return
  }
  loading.compare = true
  try {
    compareResult.value = await comparePromptTraceVersions({
      source: compareForm.source || undefined,
      version_a: compareForm.versionA,
      version_b: compareForm.versionB,
    })
  } finally {
    loading.compare = false
  }
}

async function openDetail(traceId) {
  loading.detail = true
  detailVisible.value = true
  try {
    detail.value = await getPromptTraceDetail(traceId)
  } finally {
    loading.detail = false
  }
}

function handlePageChange(page) {
  pagination.page = page
  syncRouteQuery()
  loadList()
}

function resetFilters() {
  filters.source = ''
  filters.prompt_version = ''
  filters.status = ''
  filters.response_source = ''
  filters.degraded = ''
  filters.request_id = ''
  filters.task_id = null
  filters.analysis_record_id = null
  compareResult.value = null
  reloadAll()
}

// `degraded` is a tri-state select rendered as '' | 'true' | 'false'.
function degradedParam() {
  if (filters.degraded === 'true' || filters.degraded === 'false') {
    return filters.degraded === 'true'
  }
  return undefined
}

function buildFilterParams() {
  return {
    source: filters.source || undefined,
    prompt_version: filters.prompt_version || undefined,
    status: filters.status || undefined,
    response_source: filters.response_source || undefined,
    degraded: degradedParam(),
    request_id: filters.request_id || undefined,
    task_id: filters.task_id || undefined,
    analysis_record_id: filters.analysis_record_id || undefined,
  }
}

function hydrateFiltersFromRoute() {
  filters.source = normalizeQueryText(route.query.source)
  filters.prompt_version = normalizeQueryText(route.query.prompt_version)
  filters.status = normalizeQueryText(route.query.status)
  filters.response_source = normalizeQueryText(route.query.response_source)
  filters.degraded = ['true', 'false'].includes(route.query.degraded) ? route.query.degraded : ''
  filters.request_id = normalizeQueryText(route.query.request_id)
  filters.task_id = normalizePositiveNumber(route.query.task_id)
  filters.analysis_record_id = normalizePositiveNumber(route.query.analysis_record_id)
  pagination.page = normalizePositiveNumber(route.query.page) || 1
}

function syncRouteQuery() {
  router.replace({
    query: {
      ...route.query,
      source: filters.source || undefined,
      prompt_version: filters.prompt_version || undefined,
      status: filters.status || undefined,
      response_source: filters.response_source || undefined,
      degraded: filters.degraded || undefined,
      request_id: filters.request_id || undefined,
      task_id: filters.task_id || undefined,
      analysis_record_id: filters.analysis_record_id || undefined,
      page: pagination.page > 1 ? String(pagination.page) : undefined,
    },
  })
}

function normalizeQueryText(value) {
  return typeof value === 'string' ? value : ''
}

function normalizePositiveNumber(value) {
  const num = Number(value)
  return Number.isInteger(num) && num > 0 ? num : null
}

function percentText(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function signed(value, percent = false) {
  if (value === null || value === undefined) return '-'
  const num = Number(value) || 0
  if (percent) return `${num >= 0 ? '+' : ''}${Math.round(num * 100)}%`
  return `${num >= 0 ? '+' : ''}${Number(num.toFixed(2))}`
}

function formatDate(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}
</script>

<style scoped>
.panel + .panel {
  margin-top: 16px;
}

.compare-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.muted {
  font-size: 12px;
  color: var(--app-muted);
}

.grid-6 {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card-alert {
  border-color: var(--app-danger);
}

.stat-card-alert .stat-value {
  color: var(--app-danger);
}

.stat-card {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--app-text);
  font-family: var(--app-font-mono);
}

.stat-label {
  margin-top: 6px;
  color: var(--app-muted);
  font-size: 12px;
}

.dual-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.compare-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.compare-col,
.group-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--app-line);
}

.compare-title,
.group-top strong {
  font-size: 14px;
  color: var(--app-text);
  font-weight: 700;
}

.compare-metrics,
.group-meta {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--app-muted);
}

.delta-col {
  background: var(--app-primary-light);
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 390px;
  overflow: auto;
}

.group-top {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.group-top span {
  font-size: 12px;
  color: var(--app-muted);
}

.trace-table :deep(.el-table__cell) {
  vertical-align: top;
}

.pager-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.detail-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-tabs {
  margin-top: 8px;
}

.code-block {
  margin: 0;
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: #0f1720;
  color: #dde7f2;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 520px;
  overflow: auto;
}

@media (max-width: 960px) {
  .grid-6 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .dual-grid,
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>
