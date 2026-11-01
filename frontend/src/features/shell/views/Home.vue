<template>
  <div class="app-page home-page">
    <PageHeader :title="pageTitle" :subtitle="headerSubtitle" :eyebrow="todayLabel">
      <template #actions>
        <el-button v-if="hasResume" @click="go('/resume-center')"> 简历中心 </el-button>
        <el-button type="primary" @click="go(primaryAction.link)">
          {{ primaryAction.label }}
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="overviewError"
      class="home-alert"
      type="warning"
      :closable="false"
      show-icon
      title="求职概览加载失败"
      description="其他工作台功能仍可使用。请检查网络连接后重新加载概览数据。"
    >
      <template #default>
        <el-button size="small" type="primary" plain @click="loadDashboard">重新加载</el-button>
      </template>
    </el-alert>

    <section class="ui-stat-strip" aria-label="求职关键指标">
      <div class="ui-stat">
        <span class="ui-stat-label">简历完整度</span>
        <div class="ui-stat-row">
          <span class="ui-stat-value">
            {{ resumeScoreValue ?? '—' }}<small v-if="resumeScoreValue !== null">分</small>
          </span>
          <span class="ui-delta" :class="resumeScoreValue > 0 ? 'is-up' : ''">
            {{ resumeScoreValue > 0 ? '已体检' : hasResume ? '待完善' : '待上传' }}
          </span>
        </div>
        <div class="ui-stat-bar">
          <span :style="{ width: `${resumeScoreValue ?? 0}%` }" />
        </div>
      </div>

      <div class="ui-stat">
        <span class="ui-stat-label">进行中的投递</span>
        <div class="ui-stat-row">
          <span class="ui-stat-value"> {{ activeApplications }}<small>个</small> </span>
          <span class="ui-delta" :class="weeklyNew > 0 ? 'is-up' : ''">
            {{ weeklyNew > 0 ? `本周 +${weeklyNew}` : '本周 0' }}
          </span>
        </div>
        <svg class="home-spark" viewBox="0 0 74 22" preserveAspectRatio="none" aria-hidden="true">
          <path class="home-spark-base" d="M0 21H74" />
          <polyline class="home-spark-line" :points="sparkPoints" />
        </svg>
      </div>

      <div class="ui-stat">
        <span class="ui-stat-label">最高匹配</span>
        <div class="ui-stat-row">
          <span class="ui-stat-value">
            {{ topMatch ?? '—' }}<small v-if="topMatch !== null">分</small>
          </span>
          <span class="ui-delta">{{
            recommendations.length ? `共 ${recommendations.length} 个推荐` : '暂无样本'
          }}</span>
        </div>
        <div class="ui-stat-bar">
          <span :style="{ width: `${topMatch ?? 0}%` }" />
        </div>
      </div>

      <div class="ui-stat">
        <span class="ui-stat-label">面试转化</span>
        <div class="ui-stat-row">
          <span class="ui-stat-value">
            {{ interviewRate ?? '—' }}<small v-if="interviewRate !== null">%</small>
          </span>
          <span class="ui-delta" :class="interviewRate !== null ? 'is-up' : ''">
            {{ interviewCount > 0 ? `${interviewCount} 个面试` : '还没有面试' }}
          </span>
        </div>
        <div class="ui-stat-bar">
          <span :style="{ width: `${interviewRate ?? 0}%` }" />
        </div>
      </div>
    </section>

    <div class="home-grid">
      <div class="home-main">
        <section class="ui-card home-card home-card--tasks">
          <div class="ui-card-head">
            <div>
              <h2>今日推进</h2>
              <p>
                {{ taskCount ? `有 ${taskCount} 个动作可以推进` : '按优先级排好，做完就收工。' }}
              </p>
            </div>
            <button type="button" class="ui-link" @click="go('/jobs/pipeline/kanban')">
              投递看板 <el-icon><ArrowRight /></el-icon>
            </button>
          </div>

          <div v-if="tasksLoading" class="home-skeleton-list">
            <div class="app-skeleton home-skeleton-row" style="width: 72%" />
            <div class="app-skeleton home-skeleton-row" style="width: 58%" />
            <div class="app-skeleton home-skeleton-row" style="width: 65%" />
          </div>

          <div v-else-if="tasksError" class="app-inline-error home-alert">
            <span>今日任务加载失败</span>
            <el-button size="small" text type="primary" @click="loadDashboard">重新加载</el-button>
          </div>

          <EmptyState
            v-else-if="!taskItems.length"
            compact
            :icon="CircleCheck"
            title="今天没有待办"
            description="可以去推荐岗位挑一个，或跟进已有投递。"
          >
            <template #action>
              <el-button size="small" @click="go('/jobs/recommend')">查看推荐岗位</el-button>
            </template>
          </EmptyState>

          <div v-else class="home-task-list">
            <button
              v-for="task in taskItems"
              :key="task.title"
              type="button"
              class="home-task-row"
              @click="go(task.link || '/home')"
            >
              <span
                class="home-task-dot"
                :class="`dot-${task.priority || 'low'}`"
                aria-hidden="true"
              />
              <span class="home-task-copy">
                <strong>{{ task.title }}</strong>
                <span>{{ task.subtitle }}</span>
              </span>
              <span class="home-task-meta">
                <span class="home-task-tag" :class="`is-${task.priority || 'low'}`">
                  {{ priorityLabel(task.priority) }}
                </span>
                <el-icon><ArrowRight /></el-icon>
              </span>
            </button>
          </div>

          <div v-if="!tasksLoading" class="home-task-foot">
            <span>
              今天 <strong>{{ todayCount }}</strong> 个投递 · 本周新增
              <strong>{{ weeklyNew }}</strong> 个
            </span>
            <button type="button" class="ui-link" @click="go('/jobs/recommend')">
              去挑一个岗位 <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
        </section>

        <section class="ui-card home-card home-card--board">
          <div class="ui-card-head">
            <div>
              <h2>投递管道</h2>
              <p>{{ pipelineTotal }} 个进行中{{ weeklyNew ? ` · 本周新增 ${weeklyNew}` : '' }}</p>
            </div>
            <button type="button" class="ui-link" @click="go('/jobs/pipeline/kanban')">
              看板视图 <el-icon><ArrowRight /></el-icon>
            </button>
          </div>

          <div v-if="pipelineLoading" class="home-board home-board--loading">
            <div v-for="i in 4" :key="i" class="home-board-col">
              <div class="app-skeleton home-skeleton-row" style="width: 50%" />
              <div class="app-skeleton home-skeleton-card" />
              <div class="app-skeleton home-skeleton-card" style="width: 80%" />
            </div>
          </div>

          <div v-else-if="pipelineError" class="app-inline-error home-alert">
            <span>投递管道加载失败</span>
            <el-button size="small" text type="primary" @click="loadDashboard">重新加载</el-button>
          </div>

          <div v-else class="home-board">
            <div v-for="col in boardColumns" :key="col.key" class="home-board-col">
              <div class="home-board-head">
                <span class="home-board-name">
                  <i class="home-board-dot" :class="`is-${col.key}`" />
                  {{ col.label }}
                </span>
                <span class="home-board-count">{{ col.count }}</span>
              </div>
              <div class="home-board-list">
                <button
                  v-for="card in col.cards.slice(0, 2)"
                  :key="card.id"
                  type="button"
                  class="home-board-card"
                  @click="go('/jobs/pipeline/kanban')"
                >
                  <span class="home-board-card-top">
                    <strong>{{ card.title }}</strong>
                    <em v-if="card.match_score" :class="scoreToneClass(card.match_score)">
                      {{ card.match_score }}
                    </em>
                  </span>
                  <span class="home-board-company">{{ card.company || '未填写公司' }}</span>
                  <span v-if="card.salary_range" class="home-board-salary">{{
                    card.salary_range
                  }}</span>
                </button>

                <button
                  v-if="!col.cards.length"
                  type="button"
                  class="home-board-empty"
                  @click="go(col.key === 'todo' ? '/jobs/recommend' : '/jobs/pipeline/kanban')"
                >
                  {{
                    col.count
                      ? '打开看板查看'
                      : col.key === 'todo'
                        ? '去推荐岗位挑一个'
                        : '还没有记录'
                  }}
                </button>

                <button
                  v-else-if="col.count > 2"
                  type="button"
                  class="home-board-more"
                  @click="go('/jobs/pipeline/kanban')"
                >
                  还有 {{ col.count - 2 }} 个 <el-icon><ArrowRight /></el-icon>
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>

      <aside class="home-rail">
        <section class="ui-card home-card home-card--reco">
          <div class="ui-card-head">
            <div>
              <h2>推荐岗位</h2>
              <p>{{ defaultResume ? `基于「${resumeDisplayName}」` : '上传简历后自动匹配' }}</p>
            </div>
            <button type="button" class="ui-link" @click="go('/jobs/recommend')">
              查看全部 <el-icon><ArrowRight /></el-icon>
            </button>
          </div>

          <div v-if="recoLoading" class="home-skeleton-list">
            <div class="app-skeleton home-skeleton-row" style="width: 78%" />
            <div class="app-skeleton home-skeleton-row" style="width: 62%" />
            <div class="app-skeleton home-skeleton-row" style="width: 71%" />
          </div>

          <div v-else-if="recoError" class="app-inline-error home-alert">
            <span>推荐岗位加载失败</span>
            <el-button size="small" text type="primary" @click="loadDashboard">重新加载</el-button>
          </div>

          <EmptyState
            v-else-if="!defaultResume"
            compact
            :icon="Document"
            title="先上传一份简历"
            description="上传后会自动匹配适合你的岗位。"
          >
            <template #action>
              <el-button size="small" @click="go('/resume-center')">上传简历</el-button>
            </template>
          </EmptyState>

          <EmptyState
            v-else-if="!recommendations.length"
            compact
            :icon="DataAnalysis"
            title="暂时没有匹配岗位"
            description="完善简历或调整目标岗位后再看。"
          >
            <template #action>
              <el-button size="small" @click="go('/jobs/recommend')">去岗位推荐</el-button>
            </template>
          </EmptyState>

          <div v-else class="home-reco-list">
            <button
              v-for="job in recommendations.slice(0, 3)"
              :key="job.jd_id"
              type="button"
              class="home-reco-row"
              @click="go('/jobs/recommend')"
            >
              <span class="home-reco-icon">{{ companyInitial(job.company) }}</span>
              <span class="home-reco-copy">
                <strong>{{ job.job_title }}</strong>
                <span>
                  {{ job.company }}
                  <template v-if="job.salary_range"> · {{ job.salary_range }}</template>
                </span>
              </span>
              <ScoreRing :score="job.match_score" :size="34" />
            </button>
          </div>
        </section>

        <section class="ui-card home-card home-card--week">
          <div class="ui-card-head">
            <div>
              <h2>本周投递节奏</h2>
              <p>保持每天 1-2 个高质量投递。</p>
            </div>
          </div>
          <div class="ui-card-body home-week">
            <div class="home-week-bars" aria-hidden="true">
              <div
                v-for="(bar, i) in weekBars"
                :key="i"
                class="home-week-col"
                :class="{ 'is-today': bar.today }"
              >
                <i :style="{ height: `${bar.height}%` }" />
                <span>{{ bar.label }}</span>
              </div>
            </div>
            <div class="home-week-foot">
              <span>本周 {{ weeklyTotal }} 个投递</span>
              <strong :class="{ 'is-empty': !weeklyTotal }">
                {{ weeklyTotal ? `新增 ${weeklyNew}` : '还没有投递' }}
              </strong>
            </div>
          </div>
        </section>

        <section class="ui-card home-card home-card--check">
          <div class="ui-card-head">
            <div>
              <h2>下一步检查</h2>
              <p>把这三项补齐，推荐会更准。</p>
            </div>
          </div>
          <div class="ui-card-body home-check">
            <button
              v-for="item in checklist"
              :key="item.key"
              type="button"
              class="home-check-row"
              :class="{ 'is-done': item.done }"
              @click="go(item.link)"
            >
              <span class="home-check-mark">{{ item.done ? '✓' : '!' }}</span>
              <span class="home-check-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.hint }}</span>
              </span>
              <el-icon v-if="!item.done"><ArrowRight /></el-icon>
            </button>
            <p v-if="allChecksDone" class="home-check-done">资料已就绪，继续保持节奏。</p>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, CircleCheck, DataAnalysis, Document } from '@element-plus/icons-vue'

