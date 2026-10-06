<template>
  <div class="page-shell jobsearch-page">
    <section class="hero">
      <div class="hero-copy">
        <div class="hero-title-row">
          <h2>岗位市场</h2>
          <div class="hero-orbits" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
        <div class="hero-actions">
          <el-button type="primary" size="large" :loading="searching" @click="runSearch">
            <el-icon><Search /></el-icon>
            搜索最新岗位
          </el-button>
          <el-button size="large" @click="seedDemoData" :loading="seeding">
            <el-icon><Promotion /></el-icon>
            补充演示岗位池
          </el-button>
        </div>
        <div class="source-banner" :class="sourceBannerClass">
          <strong>{{ sourceBannerTitle }}</strong>
          <span>{{ sourceBannerDesc }}</span>
        </div>
      </div>

      <div class="hero-metrics">
        <div class="metric-card accent-orange">
          <span class="metric-label">本次搜索</span>
          <strong>{{ externalJobs.length }}</strong>
          <small>{{ searchStateText }}</small>
        </div>
        <div class="metric-card accent-blue">
          <span class="metric-label">岗位仓库</span>
          <strong>{{ localJobs.length }}</strong>
          <small>已落库可复用 JD</small>
        </div>
        <div class="metric-card accent-green">
          <span class="metric-label">智能推荐</span>
          <strong>{{ recommendations.length }}</strong>
          <small>基于当前简历生成</small>
        </div>
        <div class="metric-card accent-dark">
          <span class="metric-label">流程中岗位</span>
          <strong>{{ pipelineActiveCount }}</strong>
          <small>待投递到已约面统一跟踪</small>
        </div>
      </div>
    </section>

    <section class="layout-grid">
      <div class="main-column">
        <el-card shadow="never" class="control-card">
          <div class="control-top">
            <div class="search-stack">
              <el-input
                v-model="keyword"
                class="search-input"
                size="large"
                clearable
                placeholder="搜索职位、方向或技术关键词，例如 Python、算法、前端架构"
                @keydown.enter="runSearch"
              >
                <template #prefix
                  ><el-icon><Search /></el-icon
                ></template>
              </el-input>

              <el-select
                v-model="city"
                placement="bottom-start"
                :fallback-placements="['bottom-start']"
                clearable
                filterable
                size="large"
                class="city-select"
                placeholder="城市"
              >
                <el-option
                  v-for="item in cities"
                  :key="item.code || item.name"
                  :label="item.name"
                  :value="item.name"
                />
              </el-select>

              <el-select
                v-model="source"
                placement="bottom-start"
                :fallback-placements="['bottom-start']"
                size="large"
                class="source-select"
                placeholder="渠道"
              >
                <el-option label="BOSS 直聘" value="boss" />
                <el-option label="全平台兜底" value="all" />
              </el-select>
            </div>

            <div class="resume-row">
              <span class="resume-label">目标简历</span>
              <el-select
                v-model="selectedResumeId"
                placement="bottom-start"
                :fallback-placements="['bottom-start']"
                filterable
                clearable
                class="resume-select"
                placeholder="选择用于推荐和分析的简历"
                @change="handleResumeChange"
              >
                <el-option
                  v-for="resume in resumeList"
                  :key="resume.id"
                  :label="resume.file_name || resume.name || `简历 #${resume.id}`"
                  :value="resume.id"
                />
              </el-select>
              <!-- 拉不到简历不等于没有简历：这里不说出来，用户会以为自己没上传过 -->
              <AppLoadError
                v-if="resumesError"
                title="简历列表拉取失败"
                :message="resumesError"
                @retry="loadResumes"
              />
              <!-- 列表和详情是两次 GET。只有详情失败时，简历摘要会以空串参与"改写搜索词"，
                   页面接着对一个已经选了简历的人说"先选择一份简历" -->
              <AppLoadError
                v-else-if="resumeDetailError"
                title="简历详情拉取失败"
                :message="resumeDetailError"
                @retry="loadResumeDetail(selectedResumeId)"
              />
            </div>
          </div>

          <div class="preset-row">
            <span class="preset-label">快速搜索</span>
            <button
              v-for="item in presetKeywords"
              :key="item"
              type="button"
              class="preset-chip"
              @click="searchWithKeyword(item)"
            >
              {{ item }}
            </button>
          </div>

          <div class="filter-row">
            <el-select
              v-model="searchFilters.experience"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              clearable
              size="small"
              placeholder="经验要求"
            >
              <el-option label="不限经验" value="" />
              <el-option label="1-3 年" value="1-3" />
              <el-option label="3-5 年" value="3-5" />
              <el-option label="5 年以上" value="5+" />
            </el-select>

            <el-select
              v-model="searchFilters.education"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              clearable
              size="small"
              placeholder="学历"
            >
              <el-option label="不限学历" value="" />
              <el-option label="本科" value="本科" />
              <el-option label="硕士" value="硕士" />
              <el-option label="博士" value="博士" />
            </el-select>

            <el-input
              v-model="searchFilters.skill"
              clearable
              size="small"
              placeholder="技能过滤，例如 Docker / LLM"
              class="skill-filter"
            />

            <el-radio-group v-model="searchSort" size="small">
              <el-radio-button label="default">综合排序</el-radio-button>
              <el-radio-button label="salary_desc">薪资优先</el-radio-button>
              <el-radio-button label="salary_asc">保守筛选</el-radio-button>
              <el-radio-button label="skill_desc">技能密度</el-radio-button>
            </el-radio-group>

            <el-button text @click="resetSearchFilters">重置筛选</el-button>
          </div>

          <div v-if="recentSearches.length" class="history-row">
            <span class="history-label">最近搜索</span>
            <button
              v-for="item in recentSearches"
              :key="item"
              type="button"
              class="history-chip"
              @click="searchWithKeyword(item)"
            >
              {{ item }}
            </button>
          </div>

          <div class="rewrite-row">
            <div class="rewrite-head">
              <div>
                <span class="history-label">AI 改写搜索词</span>
                <p class="rewrite-note">
                  结合当前简历和搜索意图，生成更贴近招聘平台检索习惯的词组。
                </p>
              </div>
              <el-button size="small" :loading="rewriteLoading" @click="generateRewriteSuggestions">
                生成建议
              </el-button>
            </div>
            <div v-if="rewrittenKeywords.length" class="rewrite-chips">
              <button
                v-for="item in rewrittenKeywords"
                :key="item"
                type="button"
                class="history-chip"
                @click="searchWithKeyword(item)"
              >
                {{ item }}
              </button>
            </div>
            <p v-if="rewriteMeta" class="rewrite-meta">{{ rewriteMeta }}</p>
          </div>
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div>
                <h2>市场视图</h2>
                <p>外部搜索、本地岗位池、智能推荐共用一套行动入口。</p>
              </div>
              <el-button text @click="refreshActiveTab">
                <el-icon><RefreshRight /></el-icon>
                刷新当前视图
              </el-button>
            </div>
          </template>

          <el-tabs v-model="activeTab" class="market-tabs">
            <el-tab-pane label="实时搜索" name="search">
              <SearchPane
                :jobs="filteredExternalJobs"
                :searching="searching"
                :has-searched="hasSearched"
                :search-hint="searchHint"
                :search-error="searchError"
                :is-demo="isDemo"
                :result-mode="resultMode"
                :saved-count="savedCount"
                :state-text="searchStateText"
                :banner-title="sourceBannerTitle"
                :banner-desc="sourceBannerDesc"
                :banner-class="sourceBannerClass"
                :compare-count="compareSelection.length"
                :compared-uids="compareSelection"
                :is-shortlisted="isShortlisted"
                :pipeline-status-text="pipelineStatusText"
                @open-compare="openComparePanel"
                @detail="(job) => openJobDetail(job, 'search')"
                @pipeline="handlePipelineAction"
                @compare="toggleCompare"
                @shortlist="toggleShortlist"
                @prefill="prefillAnalysis"
                @analyze="startAnalysisForJob"
              />
            </el-tab-pane>

            <el-tab-pane label="岗位仓库" name="warehouse">
              <WarehousePane
                :jobs="filteredLocalJobs"
                :loading="localLoading"
                :error="localError"
                :filters="warehouseFilters"
                :compared-uids="compareSelection"
                :pipeline-status-text="pipelineStatusText"
                @update:filters="(value) => (warehouseFilters = value)"
                @refresh="loadLocalJobs"
                @detail="(job) => openJobDetail(job, 'warehouse')"
                @pipeline="handlePipelineAction"
                @compare="toggleCompare"
                @prefill="prefillAnalysis"
                @analyze="startAnalysisForJob"
              />
            </el-tab-pane>

            <el-tab-pane label="智能推荐" name="recommend">
              <RecommendPane
                :jobs="normalizedRecommendations"
                :loading="recommendLoading"
                :error="recommendError"
                :filters="recommendFilters"
                :resume-name="selectedResumeName"
                :resume-selected="selectedResumeId"
                :compared-uids="compareSelection"
                :is-shortlisted="isShortlisted"
                :pipeline-status-text="pipelineStatusText"
                @update:filters="(value) => (recommendFilters = value)"
                @refresh="loadRecommendations"
                @detail="(job) => openJobDetail(job, 'recommend')"
                @pipeline="handlePipelineAction"
                @compare="toggleCompare"
                @shortlist="toggleShortlist"
                @analyze="startAnalysisForJob"
              />
            </el-tab-pane>

            <el-tab-pane label="投递流程" name="pipeline">
              <PipelinePane
                :entries="pipelineEntries"
                :active-count="pipelineActiveCount"
                :stats="pipelineStats"
                :by-stage="pipelineByStage"
                :visible-stages="visiblePipelineStages"
                :filters="pipelineFilters"
                :error="pipelineError"
                @update:filters="(value) => (pipelineFilters = value)"
                @refresh="loadPipelineEntries"
                @clear-rejected="clearRejectedPipeline"
                @touch="touchPipelineEntry"
                @update-stage="updatePipelineStage"
                @remove="removePipelineEntry"
                @open="openPipelineJob"
                @prefill="prefillAnalysis"
                @analyze="startAnalysisForJob"
              />
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </div>

      <aside class="side-column">
        <el-card shadow="never" class="board-card">
          <template #header>
            <div class="board-header">
              <div>
                <h3>求职作战板</h3>
                <p>把“准备投什么”和“下一步做什么”固定下来。</p>
              </div>
              <el-tag type="info" effect="plain">{{ activeTabLabel }}</el-tag>
            </div>
          </template>

          <div class="board-block">
            <span class="board-label">当前简历</span>
            <strong>{{ selectedResumeName || '未选择简历' }}</strong>
            <p class="board-note">推荐和直接分析都会默认使用这里选中的简历。</p>
          </div>

          <div class="board-block">
            <span class="board-label">市场观察</span>
            <div class="insight-grid">
              <div class="insight-item">
                <strong>{{ marketInsights.salaryBand }}</strong>
                <small>主要薪资带</small>
              </div>
              <div class="insight-item">
                <strong>{{ marketInsights.hotCity }}</strong>
                <small>最热城市</small>
              </div>
              <div class="insight-item">
                <strong>{{ marketInsights.skillFocus }}</strong>
                <small>高频技能</small>
              </div>
              <div class="insight-item">
                <strong>{{ marketInsights.highSalaryCount }}</strong>
                <small>高薪样本数</small>
              </div>
            </div>
          </div>

          <div class="board-block">
            <div class="board-row">
              <span class="board-label">投递进度总览</span>
              <button type="button" class="text-btn" @click="activeTab = 'pipeline'">
                打开看板
              </button>
            </div>
            <div class="pipeline-summary-grid">
              <div v-for="stage in pipelineStages" :key="stage.key" class="pipeline-summary-item">
                <strong>{{ pipelineStats[stage.key] || 0 }}</strong>
                <span>{{ stage.label }}</span>
              </div>
            </div>
            <div v-if="pipelineFocusList.length" class="shortlist">
              <button
                v-for="entry in pipelineFocusList"
                :key="entry.entryId"
                type="button"
                class="short-item"
                @click="openPipelineJob(entry)"
              >
                <strong>{{ entry.title }}</strong>
                <span>{{ pipelineStageLabel(entry.stage) }} · {{ entry.company }}</span>
              </button>
            </div>
            <el-empty v-else :image-size="70" description="流程里还没有岗位" />
          </div>

          <div class="board-block">
            <div class="board-row">
              <span class="board-label">待跟进清单</span>
              <button
                type="button"
                class="text-btn"
                @click="clearShortlist"
                v-if="shortlist.length"
              >
                清空
              </button>
            </div>
            <div v-if="shortlist.length" class="shortlist">
              <button
                v-for="job in shortlist.slice(0, 6)"
                :key="job.uid"
                type="button"
                class="short-item"
                @click="openShortlistedJob(job)"
              >
                <strong>{{ job.title }}</strong>
                <span>{{ job.company }}</span>
              </button>
            </div>
            <el-empty v-else :image-size="70" description="还没有加入任何岗位" />
          </div>

          <div class="board-block">
            <span class="board-label">优先投递队列</span>
            <div v-if="priorityQueue.length" class="shortlist">
              <button
                v-for="job in priorityQueue"
                :key="job.uid"
                type="button"
                class="short-item"
                @click="openJobDetail(job, 'priority')"
              >
                <strong>{{ job.title }} · {{ job.priorityScore }}</strong>
                <span>{{ job.priorityLabel }} · {{ job.company }}</span>
              </button>
            </div>
            <el-empty v-else :image-size="70" description="当前视图还没有足够样本" />
          </div>

          <div class="board-block">
            <span class="board-label">下一步动作</span>
            <div class="cta-list">
              <button type="button" class="cta-item" @click="goToSmartAnalysis">
                <span>去智能分析页完善投递素材</span>
                <el-icon><ArrowRight /></el-icon>
              </button>
              <button type="button" class="cta-item" @click="activeTab = 'recommend'">
                <span>切到智能推荐做批量筛选</span>
                <el-icon><ArrowRight /></el-icon>
              </button>
              <button type="button" class="cta-item" @click="activeTab = 'warehouse'">
                <span>查看已经落库的本地 JD</span>
                <el-icon><ArrowRight /></el-icon>
              </button>
            </div>
          </div>
        </el-card>
      </aside>
    </section>

    <JobDetailDrawer
      v-model="detailVisible"
      :job="detailJob"
      :loading="detailLoading"
      :status-text="detailStatusText"
      :shortlisted="detailShortlisted"
      :compared="detailCompared"
      :explain-result="explainResult"
      :explain-loading="explainLoading"
      @shortlist="toggleShortlist(detailJob)"
      @pipeline="handlePipelineAction(detailJob)"
      @compare="toggleCompare(detailJob)"
      @explain="explainCurrentJob"
      @analyze="startAnalysisForJob(detailJob)"
    />

    <JobCompareDialog
      v-model="compareVisible"
      :jobs="comparedJobs"
      :status-text="pipelineStatusText"
      @detail="(job) => openJobDetail(job, 'compare')"
      @pipeline="handlePipelineAction"
      @remove="toggleCompare"
      @analyze="startAnalysisForJob"
    />
  </div>
