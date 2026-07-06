<template>
  <div class="report-page" v-loading="loading">
    <template v-if="report">
      <section class="report-hero">
        <div>
          <p class="eyebrow">Interview Debrief</p>
          <h1>{{ report.jd_summary?.title || 'AI 模拟面试复盘' }}</h1>
          <p>{{ report.resume_summary?.name || '候选人' }} · {{ typeLabel }}</p>
        </div>
        <div class="hero-score">
          <div class="score-ring" :style="{ '--score-color': scoreColor(report.overall_score) }">
            <strong>{{ report.overall_score }}</strong>
            <span>综合得分</span>
          </div>
          <el-tag :type="recommendTagType" effect="dark" size="large">
            {{ localizedHiringRecommendation || '待定' }}
          </el-tag>
        </div>
      </section>

      <section class="summary-grid">
        <div class="summary-card">
          <span>完成题数</span>
          <strong>{{ report.answered_questions }} / {{ report.total_questions }}</strong>
        </div>
        <div class="summary-card">
          <span>总用时</span>
          <strong>{{ formattedDuration }}</strong>
        </div>
        <div class="summary-card">
          <span>超时次数</span>
          <strong>{{ timeoutCount }}</strong>
        </div>
        <div class="summary-card">
          <span>最强维度</span>
          <strong>{{ strongestDimension.label }}</strong>
        </div>
      </section>

      <section class="report-grid">
        <div class="main-column">
          <el-card shadow="never" class="report-card">
            <template #header>
              <div class="card-header">
                <span>面试结论</span>
                <span class="sub">把分数翻译成更接近真实面试判断的语言</span>
              </div>
            </template>
            <div class="decision-strip" :style="{ borderColor: scoreColor(report.overall_score) }">
              <div>
                <div class="decision-label">当前判断</div>
                <strong>{{ verdictTitle }}</strong>
              </div>
              <p>{{ localizedOverallEvaluation || fallbackEvaluation }}</p>
            </div>
          </el-card>

          <el-card shadow="never" class="report-card">
            <template #header>
              <div class="card-header">
                <span>能力画像</span>
                <span class="sub">看清楚强项和最容易失分的点</span>
              </div>
            </template>
            <div class="dimension-list">
              <div v-for="(score, key) in report.dimension_scores" :key="key" class="dimension-item">
                <div class="dimension-top">
                  <span>{{ dimLabels[key] || key }}</span>
                  <strong :style="{ color: scoreColor(score) }">{{ score }}</strong>
                </div>
                <div class="dimension-track">
                  <div class="dimension-fill" :style="{ width: `${score}%`, background: scoreColor(score) }"></div>
                </div>
                <p>{{ dimensionComment(key, score) }}</p>
              </div>
            </div>
          </el-card>

          <div class="two-col">
            <el-card shadow="never" class="report-card">
              <template #header>
                <div class="card-header">
                  <span>亮点</span>
                </div>
              </template>
              <ul class="plain-list">
                <li v-for="item in localizedStrengths.length ? localizedStrengths : fallbackStrengths" :key="item">
                  {{ item }}
                </li>
              </ul>
            </el-card>

            <el-card shadow="never" class="report-card">
              <template #header>
                <div class="card-header">
                  <span>风险点</span>
                </div>
              </template>
              <ul class="plain-list warning">
                <li v-for="item in localizedWeaknesses.length ? localizedWeaknesses : fallbackWeaknesses" :key="item">
                  {{ item }}
                </li>
              </ul>
            </el-card>
          </div>

          <el-card shadow="never" class="report-card">
            <template #header>
              <div class="card-header">
                <span>逐题时间线</span>
                <span class="sub">比单纯堆分数更接近真实面试复盘</span>
              </div>
            </template>

            <div class="timeline-list">
              <div
                v-for="(item, index) in report.question_evaluations"
                :key="`${index}-${item.question_index}`"
                class="timeline-item"
              >
                <div class="timeline-badge">{{ index + 1 }}</div>
                <div class="timeline-content">
                  <div class="timeline-top">
                    <div>
                      <strong>{{ item.category || '通用问题' }}</strong>
                      <p>{{ item.question }}</p>
                    </div>
                    <div class="timeline-score" :style="{ color: scoreColor(item.overall_score) }">
                      {{ item.overall_score }}
                    </div>
                  </div>

                  <div class="timeline-tags">
                    <span>完整 {{ item.completeness }}</span>
                    <span>准确 {{ item.accuracy }}</span>
                    <span>深度 {{ item.depth }}</span>
                    <span>表达 {{ item.expression }}</span>
                  </div>

                  <div class="timeline-answer">
                    <div class="field-label">你的回答</div>
                    <p>{{ item.user_answer || '本题超时或未作答' }}</p>
                  </div>

                  <div class="timeline-answer">
                    <div class="field-label">面试官反馈</div>
                    <p>{{ item.feedback || '暂无反馈' }}</p>
                  </div>

                  <div v-if="item.improvement" class="timeline-answer">
                    <div class="field-label">如何补强</div>
                    <p class="improvement">{{ item.improvement }}</p>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </div>

        <aside class="side-column">
          <el-card shadow="never" class="report-card">
            <template #header>
              <div class="card-header">
                <span>下一步训练</span>
              </div>
            </template>
            <div class="training-list">
              <div v-for="(item, index) in trainingPlan" :key="`${index}-${item}`" class="training-item">
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
                <p>{{ item }}</p>
              </div>
            </div>
          </el-card>

          <el-card shadow="never" class="report-card">
            <template #header>
              <div class="card-header">
                <span>岗位对照</span>
              </div>
            </template>
            <div class="job-panel">
              <strong>{{ report.jd_summary?.title || '目标岗位' }}</strong>
              <p>{{ report.jd_summary?.company || '未填写公司' }}</p>
              <div class="job-skills">
                <span
                  v-for="skill in (report.jd_summary?.required_skills || []).slice(0, 8)"
                  :key="skill"
                >
                  {{ skill }}
                </span>
              </div>
            </div>
          </el-card>

          <el-card shadow="never" class="report-card">
            <template #header>
              <div class="card-header">
                <span>复盘摘要</span>
              </div>
            </template>
            <ul class="plain-list">
              <li>如果只看一项，先补 {{ weakestDimension.label }}。</li>
              <li>当前最稳定的能力维度是 {{ strongestDimension.label }}。</li>
                <li>{{ localizedHiringRecommendation || '系统当前未给出明确推进建议。' }}</li>
              </ul>
            </el-card>
        </aside>
      </section>

      <div class="report-actions">
        <el-button size="large" @click="goRoom">回到面试房间</el-button>
        <el-button type="primary" size="large" @click="restart">重新模拟一次</el-button>
        <el-button size="large" @click="goSetup">更换岗位/简历</el-button>
      </div>
    </template>

    <el-empty v-else description="未找到面试报告">
      <el-button type="primary" @click="goSetup">去创建模拟面试</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { getInterviewDetail } from '@/api/interview'