import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import ScoreRing from '@/components/ui/ScoreRing.vue'
import { useAuthStore } from '@/stores/auth'
import { useSelectionStore } from '@/stores/selection'
import { getDashboardOverview, getTodayTasks } from '@/api/dashboard'
import { getJobRecommendations } from '@/api/jobs'
import { getKanban } from '@/api/targets'
import { getResumeList, getResumeQuickScore } from '@/api/resume'
import { monthDay } from '@/utils/format/date'
import { scoreToneClass } from '@/utils/scoreTone'

const router = useRouter()
const authStore = useAuthStore()
const selection = useSelectionStore()
const go = (path) => router.push(path)

/** @type {import('vue').Ref<import('@/api/dashboard').DashboardOverview>} */
const overview = ref({})
const overviewLoaded = ref(false)
const overviewError = ref(false)
const tasks = ref({ tasks: [], high_priority: 0 })
const tasksLoading = ref(true)
const tasksError = ref(false)
/** @type {import('vue').Ref<Record<string, any>>} */
const pipeline = ref({})
const pipelineLoading = ref(true)
const pipelineError = ref(false)
const resumeList = ref([])
const defaultResume = ref(null)
const resumeScoreValue = ref(null)
const recommendations = ref([])
const recoLoading = ref(true)
const recoError = ref(false)