</template>

<script setup>
import { userErrorCopy } from '@/utils/requestTracing'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { ArrowRight, Promotion, RefreshRight, Search } from '@element-plus/icons-vue'
import { getResume, getResumeList } from '@/api/resume'
import { explainMatch } from '@/api/analysis'
import { queryRewriteTest } from '@/api/knowledge'
import { getJobDetail, seedDemoJobs, startFullAnalysis } from '@/api/jobs'
import { useSelectionStore } from '@/stores/selection'
import { useLatestCall } from '@/composables/useLatestCall'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import JobCompareDialog from '@/features/jobs/components/JobCompareDialog.vue'
import JobDetailDrawer from '@/features/jobs/components/JobDetailDrawer.vue'
import PipelinePane from '@/features/jobs/components/PipelinePane.vue'
import RecommendPane from '@/features/jobs/components/RecommendPane.vue'
import SearchPane from '@/features/jobs/components/SearchPane.vue'
import WarehousePane from '@/features/jobs/components/WarehousePane.vue'
import { useJobPipeline } from '@/features/jobs/composables/useJobPipeline'
import { useJobRecommend } from '@/features/jobs/composables/useJobRecommend'
import { useJobSearch } from '@/features/jobs/composables/useJobSearch'
import { useJobShortlist } from '@/features/jobs/composables/useJobShortlist'
import { useJobWarehouse } from '@/features/jobs/composables/useJobWarehouse'
import {
  normalizeJob,
  pipelineStageLabel,
  pipelineStages,
  rankMap,
  salaryMid,
} from '@/features/jobs/lib/jobModel'
const selection = useSelectionStore()

