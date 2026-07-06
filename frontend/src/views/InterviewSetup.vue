<template>
  <div class="interview-setup-page">
    <section class="hero-card">
      <div class="hero-copy-shell">
        <div class="hero-copy-stack">
          <div class="hero-title-row">
            <div>
              <span class="hero-kicker">Interview Workspace</span>
              <h1>AI 模拟面试</h1>
            </div>
            <div class="hero-orbits" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
          <p class="hero-desc">围绕目标岗位生成一场更有节奏的模拟面试，先定配置，再进房间，最后看报告。</p>
        </div>
      </div>
      <div class="hero-stats">
        <div class="stat-card">
          <span class="stat-label">历史场次</span>
          <strong>{{ stats.total }}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">已完成</span>
          <strong>{{ stats.completed }}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">平均得分</span>
          <strong>{{ stats.avgScore }}</strong>
        </div>
      </div>
    </section>

    <section class="setup-grid">
      <el-card shadow="never" class="setup-panel">
        <template #header>
          <div class="panel-header">
            <span>面试配置</span>
            <el-tag type="danger" effect="plain">基础版</el-tag>
          </div>
        </template>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="setup-form"
        >
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
                  <span class="option-meta">{{ resume.parsed?.current_title || resume.current_title || '' }}</span>
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
              <el-option
                v-for="jd in jdList"
                :key="jd.id"
                :label="jd.title"
                :value="jd.id"
              >
                <div class="option-row">
                  <span>{{ jd.title }}</span>
                  <span class="option-meta">{{ jd.company || '未填写公司' }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>

          <el-form-item label="面试风格" prop="interview_type">
            <el-radio-group v-model="form.interview_type" class="type-group">
              <el-radio-button
                v-for="item in typeOptions"
                :key="item.value"
                :value="item.value"
              >
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
              <span v-for="focus in typeConfig.focus" :key="focus" class="focus-chip">{{ focus }}</span>
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
      </el-card>

      <div class="preview-column">
        <el-card shadow="never" class="preview-panel">
          <template #header>
            <div class="panel-header">
              <span>面试蓝图</span>
              <span class="panel-sub">进入房间前先看清楚这场面试会怎么问</span>
            </div>
          </template>

          <div class="brief-block">
            <div class="brief-title">候选人画像</div>
            <template v-if="selectedResume">
              <h3>{{ selectedResume.name || selectedResume.file_name }}</h3>
              <p>{{ selectedResume.parsed?.current_title || selectedResume.current_title || '未识别当前岗位' }}</p>
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
              <p>{{ selectedJD.company || '未填写公司' }} · {{ selectedJD.salary_range || '薪资待补充' }}</p>
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
        </el-card>

        <el-card shadow="never" class="history-panel">
          <template #header>
            <div class="panel-header">
              <span>最近面试记录</span>
              <span class="panel-sub">可以直接回看报告或继续未完成场次</span>
            </div>
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
        </el-card>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { getInterviewList } from '@/api/interview'
import { getJDList } from '@/api/jd'
import { getResumeList } from '@/api/resume'
import { useInterviewStore } from '@/stores/interview'

const router = useRouter()
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

const typeOptions = [
  { value: 'tech', label: '技术深挖' },
  { value: 'hr', label: 'HR / 行为面' },
  { value: 'comprehensive', label: '综合面试' },
]

const typeConfigs = {
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
}

const typeConfig = computed(() => typeConfigs[form.interview_type] || typeConfigs.tech)

const selectedResume = computed(() => resumeList.value.find(item => item.id === form.resume_id))
const selectedJD = computed(() => jdList.value.find(item => item.id === form.jd_id))

const questionPlan = computed(() => {
  const mapping = {
    tech: { total: '10 题', duration: '12-18 分钟' },
    hr: { total: '10 题', duration: '10-15 分钟' },
    comprehensive: { total: '10 题', duration: '15-20 分钟' },
  }
  return mapping[form.interview_type] || mapping.tech
})

const stagePlan = computed(() => [
  { index: '01', title: '开场摸底', desc: '先用基础题或背景题做热身，判断你的表达与切入方式。' },
  { index: '02', title: '核心深挖', desc: typeConfig.value.description },
  { index: '03', title: '追问和压力点', desc: '低分答案会触发追问，系统会看你能否补全逻辑链。' },
  { index: '04', title: '结果复盘', desc: '结束后生成是否建议推进、短板风险和训练建议。' },
])

const stats = computed(() => {
  const total = historyList.value.length
  const completed = historyList.value.filter(item => item.status === 'completed').length
  const scores = historyList.value
    .map(item => item.evaluation?.overall_score)
    .filter(score => typeof score === 'number' && score > 0)
  const avgScore = scores.length ? Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length) : '--'
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
  const mapping = {
    created: 'info',
    ongoing: 'warning',
    completed: 'success',
  }
  return mapping[status] || 'info'
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
    ElMessage.success(`面试已创建，共 ${session.total_questions} 道题`)
    router.push(`/interview/room/${session.id}`)
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

onMounted(() => {
  fetchResumes()
  fetchJDs()
  fetchHistory()
})
</script>

<style scoped>
.interview-setup-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero-card {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 20px;
  padding: 28px;
  border-radius: 30px;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at left bottom, rgba(223, 185, 122, 0.12), transparent 28%),
    radial-gradient(circle at top right, rgba(120, 193, 150, 0.16), transparent 28%),
    linear-gradient(135deg, #fbfdfb, #f4faf6 52%, #eef5f0);
  color: var(--app-text);
  border: 1px solid rgba(217, 231, 222, 0.92);
}

.hero-card::before {
  content: '';
  position: absolute;
  left: -32px;
  top: 22px;
  width: 180px;
  height: 180px;
  border-radius: 40px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.65), rgba(255, 255, 255, 0));
  border: 1px solid rgba(217, 231, 222, 0.9);
  transform: rotate(-14deg);
}