const username = computed(() => authStore.user?.nickname || authStore.user?.username || '求职者')

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const weekdays = ['日', '一', '二', '三', '四', '五', '六']
const todayLabel = computed(() => {
  const now = new Date()
  return `${monthDay(now.toISOString())} · 星期${weekdays[now.getDay()]}`
})

const pageTitle = computed(() => `${greeting.value}，${username.value}`)
const summary = computed(() => overview.value.summary || overview.value)
const funnel = computed(() => overview.value.funnel || {})
const stageCounts = computed(() => overview.value.stage_counts || {})
const taskItems = computed(() => tasks.value.tasks || [])
const taskCount = computed(() => tasks.value.high_priority || taskItems.value.length)
const hasResume = computed(
  () => resumeList.value.length > 0 || (summary.value.total_resumes || 0) > 0
)
const activeApplications = computed(() => summary.value.active_applications || 0)
const totalApplications = computed(() => summary.value.total_applications || 0)
const weeklyNew = computed(() => overview.value.weekly_new || 0)
const interviewCount = computed(() => stageCounts.value.interview || 0)
const topMatch = computed(() => {
  const scores = recommendations.value
    .map((job) => Number(job.match_score))
    .filter((value) => Number.isFinite(value))
  return scores.length ? Math.max(...scores) : null
})