const route = useRoute()
const router = useRouter()

const activeTab = ref('search')
const selectedResumeId = ref(null)
const resumeList = ref([])
const resumesError = ref('')
const selectedResumeDetail = ref(null)
// 详情失败与列表失败要分开：`selectedResumeSummary` 只从详情算，读不到又不出声的话，
// 它会让"改写搜索词"对一个已经选了简历的人说"先输入岗位关键词，或先选择一份简历"。
const resumeDetailError = ref('')

// 剩下的两条链各一把令牌：`useLatestCall()` 的计数器是整个实例共享的，共用会让两条链互相当场作废
// 对方在途的响应（D28 量到的就是这条），仓库与推荐那两条已随各自的 composable 搬走。
const latestResumeDetailCall = useLatestCall()
const latestJobDetailCall = useLatestCall()

const seeding = ref(false)

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailJob = ref(null)
const explainLoading = ref(false)
const explainResult = ref(null)

const compareVisible = ref(false)
const compareSelection = ref([])
const detailRouteKey = ref('')

const rewriteLoading = ref(false)
const rewrittenKeywords = ref([])
const rewriteMeta = ref('')

const presetKeywords = ['Python 后端', '前端架构', '大模型应用', '算法工程师', '数据分析', 'DevOps']

const {
  shortlist,
  recentSearches,
  toggleShortlist,
  isShortlisted,
  clearShortlist,
  pushRecentSearch,
} = useJobShortlist()

