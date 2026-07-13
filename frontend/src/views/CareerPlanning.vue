<template>
  <div class="page-shell">
    <section class="career-hero">
      <div class="hero-copy">
        <div class="hero-kicker">Career Planning</div>
        <h2>职业规划工作台</h2>
        <div class="page-header-sub">
          用现有简历做职业现状判断，设定目标岗位，再生成能力差距、成长路线图和投递策略。
        </div>
        <div class="hero-pills">
          <span>目标岗位建模</span>
          <span>能力雷达</span>
          <span>成长路线</span>
          <span>投递策略</span>
        </div>
      </div>

      <div class="hero-summary">
        <div class="summary-card tone-blue">
          <span>当前简历</span>
          <strong>{{ selectedResumeLabel || '待选择' }}</strong>
          <small>{{ selectedResumeHint }}</small>
        </div>
        <div class="summary-card tone-green">
          <span>目标岗位</span>
          <strong>{{ targetRole || selectedJDLabel || '待填写' }}</strong>
          <small>{{ selectedJD ? '使用已有 JD' : '可自动生成目标 JD' }}</small>
        </div>
        <div class="summary-card tone-amber">
          <span>当前阶段</span>
          <strong>{{ currentStageLabel }}</strong>
          <small>会影响投递节奏和学习重点</small>
        </div>
        <div class="summary-card tone-dark">
          <span>分析状态</span>
          <strong>{{ analysisStatusLabel }}</strong>
          <small>{{ latestMatchLabel }}</small>
        </div>
      </div>
    </section>

    <el-card class="control-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>规划输入</span>
          <el-tag type="info" size="small">复用 CareerAgent + Analysis Flow</el-tag>
        </div>
      </template>

      <el-alert
        v-if="baseOptionsError"
        class="load-error"
        type="warning"
        :closable="false"
        show-icon
        title="简历与岗位数据加载失败"
        description="职业规划需要一份已解析简历。请检查网络后重新加载。"
      >
        <template #default>
          <el-button size="small" type="primary" plain @click="refreshBaseOptions">重新加载</el-button>
        </template>
      </el-alert>

      <div class="control-grid">
        <div class="control-column">
          <div class="field-label">当前状态</div>
          <el-form label-position="top">
            <el-form-item label="选择简历" required>
              <el-select
                v-model="selectedResumeId"
                placement="bottom-start"
                :fallback-placements="['bottom-start']"
                filterable
                placeholder="选择一份已解析的简历"
                class="full-width"
              >
                <el-option
                  v-for="item in resumeOptions"
                  :key="item.id"
                  :label="resumeOptionLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="职业阶段">
              <el-select
                v-model="currentStage"
                placement="bottom-start"
                :fallback-placements="['bottom-start']"
                class="full-width"
              >
                <el-option
                  v-for="item in stageOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="当前关注点">
              <el-input
                v-model="focusNotes"
                type="textarea"
                :rows="4"
                placeholder="例如：希望 6 个月内从后端转向 AI 工程，优先补齐系统设计和项目深度。"
              />
            </el-form-item>
          </el-form>
        </div>

        <div class="control-column">
          <div class="field-label">目标岗位</div>
          <el-form label-position="top">
            <el-form-item label="目标岗位名称" required>
              <el-input
                v-model="targetRole"
                placeholder="例如：AI 应用工程师 / 高级后端工程师 / RAG 工程师"
              />
            </el-form-item>

            <el-form-item label="复用已有 JD（可选）">
              <el-select
                v-model="selectedJDId"
                placement="bottom-start"
                :fallback-placements="['bottom-start']"
                clearable
                filterable
                placeholder="选中后直接用该 JD 做规划"
                class="full-width"
              >
                <el-option
                  v-for="item in jdOptions"
                  :key="item.id"
                  :label="jdOptionLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="目标补充要求">
              <el-input
                v-model="goalNotes"
                type="textarea"
                :rows="4"
                placeholder="例如：希望岗位偏 AI 应用落地，要求有 LangGraph、RAG、系统设计、项目 owner 经验。"
              />
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div class="action-row">
        <div class="action-copy">
          <strong>系统会先构建目标 JD，再触发完整分析链路</strong>
          <span>输出职业阶段判断、能力差距、成长路线、项目实践和投递策略。</span>
        </div>
        <div class="action-buttons">
          <el-button @click="refreshBaseOptions" :loading="optionsLoading">刷新数据</el-button>
          <el-button type="primary" :loading="running" @click="startCareerPlanning">
            {{ running ? '职业规划生成中…' : '开始职业规划' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card v-if="running && agentSteps.length" class="progress-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>Agent 执行进度</span>
          <el-tag type="warning" size="small"
            >{{ completedSteps }} / {{ agentSteps.length }} 步</el-tag
          >
        </div>
      </template>

      <div class="progress-snapshot">
        <div class="snapshot-item">
          <span>当前步骤</span>
          <strong>{{ currentStepName }}</strong>
        </div>
        <div class="snapshot-item">
          <span>已完成</span>
          <strong>{{ completedSteps }}</strong>
        </div>
        <div class="snapshot-item">
          <span>任务状态</span>
          <strong>{{ taskStatusLabel }}</strong>
        </div>
      </div>

      <el-timeline class="progress-timeline">
        <el-timeline-item
          v-for="step in agentSteps"
          :key="step.id || `${step.step_name}-${step.step_index}`"
          :type="stepType(step.status)"
          :icon="stepIcon(step.status)"
        >
          <div class="timeline-title">{{ stepLabel(step.step_name) }}</div>
          <div class="timeline-meta">
            {{ statusText(step.status) }}
            <span v-if="step.duration_ms"> · {{ step.duration_ms }}ms</span>
          </div>
          <div v-if="step.error_msg" class="timeline-error">{{ step.error_msg }}</div>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <el-row v-if="careerResult" :gutter="18" class="result-grid">
      <el-col :xl="16" :lg="15" :md="24">
        <div class="result-stack">
          <el-card class="overview-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>规划总览</span>
                <el-tag :type="strategyTagType">{{ strategySummary.mode }}</el-tag>
              </div>
            </template>

            <div class="overview-grid">
              <div class="status-panel">
                <span>当前阶段</span>
                <strong>{{
                  careerResult.current_status?.career_stage || currentStageLabel
                }}</strong>
                <small>{{
                  localizedCurrentStatusSummary || '已结合简历与目标岗位生成阶段判断。'
                }}</small>
              </div>
              <div class="status-panel">
                <span>当前职级</span>
                <strong>{{ careerResult.current_status?.level || '-' }}</strong>
                <small>{{
                  joinedText(careerResult.current_status?.strengths) || '等待职业优势总结'
                }}</small>
              </div>
              <div class="status-panel">
                <span>能力缺口</span>
                <strong>{{ skillGapCount }}</strong>
                <small>{{
                  joinedText(careerResult.current_status?.development_areas) || '等待生成发展方向'
                }}</small>
              </div>
            </div>

            <el-alert
              v-if="localizedOverallAdvice"
              class="overview-advice"
              :title="localizedOverallAdvice"
              type="success"
              :closable="false"
              show-icon
            />
          </el-card>

          <el-card v-if="radarDimensions.length" class="radar-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>能力差距雷达图</span>
                <div class="legend-row">
                  <span class="legend-chip legend-current">当前</span>
                  <span class="legend-chip legend-target">目标</span>
                </div>
              </div>
            </template>

            <div class="radar-layout">
              <div class="radar-svg-shell">
                <svg viewBox="0 0 320 320" class="radar-svg" aria-hidden="true">
                  <polygon
                    v-for="(ring, index) in radarRings"
                    :key="`ring-${index}`"
                    :points="ring"
                    class="radar-ring"
                  />
                  <line
                    v-for="axis in radarAxes"
                    :key="axis.name"
                    :x1="centerPoint"
                    :y1="centerPoint"
                    :x2="axis.x"
                    :y2="axis.y"
                    class="radar-axis"
                  />
                  <polygon :points="radarTargetPoints" class="radar-target-shape" />
                  <polygon :points="radarCurrentPoints" class="radar-current-shape" />
                  <text
                    v-for="axis in radarAxes"
                    :key="`label-${axis.name}`"
                    :x="axis.labelX"
                    :y="axis.labelY"
                    class="radar-text"
                  >
                    {{ axis.name }}
                  </text>
                </svg>
              </div>

              <div class="radar-metrics">
                <div v-for="dim in radarDimensions" :key="dim.name" class="radar-row">
                  <div class="radar-copy">
                    <strong>{{ dim.name }}</strong>
                    <span>{{
                      dim.gap ||
                      `${safeScore(dim.target_score) - safeScore(dim.current_score)} 分提升空间`
                    }}</span>
                  </div>
                  <div class="radar-bars">
                    <div class="bar-track">
                      <div
                        class="bar-current"
                        :style="{ width: `${safeScore(dim.current_score)}%` }"
                      ></div>
                    </div>
                    <div class="bar-track target-track">
                      <div
                        class="bar-target"
                        :style="{ width: `${safeScore(dim.target_score)}%` }"
                      ></div>
                    </div>
                  </div>
                  <div class="radar-values">
                    <span>{{ safeScore(dim.current_score) }}</span>
                    <span>{{ safeScore(dim.target_score) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </el-card>

          <el-card v-if="learningResources.length" class="resource-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>学习资源推荐</span>
                <el-tag size="small" type="warning">{{ learningResources.length }} 项</el-tag>
              </div>
            </template>
            <div class="resource-list">
              <div v-for="item in learningResources" :key="item.skill" class="resource-item">
                <div class="resource-top">
                  <strong>{{ item.skill }}</strong>
                  <el-tag size="small" :type="item.priority === '高' ? 'danger' : 'warning'">{{
                    item.priority
                  }}</el-tag>
                </div>
                <div class="resource-links">
                  <a
                    v-for="res in item.resources"
                    :key="res.name"
                    :href="res.link"
                    class="resource-link"
                    target="_blank"
                  >
                    <el-tag size="small" effect="plain" type="info">{{ res.type }}</el-tag>
                    {{ res.name }}
                  </a>
                </div>
              </div>
            </div>
          </el-card>

          <el-card v-if="roadmapPhases.length" class="roadmap-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>学习路线图</span>
                <el-tag type="info" size="small">
                  {{ careerResult.visual_roadmap?.total_duration_months || roadmapDuration }} 个月
                </el-tag>
              </div>
            </template>

            <el-timeline>
              <el-timeline-item
                v-for="phase in roadmapPhases"
                :key="phase.id || phase.name"
                :timestamp="`${phase.order || '-'} / ${phase.duration_months || '-'}个月`"
                :color="phase.color || '#409EFF'"
                placement="top"
              >
                <div class="phase-card">
                  <div class="phase-head">
                    <strong>{{ phase.name }}</strong>
                    <span>{{ phase.projects?.length || 0 }} 个项目实践</span>
                  </div>
                  <div class="phase-tags">
                    <el-tag
                      v-for="skill in phase.skills || []"
                      :key="`${phase.name}-${skill}`"
                      size="small"
                      effect="plain"
                    >
                      {{ skill }}
                    </el-tag>
                  </div>
                  <ul class="phase-list">
                    <li v-for="item in phase.milestones || []" :key="item.name">
                      {{ item.name }}：{{ item.description }}
                    </li>
                  </ul>
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-card>

          <el-card v-if="projectRecommendations.length" class="projects-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>推荐项目实践</span>
                <el-tag type="success" size="small">{{ projectRecommendations.length }} 项</el-tag>
              </div>
            </template>

            <div class="project-grid">
              <article
                v-for="item in projectRecommendations"
                :key="item.project"
                class="project-card"
              >
                <div class="project-top">
                  <strong>{{ item.project }}</strong>
                  <el-tag size="small" :type="complexityTag(item.complexity)">{{
                    item.complexity || '中等'
                  }}</el-tag>
                </div>
                <p>{{ item.description || item.reason }}</p>
                <div class="project-meta">预计周期：{{ item.estimated_time || '4-8 周' }}</div>
                <div class="project-tags">
                  <el-tag
                    v-for="tech in item.tech_stack || []"
                    :key="`${item.project}-${tech}`"
                    size="small"
                    effect="plain"
                  >
                    {{ tech }}
                  </el-tag>
                </div>
              </article>
            </div>
          </el-card>
        </div>
      </el-col>

      <el-col :xl="8" :lg="9" :md="24">
        <div class="result-stack">
          <el-card class="strategy-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>岗位投递策略</span>
                <el-tag :type="strategyTagType">{{ strategySummary.mode }}</el-tag>
              </div>
            </template>

            <div class="strategy-score">
              <div class="score-circle">{{ latestMatchScore }}</div>
              <div class="score-copy">
                <strong>{{ strategySummary.title }}</strong>
                <p>{{ strategySummary.reason }}</p>
              </div>
            </div>

            <div class="strategy-split">
              <div v-for="item in strategySummary.mix" :key="item.label" class="split-row">
                <span>{{ item.label }}</span>
                <div class="split-bar">
                  <div class="split-fill" :style="{ width: `${item.value}%` }"></div>
                </div>
                <strong>{{ item.value }}%</strong>
              </div>
            </div>

            <ul class="strategy-list">
              <li v-for="item in strategySummary.actions" :key="item">{{ item }}</li>
            </ul>
          </el-card>

          <el-card v-if="skillGaps.length" class="gap-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>优先补齐能力</span>
                <el-tag type="warning" size="small">{{ skillGaps.length }} 项</el-tag>
              </div>
            </template>

            <div class="gap-list">
              <article v-for="gap in skillGaps" :key="gap.skill" class="gap-item">
                <div class="gap-top">
                  <strong>{{ gap.skill }}</strong>
                  <el-tag size="small" :type="priorityTag(gap.priority)">{{
                    gap.priority || '中'
                  }}</el-tag>
                </div>
                <p>
                  {{
                    gap.importance || gap.acquisition_method || '建议通过项目实践和定向训练补齐。'
                  }}
                </p>
                <div class="gap-levels">
                  <span>{{ gap.current_level || '当前水平未知' }}</span>
                  <span>→</span>
                  <span>{{ gap.target_level || '目标水平未知' }}</span>
                </div>
              </article>
            </div>
          </el-card>

          <el-card v-if="careerPaths.length" class="direction-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>推荐职业方向</span>
                <el-button text size="small" :loading="careerPathLoading" @click="loadCareerPaths">
                  刷新
                </el-button>
              </div>
            </template>

            <div class="direction-list">
              <article
                v-for="item in careerPaths"
                :key="item.path || item.position"
                class="direction-item"
              >
                <div class="direction-top">
                  <strong>{{ item.path || item.position || item.title || '岗位方向' }}</strong>
                  <span>{{ item.match_score || item.score || '--' }}</span>
                </div>
                <p>{{ item.reason || item.summary || '根据简历现状给出的方向建议。' }}</p>
              </article>
            </div>
          </el-card>

          <el-card class="salary-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>薪资成长预测</span>
                <el-tag size="small" type="success"
                  >{{ salaryPrediction.growthRate }}% 年增长率</el-tag
                >
              </div>
            </template>
            <div class="salary-body">
              <div class="salary-current">
                <span class="salary-label">当前预估</span>
                <strong>{{ salaryPrediction.currentSalary }}K</strong>
                <small>{{ salaryPrediction.benchmark }}</small>
              </div>
              <div class="salary-arrow">
                <el-icon><ArrowRight /></el-icon>
              </div>
              <div class="salary-current">
                <span class="salary-label">5年后预估</span>
                <strong class="salary-future">{{ salaryPrediction.fiveYearSalary }}K</strong>
                <small>{{ salaryPrediction.level }}</small>
              </div>
            </div>
            <div class="salary-chart">
              <div v-for="p in salaryPrediction.predictions" :key="p.year" class="salary-bar-col">
                <div
                  class="salary-bar"
                  :style="{ height: (p.salary / salaryPrediction.fiveYearSalary) * 100 + '%' }"
                />
                <span class="salary-bar-label">{{ p.year }}</span>
                <span class="salary-bar-val">{{ p.salary }}K</span>
              </div>
            </div>
          </el-card>

          <el-card class="next-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span>下一步动作</span>
                <div class="next-actions">
                  <el-button
                    v-if="analysisRecordId"
                    text
                    size="small"
                    @click="router.push(`/analysis/${analysisRecordId}`)"
                  >
                    查看完整分析
                  </el-button>
                  <el-button text size="small" @click="router.push('/jobs/search')"
                    >去岗位市场</el-button
                  >
                  <el-button text size="small" @click="router.push('/interview/setup')"
                    >去模拟面试</el-button
                  >
                </div>
              </div>
            </template>

            <div class="next-block">
              <div class="next-title">短期</div>
              <ul>
                <li v-for="item in localizedShortTermGoals" :key="`short-${item}`">{{ item }}</li>
              </ul>
            </div>
            <div class="next-block">
              <div class="next-title">中期</div>
              <ul>
                <li v-for="item in localizedMidTermGoals" :key="`mid-${item}`">{{ item }}</li>
              </ul>
            </div>
            <div class="next-block">
              <div class="next-title">长期</div>
              <ul>
                <li v-for="item in localizedLongTermGoals" :key="`long-${item}`">{{ item }}</li>
              </ul>
            </div>
          </el-card>
        </div>
      </el-col>
    </el-row>

    <el-card v-else-if="analysisRecordId && !running" class="next-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>结果提示</span>
          <el-tag type="warning">职业规划内容缺失</el-tag>
        </div>
      </template>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="完整分析记录已生成，但这次没有返回职业规划内容。你可以先查看完整分析结果，或重新生成职业规划。"
      />

      <div class="next-actions inline-actions">
        <el-button type="primary" @click="router.push(`/analysis/${analysisRecordId}`)"
          >查看完整分析</el-button
        >
        <el-button @click="startCareerPlanning">重新生成职业规划</el-button>
        <el-button @click="router.push('/jobs/search')">去岗位市场</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from '@/plugins/element-services'
import {
  ArrowRight,
  CircleCloseFilled,
  Loading,
  SuccessFilled,
  WarningFilled,
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { getResumeList } from '@/api/resume'
import { createJD, getJDList } from '@/api/jd'
import { runFullAnalysis, getAnalysis } from '@/api/analysis'
import { recommendCareerPaths } from '@/api/jobs'
import { useAgentTaskPolling } from '@/composables/useAgentTaskPolling'
import { localizeSentence, normalizeLocalizedTextList } from '@/utils/analysisLocalization'

const router = useRouter()

const stageOptions = [
  { value: 'entry', label: '初入职场' },
  { value: 'growth', label: '成长期' },
  { value: 'mature', label: '成熟期' },
  { value: 'transition', label: '转型期' },
]

const resumeOptions = ref([])
const jdOptions = ref([])
const selectedResumeId = ref(null)
const selectedJDId = ref(null)
const currentStage = ref('growth')
const targetRole = ref('')
const focusNotes = ref('')
const goalNotes = ref('')
const optionsLoading = ref(false)
const baseOptionsError = ref(false)

const running = ref(false)
const taskStatus = ref('pending')
const agentSteps = ref([])
const careerPathLoading = ref(false)
const careerPaths = ref([])

const analysisRecordId = ref(null)
const analysisResult = ref(null)
const { pollTask } = useAgentTaskPolling()

const centerPoint = 160
const radarRadius = 116

const selectedResume = computed(
  () => resumeOptions.value.find((item) => item.id === selectedResumeId.value) || null
)
const selectedJD = computed(
  () => jdOptions.value.find((item) => item.id === selectedJDId.value) || null
)
const careerResult = computed(() => analysisResult.value?.career_planning || null)
const latestMatchScore = computed(() => Number(analysisResult.value?.match_score || 0))
const localizedCurrentStatusSummary = computed(() =>
  localizeSentence(careerResult.value?.current_status?.summary || '')
)
const localizedOverallAdvice = computed(() =>
  localizeSentence(careerResult.value?.overall_advice || '')
)
const analysisStatusLabel = computed(() => {
  if (running.value) return '分析中'
  if (careerResult.value) return '已生成'
  if (analysisRecordId.value && taskStatus.value === 'partial') return '部分完成'
  if (analysisRecordId.value) return '已完成'
  if (taskStatus.value === 'failed') return '失败'
  if (taskStatus.value === 'cancelled') return '已取消'
  return '待启动'
})
const latestMatchLabel = computed(() => {
  if (running.value) return 'Agent 正在生成职业规划'
  if (careerResult.value) return `匹配度 ${latestMatchScore.value}`
  if (analysisRecordId.value) return '完整分析已生成，但职业规划内容为空'
  if (taskStatus.value === 'failed') return '生成失败，请重试'
  if (taskStatus.value === 'cancelled') return '任务已取消'
  return '等待生成职业规划'
})

const selectedResumeLabel = computed(() =>
  selectedResume.value ? resumeOptionLabel(selectedResume.value) : ''
)
const selectedResumeHint = computed(() => {
  if (!selectedResume.value) return '请选择一份已解析简历'
  return (
    selectedResume.value.parsed?.current_title || `${selectedResume.value.years_exp || 0} 年经验`
  )
})
const selectedJDLabel = computed(() => (selectedJD.value ? jdOptionLabel(selectedJD.value) : ''))
const currentStageLabel = computed(
  () => stageOptions.find((item) => item.value === currentStage.value)?.label || '成长期'
)

const completedSteps = computed(
  () => agentSteps.value.filter((item) => item.status === 'completed').length
)
const currentStepName = computed(() => {
  const runningStep = agentSteps.value.find((item) => item.status === 'running')
  if (runningStep) return stepLabel(runningStep.step_name)
  const pendingStep = agentSteps.value.find((item) => item.status === 'pending')
  if (pendingStep) return stepLabel(pendingStep.step_name)
  const lastStep = [...agentSteps.value].reverse().find((item) => item.status === 'completed')
  return lastStep ? stepLabel(lastStep.step_name) : '等待启动'
})
const taskStatusLabel = computed(
  () =>
    ({
      pending: '等待中',
      running: '执行中',
      completed: '已完成',
      partial: '部分完成',
      cancelled: '已取消',
      failed: '失败',
    })[taskStatus.value] || taskStatus.value
)

const radarDimensions = computed(() => {
  const dimensions = careerResult.value?.skill_radar?.dimensions || []
  return Array.isArray(dimensions) ? dimensions.slice(0, 6) : []
})

const radarAxes = computed(() => {
  const count = radarDimensions.value.length
  if (!count) return []
  return radarDimensions.value.map((item, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count
    const x = centerPoint + Math.cos(angle) * radarRadius
    const y = centerPoint + Math.sin(angle) * radarRadius
    const labelX = centerPoint + Math.cos(angle) * (radarRadius + 24)
    const labelY = centerPoint + Math.sin(angle) * (radarRadius + 24)
    return {
      name: item.name,
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
      labelX: Number(labelX.toFixed(2)),
      labelY: Number(labelY.toFixed(2)),
    }
  })
})

const radarRings = computed(() =>
  [25, 50, 75, 100].map((value) => makeRadarPolygon(radarDimensions.value.map(() => value)))
)
const radarCurrentPoints = computed(() =>
  makeRadarPolygon(radarDimensions.value.map((item) => safeScore(item.current_score)))
)
const radarTargetPoints = computed(() =>
  makeRadarPolygon(radarDimensions.value.map((item) => safeScore(item.target_score)))
)

const roadmapPhases = computed(() => {
  const phases = careerResult.value?.visual_roadmap?.phases || []
  return Array.isArray(phases) ? [...phases].sort((a, b) => (a.order || 0) - (b.order || 0)) : []
})
const roadmapDuration = computed(() =>
  roadmapPhases.value.reduce((sum, item) => sum + Number(item.duration_months || 0), 0)
)

const projectRecommendations = computed(() => {
  const items = careerResult.value?.project_recommendations || []
  return Array.isArray(items) ? items : []
})

const skillGaps = computed(() => {
  const items = careerResult.value?.skill_gaps || []
  if (!Array.isArray(items)) return []
  return items
    .map((item) => (typeof item === 'string' ? { skill: item } : item))
    .filter((item) => item && item.skill)
})
const skillGapCount = computed(() => skillGaps.value.length)
const localizedShortTermGoals = computed(() =>
  normalizeLocalizedTextList(careerResult.value?.short_term_plan?.goals)
)
const localizedMidTermGoals = computed(() =>
  normalizeLocalizedTextList(careerResult.value?.mid_term_plan?.goals)
)
const localizedLongTermGoals = computed(() =>
  normalizeLocalizedTextList(careerResult.value?.long_term_plan?.goals)
)

// 薪资成长预测
const salaryPrediction = computed(() => {
  const stage = currentStage.value
  const score = latestMatchScore.value
  const yearsExp = selectedResume.value?.years_exp || 3
  const currentTitle = selectedResume.value?.parsed?.current_title || ''

  const baseSalary = Math.max(10, yearsExp * 5 + 8)
  const growthRate = score >= 80 ? 0.35 : score >= 60 ? 0.25 : 0.15
  const stageMultiplier =
    stage === 'entry' ? 1.5 : stage === 'growth' ? 1.3 : stage === 'mature' ? 1.1 : 1.2

  const predictions = []
  for (let i = 0; i < 5; i++) {
    const year = new Date().getFullYear() + i
    const salary = Math.round(
      baseSalary * Math.pow(1 + growthRate, i) * (i === 0 ? 1 : stageMultiplier)
    )
    predictions.push({
      year,
      salary,
      growth: i === 0 ? 0 : Math.round((salary / predictions[i - 1]?.salary - 1) * 100),
    })
  }
  return {
    currentSalary: predictions[0]?.salary || baseSalary,
    fiveYearSalary: predictions[4]?.salary || baseSalary * 2,
    growthRate: Math.round(growthRate * 100),
    predictions,
    benchmark: yearsExp >= 5 ? '高级工程师/专家' : yearsExp >= 3 ? '中级工程师' : '初级工程师',
    level: currentTitle ? '对标' + currentTitle.replace(/.*?(\w+)/, '$1') : '行业平均水平',
  }
})

// 学习资源推荐
const learningResources = computed(() => {
  const gaps = skillGaps.value
  if (!gaps.length) return []
  return gaps.slice(0, 5).map((gap) => {
    const skill = gap.skill || ''
    const resources = []
    const priority = gap.priority || '中'
    if (skill.includes('系统设计') || skill.includes('架构')) {
      resources.push({
        type: '书籍',
        name: '《系统设计面试》',
        link: 'https://book.douban.com/subject/35246717/',
      })
      resources.push({ type: '课程', name: 'Grokking System Design', link: '#' })
    } else if (skill.includes('算法') || skill.includes('数据结构')) {
      resources.push({ type: '平台', name: 'LeetCode', link: 'https://leetcode.cn' })
      resources.push({ type: '书籍', name: '《算法导论》', link: '#' })
    } else if (skill.includes('项目') || skill.includes('管理')) {
      resources.push({ type: '课程', name: '项目管理 PMP 认证', link: '#' })
      resources.push({ type: '书籍', name: '《人人都是项目经理》', link: '#' })
    } else {
      resources.push({ type: '实践', name: `${skill} 专项项目`, link: '#' })
      resources.push({ type: '课程', name: `${skill} 入门到精通`, link: '#' })
    }
    return { skill, priority, resources, gap: gap }
  })
})

const strategySummary = computed(() => {
  const score = latestMatchScore.value
  const gaps = skillGapCount.value
  const stage = currentStage.value

  if (score >= 80 && gaps <= 3) {
    return {
      mode: '精准投',
      title: '以重点岗位为主线推进',
      reason: '当前匹配度较高，建议收缩投递面，优先冲击最契合的岗位和团队。',
      mix: [
        { label: '精准投', value: 65 },
        { label: '海投', value: 25 },
        { label: '保底投', value: 10 },
      ],
      actions: [
        '优先投递与目标岗位高度相符的 10-15 个 JD。',
        '围绕项目亮点和能力缺口定制简历版本。',
        '把面试准备集中在系统设计、项目深度和目标行业理解上。',
      ],
    }
  }

  if (score < 60 || stage === 'entry' || stage === 'transition') {
    return {
      mode: '保底投',
      title: '先建立成交概率，再逐步上探',
      reason: '当前还处于能力过渡期，先保证 offer 概率，再同步做技能补齐和项目积累。',
      mix: [
        { label: '精准投', value: 20 },
        { label: '海投', value: 30 },
        { label: '保底投', value: 50 },
      ],
      actions: [
        '优先投递与现有经验连续性强的岗位，缩短转化链路。',
        '每周固定补一个短板项目，把学习成果尽快转成简历素材。',
        '对高门槛岗位先做储备，不要把投递节奏完全压在少数目标公司上。',
      ],
    }
  }

  return {
    mode: '海投',
    title: '扩大样本，快速验证市场反馈',
    reason: '匹配度处于中段，先通过更大样本验证定位，再筛出适合深投的岗位。',
    mix: [
      { label: '精准投', value: 35 },
      { label: '海投', value: 45 },
      { label: '保底投', value: 20 },
    ],
    actions: [
      '按岗位族群批量投递，观察面邀率和岗位反馈。',
      '把简历拆成 2-3 个版本，分别对应后端、AI 工程、平台工程方向。',
      '每拿到一次面试反馈，就回收修正技能缺口和话术重点。',
    ],
  }
})

const strategyTagType = computed(
  () =>
    ({
      精准投: 'success',
      海投: 'warning',
      保底投: 'info',
    })[strategySummary.value.mode] || 'info'
)

watch(selectedResumeId, async (value) => {
  if (!value) {
    careerPaths.value = []
    return
  }
  localStorage.setItem('recruit.lastResumeId', String(value))
  if (!targetRole.value && selectedResume.value?.parsed?.current_title) {
    targetRole.value = selectedResume.value.parsed.current_title
  }
  await loadCareerPaths()
})

watch(selectedJDId, (value) => {
  if (value) {
    localStorage.setItem('recruit.lastJDId', String(value))
    return
  }
  localStorage.removeItem('recruit.lastJDId')
})

onMounted(async () => {
  restoreSelections()
  await refreshBaseOptions()
})

function resumeOptionLabel(item) {
  const name = item.name || item.parsed?.name || item.file_name
  const title = item.parsed?.current_title || '待补充职称'
  return `${name} · ${title}`
}

function jdOptionLabel(item) {
  const company = item.company || '未填写公司'
  return `${item.title} · ${company}`
}

function restoreSelections() {
  const resumeId = localStorage.getItem('recruit.lastResumeId')
  const jdId = localStorage.getItem('recruit.lastJDId')
  if (resumeId) selectedResumeId.value = Number(resumeId)
  if (jdId) selectedJDId.value = Number(jdId)
}

async function refreshBaseOptions() {
  optionsLoading.value = true
  baseOptionsError.value = false
  try {
    const [resumeData, jdData] = await Promise.all([
      getResumeList({ page_size: 50 }),
      getJDList({ page_size: 50 }),
    ])
    resumeOptions.value = (resumeData?.items || []).filter(
      (item) => item.parsed && Object.keys(item.parsed).length
    )
    jdOptions.value = jdData?.items || []

    if (
      selectedResumeId.value &&
      !resumeOptions.value.some((item) => item.id === selectedResumeId.value)
    ) {
      selectedResumeId.value = null
    }
    if (selectedJDId.value && !jdOptions.value.some((item) => item.id === selectedJDId.value)) {
      selectedJDId.value = null
    }

    if (!selectedResumeId.value && resumeOptions.value.length) {
      selectedResumeId.value = resumeOptions.value[0].id
    }
  } catch {
    resumeOptions.value = []
    jdOptions.value = []
    baseOptionsError.value = true
  } finally {
    optionsLoading.value = false
  }
}

async function loadCareerPaths() {
  if (!selectedResumeId.value) return
  careerPathLoading.value = true
  try {
    const data = await recommendCareerPaths(selectedResumeId.value)
    careerPaths.value = data?.career_paths || []
  } catch {
    careerPaths.value = []
  } finally {
    careerPathLoading.value = false
  }
}

async function startCareerPlanning() {
  if (!selectedResumeId.value) {
    ElMessage.warning('请先选择简历')
    return
  }
  if (!targetRole.value.trim() && !selectedJDId.value) {
    ElMessage.warning('请填写目标岗位，或直接选择一个现有 JD')
    return
  }

  running.value = true
  taskStatus.value = 'running'
  analysisResult.value = null
  analysisRecordId.value = null
  agentSteps.value = []

  try {
    const effectiveJdId = selectedJD.value?.id || (await createGoalJD())
    const startRes = await runFullAnalysis({
      resume_id: selectedResumeId.value,
      jd_id: effectiveJdId,
    })

    if (!startRes?.task_id) {
      throw new Error('未拿到 task_id')
    }

    await pollTask(startRes.task_id, {
      timeoutMessage: '职业规划生成超时，请稍后重试',
      onProgress(taskData, steps) {
        taskStatus.value = taskData?.status || 'running'
        agentSteps.value = steps
      },
      async onCompleted(taskData) {
        taskStatus.value = taskData?.status || 'completed'
        analysisRecordId.value = taskData?.analysis_record_id || null
        if (!analysisRecordId.value) {
          throw new Error('分析完成但没有生成记录')
        }
        analysisResult.value = await getAnalysis(analysisRecordId.value)
        localStorage.setItem('recruit.lastRecordId', String(analysisRecordId.value))
      },
      onFailed() {
        taskStatus.value = 'failed'
      },
      onCancelled() {
        taskStatus.value = 'cancelled'
      },
      onTimeout() {
        taskStatus.value = 'failed'
      },
    })

    if (analysisRecordId.value) {
      await loadCareerPaths()
    }
  } catch (error) {
    taskStatus.value = error?.code === 'task_cancelled' ? 'cancelled' : 'failed'
    ElMessage.error(error?.message || '职业规划生成失败')
  } finally {
    running.value = false
  }
}

async function createGoalJD() {
  const payload = {
    title: targetRole.value.trim() || '目标岗位',
    company: '职业规划目标',
    raw_text: buildGoalJDText(),
  }
  const created = await createJD(payload)
  if (!created?.id) {
    throw new Error('目标 JD 创建失败')
  }
  selectedJDId.value = created.id
  const exists = jdOptions.value.some((item) => item.id === created.id)
  if (!exists) {
    jdOptions.value.unshift({
      id: created.id,
      title: created.title,
      company: created.company,
    })
  }
  return created.id
}

function buildGoalJDText() {
  const resume = selectedResume.value?.parsed || {}
  const skills = Array.isArray(resume.skills) ? resume.skills.join('、') : ''
  const currentTitle = resume.current_title || '当前岗位待识别'
  const years = resume.years_exp || 0
  const stage = currentStageLabel.value

  return [
    `目标岗位：${targetRole.value.trim() || '待补充'}`,
    `候选人当前阶段：${stage}`,
    `候选人当前岗位：${currentTitle}`,
    `候选人经验年限：${years} 年`,
    `候选人当前技能：${skills || '待根据简历解析'}`,
    '岗位要求：',
    `1. 适合从当前阶段成长到 ${targetRole.value.trim() || '目标岗位'} 的职责与能力要求。`,
    '2. 强调项目经验、系统设计、业务理解、软技能与交付能力。',
    '3. 输出应适合职业规划与学习路线设计，而不仅是纯招聘筛选。',
    `当前关注点：${focusNotes.value.trim() || '希望结合现有经验制定成长路径。'}`,
    `目标补充要求：${goalNotes.value.trim() || '优先考虑 AI 工程、后端架构、项目 owner 能力。'}`,
  ].join('\n')
}

function makeRadarPolygon(scores) {
  const count = scores.length
  if (!count) return ''
  return scores
    .map((score, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count
      const radius = (safeScore(score) / 100) * radarRadius
      const x = centerPoint + Math.cos(angle) * radius
      const y = centerPoint + Math.sin(angle) * radius
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

function safeScore(value) {
  const number = Number(value || 0)
  return Math.max(0, Math.min(100, Math.round(number)))
}

function joinedText(value) {
  if (!Array.isArray(value) || !value.length) return ''
  return value.join(' / ')
}

function priorityTag(priority) {
  return (
    {
      高: 'danger',
      中: 'warning',
      低: 'info',
    }[priority] || 'info'
  )
}

function complexityTag(complexity) {
  return (
    {
      困难: 'danger',
      中等: 'warning',
      简单: 'success',
    }[complexity] || 'info'
  )
}

function stepLabel(name) {
  return (
    {
      intent_recognition: '意图识别',
      resume_parse: '简历解析',
      jd_parse: 'JD 解析',
      task_planning: '任务规划',
      knowledge_retrieval: '知识检索',
      matching_analysis: '匹配分析',
      resume_optimization: '简历优化',
      interview_question_generation: '面试题生成',
      self_check: '自我校验',
      final_report: '汇总报告',
      career_planning: '职业规划',
    }[name] || name
  )
}

function statusText(status) {
  return (
    {
      pending: '等待中',
      running: '执行中',
      completed: '已完成',
      failed: '失败',
      skipped: '跳过',
    }[status] || status
  )
}

function stepType(status) {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'primary'
  if (status === 'failed') return 'danger'
  return 'info'
}

function stepIcon(status) {
  if (status === 'completed') return SuccessFilled
  if (status === 'running') return Loading
  if (status === 'failed') return CircleCloseFilled
  return WarningFilled
}
</script>

<style scoped>
.page-shell {
  max-width: 1480px;
  margin: 0 auto;
  padding: 18px 0 32px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--app-text);
}

.career-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(360px, 1fr);
  gap: 18px;
  padding: 28px;
  border-radius: var(--app-radius-md, 16px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
}

.hero-copy,
.hero-summary {
  position: relative;
  z-index: 1;
}

.hero-copy {
  padding: 24px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid var(--app-line);
}

.hero-kicker {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-copy h2 {
  margin: 10px 0 0;
  font-size: 40px;
  line-height: 1.05;
}

.hero-copy p {
  margin: 14px 0 0;
  max-width: 620px;
  color: var(--app-muted);
  line-height: 1.8;
}

.hero-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

.hero-pills span {
  padding: 8px 14px;
  border-radius: 999px;
  background: var(--app-bg);
  border: 1px solid var(--app-line);
  font-size: 12px;
}

.hero-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  position: relative;
  min-height: 134px;
  padding: 18px 18px 18px 76px;
  border-radius: var(--app-radius-sm, 12px);
  color: var(--app-text);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--app-shadow-soft);
}

.summary-card::before {
  content: '';
  position: absolute;
  left: 18px;
  top: 18px;
  width: 42px;
  height: 42px;
  border-radius: var(--app-radius-xs, 8px);
}

.summary-card span,
.summary-card small {
  color: var(--app-muted);
}

.summary-card strong {
  font-size: 24px;
  line-height: 1.2;
  color: var(--app-text);
}

.tone-blue::before {
  background: linear-gradient(135deg, #dff5e7, #c7ead4);
}
.tone-green::before {
  background: linear-gradient(135deg, #e8f7ea, #d5f0da);
}
.tone-amber::before {
  background: linear-gradient(135deg, #fff1e6, #f7dcc5);
}
.tone-dark::before {
  background: linear-gradient(135deg, #eef1ff, #dce3ff);
}

.control-card,
.progress-card,
.overview-card,
.radar-card,
.roadmap-card,
.projects-card,
.strategy-card,
.gap-card,
.direction-card,
.next-card,
.salary-card,
.resource-card {
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--app-shadow-soft);
}

.salary-card :deep(.el-card__header),
.resource-card :deep(.el-card__header) {
  padding: 22px 24px 16px;
  border-bottom: 1px solid var(--app-line);
  background: var(--app-bg);
}

.salary-card :deep(.el-card__body),
.resource-card :deep(.el-card__body) {
  padding: 24px;
}

/* 薪资预测 */
.salary-body {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: 16px;
  margin-bottom: 20px;
}

.salary-current {
  text-align: center;
}

.salary-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.salary-current strong {
  display: block;
  font-size: 32px;
  font-weight: 800;
  color: var(--app-primary);
  margin: 8px 0;
}

.salary-future {
  color: var(--app-success) !important;
}

.salary-current small {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.salary-arrow {
  color: var(--app-muted);
  font-size: 24px;
}

.salary-chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 80px;
  padding: 0 8px;
}

.salary-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
}

.salary-bar {
  width: 100%;
  max-width: 32px;
  border-radius: 6px 6px 0 0;
  background: linear-gradient(180deg, var(--app-primary), #7db0ee);
  transition: height 0.4s;
}

.salary-bar-label {
  margin-top: 4px;
  font-size: 10px;
  color: var(--app-muted);
}

.salary-bar-val {
  font-size: 10px;
  font-weight: 700;
  color: var(--app-primary);
}

/* 学习资源 */
.resource-list {
  display: grid;
  gap: 12px;
}

.resource-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.resource-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.resource-top strong {
  font-size: 14px;
  font-weight: 700;
}

.resource-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.resource-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--app-primary);
  cursor: pointer;
}

.resource-link:hover {
  text-decoration: underline;
}

.control-card :deep(.el-card__header),
.progress-card :deep(.el-card__header),
.overview-card :deep(.el-card__header),
.radar-card :deep(.el-card__header),
.roadmap-card :deep(.el-card__header),
.projects-card :deep(.el-card__header),
.strategy-card :deep(.el-card__header),
.gap-card :deep(.el-card__header),
.direction-card :deep(.el-card__header),
.next-card :deep(.el-card__header) {
  padding: 22px 24px 16px;
  border-bottom: 1px solid var(--app-line);
  background: var(--app-bg);
}

.control-card :deep(.el-card__body),
.progress-card :deep(.el-card__body),
.overview-card :deep(.el-card__body),
.radar-card :deep(.el-card__body),
.roadmap-card :deep(.el-card__body),
.projects-card :deep(.el-card__body),
.strategy-card :deep(.el-card__body),
.gap-card :deep(.el-card__body),
.direction-card :deep(.el-card__body),
.next-card :deep(.el-card__body) {
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}

.control-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.control-column {
  padding: 22px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.field-label {
  margin-bottom: 14px;
  font-size: 17px;
  font-weight: 700;
}

.full-width {
  width: 100%;
}

.action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--app-line);
}

.action-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.action-copy span {
  color: var(--app-muted);
  font-size: 13px;
}

.action-buttons {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.progress-snapshot {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.snapshot-item {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.snapshot-item span {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}

.snapshot-item strong {
  display: block;
  margin-top: 8px;
  font-size: 22px;
}

.progress-timeline {
  margin-top: 18px;
  padding: 12px 12px 0;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.timeline-title {
  font-weight: 600;
}

.timeline-meta,
.timeline-error {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-muted);
}

.timeline-error {
  color: var(--app-danger, #d03050);
}

.result-grid {
  margin: 0;
}

.result-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.status-panel {
  padding: 18px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.status-panel span,
.status-panel small {
  display: block;
}

.status-panel span,
.status-panel small {
  color: var(--app-muted);
}

.status-panel strong {
  display: block;
  margin: 10px 0 8px;
  font-size: 24px;
}

.overview-advice {
  margin-top: 16px;
}

.legend-row {
  display: flex;
  gap: 8px;
}

.legend-chip {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
}

.legend-current {
  background: rgba(215, 251, 246, 0.94);
  color: var(--app-success, #1c8c5e);
}

.legend-target {
  background: rgba(236, 229, 255, 0.94);
  color: var(--app-primary, #2ea866);
}

.radar-layout {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}

.radar-svg-shell {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--app-line);
}

.radar-svg {
  width: 100%;
  max-width: 380px;
  display: block;
  margin: 0 auto;
}

.radar-ring {
  fill: none;
  stroke: var(--app-line);
  stroke-width: 1;
}

.radar-axis {
  stroke: var(--app-line);
  stroke-width: 1;
}

.radar-current-shape {
  fill: rgba(32, 180, 172, 0.18);
  stroke: rgba(32, 180, 172, 0.95);
  stroke-width: 2;
}

.radar-target-shape {
  fill: rgba(127, 99, 244, 0.12);
  stroke: rgba(127, 99, 244, 0.9);
  stroke-width: 2;
  stroke-dasharray: 6 4;
}

.radar-text {
  fill: var(--app-text);
  font-size: 12px;
  text-anchor: middle;
}

.radar-metrics {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.radar-row {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.radar-copy {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.radar-copy span {
  color: var(--app-muted);
  font-size: 12px;
}

.radar-bars {
  display: grid;
  gap: 8px;
}

.bar-track {
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--app-line);
}

.target-track {
  background: rgba(232, 225, 255, 0.94);
}

.bar-current,
.bar-target {
  height: 100%;
  border-radius: inherit;
}

.bar-current {
  background: linear-gradient(90deg, #20b4ac, #74d7d1);
}

.bar-target {
  background: linear-gradient(90deg, #7f63f4, #a993ff);
}

.radar-values {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  color: var(--app-muted);
  font-size: 12px;
}

.phase-card {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--app-line);
}

.phase-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.phase-head span {
  color: var(--app-muted);
  font-size: 12px;
}

.phase-tags,
.project-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.phase-list,
.strategy-list,
.next-block ul {
  margin: 12px 0 0;
  padding-left: 18px;
}

.phase-list li,
.strategy-list li,
.next-block li {
  line-height: 1.8;
  color: var(--app-text);
}

.project-grid,
.gap-list,
.direction-list {
  display: grid;
  gap: 12px;
}

.project-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.project-card,
.gap-item,
.direction-item {
  padding: 18px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--app-line);
}

.project-top,
.gap-top,
.direction-top,
.phase-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.project-card p,
.gap-item p,
.direction-item p,
.strategy-score p {
  margin: 10px 0 0;
  color: var(--app-muted);
  line-height: 1.75;
}

.project-meta,
.gap-levels {
  margin-top: 10px;
  color: var(--app-muted);
  font-size: 12px;
}

.gap-levels {
  display: flex;
  gap: 8px;
}

.strategy-score {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
}

.score-circle {
  width: 92px;
  height: 92px;
  border-radius: var(--app-radius-md, 16px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #7f63f4, #5f7cf7);
  box-shadow: 0 16px 32px rgba(116, 121, 240, 0.2);
}

.score-copy strong {
  font-size: 20px;
}

.strategy-split {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.split-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 40px;
  gap: 10px;
  align-items: center;
}

.split-row span,
.split-row strong {
  font-size: 12px;
}

.split-bar {
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--app-line);
}

.split-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #20b4ac, #74d7d1);
}

.next-block + .next-block {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--app-line);
}

.next-title {
  font-weight: 700;
}

@media (max-width: 1200px) {
  .career-hero,
  .radar-layout,
  .control-grid,
  .overview-grid,
  .project-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .page-shell {
    padding-top: 8px;
  }

  .career-hero {
    padding: 18px;
  }

  .hero-copy h2 {
    font-size: 30px;
  }

  .hero-summary,
  .progress-snapshot,
  .overview-grid,
  .project-grid {
    grid-template-columns: 1fr;
  }

  .action-row,
  .action-buttons {
    flex-direction: column;
    align-items: stretch;
  }

  .strategy-score {
    grid-template-columns: 1fr;
  }

  .score-circle {
    width: 80px;
    height: 80px;
    border-radius: var(--app-radius-sm, 12px);
  }
}
</style>
