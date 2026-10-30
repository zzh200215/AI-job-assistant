<template>
  <div class="app-page home-page">
    <section class="home-hero">
      <div class="home-hero-copy">
        <p class="home-eyebrow">{{ todayLabel }}</p>
        <h1 class="home-title">{{ greeting }}，{{ username }}</h1>
        <p class="home-sub">{{ heroSubtitle }}</p>
      </div>

      <div class="home-next" :class="{ 'is-muted': nextAction.tone === 'muted' }">
        <span class="home-next-label">{{ nextAction.label }}</span>
        <strong class="home-next-title">{{ nextAction.title }}</strong>
        <p class="home-next-desc">{{ nextAction.description }}</p>
        <el-button
          v-if="nextAction.action"
          type="primary"
          class="home-next-btn"
          @click="handleNextAction"
        >
          {{ nextAction.action }}
          <el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
      </div>
    </section>

    <section class="home-section">
      <div class="app-section-head">
        <div>
          <h2>核心入口</h2>
          <p>从简历开始，沿着分析、匹配、投递一路推进。</p>
        </div>
      </div>

      <div class="home-entrances">
        <button class="entrance-card" type="button" @click="go('/resume-center')">
          <span class="entrance-icon"
            ><el-icon><Document /></el-icon
          ></span>
          <span class="entrance-body">
            <strong>简历中心</strong>
            <span>上传、诊断与优化简历</span>
            <em>{{ overviewLoaded ? `${summary.total_resumes || 0} 份简历` : '读取中…' }}</em>
          </span>
          <el-icon class="entrance-arrow"><ArrowRight /></el-icon>
        </button>

        <button class="entrance-card" type="button" @click="go('/smart-analysis')">
          <span class="entrance-icon"
            ><el-icon><MagicStick /></el-icon
          ></span>
          <span class="entrance-body">
            <strong>求职分析</strong>
            <span>看清简历与目标岗位的差距</span>
            <em>{{ hasResume ? '基于你的简历分析' : '先上传一份简历' }}</em>
          </span>
          <el-icon class="entrance-arrow"><ArrowRight /></el-icon>
        </button>

        <button class="entrance-card" type="button" @click="go('/jobs/recommend')">
          <span class="entrance-icon"
            ><el-icon><DataAnalysis /></el-icon
          ></span>
          <span class="entrance-body">
            <strong>岗位推荐</strong>
            <span>按你的经历匹配机会</span>
            <em>{{ overviewLoaded ? `${summary.bookmarked_jobs || 0} 个收藏岗位` : '读取中…' }}</em>
          </span>
          <el-icon class="entrance-arrow"><ArrowRight /></el-icon>
        </button>
      </div>
    </section>

    <div class="home-columns">
      <AppPanel class="home-panel">
        <template #icon><Bell /></template>
        <template #title>今日任务</template>
        <template #actions>
          <span v-if="openTaskCount" class="home-panel-note">{{ openTaskCount }} 项待办</span>
        </template>

        <div v-if="tasksLoading && !taskItems.length" class="app-loading-block">
          <div class="app-skeleton app-loading-row" style="width: 70%" />
          <div class="app-skeleton app-loading-row" style="width: 55%" />
          <div class="app-skeleton app-loading-row" style="width: 62%" />
        </div>

        <div v-else-if="tasksError" class="app-inline-error">
          <span>今日任务加载失败</span>
          <el-button size="small" text type="primary" @click="loadDashboard">重新加载</el-button>
        </div>

        <EmptyState
          v-else-if="!taskItems.length"
          compact
          :icon="CircleCheck"
          title="今天没有待办"
          description="可以从推荐岗位里挑一个，开始今天的推进。"
        >
          <template #action>
            <el-button size="small" @click="go('/jobs/recommend')">查看岗位推荐</el-button>
          </template>
        </EmptyState>

        <div v-else class="task-list">
          <button
            v-for="task in taskItems"
            :key="task.title"
            type="button"
            class="task-row"
            @click="go(task.link || '/home')"
          >
            <span class="task-dot" :class="`dot-${task.priority || 'low'}`" aria-hidden="true" />
            <span class="task-copy">
              <strong>{{ task.title }}</strong>
              <span v-if="task.subtitle">{{ task.subtitle }}</span>
            </span>
            <el-icon class="task-arrow"><ArrowRight /></el-icon>
          </button>
        </div>
      </AppPanel>

      <AppPanel class="home-panel">
        <template #icon><TrendCharts /></template>
        <template #title>求职漏斗</template>
        <template #actions>
          <button type="button" class="app-link" @click="go('/jobs/pipeline/kanban')">
            投递看板
            <el-icon><ArrowRight /></el-icon>
          </button>
        </template>

        <div v-if="!overviewLoaded && !overviewError" class="app-loading-block">
          <div class="app-skeleton" style="height: 10px" />
          <div class="app-skeleton app-loading-row" style="width: 40%; margin-top: 12px" />
        </div>

        <div v-else-if="overviewError" class="app-inline-error">
          <span>求职进度加载失败</span>
          <el-button size="small" text type="primary" @click="loadDashboard">重新加载</el-button>
        </div>

        <EmptyState
          v-else-if="!funnelTotal"
          compact
          :icon="DataAnalysis"
          title="还没有投递记录"
          description="先挑一个岗位加入投递看板，漏斗会从第一条记录开始。"
        >
          <template #action>
            <el-button size="small" @click="go('/jobs/recommend')">去挑岗位</el-button>
          </template>
        </EmptyState>

        <div v-else class="funnel">
          <div class="funnel-bar" aria-hidden="true">
            <span
              v-for="stage in funnelStages"
              :key="stage.key"
              class="funnel-seg"
              :class="`funnel-seg--${stage.key}`"
              :style="{ width: funnelWidth(stage.count) }"
            />
          </div>
          <div class="funnel-legend">
            <div v-for="stage in funnelStages" :key="stage.key" class="funnel-item">
              <strong>{{ stage.count }}</strong>
              <span>{{ stage.label }}</span>
            </div>
          </div>
          <p class="funnel-note">
            共 {{ funnelTotal }} 个投递 ·
            {{ interviewRate === '--' ? '还没有面试记录' : `面试转化 ${interviewRate}` }}
          </p>
        </div>
      </AppPanel>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Bell,
  CircleCheck,
  DataAnalysis,
  Document,
  MagicStick,
  TrendCharts,
} from '@element-plus/icons-vue'