const {
  keyword,
  city,
  source,
  cities,
  searching,
  hasSearched,
  searchHint,
  searchError,
  isDemo,
  resultMode,
  savedCount,
  externalJobs,
  searchFilters,
  searchSort,
  filteredExternalJobs,
  searchStateText,
  sourceBannerTitle,
  sourceBannerDesc,
  sourceBannerClass,
  loadCities,
  runSearch,
  searchWithKeyword,
  resetSearchFilters,
} = useJobSearch({ pushRecentSearch })

const {
  recommendations,
  recommendLoading,
  recommendError,
  recommendFilters,
  normalizedRecommendations,
  loadRecommendations,
} = useJobRecommend({ selectedResumeId, city })

const { localLoading, localJobs, localError, warehouseFilters, filteredLocalJobs, loadLocalJobs } =
  useJobWarehouse({ city })

const selectedResumeName = computed(() => {
  const resume = resumeList.value.find((item) => item.id === selectedResumeId.value)
  return resume?.file_name || resume?.name || ''
})

const {
  pipelineError,
  pipelineEntries,
  pipelineFilters,
  pipelineStats,
  pipelineActiveCount,
  visiblePipelineStages,
  pipelineByStage,
  pipelineFocusList,
  loadPipelineEntries,
  handlePipelineAction,
  pipelineStatusText,
  openPipelineJob,
  touchPipelineEntry,
  updatePipelineStage,
  removePipelineEntry,
  clearRejectedPipeline,
} = useJobPipeline({ activeTab, selectedResumeId, selectedResumeName, openJobDetail })

