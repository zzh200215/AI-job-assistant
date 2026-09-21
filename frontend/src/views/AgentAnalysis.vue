<template>
  <div class="page-shell agent-analysis-page">
    <div class="page-header">
      <div>
        <h2>Agentic RAG 智能分析</h2>
      </div>
    </div>

    <section v-if="taskId" class="agent-focus-strip" aria-label="Agent 任务摘要">
      <div class="agent-focus-main">
        <span class="agent-focus-label">当前任务</span>
        <strong>{{ taskStatusLabel || '等待任务状态' }}</strong>
        <p>{{ agentFocusDescription }}</p>
      </div>
      <div class="agent-focus-metrics">
        <div>
          <b>{{ completedCount }}/{{ steps.length }}</b
          ><span>完成步骤</span>
        </div>
        <div>
          <b>{{ retrievalResultCount }}</b
          ><span>证据片段</span>
        </div>
        <div>
          <b>{{ passedChecks }}/{{ checks.length }}</b
          ><span>自检通过</span>
        </div>
      </div>
      <div class="agent-focus-action">
        <span class="agent-focus-label">可追溯性</span>
        <p>可查看检索证据、输入输出与 Prompt 执行记录。</p>
        <el-button size="small" type="primary" @click="openPromptTrace">打开 Prompt 追踪</el-button>
      </div>
    </section>

    <div class="panel">
      <div class="panel-body">
        <el-form :inline="true">
          <el-form-item label="简历 ID">
            <el-input-number v-model="form.resume_id" :min="1" />
          </el-form-item>
          <el-form-item label="JD ID">
            <el-input-number v-model="form.jd_id" :min="1" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="starting" @click="onStart">
              <el-icon><Promotion /></el-icon>
              {{ starting ? '启动中' : '启动 Agent 分析' }}
            </el-button>
            <el-button @click="fillLast">填充最近 ID</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <div class="panel" v-if="taskId">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>任务 #{{ taskId }} 执行流水线</h3>
          <el-tag :type="taskStatusTag" size="small">{{ taskStatusLabel }}</el-tag>
        </div>
        <div class="task-head-actions">
          <el-button size="small" @click="openTaskCenter">任务中心</el-button>
          <el-button size="small" type="primary" plain @click="openPromptTrace"
            >Prompt 追踪</el-button
          >
        </div>
      </div>
      <div class="panel-body">
        <el-descriptions
          v-if="taskUsage.tokens_used || taskUsage.cost_cents"
          :column="2"
          border
          size="small"
          class="usage-summary"
        >
          <el-descriptions-item label="Token 用量">{{
            formatTokens(taskUsage.tokens_used)
          }}</el-descriptions-item>
          <el-descriptions-item label="预估成本">{{
            formatCost(taskUsage.cost_cents)
          }}</el-descriptions-item>
        </el-descriptions>

        <el-timeline>
          <el-timeline-item
            v-for="step in steps"
            :key="step.step_index"
            :timestamp="step.completed_at || ''"
            :type="stepStatusType(step)"
            :hollow="step.status === 'pending'"
            placement="top"
            size="large"
          >
            <div class="step-header">
              <el-tag :type="stepStatusType(step)" size="small" effect="dark" class="step-badge">
                {{ stepLabel(step.step_name) }}
              </el-tag>
              <span v-if="step.duration_ms" class="step-duration">{{ step.duration_ms }}ms</span>
            </div>

            <div class="step-status-text">{{ stepStatusText(step.status) }}</div>

            <div v-if="step.status === 'running'" class="running-indicator">
              <el-icon class="is-loading"><Loading /></el-icon> 执行中
            </div>

            <div v-if="step.status === 'completed' && step.output_data" class="step-output">
              <div v-if="step.step_name === 'intent_recognition'" class="output-preview">
                意图: <b>{{ step.output_data.intent || '-' }}</b>
                <span v-if="typeof step.output_data.confidence === 'number'">
                  | 置信度 {{ (step.output_data.confidence * 100).toFixed(0) }}%
                </span>
              </div>
              <div v-else-if="step.step_name === 'task_planning'" class="output-preview">
                拆解为 {{ step.output_data.steps_count || 0 }} 个子任务
              </div>
              <div v-else-if="step.step_name === 'match_analysis'" class="output-preview">
                匹配度评分 <b>{{ step.output_data.match_score ?? '-' }}</b>
              </div>
              <div v-else-if="step.step_name === 'self_check'" class="output-preview">
                校验结果: {{ step.output_data.passed ? '通过' : '发现问题' }}
              </div>
              <div v-else-if="step.step_name === 'knowledge_retrieval'" class="output-preview">
                检索了 {{ Object.keys(step.output_data.retrievals || {}).length }} 类知识库
              </div>
            </div>

            <div v-if="step.status === 'failed'" class="step-error">
              {{ step.error_msg || '执行失败' }}
            </div>
          </el-timeline-item>
        </el-timeline>

        <div v-if="steps.length || retrievals.length || checks.length" class="trace-section">
          <div class="trace-stats">
            <div class="trace-stat-card">
              <span>步骤数</span>
              <strong>{{ steps.length }}</strong>
            </div>
            <div class="trace-stat-card">
              <span>检索次数</span>
              <strong>{{ retrievals.length }}</strong>
            </div>
            <div class="trace-stat-card">
              <span>召回文档</span>
              <strong>{{ retrievalResultCount }}</strong>
            </div>
            <div class="trace-stat-card">
              <span>自检通过</span>
              <strong>{{ passedChecks }}/{{ checks.length }}</strong>
            </div>
          </div>

          <el-tabs class="trace-tabs">
            <el-tab-pane :label="`检索日志 (${retrievals.length})`">
              <el-empty v-if="!retrievals.length" description="暂无检索日志" />
              <div v-else class="trace-list">
                <div v-for="item in retrievals" :key="item.id" class="trace-card">
                  <div class="trace-card-head">
                    <strong>{{ item.query_text }}</strong>
                    <div class="trace-card-tags">
                      <el-tag size="small" type="info">Top {{ item.top_k }}</el-tag>
                      <el-tag size="small">{{ item.result_count }} 条</el-tag>
                      <el-tag v-if="item.duration_ms" size="small" type="success"
                        >{{ item.duration_ms }}ms</el-tag
                      >
                    </div>
                  </div>
                  <div class="trace-meta">
                    <span>文档类型：{{ item.doc_type_filter || '全部' }}</span>
                    <span>步骤日志：#{{ item.step_log_id || '-' }}</span>
                  </div>
                  <div v-if="item.results?.length" class="trace-result-list">
                    <div
                      v-for="(resultItem, idx) in item.results.slice(0, 5)"
                      :key="`${item.id}-${idx}`"
                      class="trace-result-item"
                    >
                      <div class="trace-result-title">
                        {{
                          resultItem.title ||
                          resultItem.doc_title ||
                          resultItem.metadata?.title ||
                          `结果 ${idx + 1}`
                        }}
                      </div>
                      <div class="trace-meta">
                        <span
                          >分数：{{
                            firstDefined(
                              resultItem.final_score,
                              resultItem.score,
                              resultItem.similarity,
                              '-'
                            )
                          }}</span
                        >
                        <span
                          >来源：{{
                            resultItem.doc_type || resultItem.metadata?.doc_type || 'unknown'
                          }}</span
                        >
                      </div>
                      <div class="trace-snippet">
                        {{
                          snippetOf(
                            resultItem.text ||
                              resultItem.content ||
                              resultItem.chunk ||
                              resultItem.metadata?.text
                          )
                        }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="`自检日志 (${checks.length})`">
              <el-empty v-if="!checks.length" description="暂无自检日志" />
              <div v-else class="trace-list">
                <div v-for="item in checks" :key="item.id" class="trace-card">
                  <div class="trace-card-head">
                    <strong>{{ item.check_target || '自检项' }}</strong>
                    <div class="trace-card-tags">
                      <el-tag :type="item.passed ? 'success' : 'warning'" size="small">
                        {{ item.passed ? '通过' : '待修正' }}
                      </el-tag>
                      <el-tag
                        v-if="item.score !== null && item.score !== undefined"
                        size="small"
                        type="info"
                      >
                        {{ item.score }}
                      </el-tag>
                      <el-tag v-if="item.retry_needed" size="small" type="danger">建议重试</el-tag>
                    </div>
                  </div>
                  <div class="trace-grid">
                    <div>
                      <div class="trace-block-title">问题</div>
                      <ul class="trace-bullet-list">
                        <li
                          v-for="(issue, idx) in normalizeList(item.issues)"
                          :key="`issue-${item.id}-${idx}`"
                        >
                          {{ issue }}
                        </li>
                      </ul>
                    </div>
                    <div>
                      <div class="trace-block-title">改进建议</div>
                      <pre class="code-block">{{ formatJson(item.improvement) }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="`步骤 I/O (${steps.length})`">
              <el-empty v-if="!steps.length" description="暂无步骤明细" />
              <el-collapse v-else class="step-io-list">
                <el-collapse-item v-for="step in steps" :key="step.id" :name="String(step.id)">
                  <template #title>
                    <div class="step-io-title">
                      <strong>{{ stepLabel(step.step_name) }}</strong>
                      <span>{{ stepStatusText(step.status) }}</span>
                      <span v-if="step.duration_ms">{{ step.duration_ms }}ms</span>
                    </div>
                  </template>
                  <div class="trace-grid">
                    <div>
                      <div class="trace-block-title">输入</div>
                      <pre class="code-block">{{ formatJson(step.input_data) }}</pre>
                    </div>
                    <div>
                      <div class="trace-block-title">输出</div>
                      <pre class="code-block">{{ formatJson(step.output_data) }}</pre>
                    </div>
                  </div>
                  <div v-if="step.error_msg" class="step-error">
                    {{ step.error_msg }}
                  </div>
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </div>

    <div class="panel" v-if="finalReport">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>最终报告</h3>
        </div>
      </div>
      <div class="panel-body">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="候选人">{{
            finalReport.summary?.candidate_name || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="目标岗位">{{
            finalReport.summary?.target_position || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="匹配度">
            <el-tag :type="scoreToneTagType(finalReport.summary?.match_score)">
              {{ finalReport.summary?.match_score ?? '-' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="推荐建议">{{
            localizedSummaryRecommendation
          }}</el-descriptions-item>
          <el-descriptions-item label="综合评价" :span="2">
            {{ localizedOverallEvaluation }}
          </el-descriptions-item>
        </el-descriptions>

        <el-tabs>
          <el-tab-pane label="匹配分析">
            <el-row :gutter="16">
              <el-col
                v-for="(value, key) in finalReport.match_analysis?.dimension_scores || {}"
                :key="key"
                :span="6"
              >
                <div class="dim-card">
                  <div class="dim-label">{{ localizeDimensionLabel(key) }}</div>
                  <div class="dim-score">{{ value }}</div>
                </div>
              </el-col>
            </el-row>
            <h4>优势</h4>
            <ul>
              <li v-for="(item, idx) in localizedAgentStrengths" :key="idx">{{ item }}</li>
            </ul>
            <h4>短板</h4>
            <ul>
              <li v-for="(item, idx) in localizedAgentGaps" :key="idx">{{ item }}</li>
            </ul>
          </el-tab-pane>

          <el-tab-pane label="优化建议">
            <ul>
              <li v-for="(item, idx) in localizedOptimizationKeyPoints" :key="idx">
                <b>要点{{ idx + 1 }}：</b>{{ item }}
              </li>
            </ul>
            <h4>快速可执行</h4>
            <ul>
              <li v-for="(item, idx) in localizedQuickWins" :key="idx">{{ item }}</li>
            </ul>
          </el-tab-pane>

          <el-tab-pane label="面试指南">
            <p>重点考察领域：</p>
            <el-tag
              v-for="item in finalReport.interview_guide?.focus_areas || []"
              :key="item"
              style="margin: 2px"
            >
              {{ localizeSentence(item) }}
            </el-tag>
            <h4>准备建议</h4>
            <p>{{ localizedWeaknessPreparation }}</p>
          </el-tab-pane>

          <el-tab-pane label="发展建议">
            <h4>短期</h4>
            <ul>
              <li v-for="(item, idx) in localizedShortTermAdvice" :key="idx">{{ item }}</li>
            </ul>
            <h4>长期</h4>
            <ul>
              <li v-for="(item, idx) in localizedLongTermAdvice" :key="idx">{{ item }}</li>
            </ul>
          </el-tab-pane>

          <el-tab-pane label="质量保障">
            <el-alert
              :title="`自我校验评分: ${finalReport.quality_assurance?.self_check_score || 0}`"
              :type="
                scoreToneAtLeast(finalReport.quality_assurance?.self_check_score, 'good')
                  ? 'success'
                  : 'warning'
              "
              :closable="false"
              show-icon
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <div class="panel" v-if="taskId && !isTerminalTask">
      <div class="panel-body">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            <el-icon class="is-loading"><Loading /></el-icon>
            分析进行中，已完成 {{ completedCount }} / {{ steps.length }} 步
          </template>
        </el-alert>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from '@/plugins/element-services'
import { Promotion, Loading } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { getAgentSteps, startAgentAnalysis } from '@/api/agent'
import {
  localizeDimensionLabel,
  localizeRecommendationText,
  localizeSentence,
  normalizeLocalizedTextList,
} from '@/utils/analysisLocalization'
import { scoreToneAtLeast, scoreToneTagType } from '@/utils/scoreTone'

const route = useRoute()
const router = useRouter()
const starting = ref(false)
const taskId = ref(null)
const task = ref(null)
const steps = ref([])
const retrievals = ref([])
const checks = ref([])

const form = reactive({ resume_id: null, jd_id: null })
let pollTimer = null

const TASK_STATUS_LABELS = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  partial: '部分完成',
  failed: '失败',
  cancelled: '已取消',
}

const TASK_STATUS_TAGS = {
  pending: 'info',
  running: 'warning',
  completed: 'success',
  partial: 'warning',
  failed: 'danger',
  cancelled: 'info',
}

const STEP_STATUS_TEXTS = {
  pending: '等待执行',
  running: '执行中',
  completed: '执行成功',
  partial: '部分完成',
  failed: '执行失败',
  cancelled: '任务已取消',
}

const taskStatusLabel = computed(
  () => TASK_STATUS_LABELS[task.value?.status] || task.value?.status || ''
)
const taskStatusTag = computed(() => TASK_STATUS_TAGS[task.value?.status] || 'info')
const isTerminalTask = computed(() =>
  ['completed', 'partial', 'failed', 'cancelled'].includes(task.value?.status)
)
const completedCount = computed(
  () => steps.value.filter((step) => step.status === 'completed').length
)
const retrievalResultCount = computed(() =>
  retrievals.value.reduce((sum, item) => sum + Number(item.result_count || 0), 0)
)
const passedChecks = computed(() => checks.value.filter((item) => Boolean(item.passed)).length)
const agentFocusDescription = computed(() => {
  if (task.value?.status === 'completed') return '任务已完成，可从最终报告回看结论与依据。'
  if (task.value?.status === 'partial') return '任务部分完成，优先查看未完成步骤和可用结果。'
  if (task.value?.status === 'failed') return '任务失败，查看出错步骤后重试或调整输入。'
  if (task.value?.status === 'cancelled') return '任务已取消，可保留当前痕迹或重新发起分析。'
  return '任务正在执行，系统会持续更新步骤、检索和自检结果。'
})
const finalReport = computed(() => task.value?.final_report || null)
const taskUsage = computed(() => task.value?.usage || { tokens_used: 0, cost_cents: 0 })
const localizedSummaryRecommendation = computed(() =>
  localizeRecommendationText(finalReport.value?.summary?.recommendation || '')
)
const localizedOverallEvaluation = computed(() =>
  localizeSentence(finalReport.value?.summary?.overall_evaluation || '')
)
const localizedAgentStrengths = computed(() =>
  normalizeLocalizedTextList(finalReport.value?.match_analysis?.strengths)
)
const localizedAgentGaps = computed(() =>
  normalizeLocalizedTextList(finalReport.value?.match_analysis?.gaps)
)
const localizedOptimizationKeyPoints = computed(() =>
  normalizeLocalizedTextList(finalReport.value?.optimization_suggestions?.key_points)
)
const localizedQuickWins = computed(() =>
  normalizeLocalizedTextList(finalReport.value?.optimization_suggestions?.quick_wins)
)
const localizedWeaknessPreparation = computed(() =>
  localizeSentence(finalReport.value?.interview_guide?.weakness_preparation || '')
)
const localizedShortTermAdvice = computed(() =>
  normalizeLocalizedTextList(finalReport.value?.development_advice?.short_term)
)
const localizedLongTermAdvice = computed(() =>
  normalizeLocalizedTextList(finalReport.value?.development_advice?.long_term)
)

function fillLast() {
  const rid = localStorage.getItem('recruit.lastResumeId')
  const jid = localStorage.getItem('recruit.lastJDId')
  if (rid) form.resume_id = Number(rid)
  if (jid) form.jd_id = Number(jid)
}

async function onStart() {
  if (!form.resume_id || !form.jd_id) {
    ElMessage.warning('请先填写简历 ID 和 JD ID')
    return
  }

  starting.value = true
  try {
    const data = await startAgentAnalysis({
      resume_id: form.resume_id,
      jd_id: form.jd_id,
    })
    taskId.value = data.task_id
    await router.replace({
      path: route.path,
      query: { ...route.query, task_id: String(data.task_id) },
    })
    ElMessage.success('工作流已启动')
    await pollSteps()
  } catch {
    // request.js already handles message
  } finally {
    starting.value = false
  }
}

async function pollSteps() {
  if (!taskId.value) return

  try {
    const data = await getAgentSteps(taskId.value)
    task.value = data.task
    steps.value = data.steps || []
    retrievals.value = data.retrievals || []
    checks.value = data.checks || []
  } catch {
    // ignore transient polling errors
  }

  if (!isTerminalTask.value) {
    pollTimer = setTimeout(pollSteps, 1500)
  }
}

const CANONICAL_AGENT_STEP_LABELS = {
  match_analysis: '匹配分析',
  interview_questions: '面试题生成',
  career_planning: '职业规划',
  summary_report: '汇总报告',
}

function stepLabel(name) {
  return (
    {
      intent_recognition: '意图识别',
      resume_parse: '简历解析',
      jd_parse: 'JD 解析',
      task_planning: '任务规划',
      knowledge_retrieval: '知识检索',
      matching_analysis: '匹配度分析',
      resume_optimization: '简历优化',
      interview_question_generation: '面试题生成',
      self_check: '自我校验',
      final_report: '汇总报告',
    }[name] ||
    CANONICAL_AGENT_STEP_LABELS[name] ||
    name
  )
}

function stepStatusType(step) {
  if (step.status === 'completed') return 'primary'
  if (step.status === 'running') return 'warning'
  if (step.status === 'failed') return 'danger'
  return 'info'
}

function stepStatusText(status) {
  return STEP_STATUS_TEXTS[status] || status
}

function formatTokens(tokens) {
  const value = Number(tokens || 0)
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k tokens`
  return `${value} tokens`
}

function formatCost(costCents) {
  const value = Number(costCents || 0)
  if (!value) return '$0.0000'
  return `$${(value / 100).toFixed(4)}`
}

function openTaskCenter() {
  router.push('/tasks')
}

function openPromptTrace() {
  if (!taskId.value) return
  router.push({
    name: 'prompt-traces',
    query: {
      task_id: String(taskId.value),
      analysis_record_id: task.value?.analysis_record_id
        ? String(task.value.analysis_record_id)
        : undefined,
    },
  })
}

function normalizeList(value) {
  if (Array.isArray(value) && value.length) return value
  return ['暂无']
}

function formatJson(value) {
  if (value === null || value === undefined || value === '') return '暂无数据'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function snippetOf(value) {
  const text = String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return '暂无片段'
  if (text.length <= 180) return text
  return `${text.slice(0, 177)}...`
}

function firstDefined(...values) {
  const found = values.find((value) => value !== null && value !== undefined && value !== '')
  return found ?? '-'
}

onMounted(() => {
  fillLast()
})

watch(
  () => route.query.task_id,
  (tid) => {
    const nextTaskId = Number(tid)
    if (!tid || Number.isNaN(nextTaskId) || nextTaskId <= 0) {
      if (pollTimer) {
        clearTimeout(pollTimer)
        pollTimer = null
      }
      taskId.value = null
      task.value = null
      steps.value = []
      retrievals.value = []
      checks.value = []
      return
    }

    if (taskId.value === nextTaskId && (task.value || steps.value.length)) {
      return
    }

    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }

    taskId.value = nextTaskId
    task.value = null
    steps.value = []
    retrievals.value = []
    checks.value = []
    pollSteps()
  },
  { immediate: true }
)

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<style scoped>
.agent-focus-strip {
  display: grid;
  grid-template-columns: minmax(250px, 1.2fr) minmax(240px, 0.9fr) minmax(230px, 0.9fr);
  gap: 0;
  margin-bottom: 18px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}
.agent-focus-strip > div {
  min-width: 0;
  padding: 18px 20px;
  border-left: 1px solid var(--app-line);
}
.agent-focus-strip > div:first-child {
  border-left: 0;
}
.agent-focus-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.agent-focus-main strong {
  display: block;
  margin-top: 7px;
  color: var(--app-text);
  font-size: 18px;
}
.agent-focus-strip p {
  margin: 7px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}
.agent-focus-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.agent-focus-metrics div {
  display: grid;
  gap: 4px;
  padding: 2px 10px;
  text-align: center;
}
.agent-focus-metrics div + div {
  border-left: 1px solid var(--app-line);
}
.agent-focus-metrics b {
  color: var(--app-primary-dark);
  font-size: 21px;
  line-height: 1;
}
.agent-focus-metrics span {
  color: var(--app-muted);
  font-size: 12px;
}
.agent-focus-action .el-button {
  margin-top: 12px;
}
.task-card-head,
.task-head-actions,
.trace-stats,
.trace-card-head,
.trace-card-tags,
.trace-grid,
.step-io-title {
  display: flex;
  gap: 10px;
}

.task-card-head,
.trace-card-head {
  align-items: center;
  justify-content: space-between;
}

.task-head-actions,
.trace-card-tags,
.step-io-title {
  flex-wrap: wrap;
  align-items: center;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.step-badge {
  font-size: 13px;
}
.step-duration {
  color: var(--app-muted);
  font-size: 11px;
}
.step-status-text {
  color: var(--app-text);
  font-size: 13px;
  margin-bottom: 4px;
}
.step-output {
  background: var(--app-bg);
  padding: 6px 10px;
  border-radius: var(--app-radius-xs, 8px);
  font-size: 12px;
  color: var(--app-text);
}
.step-error {
  color: var(--app-danger);
  font-size: 12px;
  margin-top: 4px;
}
.running-indicator {
  color: var(--app-warning);
}
.usage-summary {
  margin-bottom: 16px;
}
.output-preview {
  color: var(--app-primary);
}
.trace-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.trace-stats {
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.trace-stat-card {
  min-width: 120px;
  padding: 12px 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}
.trace-stat-card span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}
.trace-stat-card strong {
  display: block;
  margin-top: 6px;
  font-size: 22px;
  color: var(--app-text);
}
.trace-tabs {
  margin-top: 8px;
}
.trace-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.trace-card {
  padding: 14px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}
.trace-meta {
  margin-top: 6px;
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--app-muted);
}
.trace-result-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.trace-result-item {
  padding: 10px 12px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-surface-strong);
  border: 1px solid var(--el-border-color-lighter);
}
.trace-result-title {
  font-weight: 600;
  color: var(--app-text);
}
.trace-snippet {
  margin-top: 6px;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.6;
}
.trace-grid {
  align-items: flex-start;
  margin-top: 12px;
}
.trace-grid > div {
  flex: 1;
  min-width: 0;
}
.trace-block-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--app-muted);
}
.trace-bullet-list {
  margin: 0;
  padding-left: 18px;
  color: var(--app-muted);
}
.step-io-list {
  margin-top: 4px;
}
.step-io-title {
  width: 100%;
  justify-content: space-between;
  padding-right: 12px;
}
.code-block {
  margin: 0;
  padding: 12px;
  border-radius: var(--app-radius-sm, 12px);
  background: #0f1720;
  color: #dde7f2;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow: auto;
}
.dim-card {
  text-align: center;
  padding: 8px;
  background: var(--app-bg);
  border-radius: var(--app-radius-xs, 8px);
}
.dim-label {
  font-size: 12px;
  color: var(--app-muted);
}
.dim-score {
  font-size: 24px;
  font-weight: 700;
  color: var(--app-primary);
}
h4 {
  margin: 12px 0 6px;
}
ul {
  padding-left: 18px;
  margin: 4px 0;
}

@media (max-width: 768px) {
  .agent-focus-strip,
  .agent-focus-metrics {
    grid-template-columns: 1fr;
  }
  .agent-focus-strip > div,
  .agent-focus-strip > div:first-child {
    border-top: 1px solid var(--app-line);
    border-left: 0;
  }
  .agent-focus-strip > div:first-child {
    border-top: 0;
  }
  .agent-focus-metrics {
    gap: 8px;
  }
  .agent-focus-metrics div,
  .agent-focus-metrics div + div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
    text-align: left;
  }
  .agent-focus-action .el-button {
    width: 100%;
  }

  .task-card-head,
  .trace-card-head,
  .trace-grid,
  .step-io-title {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