import AppPanel from '@/components/ui/AppPanel.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useAuthStore } from '@/stores/auth'
import { getDashboardOverview, getTodayTasks } from '@/api/dashboard'
import { monthDay } from '@/utils/format/date'

const router = useRouter()
const authStore = useAuthStore()
const go = (path) => router.push(path)

const username = computed(() => authStore.user?.nickname || authStore.user?.username || '求职者')

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const todayLabel = computed(() => monthDay(new Date().toISOString()))

/** @type {import('vue').Ref<import('@/api/dashboard').DashboardOverview>} */
const overview = ref({})
const overviewLoaded = ref(false)
const overviewError = ref(false)
const tasks = ref({ tasks: [], high_priority: 0 })
const tasksLoading = ref(true)
const tasksError = ref(false)

const summary = computed(() => overview.value.summary || overview.value)
const taskItems = computed(() => tasks.value.tasks || [])
const openTaskCount = computed(() => tasks.value.high_priority || taskItems.value.length)
const hasResume = computed(() => (summary.value.total_resumes || 0) > 0)

const interviewRate = computed(() => {
  const total = summary.value.total_applications || 0
  const interview = overview.value.stage_counts?.interview || 0
  const offer = overview.value.stage_counts?.offer || 0
  const accepted = overview.value.stage_counts?.accepted || 0
  return total > 0 ? `${Math.round(((interview + offer + accepted) / total) * 100)}%` : '--'
})