const selectedResumeSummary = computed(() => {
  const parsed = selectedResumeDetail.value?.parsed_json || selectedResumeDetail.value?.parsed || {}
  const skills = Array.isArray(parsed.skills)
    ? parsed.skills
        .map((item) => (typeof item === 'string' ? item : item?.skill))
        .filter(Boolean)
        .slice(0, 8)
    : []
  const currentTitle =
    parsed.current_title || parsed.target_position || selectedResumeDetail.value?.name || ''
  return [currentTitle, skills.join(' / ')].filter(Boolean).join('，')
})

const activeTabLabel = computed(
  () =>
    ({
      search: '实时搜索',
      warehouse: '岗位仓库',
      recommend: '智能推荐',
      pipeline: '投递流程',
    })[activeTab.value] || '实时搜索'
)

const comparedJobs = computed(() => {
  const map = new Map(marketDataset.value.map((job) => [job.uid, job]))
  return compareSelection.value.map((uid) => map.get(uid)).filter(Boolean)
})

// 抽屉一次只看一个岗位，所以这三个由父页面算好传值，而不是把函数传下去
const detailStatusText = computed(() =>
  detailJob.value ? pipelineStatusText(detailJob.value) : ''
)
const detailShortlisted = computed(() => (detailJob.value ? isShortlisted(detailJob.value) : false))
const detailCompared = computed(() => (detailJob.value ? isCompared(detailJob.value) : false))

const priorityQueue = computed(() =>
  [...marketDataset.value]
    .filter((job) => typeof job.priorityScore === 'number')
    .sort((a, b) => b.priorityScore - a.priorityScore)
    .slice(0, 5)
)

const marketDataset = computed(() => {
  if (activeTab.value === 'warehouse') return filteredLocalJobs.value
  if (activeTab.value === 'recommend') return normalizedRecommendations.value
  return filteredExternalJobs.value
})

const marketInsights = computed(() => {
  const jobs = marketDataset.value
  if (!jobs.length) {
    return {
      salaryBand: '--',
      hotCity: '--',
      skillFocus: '--',
      highSalaryCount: 0,
    }
  }

  const salaryValues = jobs.map((job) => salaryMid(job.salary)).filter((value) => value > 0)
  const avgSalary = salaryValues.length
    ? Math.round(salaryValues.reduce((sum, value) => sum + value, 0) / salaryValues.length)
    : 0

  const citiesMap = rankMap(jobs.map((job) => job.location).filter(Boolean))
  const skillsMap = rankMap(jobs.flatMap((job) => job.skillTags || []).filter(Boolean))

  return {
    salaryBand: avgSalary ? `${Math.max(avgSalary - 5, 10)}K - ${avgSalary + 5}K` : '待补齐',
    hotCity: citiesMap[0]?.label || '待补齐',
    skillFocus: skillsMap[0]?.label || '待补齐',
    highSalaryCount: jobs.filter((job) => salaryMid(job.salary) >= 30).length,
  }
})

watch(activeTab, async (value) => {
  if (value === 'warehouse' && !localJobs.value.length) {
    await loadLocalJobs()
  }
  if (value === 'recommend' && selectedResumeId.value && !recommendations.value.length) {
    await loadRecommendations()
  }
})

watch(
  () => route.query,
  async () => {
    await openRequestedJobDetailFromRoute()
  }
)

onMounted(async () => {
  await Promise.all([loadCities(), loadResumes(), loadLocalJobs(), loadPipelineEntries()])
  if (selectedResumeId.value) {
    await loadRecommendations()
  }
  await openRequestedJobDetailFromRoute()
})

async function openRequestedJobDetailFromRoute() {
  const jobId = Number(route.query.job_id)
  if (!jobId) return

  const routeKey = `${route.query.job_id || ''}:${route.query.resume_id || ''}:${route.query.tab || ''}`
  if (detailRouteKey.value === routeKey) return
  detailRouteKey.value = routeKey

  const requestedTab = typeof route.query.tab === 'string' ? route.query.tab : ''
  if (['search', 'warehouse', 'recommend', 'pipeline'].includes(requestedTab)) {
    activeTab.value = requestedTab
  }

  const resumeId = Number(route.query.resume_id)
  if (resumeId && resumeId !== selectedResumeId.value) {
    selectedResumeId.value = resumeId
    await loadResumeDetail(resumeId)
    if (activeTab.value === 'recommend') {
      await loadRecommendations()
    }
  }

  await openJobDetail(
    {
      id: jobId,
      title: '职位详情',
      company: '',
      location: '',
      salary: '',
      summary: '',
      rawText: '',
      skillTags: [],
    },
    'route'
  )
}

async function loadResumes() {
  resumesError.value = ''
  try {
    const data = await getResumeList()
    resumeList.value = data?.items || (Array.isArray(data) ? data : [])
    if (!selectedResumeId.value && resumeList.value.length) {
      selectedResumeId.value = resumeList.value[0].id
    }
    if (selectedResumeId.value) {
      await loadResumeDetail(selectedResumeId.value)
    }
  } catch (e) {
    resumeList.value = []
    resumesError.value = userErrorCopy(e, '暂时无法读取你的简历列表')
  }
}

