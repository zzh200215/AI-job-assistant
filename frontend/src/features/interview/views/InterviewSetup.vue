<template>
  <div class="page-shell interview-setup-page">
    <div class="page-header">
      <div>
        <h2>AI 模拟面试</h2>
        <div class="page-header-sub">
          围绕目标岗位生成一场更有节奏的模拟面试，先定配置，再进房间，最后看报告。
        </div>
      </div>
    </div>

    <section class="setup-journey" aria-label="面试创建步骤">
      <div
        v-for="step in journeySteps"
        :key="step.index"
        class="journey-step"
        :class="{ complete: setupStep > step.index, active: setupStep === step.index }"
      >
        <span class="journey-index">0{{ step.index }}</span>
        <div>
          <strong>{{ step.title }}</strong>
          <small>{{ step.detail }}</small>
        </div>
      </div>
    </section>

    <div class="grid-3 stat-row">
      <div class="stat-card">
        <div class="stat-body">
          <span class="stat-label">历史场次</span>
          <strong>{{ stats.total }}</strong>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-body">
          <span class="stat-label">已完成</span>
          <strong>{{ stats.completed }}</strong>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-body">
          <span class="stat-label">平均得分</span>
          <strong>{{ stats.avgScore }}</strong>
        </div>
      </div>
    </div>

    <div class="setup-grid">
      <AppPanel>
        <template #title>配置本场面试</template>
        <template #actions>
          <el-tag type="danger" effect="plain">基础版</el-tag>
        </template>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="setup-form">
          <el-form-item label="选择简历" prop="resume_id">
            <el-select
              v-model="form.resume_id"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              placeholder="选择要用于面试的简历"
              filterable
              :loading="loading.resume"
            >
              <el-option
                v-for="resume in resumeList"
                :key="resume.id"
                :label="resume.name || resume.file_name"
                :value="resume.id"
              >
                <div class="option-row">
                  <span>{{ resume.name || resume.file_name }}</span>
                  <span class="option-meta">{{
                    resume.parsed?.current_title || resume.current_title || ''
                  }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>

          <el-form-item label="目标岗位" prop="jd_id">
            <el-select
              v-model="form.jd_id"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              placeholder="选择目标 JD"
              filterable
              :loading="loading.jd"
            >
              <el-option v-for="jd in jdList" :key="jd.id" :label="jd.title" :value="jd.id">
                <div class="option-row">
                  <span>{{ jd.title }}</span>
                  <span class="option-meta">{{ jd.company || '未填写公司' }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>

          <el-form-item label="面试风格" prop="interview_type">
            <el-radio-group v-model="form.interview_type" class="type-group">
              <el-radio-button v-for="item in typeOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </el-radio-button>
            </el-radio-group>
          </el-form-item>

          <div class="type-preview">
            <div class="type-title">
              <strong>{{ typeConfig.label }}</strong>
              <span>{{ typeConfig.persona }}</span>
            </div>
            <p>{{ typeConfig.description }}</p>
            <div class="chip-row">
              <span v-for="focus in typeConfig.focus" :key="focus" class="focus-chip">{{
                focus
              }}</span>
            </div>
          </div>

          <div class="checklist">
            <div class="check-item">
              <span>预计题量</span>
              <strong>{{ questionPlan.total }}</strong>
            </div>
            <div class="check-item">
              <span>预计时长</span>
              <strong>{{ questionPlan.duration }}</strong>
            </div>
            <div class="check-item">
              <span>单题节奏</span>
              <strong>30 秒限时</strong>
            </div>
          </div>

          <!-- 题库配置 -->
          <div class="question-bank-config">
            <div class="qb-header">
              <span class="qb-title">题库配置</span>
              <span class="qb-subtitle"
                >{{ questionPlan.total }} · 覆盖 {{ questionCategories.length }} 类题型</span
              >
            </div>
            <div class="qb-grid">
              <div v-for="cat in questionCategories" :key="cat.type" class="qb-item">
                <div class="qb-icon" :class="'qb-' + cat.color">
                  <el-icon :size="16"><component :is="cat.icon" /></el-icon>
                </div>
                <div class="qb-info">
                  <span class="qb-name">{{ cat.label }}</span>
                  <span class="qb-count">{{ cat.count }} 题</span>
                </div>
              </div>
            </div>
          </div>

          <el-button
            type="primary"
            size="large"
            class="start-btn"
            :loading="loading.start"
            :disabled="!form.resume_id || !form.jd_id"
            @click="startInterview"
          >
            开始这场模拟面试
          </el-button>
        </el-form>
      </AppPanel>

      <div class="preview-column">
        <AppPanel>
          <template #title>面试蓝图</template>
          <template #actions>
            <span class="panel-sub">进入房间前先看清楚这场面试会怎么问</span>
          </template>
          <div class="brief-block">
            <div class="brief-title">候选人画像</div>
            <template v-if="selectedResume">
              <h3>{{ selectedResume.name || selectedResume.file_name }}</h3>
              <p>
                {{
                  selectedResume.parsed?.current_title ||
                  selectedResume.current_title ||
                  '未识别当前岗位'
                }}
              </p>
              <div class="chip-row">
                <span
                  v-for="skill in extractResumeSkills(selectedResume).slice(0, 6)"
                  :key="skill"
                  class="plain-chip"
                >
                  {{ skill }}
                </span>
              </div>
            </template>
            <el-empty v-else description="选择简历后会展示候选人画像" :image-size="70" />
          </div>

          <div class="brief-block">
            <div class="brief-title">岗位画像</div>
            <template v-if="selectedJD">
              <h3>{{ selectedJD.title }}</h3>
              <p>
                {{ selectedJD.company || '未填写公司' }} ·
                {{ selectedJD.salary_range || '薪资待补充' }}
              </p>
              <div class="chip-row">
                <span
                  v-for="skill in extractJDSkills(selectedJD).slice(0, 8)"
                  :key="skill"
                  class="plain-chip"
                >
                  {{ skill }}
                </span>
              </div>
            </template>
            <el-empty v-else description="选择 JD 后会展示岗位画像" :image-size="70" />
          </div>

          <div class="blueprint-list">
            <div v-for="stage in stagePlan" :key="stage.title" class="stage-card">
              <span class="stage-index">{{ stage.index }}</span>
              <div>
                <strong>{{ stage.title }}</strong>
                <p>{{ stage.desc }}</p>
              </div>
            </div>
          </div>
        </AppPanel>

        <AppPanel>
          <template #title>最近面试记录</template>
          <template #actions>
            <span class="panel-sub">可以直接回看报告或继续未完成场次</span>
          </template>
          <el-empty
            v-if="!historyList.length && !loading.history"
            description="还没有模拟面试记录"
            :image-size="80"
          />

          <div v-else class="history-list">
            <div v-for="item in historyList.slice(0, 4)" :key="item.id" class="history-item">
              <div>
                <div class="history-title">{{ item.jd_summary?.title || '未命名岗位' }}</div>
                <div class="history-meta">
                  {{ item.resume_summary?.name || '未知候选人' }}
                  <span>·</span>
                  {{ typeLabel(item.interview_type) }}
                </div>
              </div>
              <div class="history-actions">
                <el-tag :type="statusTagType(item.status)" effect="plain">
                  {{ statusLabel(item.status) }}
                </el-tag>
                <el-button text type="primary" @click="openSession(item)">
                  {{ item.status === 'completed' ? '查看报告' : '进入面试' }}
                </el-button>
              </div>
            </div>
          </div>
        </AppPanel>
      </div>
    </div>
  </div>
</template>

<script setup>
import AppPanel from '@/components/ui/AppPanel.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { getInterviewConfigTypes, getInterviewList } from '@/api/interview'
import { getJDList } from '@/api/jd'
import { getResumeList } from '@/api/resume'
import { INTERVIEW_STATUS_TAGS, tagTypeFor } from '@/utils/statusTone'
import { useInterviewStore } from '@/stores/interview'
import {
  Aim,
  ChatDotRound,
  Coin,
  DataAnalysis,
  Microphone,
  QuestionFilled,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const store = useInterviewStore()
const formRef = ref(null)

const form = reactive({
  resume_id: null,
  jd_id: null,
  interview_type: 'tech',
})

const loading = reactive({
  resume: false,
  jd: false,
  start: false,
  history: false,
})

const resumeList = ref([])
const jdList = ref([])
const historyList = ref([])

const rules = {
  resume_id: [{ required: true, message: '请选择简历', trigger: 'change' }],
  jd_id: [{ required: true, message: '请选择目标岗位', trigger: 'change' }],
  interview_type: [{ required: true, message: '请选择面试风格', trigger: 'change' }],
}

const defaultTypeOptions = [
  { value: 'tech', label: '技术深挖' },
  { value: 'hr', label: 'HR / 行为面' },
  { value: 'comprehensive', label: '综合面试' },
  { value: 'stress', label: '压力面试' },
  { value: 'group', label: '群面模拟' },
]

const defaultTypeConfigs = {
  tech: {
    label: '技术深挖',
    persona: '像一位会持续追问的技术面试官',
    description: '优先检查技术基本功、系统理解、项目细节和设计取舍。',
    focus: ['原理解释', '项目拆解', '设计权衡', '追问细节'],
  },
  hr: {
    label: 'HR / 行为面',
    persona: '像一位关注动机与表达的招聘经理',
    description: '更看重表达、动机、协作方式、成长性与稳定性。',
    focus: ['职业动机', '沟通表达', '冲突处理', '稳定性判断'],
  },
  comprehensive: {
    label: '综合面试',
    persona: '像一位全流程面试官',
    description: '技术、项目、行为与场景题混合，更接近真实面试组合拳。',
    focus: ['技术基础', '项目贡献', '行为案例', '场景判断'],
  },
  stress: {
    label: '压力面试',
    persona: '像一位会不断质疑和打断的面试官',
    description: '持续追问、挑战你的回答，考察你在压力环境下的思维逻辑和情绪控制能力。',
    focus: ['快速追问', '打断再问', '极限场景', '抗压能力'],
  },
  group: {
    label: '群面模拟',
    persona: '像一位观察多个候选人的面试官',
    description: '模拟无领导小组讨论场景，评估你的团队角色、协作方式和影响力。',
    focus: ['团队角色', '观点输出', '协调能力', '总结能力'],
  },
}

// T3-2：题型配置从后端拉取（租户自定义优先），失败回落内置静态配置
const typeOptions = ref(defaultTypeOptions)
const typeConfigs = ref(defaultTypeConfigs)

async function loadTypeConfigs() {
  try {
    const data = await getInterviewConfigTypes()
    if (!data?.items?.length) return
    const options = []
    const configs = {}
    for (const item of data.items) {
      const t = item.type
      options.push({ value: t, label: item.title || t })
      configs[t] = {
        label: item.title || t,
        persona: item.persona || defaultTypeConfigs[t]?.persona || 'AI 面试官',
        description: item.description || defaultTypeConfigs[t]?.description || '',
        focus: item.focus?.length ? item.focus : defaultTypeConfigs[t]?.focus || [],
        tags: item.tags || [],
        is_custom: !!item.is_custom,
      }
    }
    if (options.length) {
      typeOptions.value = options
      typeConfigs.value = configs
    }
  } catch {
    // 接口失败保持内置静态配置
  }
}

const typeConfig = computed(() => typeConfigs.value[form.interview_type] || typeConfigs.value.tech)

const setupStep = computed(() => {
  if (!form.resume_id) return 1
  if (!form.jd_id) return 2
  return 3
})

const journeySteps = computed(() => [
  {
    index: 1,
    title: '候选人资料',
    detail: form.resume_id ? '简历已选定' : '选择用于本场面试的简历',
  },
  { index: 2, title: '目标岗位', detail: form.jd_id ? '岗位已选定' : '确定本场面试的 JD' },
  {
    index: 3,
    title: '面试场景',
    detail: `${typeConfig.value.label} · ${questionPlan.value.total}`,
  },
])

const selectedResume = computed(() => resumeList.value.find((item) => item.id === form.resume_id))
const selectedJD = computed(() => jdList.value.find((item) => item.id === form.jd_id))

const questionPlan = computed(() => {
  const mapping = {
    tech: { total: '10 题', duration: '12-18 分钟' },
    hr: { total: '10 题', duration: '10-15 分钟' },
    comprehensive: { total: '10 题', duration: '15-20 分钟' },
    stress: { total: '12 题', duration: '15-22 分钟' },
    group: { total: '8 题', duration: '20-30 分钟' },
  }
  return mapping[form.interview_type] || mapping.tech
})

const questionCategories = computed(() => {
  const base = [
    { type: 'base', label: '基础能力', icon: QuestionFilled, color: 'blue', count: 3 },
    { type: 'project', label: '项目经验', icon: Aim, color: 'violet', count: 2 },
    { type: 'behavior', label: '行为面试', icon: ChatDotRound, color: 'amber', count: 2 },
    { type: 'tech', label: '技术深度', icon: DataAnalysis, color: 'green', count: 2 },
  ]
  if (form.interview_type === 'stress') {
    base.push({ type: 'stress_q', label: '压力场景', icon: Microphone, color: 'red', count: 3 })
  }
  if (form.interview_type === 'group') {
    base.push({ type: 'group_q', label: '小组讨论', icon: Coin, color: 'teal', count: 3 })
    base.splice(2, 1) // 群面无单独行为面
  }
  return base
})

const stagePlan = computed(() => [
  { index: '01', title: '开场摸底', desc: '先用基础题或背景题做热身，判断你的表达与切入方式。' },
  { index: '02', title: '核心深挖', desc: typeConfig.value.description },
  { index: '03', title: '追问和压力点', desc: '低分答案会触发追问，系统会看你能否补全逻辑链。' },
  { index: '04', title: '结果复盘', desc: '结束后生成是否建议推进、短板风险和训练建议。' },
])

const stats = computed(() => {
  const total = historyList.value.length
  const completed = historyList.value.filter((item) => item.status === 'completed').length
  const scores = historyList.value
    .map((item) => item.evaluation?.overall_score)
    .filter((score) => typeof score === 'number' && score > 0)
  const avgScore = scores.length
    ? Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length)
    : '--'
  return { total, completed, avgScore }
})

function extractResumeSkills(resume) {
  if (!resume) return []
  const parsed = resume.parsed || resume.parsed_json || {}
  const skills = parsed.skills || parsed.core_skills || []
  return Array.isArray(skills) ? skills : []
}

function extractJDSkills(jd) {
  if (!jd) return []
  const parsed = jd.parsed || jd.parsed_json || {}
  const skills = parsed.required_skills || parsed.skills || jd.skill_tags || []
  return Array.isArray(skills) ? skills : []
}

function typeLabel(type) {
  return typeConfigs[type]?.label || type || '未定义'
}

function statusLabel(status) {
  const mapping = {
    created: '待开始',
    ongoing: '进行中',
    completed: '已完成',
  }
  return mapping[status] || status
}

function statusTagType(status) {
  return tagTypeFor(INTERVIEW_STATUS_TAGS, status)
}

async function fetchResumes() {
  loading.resume = true
  try {
    const data = await getResumeList()
    resumeList.value = data?.items || (Array.isArray(data) ? data : [])
  } finally {
    loading.resume = false
  }
}

async function fetchJDs() {
  loading.jd = true
  try {
    const data = await getJDList()
    jdList.value = data?.items || (Array.isArray(data) ? data : [])
  } finally {
    loading.jd = false
  }
}

async function fetchHistory() {
  loading.history = true
  try {
    historyList.value = await getInterviewList()
  } finally {
    loading.history = false
  }
}

async function startInterview() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  loading.start = true
  try {
    const session = await store.initSession(form.resume_id, form.jd_id, form.interview_type)
    ElMessage.success(`面试已创建，共 ${session.total_questions} 道题，正在进入面试房间`)
    router.push(`/interview/room/${session.id}`)
  } catch (error) {
    ElMessage.error(error?.message || '创建面试失败，请检查简历和岗位配置后重试')
  } finally {
    loading.start = false
  }
}

function openSession(item) {
  if (item.status === 'completed') {
    router.push(`/interview/report/${item.id}`)
    return
  }
  router.push(`/interview/room/${item.id}`)
}

onMounted(async () => {
  await Promise.all([fetchResumes(), fetchJDs()])
  fetchHistory()
  loadTypeConfigs()
  if (route.query.jd_id) {
    const jid = Number(route.query.jd_id)
    if (!isNaN(jid)) form.jd_id = jid
  }
  if (route.query.resume_id) {
    const rid = Number(route.query.resume_id)
    if (!isNaN(rid)) form.resume_id = rid
  }
})
</script>

<style scoped>
/* ---- Stat row ---- */
.stat-row {
  margin-bottom: 20px;
}

.stat-row .stat-card {
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.stat-row .stat-body strong {
  font-size: 28px;
  margin-top: 4px;
}

.interview-setup-page {
  background: linear-gradient(135deg, #f7f9fd 0%, #f3f6fc 100%);
}

.setup-journey {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin: 0 0 20px;
  overflow: hidden;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-surface-strong);
}

.journey-step {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 74px;
  padding: 14px 18px;
  border-right: 1px solid var(--app-line);
  color: var(--app-muted);
}

.journey-step:last-child {
  border-right: 0;
}

.journey-step::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
  background: transparent;
  content: '';
}

.journey-step.active {
  background: #f4f7ff;
  color: var(--app-text);
}

.journey-step.active::after,
.journey-step.complete::after {
  background: var(--app-primary);
}

.journey-step.complete .journey-index {
  background: var(--app-success);
}

.journey-index {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 50%;
  background: #e6eaf2;
  color: #fff;
  font-family: var(--app-font-mono);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.journey-step.active .journey-index {
  background: var(--app-primary);
}

.journey-step strong,
.journey-step small {
  display: block;
}

.journey-step strong {
  font-size: 13px;
}

.journey-step small {
  margin-top: 3px;
  color: var(--app-muted);
  font-size: 12px;
}

/* ---- Setup grid ---- */
.setup-grid {
  display: grid;
  grid-template-columns: minmax(340px, 420px) 1fr;
  gap: 20px;
  align-items: start;
}

.panel-sub {
  font-size: 12px;
  color: var(--app-muted);
  font-weight: 400;
}

.setup-form :deep(.el-select) {
  width: 100%;
}

/* ---- Option row ---- */
.option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.option-meta {
  color: var(--app-muted);
  font-size: 12px;
}

/* ---- Type group ---- */
.type-group {
  width: 100%;
}

.type-group :deep(.el-radio-button) {
  margin: 0 6px 8px 0;
}

.type-group :deep(.el-radio-button__inner) {
  min-width: 94px;
  border: 1px solid var(--app-line) !important;
  border-radius: var(--app-radius-xs) !important;
  box-shadow: none !important;
}

.type-group :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  border-color: var(--app-primary) !important;
  background: var(--app-primary-light) !important;
  color: var(--app-primary) !important;
}

.type-preview {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.type-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.type-title span {
  color: var(--app-warning);
  font-size: 13px;
}

.type-preview p {
  margin: 0 0 12px;
  color: var(--app-muted);
  line-height: 1.7;
}

/* ---- Chips ---- */
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.focus-chip,
.plain-chip {
  padding: 5px 10px;
  border-radius: var(--app-radius-xs, 8px);
  font-size: 12px;
}

.focus-chip {
  background: var(--app-bg);
  color: var(--app-warning);
}

.plain-chip {
  background: var(--app-bg);
  color: var(--app-success);
}

/* ---- Checklist ---- */
.checklist {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 18px;
}

.check-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.check-item span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.check-item strong {
  display: block;
  margin-top: 8px;
  color: var(--app-text);
}

.start-btn {
  width: 100%;
  height: 48px;
  margin-top: 22px;
  border-radius: var(--app-radius-sm, 12px);
}

/* 题库配置 */
.question-bank-config {
  margin-top: 16px;
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}
.qb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.qb-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text);
}
.qb-subtitle {
  font-size: 12px;
  color: var(--app-muted);
}
.qb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.qb-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
}
.qb-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.qb-blue {
  background: var(--app-primary-light);
  color: var(--app-primary);
}
.qb-violet {
  background: var(--app-violet-light);
  color: var(--app-violet);
}
.qb-amber {
  background: #fef5e7;
  color: var(--app-warning);
}
.qb-green {
  background: #e8f8ee;
  color: var(--app-success);
}
.qb-red {
  background: #fff3f0;
  color: var(--app-danger);
}
.qb-teal {
  background: #e6fffa;
  color: #0d9488;
}
.qb-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.qb-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text);
}
.qb-count {
  font-size: 11px;
  color: var(--app-muted);
}