const funnelStages = computed(() => {
  const f = overview.value.funnel || {}
  return [
    { key: 'todo', label: '待投递', count: f.todo || 0 },
    { key: 'applied', label: '已投递', count: f.applied || 0 },
    { key: 'written_test', label: '笔试', count: f.written_test || 0 },
    { key: 'interview', label: '面试', count: f.interview || 0 },
    { key: 'offer', label: 'Offer', count: f.offer || 0 },
  ]
})

const funnelTotal = computed(() => funnelStages.value.reduce((sum, stage) => sum + stage.count, 0))

function funnelWidth(count) {
  if (!funnelTotal.value) return '0%'
  return `${Math.max(count ? 4 : 0, (count / funnelTotal.value) * 100)}%`
}

const heroSubtitle = computed(() => {
  if (!overviewLoaded.value) return '正在读取你的求职进度…'
  if (!hasResume.value) return '先上传一份简历，后面的诊断和匹配都会用到它。'
  if (!(summary.value.bookmarked_jobs || 0)) return '简历已就位，接下来挑一个目标岗位。'
  return `本周新增 ${overview.value.weekly_new || 0} 个投递 · ${summary.value.active_applications || 0} 个进行中 · ${overview.value.stage_counts?.interview || 0} 个面试`
})

const nextAction = computed(() => {
  if (overviewError.value) {
    return {
      label: '建议下一步',
      title: '进度暂时读不到',
      description: '其他功能仍可使用，稍后重新加载即可。',
      action: '重新加载',
      link: '/home',
      tone: 'muted',
    }
  }
  if (!overviewLoaded.value) {
    return {
      label: '建议下一步',
      title: '正在读取你的求职进度',
      description: '稍等片刻，我们会按当前进度给出下一步。',
      action: '',
      link: '/home',
      tone: 'muted',
    }
  }

  const resumes = summary.value.total_resumes || 0
  const saved = summary.value.bookmarked_jobs || 0
  const applications = summary.value.total_applications || 0
  const active = summary.value.active_applications || 0
  const interviews = overview.value.stage_counts?.interview || 0
  const offers = summary.value.pending_offers || 0

  if (resumes === 0) {
    return {
      label: '第一步',
      title: '上传第一份简历',
      description: '有了简历，才能做诊断和岗位匹配。',
      action: '上传简历',
      link: '/resume-center',
    }
  }
  if (saved === 0) {
    return {
      label: '建议下一步',
      title: '先确定目标岗位',
      description: '从推荐里挑一个想投的岗位，保存下来。',
      action: '查看岗位推荐',
      link: '/jobs/recommend',
    }
  }
  if (applications === 0) {
    return {
      label: '建议下一步',
      title: '把目标岗位加入投递',
      description: '在投递看板里建一条记录，开始跟进。',
      action: '打开投递看板',
      link: '/jobs/pipeline/kanban',
    }
  }
  if (interviews > 0 && offers === 0) {
    return {
      label: '建议下一步',
      title: '准备下一场面试',
      description: `有 ${interviews} 个岗位进入面试，练一遍再上场。`,
      action: '开始模拟面试',
      link: '/interview/setup',
    }
  }
  if (active > 0) {
    return {
      label: '建议下一步',
      title: '跟进进行中的投递',
      description: `还有 ${active} 个投递没有结果，看看该跟进哪一个。`,
      action: '查看投递看板',
      link: '/jobs/pipeline/kanban',
    }
  }
  return {
    label: '建议下一步',
    title: '继续拓展机会',
    description: '当前投递都有进展，可以再看看新的匹配岗位。',
    action: '查看岗位推荐',
    link: '/jobs/recommend',
  }
})

function handleNextAction() {
  if (overviewError.value) {
    loadDashboard()
    return
  }
  go(nextAction.value.link)
}

async function loadDashboard() {
  overviewError.value = false
  tasksError.value = false
  tasksLoading.value = true
  const [ov, tk] = await Promise.allSettled([getDashboardOverview(), getTodayTasks()])
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
  tasksLoading.value = false
}

onMounted(loadDashboard)
</script>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ===== Hero ===== */
.home-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 28px;
  padding: 28px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
}