async function loadResumeDetail(resumeId) {
  // 令牌在进入时领取：换简历与"清空选择"这两次意图都要作废仍在途的旧详情，
  // 否则旧简历的技能会留在摘要里，被"改写搜索词"当成当前简历发给模型
  const isCurrent = latestResumeDetailCall()
  resumeDetailError.value = ''
  if (!resumeId) {
    selectedResumeDetail.value = null
    return
  }
  try {
    const data = await getResume(resumeId)
    if (!isCurrent()) return
    selectedResumeDetail.value = data
  } catch (e) {
    if (!isCurrent()) return
    selectedResumeDetail.value = null
    resumeDetailError.value = userErrorCopy(e, '暂时读不到这份简历的详情')
  }
}

async function refreshActiveTab() {
  if (activeTab.value === 'warehouse') {
    await loadLocalJobs()
    return
  }
  if (activeTab.value === 'recommend') {
    await loadRecommendations()
    return
  }
  if (keyword.value.trim()) {
    await runSearch()
  }
}

async function seedDemoData() {
  seeding.value = true
  try {
    const data = await seedDemoJobs()
    ElMessage.success(data?.message || '演示岗位已补充')
    await loadLocalJobs()
    if (selectedResumeId.value) {
      await loadRecommendations()
    }
  } catch {
    ElMessage.error('补充演示岗位失败')
  } finally {
    seeding.value = false
  }
}

async function handleResumeChange() {
  if (!selectedResumeId.value) {
    // 清空也是一次意图：两条链都要在入口领走自己的令牌，而不是就地写空值。
    // 详情那条 D28 已经改成走 loadResumeDetail(null)；推荐这条原本漏了，
    // 于是旧简历那一发随后落地会把推荐填回"已经没选简历"的屏幕
    // （jobRecommendClear.test.js 钉的就是这条）。
    await loadRecommendations()
    await loadResumeDetail(null)
    return
  }
  await loadResumeDetail(selectedResumeId.value)
  await loadRecommendations()
  await loadPipelineEntries()
}

async function generateRewriteSuggestions() {
  if (!keyword.value.trim() && !selectedResumeSummary.value) {
    ElMessage.warning('先输入岗位关键词，或先选择一份简历')
    return
  }
  rewriteLoading.value = true
  rewrittenKeywords.value = []
  rewriteMeta.value = ''
  try {
    const res = await queryRewriteTest({
      original_query:
        keyword.value.trim() || `为我推荐适合 ${selectedResumeName.value || '当前简历'} 的岗位`,
      resume_summary: selectedResumeSummary.value,
      jd_summary: '',
      doc_type: 'jd_lib',
      top_k_per_query: 3,
      max_queries: 4,
    })
    const queries = (res?.rewritten_queries || [])
      .filter((item) => item.query_type !== 'original')
      .map((item) => item.query_text)
      .filter(Boolean)
    rewrittenKeywords.value = [...new Set(queries)].slice(0, 6)
    rewriteMeta.value = queries.length ? '可直接点击替换搜索词' : '当前关键词已经比较具体'
  } catch {
    ElMessage.error('改写搜索词失败')
  } finally {
    rewriteLoading.value = false
  }
}

async function openJobDetail(job, origin) {
  // 抽屉是模态的，但关闭不会取消已经发出的请求；站内带 job_id 的链接也会再开一个详情。
  // 这里原本是 `...detailJob.value` 就地合并，所以旧响应会把上一个岗位的内容并进当前抽屉
  const isCurrent = latestJobDetailCall()
  detailVisible.value = true
  detailLoading.value = true
  explainResult.value = null
  detailJob.value = {
    ...job,
    rawText: job.rawText || '',
  }

  if (!job.id) {
    detailLoading.value = false
    return
  }

  try {
    const data = await getJobDetail(job.id)
    if (!isCurrent()) return
    detailJob.value = {
      ...detailJob.value,
      ...normalizeJob(
        {
          id: data?.id,
          title: data?.title,
          company: data?.company,
          location: data?.location,
          salary_range: data?.salary_range,
          industry: data?.industry,
          raw_text: data?.raw_text,
          jd_summary: data?.parsed?.jd_summary || job.summary,
          skill_tags: data?.parsed?.skill_tags || data?.parsed?.required_skills || job.skillTags,
          education_requirement: data?.parsed?.education_requirement || job.education,
          experience_requirement: data?.parsed?.experience_requirement || job.experience,
          source: data?.source || job.source,
        },
        `${origin}-detail`,
        city.value
      ),
    }
  } catch {
    if (!isCurrent()) return
    detailJob.value = { ...job }
  } finally {
    if (isCurrent()) detailLoading.value = false
  }
}