const interviewRate = computed(() => {
  if (!totalApplications.value) return null
  const hit =
    interviewCount.value + (stageCounts.value.offer || 0) + (stageCounts.value.accepted || 0)
  return Math.round((hit / totalApplications.value) * 100)
})

const primaryAction = computed(() => {
  if (!hasResume.value) return { label: '上传简历', link: '/resume-center' }
  if (!totalApplications.value) return { label: '去岗位推荐', link: '/jobs/recommend' }
  return { label: '打开投递看板', link: '/jobs/pipeline/kanban' }
})

const headerSubtitle = computed(() => {
  if (overviewError.value) return '求职进度加载失败，其他功能仍可使用。'
  if (!overviewLoaded.value) return '正在读取你的求职进度…'
  if (taskCount.value) return `今天有 ${taskCount.value} 个动作可以推进，先处理高优先级的。`
  if (!hasResume.value) return '先上传一份简历，后面的诊断和匹配都会用到它。'
  return '今天没有待办，可以去看看新的匹配岗位。'
})

const pipelineStages = computed(() => pipeline.value || {})
const boardColumns = computed(() =>
  [
    { key: 'todo', label: '待投递' },
    { key: 'applied', label: '已投递' },
    { key: 'interview', label: '面试' },
    { key: 'offer', label: 'Offer' },
  ].map((col) => ({
    ...col,
    count: Math.max(funnel.value[col.key] || 0, (pipelineStages.value[col.key] || []).length),
    cards: pipelineStages.value[col.key] || [],
  }))
)
const pipelineTotal = computed(() => boardColumns.value.reduce((sum, col) => sum + col.count, 0))