.home-hero-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
}

.home-eyebrow {
  margin: 0;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 500;
}

.home-title {
  margin: 8px 0 0;
  color: var(--app-text);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.02em;
}

.home-sub {
  margin: 10px 0 0;
  color: var(--app-muted);
  font-size: 14px;
  line-height: 1.6;
}

.home-next {
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: center;
  padding: 20px;
  border: 1px solid var(--app-line);
  border-left: 3px solid var(--app-primary);
  border-radius: var(--app-radius-md);
  background: color-mix(in srgb, var(--app-primary), var(--app-surface-strong) 96%);
}

.home-next.is-muted {
  border-left-color: var(--app-line-strong);
  background: var(--app-surface-muted);
}

.home-next-label {
  color: var(--app-primary-dark);
  font-size: 12px;
  font-weight: 600;
}

.home-next.is-muted .home-next-label {
  color: var(--app-muted);
}

.home-next-title {
  color: var(--app-text);
  font-size: 17px;
  font-weight: 650;
  line-height: 1.4;
}

.home-next-desc {
  margin: 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
}

.home-next-btn {
  align-self: flex-start;
  margin-top: 4px;
}

/* ===== Entrances ===== */
.home-entrances {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.entrance-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.entrance-card:hover {
  border-color: var(--app-line-strong);
  box-shadow: var(--app-shadow);
}

.entrance-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: var(--app-radius-sm);
  background: var(--app-primary-light);
  color: var(--app-primary-dark);
  font-size: 17px;
}

.entrance-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.entrance-body strong {
  color: var(--app-text);
  font-size: 14px;
  font-weight: 650;
}

.entrance-body span {
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.5;
}

.entrance-body em {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
  font-style: normal;
}

.entrance-arrow {
  margin-top: 8px;
  color: var(--app-muted);
  flex-shrink: 0;
}

/* ===== Columns ===== */
.home-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.home-panel {
  min-width: 0;
}

.home-panel-note {
  color: var(--app-muted);
  font-size: 12px;
}

/* ===== Tasks ===== */
.task-list {
  display: flex;
  flex-direction: column;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 8px;
  border: 0;
  border-bottom: 1px solid var(--app-line);
  border-radius: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.task-row:last-child {
  border-bottom: 0;
}

.task-row:hover {
  background: var(--app-surface-muted);
}

.task-dot {
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

.task-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.task-copy strong {
  overflow: hidden;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 550;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-copy span {
  overflow: hidden;
  color: var(--app-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-arrow {
  color: var(--app-muted);
  flex-shrink: 0;
}

/* ===== Funnel ===== */
.funnel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.funnel-bar {
  display: flex;
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--app-surface-muted);
}

.funnel-seg {
  height: 100%;
  min-width: 0;
}

.funnel-seg + .funnel-seg {
  border-left: 2px solid var(--app-surface-strong);
}

.funnel-seg--todo {
  background: var(--app-muted);
}

.funnel-seg--applied {
  background: var(--app-primary);
}

.funnel-seg--written_test {
  background: var(--app-violet);
}

.funnel-seg--interview {
  background: color-mix(in srgb, var(--app-warning), black 25%);
}

.funnel-seg--offer {
  background: color-mix(in srgb, var(--app-success), black 25%);
}

.funnel-legend {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.funnel-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.funnel-item strong {
  color: var(--app-text);
  font-size: 18px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.funnel-item span {
  color: var(--app-muted);
  font-size: 12px;
}

.funnel-note {
  margin: 0;
  color: var(--app-muted);
  font-size: 12px;
}

/* ===== Responsive ===== */
@media (max-width: 1024px) {
  .home-hero {
    grid-template-columns: 1fr;
    gap: 20px;
  }

  .home-entrances {
    grid-template-columns: 1fr;
  }

  .home-columns {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .home-page {
    gap: 20px;
  }

  .home-hero {
    padding: 20px;
  }

  .home-title {
    font-size: 24px;
  }

  .funnel-legend {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    row-gap: 12px;
  }
}
</style>