async function explainCurrentJob() {
  if (!selectedResumeId.value || !detailJob.value?.id) {
    ElMessage.warning('需要已选简历和已落库岗位，才能生成投递解读')
    return
  }
  explainLoading.value = true
  try {
    explainResult.value = await explainMatch({
      resume_id: selectedResumeId.value,
      jd_id: detailJob.value.id,
    })
  } catch {
    explainResult.value = null
  } finally {
    explainLoading.value = false
  }
}

function prefillAnalysis(job) {
  if (!selectedResumeId.value) {
    ElMessage.warning('先选择一份简历，再把岗位带入分析')
    return
  }
  persistAnalysisContext(job)
  ElMessage.success('已带入分析上下文，接下来可继续完善和启动分析')
  router.push('/smart-analysis')
}

async function startAnalysisForJob(job) {
  if (!selectedResumeId.value) {
    ElMessage.warning('先选择一份简历，再启动分析')
    return
  }

  persistAnalysisContext(job)

  if (!job.id) {
    router.push('/smart-analysis')
    return
  }

  try {
    const data = await startFullAnalysis(selectedResumeId.value, job.id)
    if (data?.task_id) {
      ElMessage.success('分析任务已启动')
      router.push({ name: 'task-center', query: { task_id: String(data.task_id) } })
      return
    }
  } catch {
    ElMessage.warning('自动启动失败，已带你进入分析页继续处理')
  }

  router.push('/smart-analysis')
}

function persistAnalysisContext(job) {
  selection.rememberResume(selectedResumeId.value)
  localStorage.setItem(
    'recruit.pendingAnalysis',
    JSON.stringify({
      jdId: job.id,
      title: job.title,
      company: job.company,
      jd_text: job.rawText || job.summary || '',
    })
  )
}

function toggleCompare(job) {
  const exists = compareSelection.value.includes(job.uid)
  if (exists) {
    compareSelection.value = compareSelection.value.filter((item) => item !== job.uid)
    return
  }
  if (compareSelection.value.length >= 3) {
    ElMessage.warning('最多同时对比 3 个岗位')
    return
  }
  compareSelection.value = [...compareSelection.value, job.uid]
}

function isCompared(job) {
  return compareSelection.value.includes(job.uid)
}

function openComparePanel() {
  if (comparedJobs.value.length < 2) {
    ElMessage.warning('至少选择 2 个岗位再进行对比')
    return
  }
  compareVisible.value = true
}

function openShortlistedJob(job) {
  openJobDetail(job, 'shortlist')
}

function goToSmartAnalysis() {
  router.push('/smart-analysis')
}
</script>

<style scoped>
/* D44 把仓库面板与投递流程面板搬出去了，但这里的规则一条都没删：
   静态切分看不见 `:class="signalClass(...)"` 这类函数生成的类名（本页 494-500 行有 3 处），
   删错了是没人能看见的视觉回归。所以两个面板的样式是**复制**进子组件的，本文件里留下 27 条
   只指向 `.warehouse-*` / `.pipeline-*` 的死选择器（两个面板都是多根片段，父作用域 id 落不到
   子组件元素上，因此它们今天不影响渲染）。要清这 27 条，先在真浏览器里逐路由差分确认。 */
.page-shell {
  max-width: 1480px;
  margin: 0 auto;
  padding: 18px 0 28px;
  color: var(--app-text);
}

.hero {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 18px;
  padding: 26px;
  border-radius: var(--app-radius-md, 16px);
  position: relative;
  overflow: hidden;
  background: var(--app-bg);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
}

.hero::before {
  content: '';
  position: absolute;
  inset: 18px auto auto 18px;
  width: 120px;
  height: 120px;
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.7), rgba(255, 255, 255, 0.08));
  transform: rotate(-10deg);
  pointer-events: none;
}

.hero::after {
  content: '';
  position: absolute;
  right: 36px;
  bottom: -28px;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  border: 1px dashed var(--app-line);
  pointer-events: none;
}

.hero h2 {
  margin: 0;
  font-size: 38px;
  line-height: 1.05;
}

.hero-copy {
  position: relative;
  z-index: 1;
  min-height: 160px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.hero-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.52);
  border: 1px solid var(--app-line);
  backdrop-filter: blur(10px);
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
  background: linear-gradient(135deg, var(--app-primary, #7c6cff), var(--app-primary, #9ca1ff));
  box-shadow: 0 8px 18px rgba(124, 108, 255, 0.22);
}

.hero-orbits span:nth-child(1) {
  width: 12px;
  height: 12px;
}

.hero-orbits span:nth-child(2) {
  width: 32px;
  height: 10px;
  opacity: 0.78;
}

.hero-orbits span:nth-child(3) {
  width: 18px;
  height: 18px;
  opacity: 0.55;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
  padding-left: 6px;
}

.source-banner,
.result-source-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 16px;
  padding: 12px 14px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.58);
}

.source-banner strong,
.result-source-note strong {
  font-size: 13px;
  color: var(--app-text);
}

.source-banner span,
.result-source-note span {
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.55;
}

.source-banner.is-live,
.result-source-note.is-live {
  border-color: rgba(59, 130, 246, 0.16);
  background: rgba(255, 255, 255, 0.62);
}