.hero-card::after {
  content: '';
  position: absolute;
  right: 56px;
  bottom: -46px;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  border: 1px dashed rgba(140, 171, 152, 0.36);
}

.hero-kicker {
  display: inline-block;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-card h1 {
  margin: 8px 0 0;
  font-size: 32px;
  line-height: 1.2;
}

.hero-copy-shell {
  position: relative;
  z-index: 1;
  min-height: 140px;
  display: flex;
  align-items: center;
}

.hero-copy-stack {
  width: 100%;
}

.hero-title-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(217, 231, 222, 0.9);
  backdrop-filter: blur(10px);
}

.hero-desc {
  margin: 14px 2px 0;
  max-width: 640px;
  color: var(--app-muted);
  line-height: 1.8;
}

.hero-orbits {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.hero-orbits span {
  display: block;
  border-radius: 999px;
  background: linear-gradient(135deg, #c66a3d, #dfb76a);
  box-shadow: 0 8px 18px rgba(198, 106, 61, 0.18);
}

.hero-orbits span:nth-child(1) {
  width: 12px;
  height: 12px;
}

.hero-orbits span:nth-child(2) {
  width: 30px;
  height: 10px;
  opacity: 0.8;
}

.hero-orbits span:nth-child(3) {
  width: 18px;
  height: 18px;
  opacity: 0.58;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  align-self: end;
  position: relative;
  z-index: 1;
}

.stat-card {
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(217, 231, 222, 0.9);
  backdrop-filter: blur(10px);
}

.stat-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.stat-card strong {
  display: block;
  margin-top: 8px;
  font-size: 28px;
  color: var(--app-text);
}

.setup-grid {
  display: grid;
  grid-template-columns: minmax(340px, 420px) 1fr;
  gap: 20px;
  align-items: start;
}

.setup-panel,
.preview-panel,
.history-panel {
  border-radius: 26px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}

.panel-sub {
  font-size: 12px;
  color: var(--app-muted);
  font-weight: 400;
}

.setup-form :deep(.el-select) {
  width: 100%;
}

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

.type-group {
  width: 100%;
}

.type-preview {
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, #fff8f1, #f8fbf8);
  border: 1px solid rgba(228, 216, 194, 0.92);
}

.type-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.type-title span {
  color: #9a6d4a;
  font-size: 13px;
}

.type-preview p {
  margin: 0 0 12px;
  color: #586a61;
  line-height: 1.7;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.focus-chip,
.plain-chip {
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 12px;
}

.focus-chip {
  background: #fff0e4;
  color: #b66036;
}

.plain-chip {
  background: #f2f6f3;
  color: #4d6157;
}

.checklist {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 18px;
}

.check-item {
  padding: 14px;
  border-radius: 16px;
  background: #f4f8f5;
  border: 1px solid rgba(217, 231, 222, 0.9);
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
  border-radius: 14px;
}

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
  color: #8b95a7;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.brief-block h3 {
  margin: 0 0 6px;
  font-size: 22px;
  color: #1d2a39;
}

.brief-block p {
  margin: 0 0 12px;
  color: #64748b;
}

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
  border-radius: 18px;
  background: #f6f8fb;
}

.stage-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: #1c3351;
  color: #fff;
  font-weight: 700;
}

.stage-card strong {
  display: block;
  color: #223145;
}

.stage-card p {
  margin: 6px 0 0;
  color: #6b778a;
  line-height: 1.6;
}

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
  border-bottom: 1px solid #edf0f5;
}

.history-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.history-title {
  font-weight: 600;
  color: #1e2b3b;
}

.history-meta {
  margin-top: 5px;
  color: #8b95a7;
  font-size: 13px;
}

.history-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 1100px) {
  .hero-card,
  .setup-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .hero-card {
    padding: 22px;
  }

  .hero-title-row {
    padding: 16px;
  }

  .hero-card h1 {
    font-size: 26px;
  }

  .hero-copy-shell {
    min-height: auto;
  }

  .hero-stats,
  .checklist {
    grid-template-columns: 1fr;
  }

  .hero-title-row,
  .history-actions {
    width: 100%;
  }

  .hero-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .history-item,
  .type-title {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