/* ---- Preview column ---- */
.preview-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.brief-block + .brief-block {
  margin-top: 20px;
}

.brief-title {
  margin-bottom: 10px;
  color: var(--app-muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.brief-block h3 {
  margin: 0 0 6px;
  font-size: 18px;
  color: var(--app-text);
}

.brief-block p {
  margin: 0 0 12px;
  color: var(--app-muted);
}

/* ---- Blueprint list ---- */
.blueprint-list {
  display: grid;
  gap: 12px;
  margin-top: 20px;
}

.stage-card {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 12px;
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.stage-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-primary);
  color: #fff;
  font-weight: 700;
}

.stage-card strong {
  display: block;
  color: var(--app-text);
}

.stage-card p {
  margin: 6px 0 0;
  color: var(--app-muted);
  line-height: 1.6;
}

.setup-grid > .panel:first-child {
  border-top: 3px solid var(--app-primary);
}

.preview-column > .panel:first-child {
  border-top: 3px solid var(--app-cyan);
}

/* ---- History ---- */
.history-list {
  display: grid;
  gap: 12px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--app-line);
}

.history-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.history-title {
  font-weight: 600;
  color: var(--app-text);
}

.history-meta {
  margin-top: 5px;
  color: var(--app-muted);
  font-size: 13px;
}

.history-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ---- Responsive ---- */
@media (max-width: 1100px) {
  .setup-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .setup-journey {
    grid-template-columns: 1fr;
  }

  .journey-step {
    min-height: 64px;
    border-right: 0;
    border-bottom: 1px solid var(--app-line);
  }

  .journey-step:last-child {
    border-bottom: 0;
  }

  .checklist {
    grid-template-columns: 1fr;
  }

  .history-item,
  .type-title {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
