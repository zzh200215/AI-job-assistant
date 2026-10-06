<template>
  <div class="page-shell">
    <!-- Hero -->
    <section class="analysis-hero">
      <div class="hero-title-area">
        <div class="hero-title-main">
          <div class="hero-badge">
            <span class="badge-dot" />
            Agentic RAG
          </div>
          <h2>智能分析</h2>
          <div class="page-header-sub">
            把简历、岗位 JD、知识召回与分析结论整合成一个更完整的决策工作台。
          </div>
          <div class="hero-tags">
            <span>多智能体协作</span>
            <span>匹配分析</span>
            <span>引用溯源</span>
          </div>
        </div>
        <!-- Decorative pipeline node -->
        <div class="hero-node" aria-hidden="true">
          <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
            <circle
              cx="40"
              cy="40"
              r="38"
              stroke="var(--app-primary)"
              stroke-width="1"
              opacity="0.15"
            />
            <circle
              cx="40"
              cy="40"
              r="28"
              stroke="var(--app-primary)"
              stroke-width="1"
              opacity="0.2"
            />
            <circle cx="40" cy="40" r="8" fill="var(--app-primary)" opacity="0.3" />
            <path
              d="M4 40 Q 20 16 40 12 Q 60 8 76 40"
              stroke="var(--app-primary)"
              stroke-width="1"
              opacity="0.12"
              fill="none"
              stroke-dasharray="3 3"
            />
            <path
              d="M4 40 Q 20 64 40 68 Q 60 72 76 40"
              stroke="var(--app-primary)"
              stroke-width="1"
              opacity="0.12"
              fill="none"
              stroke-dasharray="3 3"
            />
          </svg>
        </div>
      </div>

      <div class="hero-metrics">
        <div class="hm-item" :class="{ ready: !!resumeInfo }">
          <span class="hm-label">简历状态</span>
          <strong class="data-value">{{ resumeInfo ? '已上传' : '待上传' }}</strong>
          <small>{{ resumeInfo?.file_name || '等待候选人简历' }}</small>
        </div>
        <div class="hm-item" :class="{ ready: !!(jdInfo || jdForm.title || jdForm.raw_text) }">
          <span class="hm-label">JD 状态</span>
          <strong class="data-value">{{
            jdInfo || jdForm.title || jdForm.raw_text ? '已就绪' : '待填写'
          }}</strong>
          <small>{{ jdInfo?.title || jdForm.title || '等待目标岗位 JD' }}</small>
        </div>
        <div class="hm-item" :class="{ ready: loading || !!result }">
          <span class="hm-label">分析流程</span>
          <strong class="data-value">{{ analysisFlowLabel }}</strong>
          <small>{{ analysisFlowHint }}</small>
        </div>
        <div class="hm-item" :class="{ ready: !!result }">
          <span class="hm-label">结果总览</span>
          <strong class="data-value">{{ result ? result.match_score : '--' }}</strong>
          <small>{{ analysisConfidence?.label || '等待生成匹配报告' }}</small>
        </div>
      </div>
    </section>

    <!-- Input Card -->
    <section class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon><MagicStick /></el-icon>
          <span>一键智能分析</span>
        </div>
        <el-tag size="small">Agentic RAG + 多智能体协作</el-tag>
      </div>

      <div class="panel-body">
        <div class="input-split">
          <!-- Resume Upload -->
          <div class="input-col">
            <div class="input-col-label">上传简历</div>
            <el-upload
              drag
              action="#"
              :http-request="customUploadResume"
              :show-file-list="false"
              :before-upload="beforeUploadResume"
              accept=".pdf,.docx,.doc"
              :disabled="loading"
              class="resume-upload"
            >
              <div v-if="!resumeInfo" class="upload-blank">
                <el-icon class="upload-icon"><UploadFilled /></el-icon>
                <div class="upload-title">拖拽简历到此处，或<em>点击上传</em></div>
                <div class="upload-hint">支持 PDF / DOCX，不超过 10MB</div>
              </div>
              <div v-else class="upload-ready">
                <el-icon class="done-icon"><SuccessFilled /></el-icon>
                <div class="upload-ready-copy">
                  <strong>{{ resumeInfo.file_name }}</strong>
                  <span>ID: {{ resumeInfo.id }}</span>
                </div>
                <el-button text type="danger" size="small" @click.stop="clearResume"
                  >移除</el-button
                >
              </div>
            </el-upload>
          </div>

          <!-- JD Input -->
          <div class="input-col">
            <div class="input-col-label">输入岗位 JD</div>
            <el-form :model="jdForm" label-position="top" :disabled="loading" class="jd-form">
              <el-form-item label="岗位名称" required>
                <el-input v-model="jdForm.title" placeholder="如：Python 后端开发工程师" />
              </el-form-item>
              <el-form-item label="公司（可选）">
                <el-input v-model="jdForm.company" placeholder="如：示例科技" />
              </el-form-item>
              <el-form-item label="JD 内容" required>
                <el-input
                  v-model="jdForm.raw_text"
                  type="textarea"
                  :rows="4"
                  placeholder="粘贴岗位 JD 完整内容…"
                />
              </el-form-item>
            </el-form>
            <div v-if="jdInfo" class="jd-ready">
              <el-tag size="small" type="success">JD 已创建，ID: {{ jdInfo.id }}</el-tag>
              <el-button text type="danger" size="small" @click="clearJD">移除</el-button>
            </div>
          </div>
        </div>

        <!-- Action -->
        <div class="action-bar">
          <div class="action-copy">
            <strong>输出包括</strong>
            <span>匹配度、差距、职业方向、面试题与引用来源</span>
          </div>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            :disabled="!canAnalyze"
            @click="onStartAnalysis"
          >
            <el-icon><Promotion /></el-icon>
            {{ loading ? '智能分析中…' : '一键智能分析' }}
          </el-button>
        </div>
      </div>
    </section>

    <!-- Agent Pipeline Progress -->
    <section v-if="loading && agentSteps.length" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>Agent Pipeline</span>
        </div>
        <el-tag type="warning" size="small"
          >{{ completedStepCount }} / {{ agentSteps.length }} 步</el-tag
        >
      </div>

      <div class="panel-body">
        <!-- Progress snapshot -->
        <div class="pipeline-status">
          <div class="ps-item">
            <span>当前阶段</span>
            <strong class="data-value">{{ currentStepName }}</strong>
          </div>
          <div class="ps-item">
            <span>已完成</span>
            <strong class="data-value">{{ completedStepCount }}</strong>
          </div>
          <div class="ps-item">
            <span>总步骤</span>
            <strong class="data-value">{{ agentSteps.length }}</strong>
          </div>
        </div>

        <!-- Pipeline visual timeline -->
        <div class="pipeline-timeline">
          <div
            v-for="(s, i) in agentSteps"
            :key="i"
            class="pipeline-node"
            :class="`node-${s.status}`"
          >
            <div class="pipeline-connector" />
            <div class="pipeline-dot">
              <el-icon v-if="s.status === 'completed'" :size="14"><SuccessFilled /></el-icon>
              <el-icon v-else-if="s.status === 'failed'" :size="14"><CircleCloseFilled /></el-icon>
              <el-icon v-else-if="s.status === 'running'" :size="14" class="is-loading"
                ><Loading
              /></el-icon>
              <span v-else class="dot-empty" />
            </div>
            <div class="pipeline-content">
              <div class="pl-head">
                <strong>{{ stepLabel(s.step_name) }}</strong>
                <span class="pl-meta">
                  {{ statusText(s.status) }}
                  <span v-if="s.duration_ms"> · {{ s.duration_ms }}ms</span>
                </span>
              </div>
              <div v-if="s.status === 'completed' && s.output_data" class="pl-preview">
                <span v-if="s.step_name === 'intent_recognition'">
                  意图: <b>{{ s.output_data.intent || '-' }}</b>
                </span>
                <span v-else-if="s.step_name === 'match_analysis'">
                  匹配度: <b>{{ s.output_data.match_score ?? '-' }}</b>
                </span>
                <span v-else-if="s.step_name === 'resume_optimization'">
                  优化建议: <b>{{ (s.output_data.sections || []).length }} 项</b>
                </span>
                <span v-else-if="s.step_name === 'interview_questions'">
                  面试题: <b>{{ s.output_data.total_questions ?? '-' }} 题</b>
                </span>
                <span v-else-if="s.step_name === 'summary_report'">汇总完成</span>
              </div>
              <el-tag v-if="s.error_msg" size="small" type="danger">{{ s.error_msg }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Terminal state -->
    <section v-if="!loading && !result && agentSteps.length" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon><InfoFilled /></el-icon>
          <span>任务提示</span>
        </div>
        <el-tag :type="taskOutcomeTag" size="small">{{ analysisFlowLabel }}</el-tag>
      </div>
      <div class="panel-body">
        <el-alert
          :type="taskOutcomeTag === 'danger' ? 'error' : taskOutcomeTag"
          :closable="false"
          show-icon
          :title="terminalHint"
        />
      </div>
    </section>

    <!-- Results -->
    <div v-if="result" class="results-section">
      <!-- Score -->
      <section class="panel score-section">
        <div class="panel-body score-body">
          <div class="score-center">
            <el-progress
              type="dashboard"
              :percentage="result.match_score"
              :color="scoreToneColor(result.match_score)"
              :width="140"
              :stroke-width="10"
            >
              <template #default="{ percentage }">
                <div class="score-value data-value">{{ percentage }}</div>
                <div class="score-label">匹配度</div>
              </template>
            </el-progress>
            <div class="score-meta">
              <div class="score-rec">{{ localizedMatchRecommendation }}</div>
              <div class="score-sum">{{ localizedMatchSummary }}</div>
              <div class="score-chips">
                <span class="chip chip-match">已匹配 {{ matchedSkills.length }} 项</span>
                <span class="chip chip-gap">待补足 {{ missingSkills.length }} 项</span>
                <span class="chip chip-ref">
                  置信度 {{ analysisConfidence ? (analysisConfidence.score ?? 0) : '--' }}
                </span>
              </div>
              <div class="next-step-bar">
                <el-button
                  type="primary"
                  size="small"
                  @click="
                    router.push({
                      path: '/jobs/recommend',
                      query: { resume_id: String(result.resume_id || resumeInfo?.id || '') },
                    })
                  "
                >
                  <el-icon><Search /></el-icon> 去岗位推荐
                </el-button>
                <el-button
                  size="small"
                  @click="
                    router.push({
                      path: '/interview/setup',
                      query: { jd_id: String(jdInfo?.id || '') },
                    })
                  "
                >
                  <el-icon><Microphone /></el-icon> 去模拟面试
                </el-button>
              </div>
            </div>
          </div>

          <el-descriptions :column="4" border size="small" class="dim-table">
            <el-descriptions-item label="技能">
              <span class="data-value dim-val">{{ dimensionScore(result, 'skills') }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="经验">
              <span class="data-value dim-val">{{ dimensionScore(result, 'experience') }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="学历">
              <span class="data-value dim-val">{{ dimensionScore(result, 'education') }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="行业">
              <span class="data-value dim-val">{{ dimensionScore(result, 'industry') }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <!-- RAG Confidence -->
          <div v-if="analysisConfidence" class="rag-confidence">
            <div class="rag-confidence-main">
              <div class="rag-badge" :class="`badge-${analysisConfidence.level || 'low'}`">
                {{ analysisConfidence.score ?? 0 }}
              </div>
              <div class="rag-confidence-copy">
                <div class="rag-confidence-title">
                  分析可信度
                  <el-tag size="small" :type="confidenceTagType(analysisConfidence.level)">
                    {{ analysisConfidence.label || '-' }}
                  </el-tag>
                </div>
                <div class="rag-confidence-summary">
                  {{ analysisConfidence.summary || '暂无可信度说明' }}
                </div>
              </div>
            </div>
            <div class="rag-confidence-metrics">
              <div class="rag-metric">
                <span>召回片段</span>
                <strong class="data-value">{{
                  analysisConfidence.signals?.total_chunks ?? 0
                }}</strong>
              </div>
              <div class="rag-metric">
                <span>覆盖文档</span>
                <strong class="data-value">{{
                  analysisConfidence.signals?.unique_docs ?? 0
                }}</strong>
              </div>
              <div class="rag-metric">
                <span>平均相关度</span>
                <strong class="data-value">{{
                  analysisConfidence.signals?.avg_similarity ?? 0
                }}</strong>
              </div>
              <div class="rag-metric">
                <span>命中能力模型</span>
                <strong class="data-value">{{
                  analysisConfidence.signals?.has_skill_model ? '是' : '否'
                }}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Tabs -->
      <section class="panel">
        <div class="panel-body tab-body">
          <el-tabs v-model="reportTab" @tab-click="onTabClick">
            <!-- 技能匹配 -->
            <el-tab-pane label="技能匹配" name="skills">
              <SkillsPane
                :matched-skills="matchedSkills"
                :missing-skills="missingSkills"
                :strengths="localizedStrengths"
                :gaps="localizedGaps"
                :risk-points="localizedRiskPoints"
              />
            </el-tab-pane>

            <!-- 匹配度解释 -->
            <el-tab-pane label="匹配度解释" name="explain">
              <ExplainPane :loading="explainLoading" :explain-result="explainResult" />
            </el-tab-pane>

            <!-- 职业方向 -->
            <el-tab-pane label="🎯 职业方向" name="career-paths">
              <CareerDirectionPane
                :loading="careerPathsLoading"
                :paths="careerPaths"
                :summary="careerPathSummary"
              />
            </el-tab-pane>

            <!-- 简历优化 -->
            <el-tab-pane label="简历优化建议" name="optimize">
              <ResumeOptimizePane
                :suggestions="result.optimize_suggestions"
                :busy="genOptimizing"
                @generate="onGenerateOptimized"
              />
            </el-tab-pane>

            <!-- 面试题 -->
            <el-tab-pane label="个性化面试题" name="interview">
              <InterviewQuestionsPane :groups="interviewGroups" />
            </el-tab-pane>

            <!-- 职业规划 -->
            <el-tab-pane label="🎯 职业规划" name="career">
              <CareerPlanPane
                :career-data="careerData"
                :visual-phases="visualPhases"
                :has-structured-skill-gaps="hasStructuredSkillGaps"
              />
            </el-tab-pane>

            <!-- 综合评价 -->
            <el-tab-pane label="综合评价" name="summary">
              <ReportSummaryPane
                :report="finalReport"
                :recommendation="localizedSummaryRecommendation"
                :evaluation="localizedOverallEvaluation"
              />
            </el-tab-pane>

            <!-- 引用来源 -->
            <el-tab-pane label="📚 引用来源" name="references">
              <ReferencesPane
                v-model:ref-open-docs="refOpenDocs"
                :loading="referencesLoading"
                :references="references"
                :reference-query="referenceQuery"
                :analysis-confidence="analysisConfidence"
              />
            </el-tab-pane>
          </el-tabs>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { userErrorCopy } from '@/utils/requestTracing'
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import {
  UploadFilled,
  SuccessFilled,
  MagicStick,
  Microphone,
  Promotion,
  Loading,
  CircleCloseFilled,
  InfoFilled,
  Search,
} from '@element-plus/icons-vue'
import {
  readJDId,
  readResumeId,
  rememberJD,
  rememberRecord,
  rememberResume,
} from '@/utils/lastSelection'
import { uploadResume, parseResume } from '@/api/resume'
import { createJD, parseJD } from '@/api/jd'
import { runFullAnalysis, getAnalysis } from '@/api/analysis'
import { generateOptimized } from '@/api/resume'
import { useAgentTaskPolling } from '@/composables/useAgentTaskPolling'
import { useAnalysisReferences } from '@/features/analysis/composables/useAnalysisReferences'
import { useCareerPaths } from '@/features/analysis/composables/useCareerPaths'
import { useMatchExplain } from '@/features/analysis/composables/useMatchExplain'
import CareerDirectionPane from '@/features/analysis/components/CareerDirectionPane.vue'
import CareerPlanPane from '@/features/analysis/components/CareerPlanPane.vue'
import ExplainPane from '@/features/analysis/components/ExplainPane.vue'
import InterviewQuestionsPane from '@/features/analysis/components/InterviewQuestionsPane.vue'
import ReferencesPane from '@/features/analysis/components/ReferencesPane.vue'
import ReportSummaryPane from '@/features/analysis/components/ReportSummaryPane.vue'
import ResumeOptimizePane from '@/features/analysis/components/ResumeOptimizePane.vue'
import SkillsPane from '@/features/analysis/components/SkillsPane.vue'
import { scoreToneColor } from '@/utils/scoreTone'
import {
  localizeRecommendationText,
  localizeSentence,
  normalizeLocalizedObjectList,
  normalizeLocalizedTextList,
} from '@/utils/analysisLocalization'
import {
  confidenceTagType,
  dimensionScore,
  groupInterviewQuestions,
  hasStructuredCareerGaps,
  normalizeConfidence,
  pickMatchedSkills,
  pickMissingSkills,
  statusText,
  stepLabel,
} from '@/features/analysis/lib/analysisModel'

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const resumeInfo = ref(null)
const jdInfo = ref(null)
const result = ref(null)
const reportTab = ref('skills')
const agentSteps = ref([])
const genOptimizing = ref(false)
const genRedirecting = ref(false)
const { pollTask: pollAgentTask } = useAgentTaskPolling()
const taskOutcome = ref('idle')

const jdForm = reactive({ title: '', company: '', raw_text: '' })

/* 三条按标签页触发的链（D50 出页）。"用哪个简历 / 哪个 JD / 哪条记录"仍是页面上的跨链知识，
   所以传的是取值函数，链自己不持有 refs。 */
const { explainLoading, explainResult, loadExplainMatch, clearExplain } = useMatchExplain({
  getResumeId: () => result.value?.resume_id || resumeInfo.value?.id,
  getJdId: () => result.value?.jd_id || jdInfo.value?.id,
})
const {
  references,
  referencesLoading,
  refOpenDocs,
  referenceQuery,
  referenceConfidence,
  loadReferences,
  clearReferences,
} = useAnalysisReferences({ getResult: () => result.value })
const { careerPaths, careerPathsLoading, careerPathSummary, loadCareerPaths, clearCareerPaths } =
  useCareerPaths({
    getResumeId: () => result.value?.resume_id || resumeInfo.value?.id,
  })

const canAnalyze = computed(() => {
  const hasJD = jdInfo.value || (jdForm.title.trim() && jdForm.raw_text.trim())
  return resumeInfo.value && hasJD
})

const completedStepCount = computed(
  () => agentSteps.value.filter((s) => s.status === 'completed').length
)

const analysisFlowLabel = computed(() => {
  if (loading.value) return '分析中'
  if (result.value) return '已完成'
  if (taskOutcome.value === 'partial') return '部分完成'
  if (taskOutcome.value === 'failed') return '失败'
  if (taskOutcome.value === 'cancelled') return '已取消'
  if (taskOutcome.value === 'timeout') return '已超时'
  return '待开始'
})

const analysisFlowHint = computed(() => {
  if (loading.value || agentSteps.value.length) {
    return `${completedStepCount.value} / ${agentSteps.value.length || 0} 步`
  }
  if (taskOutcome.value === 'failed') return '分析失败，请检查输入或稍后重试'
  if (taskOutcome.value === 'cancelled') return '任务已取消'
  if (taskOutcome.value === 'timeout') return '轮询超时，请稍后查看历史记录'
  return '尚未启动分析任务'
})

const taskOutcomeTag = computed(
  () =>
    ({
      partial: 'warning',
      failed: 'danger',
      cancelled: 'info',
      timeout: 'warning',
    })[taskOutcome.value] || 'info'
)

const terminalHint = computed(() => {
  if (taskOutcome.value === 'partial')
    return '任务部分完成，但没有生成完整分析结果。可以稍后去历史记录查看，或直接重试。'
  if (taskOutcome.value === 'failed') return '任务执行失败，当前没有可展示的分析结果。'
  if (taskOutcome.value === 'cancelled') return '任务已取消，当前没有可展示的分析结果。'
  if (taskOutcome.value === 'timeout')
    return '前端轮询已超时，后台任务可能仍在继续。你可以稍后去历史记录查看结果。'
  return '当前没有可展示的分析结果。'
})

const currentStepName = computed(() => {
  const running = agentSteps.value.find((s) => s.status === 'running')
  if (running) return stepLabel(running.step_name)
  const pending = agentSteps.value.find((s) => s.status === 'pending')
  if (pending) return stepLabel(pending.step_name)
  const lastCompleted = [...agentSteps.value].reverse().find((s) => s.status === 'completed')
  if (lastCompleted) return stepLabel(lastCompleted.step_name)
  return '准备中'
})

const matchedSkills = computed(() => pickMatchedSkills(result.value))
const missingSkills = computed(() => pickMissingSkills(result.value))
const finalReport = computed(() => result.value?.final_report || null)
const rawMatchRecommendation = computed(() => result.value?.match_report?.recommendation || '')
const rawMatchSummary = computed(() => result.value?.match_report?.summary || '')
const localizedMatchRecommendation = computed(() =>
  localizeRecommendationText(rawMatchRecommendation.value)
)
const localizedMatchSummary = computed(() => localizeSentence(rawMatchSummary.value))
const localizedStrengths = computed(() =>
  normalizeLocalizedObjectList(result.value?.match_report?.strengths)
)
const localizedGaps = computed(() => normalizeLocalizedObjectList(result.value?.match_report?.gaps))
const localizedRiskPoints = computed(() =>
  normalizeLocalizedTextList(result.value?.match_report?.risk_points)
)
const rawSummaryRecommendation = computed(() => finalReport.value?.summary?.recommendation || '')
const rawOverallEvaluation = computed(() => finalReport.value?.summary?.overall_evaluation || '')
const localizedSummaryRecommendation = computed(() =>
  localizeRecommendationText(rawSummaryRecommendation.value)
)
const localizedOverallEvaluation = computed(() => localizeSentence(rawOverallEvaluation.value))

const analysisConfidence = computed(
  () =>
    normalizeConfidence(result.value?.rag_confidence) ||
    normalizeConfidence(referenceConfidence.value)
)

const careerData = computed(() => result.value?.career_planning || null)
const visualPhases = computed(() => careerData.value?.visual_roadmap?.phases || [])
const hasStructuredSkillGaps = computed(() => hasStructuredCareerGaps(result.value))

const interviewGroups = computed(() => groupInterviewQuestions(result.value))

// ---- Resume upload ----
const beforeUploadResume = (file) => {
  const ext = file.name.split('.').pop().toLowerCase()
  if (!['pdf', 'docx', 'doc'].includes(ext)) {
    ElMessage.error('仅支持 PDF / DOCX / DOC 格式')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('文件超过 10MB')
    return false
  }
  return true
}

const customUploadResume = async ({ file }) => {
  try {
    const data = await uploadResume(file)
    ElMessage.success('简历上传成功，正在解析…')
    const parsed = await parseResume(data.id)
    resumeInfo.value = { id: data.id, file_name: file.name, parsed: parsed.parsed }
    rememberResume(data.id)
    ElMessage.success('简历解析完成')
  } catch {
    /* request.js 已提示 */
  }
}

const clearResume = () => {
  resumeInfo.value = null
  clearExplain()
}
const clearJD = () => {
  jdInfo.value = null
  jdForm.title = ''
  jdForm.company = ''
  jdForm.raw_text = ''
  clearExplain()
}

// ---- Analysis ----
const onStartAnalysis = async () => {
  if (!canAnalyze.value) return
  if (!jdInfo.value) {
    if (!jdForm.title.trim() || !jdForm.raw_text.trim()) {
      ElMessage.warning('请填写岗位名称和 JD 内容')
      return
    }
    try {
      const jd = await createJD({
        title: jdForm.title,
        company: jdForm.company || '',
        raw_text: jdForm.raw_text,
      })
      await parseJD(jd.id)
      jdInfo.value = { id: jd.id, title: jdForm.title }
      rememberJD(jd.id)
    } catch {
      return
    }
  }

  loading.value = true
  taskOutcome.value = 'idle'
  result.value = null
  agentSteps.value = []
  /* 三条链一起作废，而不是只把值清掉：上一轮的响应可能还在飞，只清值等于让它待会儿
     把旧简历/旧 JD 的结果写在新一轮的屏幕上。 */
  clearExplain()
  clearReferences()
  clearCareerPaths()

  try {
    const startRes = await runFullAnalysis({
      resume_id: resumeInfo.value.id,
      jd_id: jdInfo.value.id,
    })
    const taskId = startRes?.task_id
    if (!taskId) {
      ElMessage.error('启动智能分析失败')
      return
    }
    await pollAgentTask(taskId, {
      onProgress(taskData, steps) {
        agentSteps.value = steps
        taskOutcome.value = taskData?.status || 'running'
      },
      async onCompleted(taskData) {
        taskOutcome.value = taskData?.status || 'completed'
        const recordId = taskData?.analysis_record_id
        if (!recordId) {
          ElMessage.error('任务完成但未生成分析记录')
          return
        }
        const data = await getAnalysis(recordId)
        result.value = data
        rememberRecord(data.record_id || data.id || recordId)
        await loadExplainMatch(true)
        await loadReferences(true)
        ElMessage.success(`智能分析完成，匹配度 ${data.match_score}`)
        reportTab.value = 'skills'
      },
      onFailed(error) {
        taskOutcome.value = 'failed'
        ElMessage.error(`智能分析失败: ${userErrorCopy(error, '未知错误')}`)
      },
      onCancelled(error) {
        taskOutcome.value = 'cancelled'
        ElMessage.warning(userErrorCopy(error, '分析任务已取消'))
      },
      onTimeout() {
        taskOutcome.value = 'timeout'
        ElMessage.warning('分析超时，请稍后查看历史记录')
      },
    })
  } catch {
    /* request.js 已提示 */
  } finally {
    loading.value = false
  }
}

const onTabClick = (tab) => {
  if (tab.paneName === 'references') loadReferences()
  else if (tab.paneName === 'explain') loadExplainMatch()
  else if (tab.paneName === 'career-paths') loadCareerPaths()
}

const onGenerateOptimized = async () => {
  const resumeId = resumeInfo.value?.id
  if (!resumeId) {
    ElMessage.warning('请先上传简历')
    return
  }
  genOptimizing.value = true
  try {
    await generateOptimized(resumeId, jdInfo.value?.id || null)
    ElMessage.success('优化版简历生成成功')
    window.location.href = `/resume/compare/${resumeId}`
  } catch {
    /* request.js 已提示 */
  } finally {
    genOptimizing.value = false
    genRedirecting.value = false
  }
}

onMounted(() => {
  // URL query params take priority (from PipelineKanban / other pages)
  const qRid = route.query.resume_id ? Number(route.query.resume_id) : null
  const qJid = route.query.jd_id ? Number(route.query.jd_id) : null
  const rid = qRid || readResumeId()
  const jid = qJid || readJDId()
  if (rid && !isNaN(rid)) resumeInfo.value = { id: rid, file_name: `简历 #${rid}` }
  if (jid && !isNaN(jid)) jdInfo.value = { id: jid, title: `JD #${jid}` }

  const pending = localStorage.getItem('recruit.pendingAnalysis')
  if (pending) {
    try {
      const ctx = JSON.parse(pending)
      if (ctx.title) jdForm.title = ctx.title
      if (ctx.company) jdForm.company = ctx.company
      if (ctx.jd_text) jdForm.raw_text = ctx.jd_text
      if (ctx.jdId) {
        jdInfo.value = { id: Number(ctx.jdId), title: ctx.title || `JD #${ctx.jdId}` }
        rememberJD(ctx.jdId)
      }
    } catch (e) {
      console.warn('解析 pendingAnalysis 失败', e)
    } finally {
      localStorage.removeItem('recruit.pendingAnalysis')
    }
  }
})
</script>

<style scoped>
.page-shell {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Hero ===== */
.analysis-hero {
  padding: 24px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow);
}

.hero-title-area {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-size: 11px;
  font-weight: 600;
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--app-primary);
}

.hero-title-main h2 {
  margin: 6px 0 0;
  font-size: 30px;
  font-weight: 800;
  line-height: 1.1;
}

.hero-title-main .page-header-sub {
  margin: 10px 0 0;
  max-width: 540px;
  color: var(--app-muted);
  line-height: 1.7;
  font-size: 14px;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.hero-tags span {
  padding: 5px 10px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--app-line);
  font-size: 11px;
  color: var(--app-muted);
}

.hero-node {
  flex-shrink: 0;
  opacity: 0.6;
  display: none;
}

@media (min-width: 1024px) {
  .hero-node {
    display: block;
  }
}

/* Hero metrics */
.hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.hm-item {
  padding: 14px 16px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  transition: background 0.2s ease;
}

.hm-item.ready {
  background: var(--el-fill-color-light);
}

.hm-label {
  display: block;
  font-size: 11px;
  color: var(--app-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hm-item strong {
  display: block;
  margin-top: 8px;
  font-size: 20px;
  line-height: 1.1;
}

.hm-item small {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}

/* ===== Panel overrides ===== */
.panel.score-section {
  overflow: hidden;
}

/* ===== Input split ===== */
.input-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.input-col-label {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--app-text);
}

/* Upload */
.resume-upload :deep(.el-upload),
.resume-upload :deep(.el-upload-dragger) {
  width: 100%;
}

.resume-upload :deep(.el-upload-dragger) {
  min-height: 220px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px dashed var(--app-line);
  background: var(--el-fill-color-light);
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.resume-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--app-primary);
  background: var(--app-primary-light);
}

.upload-blank {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.upload-icon {
  font-size: 36px;
  color: var(--app-muted);
}

.upload-title {
  font-size: 14px;
  color: var(--app-muted);
}

.upload-title em {
  font-style: normal;
  color: var(--app-primary);
  font-weight: 600;
}

.upload-hint {
  font-size: 12px;
  color: var(--app-muted);
}

.upload-ready {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}

.done-icon {
  font-size: 32px;
  color: var(--app-success);
}

.upload-ready-copy strong {
  display: block;
  font-size: 14px;
}

.upload-ready-copy span {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-muted);
}

/* JD */
.jd-form {
  width: 100%;
}
.jd-form :deep(.el-form-item) {
  margin-bottom: 14px;
}
.jd-ready {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

/* Action bar */
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--app-line);
}

.action-copy strong {
  display: block;
  color: var(--app-text);
  font-size: 14px;
}

.action-copy span {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}

/* ===== Pipeline ===== */
.pipeline-status {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}

.ps-item {
  padding: 14px 16px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--el-fill-color-light);
}

.ps-item span {
  display: block;
  color: var(--app-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ps-item strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

/* Pipeline timeline */
.pipeline-timeline {
  position: relative;
  padding-left: 28px;
}

.pipeline-node {
  position: relative;
  display: flex;
  gap: 14px;
  padding-bottom: 18px;
}

.pipeline-node:last-child {
  padding-bottom: 0;
}

.pipeline-connector {
  position: absolute;
  left: -8px;
  top: 20px;
  bottom: 0;
  width: 2px;
  background: var(--el-border-color);
}

.pipeline-node:last-child .pipeline-connector {
  display: none;
}

.pipeline-dot {
  position: relative;
  z-index: 1;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.node-completed .pipeline-dot {
  background: var(--app-success);
  color: #fff;
}

.node-running .pipeline-dot {
  background: var(--app-primary);
  color: #fff;
  box-shadow: 0 0 0 4px rgba(25, 107, 219, 0.15);
}

.node-failed .pipeline-dot {
  background: var(--app-danger);
  color: #fff;
}

.node-pending .pipeline-dot {
  background: var(--el-border-color);
}

.dot-empty {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-border-color);
}

.pipeline-content {
  flex: 1;
  min-width: 0;
}

.pl-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.pl-head strong {
  font-size: 14px;
}

.pl-meta {
  font-size: 12px;
  color: var(--app-muted);
}

.pl-preview {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--el-fill-color-light);
  font-size: 12px;
  color: var(--app-primary-dark);
}

/* ===== Results ===== */
.results-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.score-body {
  padding: 24px;
}

.score-center {
  display: flex;
  gap: 24px;
  align-items: center;
  padding-bottom: 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--app-line);
}

.score-value {
  font-size: 36px;
  line-height: 1;
}

.score-label {
  font-size: 12px;
  color: var(--app-muted);
}

.score-meta {
  flex: 1;
}

.score-rec {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}

.score-sum {
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.7;
}

.score-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.next-step-bar {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.chip {
  padding: 6px 10px;
  border-radius: var(--app-radius-xs, 8px);
  font-size: 11px;
  font-weight: 500;
  border: 1px solid transparent;
}

.chip-match {
  background: #e8f8ee;
  color: var(--app-success);
  border-color: #ccecd7;
}

.chip-gap {
  background: var(--app-violet-light);
  color: var(--app-violet);
  border-color: #d9cef0;
}

.chip-ref {
  background: var(--app-primary-light);
  color: var(--app-primary);
  border-color: #c1d6f0;
}

.dim-table {
  margin-top: 0;
}
.dim-val {
  color: var(--app-primary);
}

/* RAG Confidence */
.rag-confidence {
  margin-top: 16px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
}

.rag-confidence-main {
  display: flex;
  gap: 14px;
  align-items: center;
}

.rag-badge {
  width: 56px;
  height: 56px;
  border-radius: var(--app-radius-xs, 8px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.rag-confidence-copy {
  flex: 1;
  min-width: 0;
}

.rag-confidence-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
}

.rag-confidence-summary {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
}

.rag-confidence-metrics {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.rag-metric {
  padding: 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-surface-strong);
  border: 1px solid var(--el-border-color);
}

.rag-metric span {
  display: block;
  color: var(--app-muted);
  font-size: 11px;
  margin-bottom: 4px;
}

.rag-metric strong {
  font-size: 16px;
}

/* Tab body */
.tab-body {
  padding: 0;
}
.tab-body :deep(.el-tabs__header) {
  margin: 0 20px;
}
.tab-body :deep(.el-tabs__content) {
  padding: 16px 20px 20px;
}

/* ===== Responsive ===== */
@media (max-width: 1024px) {
  .hero-metrics {
    grid-template-columns: 1fr 1fr;
  }
  .input-split {
    grid-template-columns: 1fr;
  }
  .rag-confidence-metrics {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 768px) {
  .analysis-hero {
    padding: 18px;
  }
  .hero-metrics {
    grid-template-columns: 1fr;
  }
  .score-center {
    flex-direction: column;
    text-align: center;
  }
  .action-bar {
    flex-direction: column;
    align-items: flex-start;
  }
  .pipeline-status {
    grid-template-columns: 1fr;
  }
  .rag-confidence-metrics {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .panel-body {
    padding: 16px;
  }
  .hero-metrics {
    grid-template-columns: 1fr;
  }
  .hero-title-main h2 {
    font-size: 26px;
  }
}
</style>