const trend = computed(() => (overview.value.trend || []).slice(-7))
const trendMax = computed(() => Math.max(1, ...trend.value.map((item) => item.count || 0)))
const sparkPoints = computed(() => {
  if (!trend.value.length) return '0,21 74,21'
  return trend.value
    .map((item, index) => {
      const x = trend.value.length === 1 ? 37 : (index / (trend.value.length - 1)) * 74
      const y = 21 - ((item.count || 0) / trendMax.value) * 18
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})
const weekBars = computed(() =>
  trend.value.map((item, index) => {
    const date = new Date(item.date)
    const label = Number.isNaN(date.getTime()) ? '·' : weekdays[date.getDay()]
    return {
      label,
      count: item.count || 0,
      height: Math.round(((item.count || 0) / trendMax.value) * 100),
      today: index === trend.value.length - 1,
    }
  })
)
const weeklyTotal = computed(() => trend.value.reduce((sum, item) => sum + (item.count || 0), 0))
const todayCount = computed(() => {
  const last = weekBars.value[weekBars.value.length - 1]
  return last?.count || 0
})

const checklist = computed(() => [
  {
    key: 'resume',
    label: '上传简历',
    done: hasResume.value,
    hint: hasResume.value ? '已完成 · 已选默认简历' : '还没有上传',
    link: '/resume-center',
  },
  {
    key: 'target',
    label: '设定目标岗位',
    done: (summary.value.bookmarked_jobs || 0) > 0 || totalApplications.value > 0,
    hint:
      totalApplications.value > 0
        ? '已把目标岗位加入投递'
        : (summary.value.bookmarked_jobs || 0) > 0
          ? `已收藏 ${summary.value.bookmarked_jobs} 个岗位`
          : '去推荐里挑一个',
    link: '/jobs/recommend',
  },
  {
    key: 'apply',
    label: '开始投递',
    done: totalApplications.value > 0,
    hint:
      totalApplications.value > 0 ? `已有 ${totalApplications.value} 个投递` : '把目标岗位加入看板',
    link: '/jobs/pipeline/kanban',
  },
])
const allChecksDone = computed(() => checklist.value.every((item) => item.done))

const resumeDisplayName = computed(() => {
  const raw = defaultResume.value?.name || defaultResume.value?.file_name || ''
  const base = raw.replace(/\.[^.]+$/, '')
  if (base && !/^[0-9a-f-]{16,}$/i.test(base)) return base
  if (defaultResume.value?.parsed?.name) return `${defaultResume.value.parsed.name}的简历`
  return '我的简历'
})

function priorityLabel(priority) {
  if (priority === 'high') return '优先'
  if (priority === 'medium') return '今天'
  return '稍后'
}

function companyInitial(company) {
  return company ? String(company).slice(0, 1) : '岗'
}

function pickDefaultResume(items) {
  if (!items.length) return null
  const stored = selection.defaultResumeId()
  return (
    items.find((item) => item.id === stored) ||
    [...items].sort(
      (a, b) => new Date(b.create_time || 0).getTime() - new Date(a.create_time || 0).getTime()
    )[0]
  )
}

async function loadDashboard() {
  overviewError.value = false
  tasksError.value = false
  pipelineError.value = false
  recoError.value = false
  tasksLoading.value = true
  pipelineLoading.value = true
  recoLoading.value = true
  overviewLoaded.value = false

  const [ov, tk, pipe, resumeData] = await Promise.allSettled([
    getDashboardOverview(),
    getTodayTasks(),
    getKanban(),
    getResumeList({ page: 1, page_size: 20 }),
  ])

  if (ov.status === 'fulfilled') {
    overview.value = ov.value
    overviewLoaded.value = true
  } else {
    overviewError.value = true
  }
  if (tk.status === 'fulfilled') {
    tasks.value = tk.value
  } else {
    tasksError.value = true
  }
  if (pipe.status === 'fulfilled') {
    pipeline.value = pipe.value?.stages || pipe.value || {}
  } else {
    pipelineError.value = true
  }
  tasksLoading.value = false
  pipelineLoading.value = false

  if (resumeData.status === 'fulfilled') {
    resumeList.value = resumeData.value?.items || []
    defaultResume.value = pickDefaultResume(resumeList.value)
    if (defaultResume.value) selection.rememberResume(defaultResume.value.id)
  } else {
    resumeList.value = []
    defaultResume.value = null
  }

  if (!defaultResume.value) {
    recommendations.value = []
    resumeScoreValue.value = null
    recoLoading.value = false
    return
  }

  const [score, rec] = await Promise.allSettled([
    getResumeQuickScore(defaultResume.value.id, { notifyError: false }),
    getJobRecommendations({ resume_id: defaultResume.value.id, limit: 3 }),
  ])
  if (score.status === 'fulfilled') {
    const value = score.value?.completeness_score
    resumeScoreValue.value = Number.isFinite(Number(value)) ? Number(value) : null
  } else {
    resumeScoreValue.value = null
  }
  if (rec.status === 'fulfilled') {
    recommendations.value = rec.value?.recommendations || []
  } else {
    recoError.value = true
  }
  recoLoading.value = false
}

onMounted(loadDashboard)
</script>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.home-page :deep(.page-head) {
  margin-bottom: 0;
}

.home-alert {
  margin: 0;
}

.home-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-areas:
    'tasks week'
    'board board'
    'reco check';
  gap: 14px;
  align-items: stretch;
}

.home-main,
.home-rail {
  display: contents;
}

.home-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.home-card--tasks {
  grid-area: tasks;
}

.home-card--board {
  grid-area: board;
}

.home-card--reco {
  grid-area: reco;
}

.home-card--week {
  grid-area: week;
}

.home-card--check {
  grid-area: check;
}

/* ===== Stats ===== */
.home-spark {
  width: 74px;
  height: 22px;
  overflow: visible;
}

.home-spark-base {
  fill: none;
  stroke: var(--app-line);
  stroke-width: 1;
  stroke-dasharray: 2 3;
}

.home-spark-line {
  fill: none;
  stroke: var(--app-primary);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* ===== Tasks ===== */
.home-skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
}

.home-skeleton-row {
  height: 13px;
}

.home-skeleton-card {
  height: 76px;
  margin-top: 10px;
}

.home-task-list {
  padding: 2px 8px 8px;
}

.home-task-foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px 12px;
  margin-top: auto;
  padding: 10px 16px;
  border-top: 1px solid var(--app-line);
  color: var(--app-muted);
  font-size: 11px;
}

