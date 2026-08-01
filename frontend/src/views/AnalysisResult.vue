<template>
  <div class="page-shell analysis-result-page">
    <section class="result-hero">
      <div class="hero-copy">
        <span class="hero-kicker">Analysis Workspace</span>
        <h2>智能分析结果</h2>
        <div class="page-header-sub">先看结论，再看依据，最后决定下一步动作。</div>
      </div>
      <div class="hero-actions">
        <el-button @click="fillLast">填充最近 ID</el-button>
        <el-button type="primary" :loading="loading" @click="onAnalyze">
          <el-icon><Promotion /></el-icon>
          {{ loading ? '分析中' : '重新发起分析' }}
        </el-button>
      </div>
    </section>

    <div class="panel">
      <div class="panel-body">
        <el-form :inline="true" :model="form" class="control-form">
          <el-form-item label="简历 ID">
            <el-input-number v-model="form.resume_id" :min="1" placeholder="简历 ID" />
          </el-form-item>
          <el-form-item label="JD ID">
            <el-input-number v-model="form.jd_id" :min="1" placeholder="JD ID" />
          </el-form-item>
        </el-form>

        <el-alert
          v-if="lastIdsTip"
          type="info"
          :closable="false"
          show-icon
          :title="`检测到最近使用：简历 ID=${lastIdsTip.rid}，JD ID=${lastIdsTip.jid}`"
        />
      </div>
    </div>

    <el-alert
      v-if="analysisLoadError"
      class="load-error"
      type="error"
      :closable="false"
      show-icon
      title="分析结果加载失败"
      description="请检查网络连接后重试，或返回智能分析页重新发起任务。"
    >
      <template #default>
        <el-button size="small" type="primary" plain @click="retryLoadAnalysis">重试加载</el-button>
      </template>
    </el-alert>

    <div class="panel" v-if="loading && agentSteps.length">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>
            <el-icon class="is-loading"><Loading /></el-icon> 分析进度
          </h3>
          <el-tag type="warning" effect="plain"
            >{{ completedStepCount }} / {{ agentSteps.length }}</el-tag
          >
        </div>
      </div>
      <div class="panel-body">
        <div class="progress-grid">
          <div class="progress-stat">
            <span>当前阶段</span>
            <strong>{{ currentStepName }}</strong>
          </div>
          <div class="progress-stat">
            <span>已完成</span>
            <strong>{{ completedStepCount }}</strong>
          </div>
          <div class="progress-stat">
            <span>总步骤</span>
            <strong>{{ agentSteps.length }}</strong>
          </div>
        </div>

        <el-timeline>
          <el-timeline-item
            v-for="(s, i) in agentSteps"
            :key="i"
            :type="stepType(s.status)"
            :icon="stepIcon(s.status)"
          >
            <div class="step-title">{{ stepLabel(s.step_name) }}</div>
            <div class="step-status">
              {{ statusText(s.status) }} {{ s.duration_ms ? `(${s.duration_ms}ms)` : '' }}
            </div>
            <el-tag v-if="s.error_msg" size="small" type="danger">{{ s.error_msg }}</el-tag>
          </el-timeline-item>
        </el-timeline>
      </div>
    </div>

    <template v-if="result">
      <section class="decision-strip" aria-label="分析决策摘要">
        <div class="decision-conclusion">
          <span class="decision-label">结论</span>
          <strong>{{ localizedMatchRecommendation || '待评估' }}</strong>
          <p>{{ localizedMatchSummary || '当前报告尚未提供摘要。' }}</p>
        </div>
        <div class="decision-evidence">
          <span class="decision-label">关键依据</span>
          <div class="evidence-stats">
            <span
              ><b>{{ localizedStrengths.length }}</b> 项优势</span
            >
            <span
              ><b>{{ localizedGaps.length }}</b> 项待补齐</span
            >
            <span
              ><b>{{ localizedRiskPoints.length }}</b> 个风险点</span
            >
          </div>
          <p><b>优先处理：</b>{{ primaryGap }}</p>
        </div>
        <div class="decision-next">
          <span class="decision-label">下一步</span>
          <p>{{ priorityAction }}</p>
          <el-button type="primary" @click="onGenerateOptimized">
            <el-icon><EditPen /></el-icon> 生成优化版本
          </el-button>
        </div>
      </section>

      <section class="overview-grid">
        <div class="panel score-card">
          <div class="panel-body">
            <div class="score-shell">
              <span class="score-label">匹配度</span>
              <strong class="score-value">{{ result.match_score }}</strong>
              <p class="score-rec">{{ localizedMatchRecommendation || '待评估' }}</p>
              <p class="score-summary">{{ localizedMatchSummary || '暂无摘要' }}</p>
              <div class="score-actions">
                <el-button
                  size="small"
                  type="warning"
                  :loading="regenOptimizeLoading"
                  @click="onRegenOptimize"
                >
                  重生成优化建议
                </el-button>
                <el-button
                  size="small"
                  type="success"
                  :loading="regenIntervLoading"
                  @click="onRegenInterview"
                >
                  重生成面试题
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <div class="panel summary-card">
          <div class="panel-header">
            <div class="panel-title-row">
              <h3>这份结果告诉你什么</h3>
              <el-tag type="info" effect="plain">记录 {{ result.record_id || result.id }}</el-tag>
            </div>
          </div>
          <div class="panel-body">
            <div class="metric-grid">
              <div class="metric-item">
                <span>技能</span>
                <strong>{{ result.match_report?.dimension_scores?.skills?.score ?? 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>经验</span>
                <strong>{{ result.match_report?.dimension_scores?.experience?.score ?? 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>学历</span>
                <strong>{{ result.match_report?.dimension_scores?.education?.score ?? 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>行业</span>
                <strong>{{ result.match_report?.dimension_scores?.industry?.score ?? 0 }}</strong>
              </div>
            </div>

            <div class="next-actions">
              <el-button type="primary" @click="goInterview">
                <el-icon><ChatLineSquare /></el-icon> 去看面试题
              </el-button>
              <el-button @click="goCareer">职业规划</el-button>
              <el-button @click="goJobMarket">岗位市场</el-button>
            </div>
          </div>
        </div>
      </section>

      <div class="panel detail-card">
        <div class="panel-body">
          <el-tabs v-model="tab">
            <el-tab-pane label="匹配报告" name="match">
              <div class="detail-grid">
                <section class="detail-block">
                  <h3>优势</h3>
                  <ul>
                    <li v-for="(x, i) in localizedStrengths" :key="i">
                      <b>{{ x.item || x }}</b>
                      <span v-if="x.impact">：{{ x.impact }}</span>
                      <span v-if="x.evidence" class="muted">（{{ x.evidence }}）</span>
                    </li>
                  </ul>
                </section>

                <section class="detail-block">
                  <h3>差距</h3>
                  <ul>
                    <li v-for="(x, i) in localizedGaps" :key="i">
                      <b>{{ x.item || x }}</b>
                      <span v-if="x.action">：{{ x.action }}</span>
                      <span v-else-if="x.impact">：{{ x.impact }}</span>
                    </li>
                  </ul>
                </section>

                <section class="detail-block">
                  <h3>风险点</h3>
                  <ul>
                    <li v-for="(x, i) in localizedRiskPoints" :key="i">{{ x }}</li>
                  </ul>
                </section>
              </div>
            </el-tab-pane>

            <el-tab-pane label="优化建议" name="optimize">
              <el-alert
                :title="result.optimize_suggestions?.overall || '暂无优化摘要'"
                type="success"
                :closable="false"
              />
              <el-collapse class="mt">
                <el-collapse-item
                  v-for="(s, i) in result.optimize_suggestions?.sections || []"
                  :key="i"
                  :title="s.section"
                >
                  <ul>
                    <li v-for="(x, j) in s.suggestions" :key="j">{{ x }}</li>
                  </ul>
                </el-collapse-item>
              </el-collapse>

              <div class="keyword-grid">
                <div class="detail-block">
                  <h3>建议补充</h3>
                  <div class="tag-row">
                    <el-tag
                      v-for="k in result.optimize_suggestions?.keywords_to_add || []"
                      :key="k"
                      type="success"
                      >{{ k }}</el-tag
                    >
                  </div>
                </div>
                <div class="detail-block">
                  <h3>建议删减</h3>
                  <div class="tag-row">
                    <el-tag
                      v-for="k in result.optimize_suggestions?.keywords_to_remove || []"
                      :key="k"
                      type="danger"
                      >{{ k }}</el-tag
                    >
                  </div>
                </div>
              </div>

              <div class="generate-area">
                <p class="generate-desc">如果你准备继续投递，可以直接生成一份优化后的简历版本。</p>
                <el-button
                  type="primary"
                  size="large"
                  :loading="genOptimizing"
                  @click="onGenerateOptimized"
                >
                  <el-icon><EditPen /></el-icon> 生成优化版简历
                </el-button>
              </div>
            </el-tab-pane>

            <el-tab-pane label="面试题" name="interview">
              <el-empty v-if="!hasInterview" description="暂无面试题" />
              <template v-else>
                <div v-for="(items, key) in interviewGroups" :key="key" class="question-group">
                  <h3>{{ groupTitle(key) }}</h3>
                  <div class="panel q-card" v-for="(q, i) in items" :key="i">
                    <div class="panel-body">
                      <div class="q">
                        <b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}
                      </div>
                      <div class="i">考察点：{{ q.focus || q.intent }}</div>
                      <div class="a">
                        参考答案：{{ q.suggested_answer || q.expected_answer || q.ref_answer }}
                      </div>
                      <div v-if="q.preparation_tips" class="tip">
                        准备建议：{{ q.preparation_tips }}
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </el-tab-pane>

            <el-tab-pane name="references" :disabled="!hasReferences">
              <template #label>
                <span
                  ><el-icon><Reading /></el-icon> 参考依据
                  <el-tag v-if="refCount" size="small" type="info">{{ refCount }}</el-tag></span
                >
              </template>

              <el-empty v-if="!hasReferences" description="本次分析没有附带参考依据" />
              <template v-else>
                <div v-for="(reference, ri) in result.references" :key="ri" class="ref-card">
                  <div class="panel">
                    <div class="panel-header">
                      <div class="panel-title-row">
                        <h3>{{ reference.doc_title }}</h3>
                        <el-tag :type="refTypeTag(reference.doc_type)" size="small">{{
                          refTypeLabel(reference.doc_type)
                        }}</el-tag>
                      </div>
                    </div>
                    <div class="panel-body">
                      <div v-for="(chunk, ci) in reference.chunks" :key="ci" class="ref-chunk">
                        <div class="ref-meta">片段 {{ ci + 1 }} · 相似度 {{ chunk.score }}</div>
                        <div class="ref-text">
                          {{ chunk.text }}{{ chunk.text?.length >= 200 ? '...' : '' }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import {
  Loading,
  Reading,
  SuccessFilled,
  WarningFilled,
  CircleCloseFilled,
  Promotion,
  ChatLineSquare,
} from '@element-plus/icons-vue'
import { getAnalysis, regenOptimize, regenInterview } from '@/api/analysis'
import { startAgentAnalysis } from '@/api/agent'
import { generateOptimized } from '@/api/resume'
import { EditPen } from '@element-plus/icons-vue'
import { useAgentTaskPolling } from '@/composables/useAgentTaskPolling'
import {
  getInterviewGroupTitle,
  normalizeInterviewQuestions,
  hasInterviewQuestions as checkHasInterviewQuestions,
} from '@/utils/interviewQuestions'
import {
  localizeRecommendationText,
  localizeSentence,
  normalizeLocalizedObjectList,
  normalizeLocalizedTextList,
} from '@/utils/analysisLocalization'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const analysisLoadError = ref(false)
const regenOptimizeLoading = ref(false)
const regenIntervLoading = ref(false)
const tab = ref('match')
const result = ref(null)
const lastIdsTip = ref(null)
const agentSteps = ref([])
const genOptimizing = ref(false)
const { pollTask: pollAgentTask } = useAgentTaskPolling()

const form = reactive({ resume_id: null, jd_id: null })

onMounted(fillLast)
watch(
  () => route.params.id,
  (id) => {
    if (id) {
      const recordId = Number(id)
      if (!Number.isNaN(recordId)) {
        loadAnalysisById(recordId)
      }
    }
  },
  { immediate: true }
)

function fillLast() {
  const rid = localStorage.getItem('recruit.lastResumeId')
  const jid = localStorage.getItem('recruit.lastJDId')
  if (rid) form.resume_id = Number(rid)
  if (jid) form.jd_id = Number(jid)
  if (rid || jid) lastIdsTip.value = { rid, jid }
}

async function loadAnalysisById(recordId) {
  analysisLoadError.value = false
  try {
    const data = await getAnalysis(recordId)
    result.value = data
    localStorage.setItem('recruit.lastRecordId', String(data.record_id || data.id || recordId))
    if (data?.record_id || data.id) {
      tab.value = 'match'
    }
  } catch {
    analysisLoadError.value = true
  }
}

function retryLoadAnalysis() {
  const recordId = Number(route.params.id)
  if (!Number.isNaN(recordId)) loadAnalysisById(recordId)
}

const hasInterview = computed(() => checkHasInterviewQuestions(result.value?.interview_questions))
const interviewGroups = computed(() =>
  normalizeInterviewQuestions(result.value?.interview_questions)
)
const groupTitle = getInterviewGroupTitle

const hasReferences = computed(() => result.value?.references && result.value.references.length > 0)
const refCount = computed(() => result.value?.references?.length || 0)
const completedStepCount = computed(
  () => agentSteps.value.filter((item) => item.status === 'completed').length
)
const currentStepName = computed(() => {
  const running = agentSteps.value.find((item) => item.status === 'running')
  return running ? stepLabel(running.step_name) : '等待中'
})
const localizedMatchRecommendation = computed(() =>
  localizeRecommendationText(result.value?.match_report?.recommendation || '')
)
const localizedMatchSummary = computed(() =>
  localizeSentence(result.value?.match_report?.summary || '')
)
const localizedStrengths = computed(() =>
  normalizeLocalizedObjectList(result.value?.match_report?.strengths)
)
const localizedGaps = computed(() => normalizeLocalizedObjectList(result.value?.match_report?.gaps))
const localizedRiskPoints = computed(() =>
  normalizeLocalizedTextList(result.value?.match_report?.risk_points)
)
const primaryGap = computed(() => {
  const gap = localizedGaps.value[0]
  if (!gap) return '当前没有识别到需要优先补齐的明显差距。'
  return typeof gap === 'string'
    ? gap
    : gap.item || gap.action || gap.impact || '查看完整匹配报告。'
})
const priorityAction = computed(() => {
  const gap = localizedGaps.value[0]
  if (gap && typeof gap === 'object' && gap.action) return gap.action
  return '先生成优化版本，再用目标岗位重新验证匹配度。'
})

const refTypeLabel = (t) =>
  ({
    resume_template: '简历模板',
    jd_lib: '岗位描述',
    interview_q: '面试题库',
    skill_model: '能力模型',
    industry_report: '行业报告',
    general: '通用',
  })[t] ||
  t ||
  '通用'

const refTypeTag = (t) =>
  ({
    resume_template: 'success',
    jd_lib: 'primary',
    interview_q: 'warning',
    skill_model: 'danger',
    industry_report: 'info',
    general: '',
  })[t] || ''

const STEP_LABELS = {
  intent_recognition: '意图识别',
  resume_parse: '简历解析',
  jd_parse: 'JD 解析',
  task_planning: '任务规划',
  knowledge_retrieval: '知识检索',
  matching_analysis: '匹配分析',
  resume_optimization: '简历优化',
  interview_question_generation: '面试题生成',
  self_check: '自检校验',
  final_report: '汇总报告',
}

function stepLabel(name) {
  return STEP_LABELS[name] || name
}

function stepType(status) {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'primary'
  if (status === 'failed') return 'danger'
  return 'info'
}

function stepIcon(status) {
  if (status === 'completed') return SuccessFilled
  if (status === 'failed') return CircleCloseFilled
  if (status === 'running') return Loading
  return WarningFilled
}

function statusText(status) {
  return (
    { pending: '等待中', running: '执行中', completed: '已完成', failed: '失败' }[status] || status
  )
}

const onAnalyze = async () => {
  if (!form.resume_id || !form.jd_id) {
    ElMessage.warning('请先填写简历 ID 和 JD ID')
    return
  }
  loading.value = true
  result.value = null
  agentSteps.value = []

  try {
    const startRes = await startAgentAnalysis({ resume_id: form.resume_id, jd_id: form.jd_id })
    const taskId = startRes?.task_id
    if (!taskId) {
      ElMessage.error('启动分析任务失败')
      return
    }

    await pollAgentTask(taskId, {
      onProgress(taskData, steps) {
        agentSteps.value = steps
      },
      async onCompleted(taskData) {
        const recordId = taskData?.analysis_record_id
        if (!recordId) {
          ElMessage.error('分析完成但未生成记录')
          return
        }

        const data = await getAnalysis(recordId)
        result.value = data
        localStorage.setItem('recruit.lastRecordId', String(data.record_id || data.id || recordId))
        ElMessage.success(`分析完成，匹配度 ${data.match_score}`)
        tab.value = 'match'
      },
      onFailed(error) {
        ElMessage.error(`分析失败: ${error.message || '未知错误'}`)
      },
      onCancelled(error) {
        ElMessage.warning(error.message || '分析任务已取消')
      },
      onTimeout() {
        ElMessage.warning('分析超时，请稍后刷新查看结果')
      },
    })
  } catch {
    // request.js already handles feedback
  } finally {
    loading.value = false
  }
}

const onRegenOptimize = async () => {
  if (!result.value?.record_id) return
  regenOptimizeLoading.value = true
  try {
    const res = await regenOptimize(result.value.record_id)
    result.value = { ...result.value, optimize_suggestions: res.optimize_suggestions }
    ElMessage.success('优化建议已重新生成')
    tab.value = 'optimize'
  } finally {
    regenOptimizeLoading.value = false
  }
}

const onGenerateOptimized = async () => {
  const resumeId = form.resume_id
  if (!resumeId) {
    ElMessage.warning('请先填写简历 ID')
    return
  }
  genOptimizing.value = true
  try {
    await generateOptimized(resumeId, form.jd_id)
    ElMessage.success('优化版简历生成成功')
    router.push(`/resume/compare/${resumeId}`)
  } finally {
    genOptimizing.value = false
  }
}

const onRegenInterview = async () => {
  if (!result.value?.record_id) return
  regenIntervLoading.value = true
  try {
    const res = await regenInterview(result.value.record_id)
    result.value = { ...result.value, interview_questions: res.interview_questions }
    ElMessage.success('面试题已重新生成')
    tab.value = 'interview'
  } finally {
    regenIntervLoading.value = false
  }
}

const goInterview = () => {
  const recordId = result.value?.record_id || result.value?.id
  if (!recordId) {
    ElMessage.warning('当前结果缺少记录 ID，无法打开面试题')
    return
  }
  router.push({ name: 'interview', query: { record_id: String(recordId) } })
}

const goCareer = () => router.push('/career-planning')
const goJobMarket = () => router.push('/jobs/search')
</script>

<style scoped>
.result-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
  padding: 24px 26px;
  border-radius: var(--app-radius-sm, 8px);
  background: #fff;
  border: 1px solid var(--app-line);
  border-top: 3px solid var(--app-primary);
}

.hero-kicker {
  display: inline-block;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--app-muted);
}

.hero-copy h2 {
  margin: 8px 0 8px;
  font-size: 34px;
  color: var(--app-text);
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.control-form {
  margin-bottom: 14px;
}

.control-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.progress-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.progress-stat {
  padding: 16px 18px;
  border-radius: var(--app-radius-xs, 6px);
  background: #fff;
  border: 1px solid var(--app-line);
}

.progress-stat span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.progress-stat strong {
  display: block;
  margin-top: 8px;
  font-size: 22px;
  color: var(--app-text);
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
  gap: 18px;
}

.decision-strip {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) minmax(210px, 0.72fr);
  gap: 0;
  margin-bottom: 18px;
  background: #fff;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.decision-strip > div {
  min-width: 0;
  padding: 19px 20px;
  border-left: 1px solid var(--app-line);
}

.decision-strip > div:first-child {
  border-left: 0;
}

.decision-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.decision-conclusion strong {
  display: block;
  margin-top: 7px;
  color: var(--app-text);
  font-size: 20px;
  line-height: 1.35;
}

.decision-strip p {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.65;
}

.evidence-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 9px;
}

.evidence-stats span {
  padding: 4px 7px;
  border-radius: 3px;
  background: var(--app-bg);
  color: var(--app-muted);
  font-size: 12px;
}

.evidence-stats b {
  color: var(--app-text);
}

.decision-next .el-button {
  margin-top: 13px;
}

.score-shell {
  padding: 8px;
  text-align: center;
}

.score-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.score-value {
  display: block;
  margin-top: 12px;
  font-size: 56px;
  line-height: 1;
  color: var(--app-primary-dark);
}

.score-rec {
  margin: 12px 0 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--app-text);
}

.score-summary {
  margin: 10px 0 0;
  color: var(--app-muted);
  line-height: 1.8;
}

.score-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 18px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-item {
  padding: 16px 18px;
  border-radius: var(--app-radius-xs, 6px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.metric-item span {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}

.metric-item strong {
  display: block;
  margin-top: 8px;
  font-size: 26px;
  color: var(--app-text);
}

.next-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 18px;
}

.detail-grid,
.keyword-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 14px;
}

.keyword-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.detail-block {
  padding: 18px;
  border-radius: var(--app-radius-xs, 6px);
  background: #fff;
  border: 1px solid var(--app-line);
}

.detail-block h3,
.question-group h3 {
  margin: 0 0 12px;
  color: var(--app-text);
}

.detail-block ul,
.question-group ul {
  margin: 0;
  padding-left: 18px;
}

.detail-block li {
  line-height: 1.8;
  color: var(--app-muted);
}

.tag-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.generate-area {
  margin-top: 18px;
  padding: 24px;
  border-radius: var(--app-radius-sm, 8px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
  text-align: center;
}

.generate-desc {
  margin: 0 0 14px;
  color: var(--app-muted);
}

.question-group + .question-group {
  margin-top: 16px;
}

.q-card {
  margin-bottom: 10px;
  border-radius: var(--app-radius-sm, 12px);
}

.q {
  font-size: 14px;
}

.i,
.tip,
.ref-meta,
.step-status {
  color: var(--app-muted);
  font-size: 12px;
  margin-top: 6px;
}

.a {
  color: var(--app-primary-dark);
  font-size: 13px;
  margin-top: 6px;
}

.muted {
  color: var(--app-muted);
}

.ref-card + .ref-card {
  margin-top: 12px;
}

.ref-chunk + .ref-chunk {
  margin-top: 10px;
}

.ref-text {
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
  color: var(--app-muted);
  line-height: 1.7;
}

@media (max-width: 960px) {
  .result-hero,
  .overview-grid,
  .decision-strip,
  .detail-grid,
  .keyword-grid,
  .progress-grid {
    grid-template-columns: 1fr;
  }

  .result-hero,
  .hero-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .decision-strip > div,
  .decision-strip > div:first-child {
    border-top: 1px solid var(--app-line);
    border-left: 0;
  }

  .decision-strip > div:first-child {
    border-top: 0;
  }
}

@media (max-width: 640px) {
  .result-hero {
    padding: 20px;
  }

  .hero-copy h2 {
    font-size: 28px;
  }

  .hero-actions,
  .next-actions,
  .score-actions {
    width: 100%;
    flex-direction: column;
  }

  .decision-next .el-button {
    width: 100%;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