import {
  localizeRecommendationText,
  localizeSentence,
  normalizeLocalizedTextList,
} from '@/utils/analysisLocalization'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const report = ref(null)

const dimLabels = {
  completeness: '完整性',
  accuracy: '准确性',
  depth: '深度',
  expression: '表达',
}

const typeLabel = computed(() => {
  const labels = {
    tech: '技术深挖',
    hr: 'HR / 行为面',
    comprehensive: '综合面试',
  }
  return labels[report.value?.interview_type] || report.value?.interview_type || '未定义'
})

const formattedDuration = computed(() => {
  const seconds = report.value?.total_duration_seconds || 0
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins} 分 ${secs} 秒`
})

const timeoutCount = computed(() => {
  return report.value?.timeout_count || 0
})
const localizedHiringRecommendation = computed(() => localizeRecommendationText(report.value?.hiring_recommendation || ''))
const localizedOverallEvaluation = computed(() => localizeSentence(report.value?.overall_evaluation || ''))
const localizedStrengths = computed(() => normalizeLocalizedTextList(report.value?.strengths))
const localizedWeaknesses = computed(() => normalizeLocalizedTextList(report.value?.weaknesses))

const recommendTagType = computed(() => {
  const text = localizedHiringRecommendation.value || ''
  if (text.includes('推荐') || text.includes('推进')) return 'success'
  if (text.includes('不') || text.includes('谨慎')) return 'danger'
  return 'warning'
})

const sortedDimensions = computed(() => {
  const entries = Object.entries(report.value?.dimension_scores || {})
  return entries
    .map(([key, score]) => ({ key, label: dimLabels[key] || key, score: Number(score) || 0 }))
    .sort((a, b) => b.score - a.score)
})

const strongestDimension = computed(() => {
  return sortedDimensions.value[0] || { label: '待生成', score: 0 }
})

const weakestDimension = computed(() => {
  return sortedDimensions.value[sortedDimensions.value.length - 1] || { label: '待生成', score: 0 }
})

const fallbackEvaluation = computed(() => {
  return localizeSentence(`整体表现落在 ${verdictTitle.value}，建议优先补强 ${weakestDimension.value.label}，再巩固 ${strongestDimension.value.label} 的优势展示。`)
})

const fallbackStrengths = computed(() => [
  localizeSentence(`${strongestDimension.value.label} 是当前相对稳定的输出项`),
  localizeSentence('至少已经形成了一定的答题结构，不是完全散乱式回答'),
])

const fallbackWeaknesses = computed(() => [
  localizeSentence(`${weakestDimension.value.label} 是当前主要短板`),
  localizeSentence('部分回答可能还停留在结论层，缺少细节、数据或取舍支撑'),
])

const verdictTitle = computed(() => {
  const score = report.value?.overall_score || 0
  if (score >= 85) return '可以积极推进'
  if (score >= 70) return '值得继续面'
  if (score >= 60) return '可继续观察'
  return '当前风险较高'
})

const trainingPlan = computed(() => {
  const suggestions = report.value?.improvement_suggestions || []
  if (suggestions.length) return suggestions.slice(0, 5)
  return [
    `优先补强 ${weakestDimension.value.label}，把低分回答重新组织一遍`,
    '挑 2 道低分题，补齐案例、数据和取舍说明',
    '按目标岗位技能标签再做一轮定向练习',
  ]
})

function scoreColor(score) {
  if (score >= 85) return '#2d9b57'
  if (score >= 70) return '#2f6fde'
  if (score >= 55) return '#d08a20'
  return '#cf4d36'
}

function dimensionComment(key, score) {
  if (score >= 85) return `${dimLabels[key] || key} 已经具备较强说服力。`
  if (score >= 70) return `${dimLabels[key] || key} 基本稳定，但还可以更锋利。`
  if (score >= 55) return `${dimLabels[key] || key} 达到基本线，但容易在追问中失分。`
  return `${dimLabels[key] || key} 偏弱，建议优先针对性训练。`
}

async function loadReport() {
  loading.value = true
  try {
    const data = await getInterviewDetail(Number(route.params.sessionId))
    const evaluation = data.evaluation || {}
    report.value = {
      ...evaluation,
      resume_summary: data.resume_summary || {},
      jd_summary: data.jd_summary || {},
      interview_type: data.interview_type || evaluation.interview_type || 'tech',
      total_questions: data.total_questions || evaluation.total_questions || 0,
      answered_questions: data.answered_count || evaluation.answered_questions || 0,
      timeout_count: data.timeout_count || 0,
      question_evaluations: evaluation.question_evaluations || [],
      dimension_scores: evaluation.dimension_scores || {},
      strengths: evaluation.strengths || [],
      weaknesses: evaluation.weaknesses || [],
      improvement_suggestions: evaluation.improvement_suggestions || [],
      overall_score: evaluation.overall_score || 0,
      total_duration_seconds: evaluation.total_duration_seconds || 0,
      overall_evaluation: evaluation.overall_evaluation || '',
      hiring_recommendation: evaluation.hiring_recommendation || '',
    }
  } catch (error) {
    ElMessage.error(`加载报告失败: ${error.message || error}`)
  } finally {
    loading.value = false
  }
}

function goRoom() {
  router.push(`/interview/room/${route.params.sessionId}`)
}

function restart() {
  router.push('/interview/setup')
}

function goSetup() {
  router.push('/interview/setup')
}

onMounted(() => {
  loadReport()
})
</script>

<style scoped>
.report-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.report-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  border-radius: 26px;
  background:
    radial-gradient(circle at top right, rgba(214, 93, 47, 0.18), transparent 32%),
    linear-gradient(135deg, #16253c, #243a59 52%, #35556f);
  color: #fff;
}

.eyebrow {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 12px;
  opacity: 0.72;
}

.report-hero h1 {
  margin: 0 0 8px;
  font-size: 30px;
}

.report-hero p {
  margin: 0;
  color: rgba(255, 255, 255, 0.74);
}

.hero-score {
  display: flex;
  align-items: center;
  gap: 18px;
}

.score-ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 130px;
  height: 130px;
  border-radius: 50%;
  border: 8px solid var(--score-color);
  box-shadow: inset 0 0 0 10px rgba(255, 255, 255, 0.08);
}

.score-ring strong {
  font-size: 38px;
}

.score-ring span {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.74);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.summary-card {
  padding: 18px;
  border-radius: 20px;
  background: #fff;
}

.summary-card span {
  display: block;
  color: #8b95a7;
  font-size: 12px;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  color: #1e2b3b;
}

.report-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) 340px;
  gap: 18px;
  align-items: start;
}

.main-column,
.side-column {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.report-card {
  border: none;
  border-radius: 22px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}

.sub {
  font-size: 12px;
  color: #8b95a7;
  font-weight: 400;
}

.decision-strip {
  padding: 18px;
  border-left: 4px solid #2f6fde;
  border-radius: 18px;
  background: #f7f9fd;
}

.decision-label {
  color: #8b95a7;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.decision-strip strong {
  display: block;
  margin-top: 8px;
  color: #1e2b3b;
  font-size: 24px;
}

.decision-strip p {
  margin: 12px 0 0;
  color: #617083;
  line-height: 1.8;
}

.dimension-list {
  display: grid;
  gap: 16px;
}

.dimension-item {
  padding: 16px;
  border-radius: 18px;
  background: #f7f9fc;
}

.dimension-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dimension-track {
  margin: 12px 0 10px;
  height: 10px;
  background: #e8edf5;
  border-radius: 999px;
  overflow: hidden;
}

.dimension-fill {
  height: 100%;
  border-radius: 999px;
}

.dimension-item p {
  margin: 0;
  color: #6b778a;
  line-height: 1.7;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.plain-list {
  margin: 0;
  padding-left: 18px;
  color: #4f5d71;
  line-height: 1.9;
}

.plain-list.warning {
  color: #8a5529;
}

.timeline-list {
  display: grid;
  gap: 14px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 14px;
}

.timeline-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: #1d3655;
  color: #fff;
  font-weight: 700;
}

.timeline-content {
  padding: 16px;
  border-radius: 18px;
  background: #f7f9fc;
}

.timeline-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.timeline-top strong {
  color: #1f2d3d;
}

.timeline-top p {
  margin: 6px 0 0;
  color: #607086;
  line-height: 1.7;
}

.timeline-score {
  font-size: 28px;
  font-weight: 700;
}

.timeline-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}

.timeline-tags span {
  padding: 5px 10px;
  border-radius: 999px;
  background: #eaf0fb;
  color: #3f5d88;
  font-size: 12px;
}

.timeline-answer + .timeline-answer {
  margin-top: 12px;
}

.field-label {
  margin-bottom: 6px;
  color: #8b95a7;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.timeline-answer p {
  margin: 0;
  color: #546477;
  line-height: 1.8;
  white-space: pre-wrap;
}

.timeline-answer p.improvement {
  color: #a75a1e;
}

.training-list {
  display: grid;
  gap: 12px;
}

.training-item {
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 12px;
  padding: 14px;
  border-radius: 18px;
  background: #f7f9fc;
}

.training-item span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: #eef2ff;
  color: #2f57b9;
  font-weight: 700;
}

.training-item p {
  margin: 0;
  color: #4f5d71;
  line-height: 1.7;
}

.job-panel strong {
  display: block;
  color: #1e2b3b;
}

.job-panel p {
  margin: 6px 0 12px;
  color: #7a8699;
}

.job-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.job-skills span {
  padding: 5px 10px;
  border-radius: 999px;
  background: #f3f6fb;
  color: #44556c;
  font-size: 12px;
}

.report-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding-bottom: 8px;
}

@media (max-width: 1100px) {
  .report-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 800px) {
  .report-hero,
  .hero-score {
    flex-direction: column;
    align-items: flex-start;
  }

  .summary-grid,
  .two-col {
    grid-template-columns: 1fr;
  }

  .report-actions {
    flex-direction: column;
  }
}
</style>