.home-task-foot strong {
  color: var(--app-text);
  font-family: var(--app-font-mono);
  font-weight: 600;
}

.home-task-row {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 12px;
  padding: 13px 10px;
  border: 0;
  border-bottom: 1px solid var(--app-line);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.home-task-row:last-child {
  border-bottom: 0;
}

.home-task-row:hover {
  background: var(--app-surface-muted);
}

.home-task-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.dot-high {
  background: color-mix(in srgb, var(--app-danger), black 10%);
}

.dot-medium {
  background: color-mix(in srgb, var(--app-warning), black 30%);
}

.dot-low {
  background: color-mix(in srgb, var(--app-success), black 25%);
}

.home-task-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.home-task-copy strong {
  overflow: hidden;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-task-copy span {
  overflow: hidden;
  color: var(--app-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-task-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  color: var(--app-muted);
}

.home-task-tag {
  display: inline-flex;
  align-items: center;
  height: 21px;
  padding: 0 7px;
  border-radius: 5px;
  background: var(--app-surface-muted);
  color: var(--app-muted);
  font-size: 10px;
  font-weight: 600;
}

.home-task-tag.is-high {
  background: color-mix(in srgb, var(--app-danger), white 92%);
  color: color-mix(in srgb, var(--app-danger), black 25%);
}

.home-task-tag.is-medium {
  background: color-mix(in srgb, var(--app-warning), white 92%);
  color: color-mix(in srgb, var(--app-warning), black 30%);
}

/* ===== Pipeline ===== */
.home-board {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.home-board--loading {
  padding: 14px;
  gap: 12px;
}

.home-board-col {
  min-width: 0;
  padding: 14px 12px 16px;
  border-right: 1px solid var(--app-line);
}

.home-board-col:last-child {
  border-right: 0;
}

.home-board--loading .home-board-col {
  border-right: 0;
  padding: 0;
}

.home-board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 2px 10px;
}

.home-board-name {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--app-text);
  font-size: 12px;
  font-weight: 600;
}

.home-board-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.home-board-dot.is-todo {
  background: var(--app-muted);
}

.home-board-dot.is-applied {
  background: var(--app-primary);
}

.home-board-dot.is-interview {
  background: var(--app-warning);
}

.home-board-dot.is-offer {
  background: var(--app-success);
}

.home-board-count {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--app-surface-muted);
  color: var(--app-muted);
  font-size: 10px;
  font-weight: 600;
}

.home-board-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.home-board-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-surface-strong);
  text-align: left;
  cursor: pointer;
}

.home-board-card:hover {
  border-color: var(--app-line-strong);
}