.source-banner.is-local,
.result-source-note.is-local {
  border-color: rgba(20, 184, 166, 0.18);
  background: rgba(236, 253, 250, 0.9);
}

.source-banner.is-demo,
.result-source-note.is-demo {
  border-color: rgba(245, 158, 11, 0.18);
  background: rgba(255, 247, 237, 0.94);
}

.source-banner.is-loading,
.result-source-note.is-loading {
  border-color: rgba(124, 108, 255, 0.16);
}

.hero-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  position: relative;
  z-index: 1;
}

.metric-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 124px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  color: #fff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.metric-card strong {
  font-size: 34px;
  line-height: 1;
}

.metric-card small,
.metric-label {
  opacity: 0.9;
}

.accent-orange {
  background: linear-gradient(135deg, var(--app-primary, #7c6cff), #9b8cff);
}
.accent-blue {
  background: linear-gradient(135deg, #3b82f6, #6aa6ff);
}
.accent-green {
  background: linear-gradient(135deg, #14b8a6, #39d2bf);
}
.accent-dark {
  background: linear-gradient(135deg, #15202b, #314456);
}

.layout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.9fr) minmax(320px, 0.9fr);
  gap: 18px;
  margin-top: 18px;
}

.main-column,
.side-column {
  min-width: 0;
}

.control-card,
.panel-card,
.board-card {
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.96);
}

.panel-card,
.board-card {
  margin-top: 18px;
}

.control-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 14px;
}

.search-stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px 140px;
  gap: 10px;
}

.resume-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.resume-label,
.preset-label,
.history-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.preset-row,
.history-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}

.rewrite-row {
  margin-top: 16px;
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.rewrite-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.rewrite-note,
.rewrite-meta,
.priority-reason {
  color: var(--app-muted);
}

.rewrite-note,
.rewrite-meta {
  margin: 6px 0 0;
  font-size: 13px;
}

.rewrite-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.preset-chip,
.history-chip {
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  border-radius: 999px;
  padding: 8px 12px;
  color: var(--app-text);
  cursor: pointer;
  transition: 0.2s ease;
}

.preset-chip:hover,
.history-chip:hover,
.bookmark-btn:hover,
.short-item:hover,
.cta-item:hover {
  transform: translateY(-1px);
  border-color: var(--app-line);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-top: 16px;
}

.skill-filter {
  width: 220px;
}

.board-header,
.result-toolbar,
.warehouse-toolbar,
.recommend-toolbar,
.board-row,
.board-header h3 {
  margin: 0;
  font-size: 20px;
}

.board-header p,
.board-note,
.toolbar-sub,
.toolbar-meta,
.job-summary,
.warehouse-summary,
.recommend-reason {
  color: var(--app-muted);
}

.bookmark-btn,
.text-btn,
.short-item,
.cta-item {
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-xs, 8px);
  cursor: pointer;
  transition: 0.2s ease;
}

.board-card {
  position: sticky;
  top: 18px;
}

.board-block + .board-block {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--app-line);
}

.board-label {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--app-muted);
}

.insight-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.insight-item {
  padding: 12px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
}

.insight-item strong {
  display: block;
  font-size: 18px;
}

.insight-item small {
  color: var(--app-muted);
}

.shortlist {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.short-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 10px 12px;
  text-align: left;
}

.short-item span {
  color: var(--app-muted);
  font-size: 12px;
}

.cta-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cta-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  text-align: left;
}

.pipeline-stage-pill,
.pipeline-summary-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.82);
}

.pipeline-stage-pill strong,
.pipeline-summary-item strong {
  display: block;
  font-size: 24px;
}

.pipeline-stage-pill span,
.pipeline-summary-item span {
  color: var(--app-muted);
  font-size: 13px;
}

.pipeline-summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}

@media (max-width: 1180px) {
  .hero,
  .layout-grid,
  .control-top,
  .search-stack,
  .warehouse-item,
  .result-grid,
  .recommend-grid,
  .pipeline-overview {
    grid-template-columns: 1fr;
  }

  .side-column {
    order: -1;
  }

  .board-card {
    position: static;
  }
}

@media (max-width: 768px) {
  .page-shell {
    padding-top: 8px;
  }

  .hero {
    padding: 16px;
  }

  .hero-title-row {
    padding: 16px;
  }

  .hero h2 {
    font-size: 30px;
  }

  .hero-copy {
    min-height: auto;
  }

  .filter-row,
  .board-header,
  .result-toolbar,
  .warehouse-toolbar,
  .recommend-toolbar,
  .rewrite-head,
  .pipeline-toolbar,
  .pipeline-form-row {
    flex-direction: column;
    align-items: stretch;
  }

  .resume-select,
  .city-select,
  .source-select,
  .search-input,
  .mini-input,
  .warehouse-search,
  .skill-filter,
  .pipeline-search,
  .pipeline-stage-select,
  .pipeline-date {
    width: 100%;
  }

  .pipeline-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