.home-board-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.home-board-card-top strong {
  overflow: hidden;
  color: var(--app-text);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-board-card-top em {
  flex-shrink: 0;
  font-family: var(--app-font-mono);
  font-size: 11px;
  font-style: normal;
  font-weight: 600;
}

.home-board-company,
.home-board-salary {
  overflow: hidden;
  color: var(--app-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-board-empty {
  min-height: 78px;
  padding: 12px 8px;
  border: 1px dashed var(--app-line-strong);
  border-radius: var(--app-radius-sm);
  background: transparent;
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.5;
  text-align: center;
  cursor: pointer;
}

.home-board-empty:hover {
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.home-board-more {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  align-self: flex-start;
  padding: 2px 0;
  border: 0;
  background: none;
  color: var(--app-muted);
  font-size: 11px;
  cursor: pointer;
}

.home-board-more:hover {
  color: var(--app-primary);
}

/* ===== Recommendations ===== */
.home-reco-list {
  padding: 4px 8px 8px;
}

.home-reco-row {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 10px;
  padding: 10px;
  border: 0;
  border-bottom: 1px solid var(--app-line);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.home-reco-row:last-child {
  border-bottom: 0;
}

.home-reco-row:hover {
  background: var(--app-surface-muted);
}

.home-reco-icon {
  display: grid;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  place-items: center;
  border-radius: var(--app-radius-sm);
  background: var(--app-primary-light);
  color: var(--app-primary-dark);
  font-size: 12px;
  font-weight: 700;
}

.home-reco-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.home-reco-copy strong {
  overflow: hidden;
  color: var(--app-text);
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-reco-copy span {
  overflow: hidden;
  color: var(--app-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===== Weekly rhythm ===== */
.home-week {
  padding-top: 14px;
}

.home-week-bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 74px;
}

.home-week-col {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  gap: 5px;
}

.home-week-col i {
  display: block;
  width: 100%;
  max-width: 18px;
  min-height: 0;
  border-radius: 3px 3px 0 0;
  background: var(--app-primary);
  opacity: 0.22;
}

.home-week-col.is-today i {
  opacity: 1;
}

.home-week-col span {
  color: var(--app-muted);
  font-size: 10px;
}

.home-week-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--app-line);
}

.home-week-foot span {
  color: var(--app-muted);
  font-size: 11px;
}

.home-week-foot strong {
  color: color-mix(in srgb, var(--app-success), black 35%);
  font-size: 12px;
  font-weight: 600;
}

.home-week-foot strong.is-empty {
  color: var(--app-muted);
}

/* ===== Checklist ===== */
.home-check {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.home-check-row {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.home-check-row:hover .home-check-copy strong {
  color: var(--app-primary);
}

.home-check-mark {
  display: grid;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--app-warning), white 92%);
  color: color-mix(in srgb, var(--app-warning), black 30%);
  font-size: 10px;
  font-weight: 700;
}

.home-check-row.is-done .home-check-mark {
  background: color-mix(in srgb, var(--app-success), white 92%);
  color: color-mix(in srgb, var(--app-success), black 35%);
}

.home-check-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.home-check-copy strong {
  color: var(--app-text);
  font-size: 12px;
  font-weight: 600;
}

.home-check-copy span {
  overflow: hidden;
  color: var(--app-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-check-row > .el-icon {
  color: var(--app-muted);
  flex-shrink: 0;
}

.home-check-done {
  margin: 2px 0 0;
  color: color-mix(in srgb, var(--app-success), black 35%);
  font-size: 11px;
}

/* ===== Responsive ===== */
@media (max-width: 1180px) {
  .home-grid {
    grid-template-columns: 1fr;
    grid-template-areas:
      'tasks'
      'week'
      'board'
      'reco'
      'check';
  }

  .home-board {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .home-board-col:nth-child(2) {
    border-right: 0;
  }

  .home-board-col:nth-child(1),
  .home-board-col:nth-child(2) {
    border-bottom: 1px solid var(--app-line);
  }
}

@media (max-width: 900px) {
  .home-board {
    grid-template-columns: 1fr;
  }

  .home-board-col {
    border-right: 0;
    border-bottom: 1px solid var(--app-line);
  }

  .home-board-col:last-child {
    border-bottom: 0;
  }
}

@media (max-width: 768px) {
  .home-task-meta {
    gap: 4px;
  }

  .home-task-tag {
    display: none;
  }
}
</style>
