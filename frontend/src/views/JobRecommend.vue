<template>
  <div class="page-shell job-recommend-page">
    <!-- 每日推荐头部 -->
    <div class="panel daily-feed-header">
      <div class="panel-body feed-header-body">
        <div class="feed-header-left">
          <div class="feed-header-icon">
            <el-icon :size="28"><DataAnalysis /></el-icon>
          </div>
          <div>
            <h3>每日岗位推荐</h3>
            <p class="feed-header-sub">
              {{ todayText }} · 基于简历智能匹配
              <span v-if="recommendations.length"
                >，已推荐 <strong>{{ recommendations.length }}</strong> 个岗位</span
              >
            </p>
          </div>
        </div>
        <div class="feed-header-right">
          <el-button @click="loadRecommendations" :loading="loading.recommend" size="small">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
          <el-button type="primary" @click="$router.push('/jobs/pipeline/kanban')" size="small">
            <el-icon><Grid /></el-icon> 查看投递看板
          </el-button>
        </div>
      </div>
    </div>

    <section v-if="selectedResumeId" class="recommendation-brief" aria-label="本轮推荐摘要">
      <div class="brief-current">
        <span class="brief-label">本轮匹配</span>
        <strong>{{ selectedResumeLabel }}</strong>
        <small>岗位建议会随着简历版本和筛选条件变化</small>
      </div>
      <div class="brief-metrics">
        <div>
          <b>{{ recommendations.length }}</b
          ><span>匹配岗位</span>
        </div>
        <div>
          <b>{{ priorityJobCount }}</b
          ><span>优先投递</span>
        </div>
        <div>
          <b>{{ pipelineJobCount }}</b
          ><span>已加入看板</span>
        </div>
      </div>
      <div class="brief-next">
        <span class="brief-label">建议动作</span>
        <p>
          {{
            priorityJobCount
              ? '先处理高匹配岗位，再把有意向的机会加入投递节奏。'
              : '调整筛选条件，或补全简历后重新匹配。'
          }}
        </p>
        <el-button size="small" @click="$router.push('/jobs/pipeline/kanban')"
          >查看投递节奏</el-button
        >
      </div>
    </section>

    <!-- 顶部：选择简历 + 操作 -->
    <div class="panel">
      <div class="panel-body">
        <div class="top-row">
          <div class="resume-selector">
            <span class="label">选择简历：</span>
            <el-select
              v-model="selectedResumeId"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              placeholder="请选择一份简历"
              style="width: 280px"
              filterable
              :loading="loading.resumes"
              @change="loadRecommendations"
            >
              <el-option
                v-for="r in resumeList"
                :key="r.id"
                :label="r.name || r.file_name"
                :value="r.id"
              >
                <span>{{ r.name || r.file_name }}</span>
                <span class="opt-meta">{{ r.parsed?.current_title || '' }}</span>
              </el-option>
            </el-select>
          </div>

          <div class="top-actions">
            <el-button @click="$router.push('/jobs/recommend/evaluation')">
              <el-icon><TrendCharts /></el-icon> 推荐评测
            </el-button>
            <el-button type="primary" @click="seedData" :loading="loading.seed">
              <el-icon><DataAnalysis /></el-icon> 生成模拟岗位
            </el-button>
            <el-upload :show-file-list="false" :before-upload="handleImport" accept=".csv,.json">
              <el-button>
                <el-icon><Upload /></el-icon> 导入 JD
              </el-button>
            </el-upload>
          </div>
        </div>

        <!-- 空状态引导 -->
        <el-empty v-if="!selectedResumeId && !loading.resumes" :image-size="120" class="empty-hint">
          <template #description>
            <span>请先选择一份简历，系统将自动为您匹配推荐岗位</span>
          </template>
          <el-button type="primary" @click="$router.push('/resume-center')"> 去上传简历 </el-button>
        </el-empty>
      </div>
    </div>

    <!-- 反馈统计：拉不到时说明失败并给重试，不能让面板整块消失冒充"没有反馈数据" -->
    <AppLoadError
      v-if="!feedbackStats && feedbackStatsError"
      title="反馈统计加载失败"
      :message="feedbackStatsError"
      @retry="loadFeedbackStats"
    />

    <div class="panel" v-if="feedbackStats">
      <div class="panel-body">
        <div class="stats-row">
          <div class="stats-item">
            <div class="stats-value">{{ feedbackStats.total || 0 }}</div>
            <div class="stats-label">总反馈</div>
          </div>
          <div class="stats-item">
            <div class="stats-value">{{ feedbackStats.like_count || 0 }}</div>
            <div class="stats-label">点赞</div>
          </div>
          <div class="stats-item">
            <div class="stats-value">{{ feedbackStats.dislike_count || 0 }}</div>
            <div class="stats-label">点踩</div>
          </div>
          <div class="stats-item">
            <div class="stats-value">{{ feedbackStats.avg_match_score ?? '-' }}</div>
            <div class="stats-label">平均匹配分</div>
          </div>
          <div class="stats-item">
            <div class="stats-value">{{ percentText(feedbackStats.like_rate || 0) }}</div>
            <div class="stats-label">点赞率</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="hasFeedbackInsights" class="panel insight-card">
      <div class="panel-body">
        <div class="insight-grid">
          <div class="insight-block">
            <div class="insight-title">近 7 天反馈趋势</div>
            <div class="trend-list">
              <div v-for="point in feedbackStats.trend || []" :key="point.date" class="trend-item">
                <div class="trend-head">
                  <span>{{ isoMonthDay(point.date) }}</span>
                  <strong>{{ point.total }}</strong>
                </div>
                <div class="trend-bar">
                  <span class="trend-like" :style="segmentStyle(point.like, point.total)" />
                  <span class="trend-dislike" :style="segmentStyle(point.dislike, point.total)" />
                </div>
                <div class="trend-meta">
                  赞 {{ point.like }} / 踩 {{ point.dislike }}
                  <span v-if="point.avg_match_score !== null"
                    >· 均分 {{ point.avg_match_score }}</span
                  >
                </div>
              </div>
            </div>
          </div>

          <div class="insight-block">
            <div class="insight-title">调优建议</div>
            <div v-if="feedbackStats.tuning_signals?.action_items?.length" class="action-list">
              <div
                v-for="item in feedbackStats.tuning_signals.action_items"
                :key="`${item.type}-${item.title}`"
                class="action-item"
                :class="`action-${item.severity || 'low'}`"
              >
                <div class="action-title">{{ item.title }}</div>
                <div class="action-detail">{{ item.detail }}</div>
              </div>
            </div>
            <el-empty v-else :image-size="72" description="反馈样本较少，暂时没有调优建议" />
          </div>
        </div>

        <div class="insight-grid secondary-grid">
          <div class="insight-block">
            <div class="insight-title">按简历分布</div>
            <div v-if="feedbackStats.by_resume?.length" class="mix-list">
              <div v-for="item in feedbackStats.by_resume" :key="item.resume_id" class="mix-item">
                <div class="mix-head">
                  <span class="mix-name">{{ item.resume_title }}</span>
                  <span class="mix-rate">{{ percentText(item.like_rate || 0) }}</span>
                </div>
                <div class="mix-bar">
                  <span class="mix-like" :style="segmentStyle(item.like, item.total)" />
                  <span class="mix-dislike" :style="segmentStyle(item.dislike, item.total)" />
                </div>
                <div class="mix-meta">
                  {{ item.total }} 条反馈
                  <span v-if="item.avg_match_score !== null"
                    >· 均分 {{ item.avg_match_score }}</span
                  >
                </div>
              </div>
            </div>
            <el-empty v-else :image-size="72" description="暂无简历反馈分布" />
          </div>

          <div class="insight-block">
            <div class="insight-title">按行业分布</div>
            <div v-if="feedbackStats.by_industry?.length" class="mix-list">
              <div v-for="item in feedbackStats.by_industry" :key="item.industry" class="mix-item">
                <div class="mix-head">
                  <span class="mix-name">{{ item.industry }}</span>
                  <span class="mix-rate">{{ percentText(item.like_rate || 0) }}</span>
                </div>
                <div class="mix-bar">
                  <span class="mix-like" :style="segmentStyle(item.like, item.total)" />
                  <span class="mix-dislike" :style="segmentStyle(item.dislike, item.total)" />
                </div>
                <div class="mix-meta">
                  {{ item.total }} 条反馈
                  <span v-if="item.avg_match_score !== null"
                    >· 均分 {{ item.avg_match_score }}</span
                  >
                </div>
              </div>
            </div>
            <el-empty v-else :image-size="72" description="暂无行业反馈分布" />
          </div>
        </div>

        <div v-if="hasAnomalySignals" class="insight-grid secondary-grid">
          <div class="insight-block">
            <div class="insight-title">高分却被点踩</div>
            <div
              v-if="feedbackStats.tuning_signals?.high_score_dislikes?.length"
              class="signal-list"
            >
              <div
                v-for="item in feedbackStats.tuning_signals.high_score_dislikes"
                :key="`high-${item.resume_id}-${item.jd_id}-${item.created_at}`"
                class="signal-item"
              >
                <div class="signal-main">
                  {{ item.jd_title || '未命名岗位' }} · {{ item.jd_company || '未知公司' }}
                </div>
                <div class="signal-sub">{{ item.resume_title }} · {{ item.match_score }} 分</div>
              </div>
            </div>
            <el-empty v-else :image-size="72" description="暂无高分点踩样本" />
          </div>

          <div class="insight-block">
            <div class="insight-title">低分却被点赞</div>
            <div v-if="feedbackStats.tuning_signals?.low_score_likes?.length" class="signal-list">
              <div
                v-for="item in feedbackStats.tuning_signals.low_score_likes"
                :key="`low-${item.resume_id}-${item.jd_id}-${item.created_at}`"
                class="signal-item"
              >
                <div class="signal-main">
                  {{ item.jd_title || '未命名岗位' }} · {{ item.jd_company || '未知公司' }}
                </div>
                <div class="signal-sub">{{ item.resume_title }} · {{ item.match_score }} 分</div>
              </div>
            </div>
            <el-empty v-else :image-size="72" description="暂无低分点赞样本" />
          </div>
        </div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div v-if="hasResults" class="panel">
      <div class="panel-body">
        <div class="filter-row">
          <el-input
            v-model="filters.location"
            placeholder="地点筛选"
            clearable
            style="width: 140px"
            size="small"
            @change="loadRecommendations"
          >
            <template #prefix
              ><el-icon><Location /></el-icon
            ></template>
          </el-input>

          <el-select
            v-model="filters.industry"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            placeholder="行业"
            clearable
            style="width: 160px"
            size="small"
            @change="loadRecommendations"
          >
            <el-option label="互联网" value="internet" />
            <el-option label="AI" value="ai" />
            <el-option label="电商" value="e-commerce" />
            <el-option label="云计算" value="cloud" />
            <el-option label="数据" value="data" />
          </el-select>

          <el-select
            v-model="filters.exp_level"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            placeholder="经验要求"
            clearable
            style="width: 130px"
            size="small"
            @change="loadRecommendations"
          >
            <el-option label="初级 (1-3年)" value="junior" />
            <el-option label="中级 (3-5年)" value="mid" />
            <el-option label="高级 (5年+)" value="senior" />
          </el-select>

          <div class="salary-filter">
            <span class="filter-label">最低薪资：</span>
            <el-slider
              v-model="filters.salary_min"
              :min="0"
              :max="100"
              :step="5"
              style="width: 160px"
              @change="loadRecommendations"
            />
            <span class="salary-val">{{ filters.salary_min || 0 }}k</span>
          </div>

          <el-button size="small" text @click="resetFilters">重置</el-button>
        </div>
      </div>
    </div>

    <!-- 推荐结果 -->
    <div v-if="loading.recommend" class="loading-state">
      <el-icon class="is-loading" size="28"><Loading /></el-icon>
      <p>正在分析您的简历，智能匹配岗位...</p>
    </div>

    <template v-else-if="hasResults">
      <div class="result-summary">
        <span class="summary-text">
          为您推荐 <strong>{{ recommendations.length }}</strong> 个岗位
          <span v-if="appliedFilters" class="summary-filters">（已应用筛选条件）</span>
        </span>
        <el-button size="small" text @click="openSuppressedDialog">已忽略的岗位</el-button>
      </div>

      <div class="card-grid">
        <div v-for="job in recommendations" :key="job.jd_id" class="panel job-card">
          <div class="panel-body">
            <!-- 匹配度徽标 -->
            <div class="score-badge" :class="scoreToneFillClass(job.match_score)">
              <span class="score-num">{{ job.match_score }}</span>
              <span class="score-unit">分</span>
            </div>

            <div class="card-body">
              <!-- 头部 -->
              <div class="card-header">
                <div class="job-title-row">
                  <h3 class="job-title">{{ job.job_title }}</h3>
                  <el-tag v-if="job._applied" size="small" type="success" effect="dark"
                    >已投递</el-tag
                  >
                  <el-tag v-if="job._bookmarked" size="small" type="warning" effect="plain"
                    >已收藏</el-tag
                  >
                  <el-tag
                    v-if="!job._applied && job.match_score >= 80"
                    size="small"
                    type="danger"
                    effect="dark"
                    >优先投递</el-tag
                  >
                  <el-tag v-if="job.source" size="small" effect="plain" class="source-tag">{{
                    sourceText(job.source)
                  }}</el-tag>
                  <el-tag
                    size="small"
                    :type="recommendTagType(job.recommendation_type)"
                    effect="dark"
                    >{{ job.recommendation_type }}</el-tag
                  >
                  <el-button
                    size="small"
                    text
                    class="dismiss-btn"
                    title="不再推荐该岗位，可在「已忽略」中恢复"
                    @click="dismissJob(job)"
                  >
                    <el-icon><CircleClose /></el-icon> 不感兴趣
                  </el-button>
                </div>
                <div class="job-company">
                  <el-icon><OfficeBuilding /></el-icon>
                  {{ job.company }}
                </div>
              </div>

              <!-- 匹配原因 -->
              <p class="match-reason">{{ job.match_reason }}</p>

              <!-- 技能标签 -->
              <div class="skill-section">
                <div v-if="job.skill_overlap?.length" class="skill-group">
                  <span class="skill-label overlap-label">重合</span>
                  <el-tag
                    v-for="s in job.skill_overlap"
                    :key="s"
                    size="small"
                    type="success"
                    effect="plain"
                    >{{ s }}</el-tag
                  >
                </div>
                <div v-if="job.skill_gap?.length" class="skill-group">
                  <span class="skill-label gap-label">缺失</span>
                  <el-tag
                    v-for="s in job.skill_gap"
                    :key="s"
                    size="small"
                    type="danger"
                    effect="plain"
                    >{{ s }}</el-tag
                  >
                </div>
              </div>

              <!-- 匹配详情 -->
              <div class="match-details">
                <span
                  v-if="job.salary_match !== undefined"
                  class="detail-tag"
                  :class="job.salary_match ? 'dt-ok' : 'dt-no'"
                >
                  <el-icon><Money /></el-icon> 薪资{{ job.salary_match ? '匹配' : '不匹配' }}
                </span>
                <span
                  v-if="job.location_match !== undefined"
                  class="detail-tag"
                  :class="job.location_match ? 'dt-ok' : 'dt-no'"
                >
                  <el-icon><Location /></el-icon> 地点{{ job.location_match ? '匹配' : '不匹配' }}
                </span>
                <span
                  v-if="job.experience_match !== undefined"
                  class="detail-tag"
                  :class="job.experience_match !== false ? 'dt-ok' : 'dt-no'"
                >
                  <el-icon><Timer /></el-icon> 经验{{
                    job.experience_match !== false ? '匹配' : '不匹配'
                  }}
                </span>
              </div>

              <!-- 操作 -->
              <div class="card-actions">
                <el-button size="small" @click="viewDetail(job.jd_id)"> 查看详情 </el-button>
                <el-button
                  size="small"
                  type="primary"
                  :loading="analyzingId === job.jd_id"
                  @click="analyzeJob(job.jd_id)"
                >
                  立即分析
                </el-button>
                <el-button size="small" @click="addToKanban(job)">
                  <el-icon><Grid /></el-icon> 加入看板
                </el-button>
                <el-button size="small" @click="generateInterviewPrep(job)">
                  <el-icon><Microphone /></el-icon> 面试准备
                </el-button>
                <el-button
                  size="small"
                  :type="job._bookmarked ? 'warning' : ''"
                  @click="toggleBookmark(job)"
                >
                  <el-icon><Star /></el-icon> {{ job._bookmarked ? '已收藏' : '收藏' }}
                </el-button>
                <div class="feedback-btns">
                  <el-button
                    text
                    :type="job._feedback === 'like' ? 'success' : ''"
                    :icon="job._feedback === 'like' ? 'ThumbsUp' : 'ThumbsUp'"
                    @click="toggleFeedback(job, 'like')"
                  />
                  <el-button
                    text
                    :type="job._feedback === 'dislike' ? 'danger' : ''"
                    :icon="job._feedback === 'dislike' ? 'ThumbsDown' : 'ThumbsDown'"
                    @click="toggleFeedback(job, 'dislike')"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 无结果 -->
    <!-- 失败态：和"没有推荐"分开，并且给出重试 -->
    <AppLoadError
      v-else-if="recommendError && !recommendations.length"
      title="推荐加载失败"
      :message="recommendError"
      @retry="loadRecommendations"
    />

    <el-empty v-else-if="!loading.recommend && selectedResumeId" :image-size="120">
      <template #description>
        <span v-if="appliedFilters"
          >没有找到符合条件的岗位，试试调整筛选条件；标记过不感兴趣的岗位也会在这里被排除</span
        >
        <span v-else
          >暂无匹配的岗位推荐，请完善简历信息或导入更多岗位数据；已隐藏的岗位可在下方找回</span
        >
      </template>
      <el-button v-if="appliedFilters" @click="resetFilters">清除筛选</el-button>
      <el-button v-else type="primary" @click="seedData">生成模拟岗位</el-button>
      <el-button @click="openSuppressedDialog">查看已忽略的岗位</el-button>
    </el-empty>

    <!-- 已忽略岗位：隐藏必须可逆，否则一次误点就永久减少推荐 -->
    <el-dialog v-model="suppressed.dialog" title="已忽略的岗位" width="640px">
      <div v-if="suppressed.loading" class="suppressed-loading">
        <el-icon class="is-loading"><Loading /></el-icon> 加载中…
      </div>
      <template v-else>
        <el-table v-if="suppressed.items.length" :data="suppressed.items" size="small">
          <el-table-column label="岗位">
            <template #default="{ row }">
              <div class="suppressed-title">{{ row.job_title || '未命名岗位' }}</div>
              <div class="suppressed-sub">{{ row.company }} · {{ row.location || '地点不限' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="隐藏原因" width="150">
            <template #default="{ row }">
              <span class="suppressed-reason">{{ reasonText(row.reasons) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="right">
            <template #default="{ row }">
              <el-button
                size="small"
                text
                :loading="suppressed.submittingId === row.jd_id"
                @click="restoreSuppressed(row)"
                >恢复</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else :image-size="80" description="没有已忽略的岗位" />
        <p v-if="suppressed.orphaned > 0" class="suppressed-note">
          另有 {{ suppressed.orphaned }} 条记录对应的岗位已下架，无法恢复。
        </p>
        <p v-if="suppressed.truncated > 0" class="suppressed-note">
          还有 {{ suppressed.truncated }} 个隐藏岗位未在此列出（单次最多展示
          {{ suppressedMax }} 条）。
        </p>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getResumeList } from '@/api/resume'
import {
  getJobRecommendations,
  getJobFeedbackStats,
  seedMockJobs,
  batchImportJobs,
  submitJobFeedback,
  startFullAnalysis,
  getJobPipelineList,
  getJobBookmarks,
  getSuppressedJobs,
  restoreSuppressedJob,
  bookmarkJob,
  unbookmarkJob,
} from '@/api/jobs'
import { ElMessage } from '@/plugins/element-services'
import {
  DataAnalysis,
  Upload,
  Location,
  Money,
  Timer,
  TrendCharts,
  Grid,
  Microphone,
  Star,
  Refresh,
  CircleClose,
  Loading,
} from '@element-plus/icons-vue'
import { OfficeBuilding } from '@element-plus/icons-vue'
import { createJobPipelineEntry } from '@/api/targets'
import { scoreToneFillClass } from '@/utils/scoreTone'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import { isoMonthDay } from '@/utils/format/date'
import { useLatestCall } from '@/composables/useLatestCall'

const router = useRouter()
const route = useRoute()
const selectedResumeId = ref(null)
const resumeList = ref([])
const recommendations = ref([])
const latestCall = useLatestCall()
// 统计与推荐列表各自一把令牌：点一下喜欢会重发统计，但不会重发列表，共用一把会让两件事互相作废。
const latestStatsCall = useLatestCall()
// 失败与"没有推荐"必须是两个状态：GET 失败不弹提示（request.js 只对非 GET 通知），
// 若只清空列表，页面会对候选人说"请完善简历信息"，而实际是服务端错了。
const recommendError = ref('')
const analyzingId = ref(null)
const feedbackStats = ref(null)
const feedbackStatsError = ref('')

// 被隐藏岗位的恢复面板：隐藏是双向操作，没有它"不感兴趣"就是单向陷阱
const suppressed = reactive({
  dialog: false,
  loading: false,
  submittingId: null,
  items: [],
  total: 0,
  orphaned: 0,
  truncated: 0,
})
const suppressedMax = 200

const loading = reactive({
  resumes: false,
  recommend: false,
  seed: false,
})

const filters = reactive({
  location: '',
  industry: '',
  exp_level: '',
  salary_min: null,
})

const appliedFilters = computed(
  () => filters.location || filters.industry || filters.exp_level || filters.salary_min !== null
)

const hasResults = computed(() => recommendations.value.length > 0)
const hasFeedbackInsights = computed(() => (feedbackStats.value?.total || 0) > 0)
const hasAnomalySignals = computed(() => {
  const signals = feedbackStats.value?.tuning_signals
  return Boolean(signals?.high_score_dislikes?.length || signals?.low_score_likes?.length)
})
const selectedResumeLabel = computed(() => {
  const resume = resumeList.value.find((item) => item.id === selectedResumeId.value)
  return resume?.name || resume?.file_name || '已选简历'
})
const priorityJobCount = computed(
  () =>
    recommendations.value.filter((job) => Number(job.match_score || 0) >= 80 && !job._applied)
      .length
)
const pipelineJobCount = computed(() => recommendations.value.filter((job) => job._applied).length)

// === 每日推荐 ===
const todayText = computed(() => {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  return `${y}.${m}.${day} ${weekdays[d.getDay()]}`
})

// === 生命周期 ===
onMounted(async () => {
  await fetchResumes()
  loadFeedbackStats()
  if (route.query.resume_id) {
    const rid = Number(route.query.resume_id)
    if (!isNaN(rid)) {
      selectedResumeId.value = rid
      loadRecommendations()
    }
  }
})

// === 数据加载 ===
async function fetchResumes() {
  loading.resumes = true
  try {
    const data = await getResumeList()
    resumeList.value = data?.items || (Array.isArray(data) ? data : [])
  } catch (e) {
    console.error('获取简历列表失败:', e)
  } finally {
    loading.resumes = false
  }
}

async function loadRecommendations() {
  // 一轮推荐是三个串联请求（列表 → 投递状态 → 收藏状态），换简历/改筛选都会重发；
  // 不守序号的话，旧那一轮的回填会把它自己的投递/收藏标记打到新简历的卡片上。
  const isCurrent = latestCall()
  recommendError.value = ''
  if (!selectedResumeId.value) return
  loading.recommend = true
  try {
    const params = { resume_id: selectedResumeId.value, limit: 10 }
    if (filters.location) params.location = filters.location
    if (filters.industry) params.industry = filters.industry
    if (filters.exp_level) params.exp_level = filters.exp_level
    if (filters.salary_min !== null) params.salary_min = filters.salary_min

    const data = await getJobRecommendations(params)
    if (!isCurrent()) return
    recommendations.value = (data?.recommendations || []).map((j) => ({
      ...j,
      _feedback: null,
      _applied: false,
      _bookmarked: false,
    }))
    // Check which jobs are already in pipeline
    try {
      const pipeline = await getJobPipelineList({ limit: 200 })
      if (!isCurrent()) return
      const applied = (pipeline?.items || pipeline || []).map((p) => p.jd_id).filter(Boolean)
      recommendations.value.forEach((j) => {
        if (applied.includes(j.jd_id)) j._applied = true
      })
    } catch {
      // 投递状态加载失败时，推荐列表仍可继续浏览。
    }
    // 收藏状态由后端持久化，不回填的话刷新后卡片会显示"未收藏"的假状态
    if (!isCurrent()) return
    try {
      const bookmarks = await getJobBookmarks()
      if (!isCurrent()) return
      const saved = (bookmarks?.items || []).map((b) => b.jd_id).filter(Boolean)
      recommendations.value.forEach((j) => {
        j._bookmarked = saved.includes(j.jd_id)
      })
    } catch {
      // 同上：拿不到就保持 false，不假装已收藏。
    }
  } catch (e) {
    if (!isCurrent()) return
    console.error('获取推荐失败:', e)
    recommendations.value = []
    recommendError.value = e?.userMessage || e?.message || '推荐加载失败，请稍后重试'
  } finally {
    if (isCurrent()) loading.recommend = false
  }
}

async function loadFeedbackStats() {
  // 每次点喜欢/不喜欢都会重发统计；不守序号的话，先发起的那次后回来会把计数退回点之前。
  const isCurrent = latestStatsCall()
  feedbackStatsError.value = ''
  try {
    const data = await getJobFeedbackStats()
    if (!isCurrent()) return
    feedbackStats.value = data
  } catch (e) {
    if (!isCurrent()) return
    feedbackStats.value = null
    // GET 失败不弹提示，所以"面板消失"曾是它唯一的对外表现——那等于说"你没有反馈数据"。
    feedbackStatsError.value = e?.userMessage || e?.message || '反馈统计加载失败，请稍后重试'
  }
}

// === 操作 ===
async function seedData() {
  loading.seed = true
  try {
    const data = await seedMockJobs()
    ElMessage.success(data?.message || `模拟岗位数据写入成功`)
    if (selectedResumeId.value) {
      await loadRecommendations()
    }
  } catch (e) {
    ElMessage.error('生成失败: ' + (e.message || e))
  } finally {
    loading.seed = false
  }
}

async function handleImport(file) {
  try {
    const data = await batchImportJobs(file)
    ElMessage.success(data?.message || '导入成功')
    if (selectedResumeId.value) {
      await loadRecommendations()
    }
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.message || e))
  }
  return false // 阻止默认上传
}

async function analyzeJob(jdId) {
  if (!selectedResumeId.value) return
  analyzingId.value = jdId
  try {
    const data = await startFullAnalysis(selectedResumeId.value, jdId)
    ElMessage.success('分析已启动')
    if (data?.task_id) {
      router.push({ name: 'task-center', query: { task_id: String(data.task_id) } })
      return
    }
    router.push('/smart-analysis')
  } catch (e) {
    ElMessage.error('分析启动失败: ' + (e.message || e))
  } finally {
    analyzingId.value = null
  }
}

function generateInterviewPrep(job) {
  router.push({
    path: '/interview/setup',
    query: { jd_id: String(job.jd_id) },
  })
}

async function toggleBookmark(job) {
  // 同步后端：收藏/取消收藏落库，避免只改本地状态、刷新后丢失
  const next = !job._bookmarked
  const jdId = job.jd_id || job.id
  try {
    if (next) {
      await bookmarkJob(jdId, 'bookmark')
    } else {
      await unbookmarkJob(jdId)
    }
    job._bookmarked = next
    ElMessage.success(next ? '已收藏' : '已取消收藏')
  } catch (e) {
    ElMessage.error('收藏操作失败: ' + (e.userMessage || e.message || e))
  }
}

// 隐藏 = 写 JobBookmark(action='dismiss')，推荐引擎会在 SQL 层排除，不再只是记一笔
async function dismissJob(job) {
  const jdId = job.jd_id || job.id
  try {
    await bookmarkJob(jdId, 'dismiss')
    const idx = recommendations.value.indexOf(job)
    if (idx >= 0) recommendations.value.splice(idx, 1)
    ElMessage.success('已标记不感兴趣，可在「已忽略」中恢复')
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.userMessage || e.message || e))
  }
}

function openSuppressedDialog() {
  suppressed.dialog = true
  loadSuppressed()
}

async function loadSuppressed() {
  suppressed.loading = true
  try {
    const data = await getSuppressedJobs()
    suppressed.items = data?.items || []
    suppressed.total = Number(data?.total ?? suppressed.items.length)
    suppressed.orphaned = Number(data?.orphaned ?? 0)
    suppressed.truncated = Number(data?.truncated ?? 0)
  } catch (e) {
    suppressed.items = []
    suppressed.total = 0
    suppressed.orphaned = 0
    suppressed.truncated = 0
    ElMessage.error('获取已忽略岗位失败: ' + (e.userMessage || e.message || e))
  } finally {
    suppressed.loading = false
  }
}

async function restoreSuppressed(item) {
  suppressed.submittingId = item.jd_id
  try {
    await restoreSuppressedJob(item.jd_id)
    ElMessage.success(`已恢复「${item.job_title || '该岗位'}」`)
    await loadSuppressed()
    await loadRecommendations()
  } catch (e) {
    ElMessage.error('恢复失败: ' + (e.userMessage || e.message || e))
  } finally {
    suppressed.submittingId = null
  }
}

function reasonText(reasons) {
  const labels = (reasons || []).map((r) => (r === 'dislike' ? '点踩过' : '标记不感兴趣'))
  return labels.join(' · ') || '已被隐藏'
}

async function addToKanban(job) {
  try {
    await createJobPipelineEntry({
      title: job.job_title || '',
      company: job.company || '',
      jd_id: job.jd_id,
      salary_range: job.salary_range || '',
      stage: 'todo',
      source: job.source || 'recommend',
    })
    job._applied = true
    ElMessage.success('已加入投递看板')
  } catch {
    ElMessage.error('加入看板失败')
  }
}

async function toggleFeedback(job, type) {
  if (job._feedback === type) {
    ElMessage.info('该反馈已记录，如需恢复推荐请到「已忽略」中查看')
    return
  }
  try {
    await submitJobFeedback(selectedResumeId.value, job.jd_id, type, job.match_score)
    job._feedback = type
    if (type === 'dislike') {
      // 点踩同样是隐藏信号，引擎会把它排除在下次推荐之外——卡片不能继续留在列表里
      const idx = recommendations.value.indexOf(job)
      if (idx >= 0) recommendations.value.splice(idx, 1)
      ElMessage.success('已点踩，该岗位不再出现在推荐中')
    } else {
      ElMessage.success('已点赞')
    }
    await loadFeedbackStats()
  } catch {
    ElMessage.error('反馈提交失败')
  }
}

function viewDetail(jdId) {
  router.push({
    path: '/jobs/search',
    query: {
      tab: 'recommend',
      job_id: String(jdId),
      resume_id: selectedResumeId.value ? String(selectedResumeId.value) : undefined,
    },
  })
}

function resetFilters() {
  filters.location = ''
  filters.industry = ''
  filters.exp_level = ''
  filters.salary_min = null
  nextTick(() => loadRecommendations())
}

// === 样式工具 ===

function recommendTagType(type) {
  if (type?.includes('高度推荐')) return 'success'
  if (type?.includes('值得一试')) return 'warning'
  return 'info'
}

function sourceText(value) {
  const sourceMap = {
    imported: '导入',
    api: '接口',
    manual: '手工',
    crawled: '抓取',
    local: '本地',
    recommend: '推荐',
    boss: 'BOSS',
    _mock: '演示',
  }
  return sourceMap[value] || value || '未知'
}

function percentText(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function segmentStyle(value, total) {
  const safeTotal = Number(total) || 0
  const width = safeTotal > 0 ? Math.max(((Number(value) || 0) / safeTotal) * 100, 0) : 0
  return { width: `${width}%` }
}
</script>

<style scoped>
.page-shell {
  width: 100%;
  padding: 18px 0 32px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* 每日推荐头部 */
.daily-feed-header {
  background: var(--app-surface-strong);
  border-color: var(--app-line);
  border-top: 3px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
}

.feed-header-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.feed-header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.feed-header-icon {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  background: var(--app-primary-light);
  color: var(--app-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.feed-header-body h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--app-text);
}

.feed-header-sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--app-muted);
}

.feed-header-right {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

@media (max-width: 960px) {
  .recommendation-brief {
    grid-template-columns: 1fr 1fr;
  }

  .brief-next {
    grid-column: 1 / -1;
    padding-top: 14px;
    border-top: 1px solid var(--app-line);
  }
}

@media (max-width: 640px) {
  .recommendation-brief,
  .brief-metrics {
    grid-template-columns: 1fr;
  }

  .brief-metrics {
    gap: 8px;
    border: 0;
  }

  .brief-metrics div,
  .brief-metrics div + div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
    text-align: left;
  }
}

.recommendation-brief {
  display: grid;
  grid-template-columns: minmax(190px, 1fr) minmax(270px, 1fr) minmax(250px, 1.2fr);
  gap: 20px;
  align-items: center;
  padding: 18px 20px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.brief-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.brief-current strong {
  display: block;
  margin-top: 6px;
  overflow: hidden;
  color: var(--app-text);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brief-current small,
.brief-next p {
  display: block;
  margin: 6px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}

.brief-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-right: 1px solid var(--app-line);
  border-left: 1px solid var(--app-line);
}

.brief-metrics div {
  display: grid;
  gap: 4px;
  padding: 2px 13px;
  text-align: center;
}

.brief-metrics div + div {
  border-left: 1px solid var(--app-line);
}

.brief-metrics b {
  color: var(--app-primary-dark);
  font-size: 23px;
  line-height: 1;
}

.brief-metrics span {
  color: var(--app-muted);
  font-size: 12px;
}

.brief-next {
  display: grid;
  justify-items: start;
}

.brief-next .el-button {
  margin-top: 10px;
}

/* 顶部 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}
.stats-item {
  padding: 12px 14px;
  border-radius: var(--app-radius-xs, 6px);
  background: var(--app-bg);
}
.stats-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text);
}
.stats-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-muted);
}
.insight-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}
.secondary-grid {
  margin-top: 16px;
  grid-template-columns: 1fr 1fr;
}
.insight-block {
  padding: 16px;
  border-radius: var(--app-radius-xs, 6px);
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
}
.insight-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--app-text);
  margin-bottom: 12px;
}
.trend-list,
.mix-list,
.signal-list,
.action-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.trend-item,
.mix-item,
.signal-item,
.action-item {
  padding: 12px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
}
.trend-head,
.mix-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--app-text);
}
.trend-bar,
.mix-bar {
  display: flex;
  width: 100%;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf2ee;
}
.trend-like,
.mix-like {
  display: block;
  background: linear-gradient(90deg, #2ea866, #5ec388);
}
.trend-dislike,
.mix-dislike {
  display: block;
  background: linear-gradient(90deg, #df8d72, #d96a6a);
}
.trend-meta,
.mix-meta,
.signal-sub,
.action-detail {
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-muted);
}
.mix-name,
.signal-main,
.action-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}
.mix-rate {
  color: var(--app-primary);
  font-weight: 700;
}
.action-high {
  border-color: rgba(223, 106, 106, 0.22);
  background: #fff7f5;
}
.action-medium {
  border-color: rgba(220, 156, 63, 0.2);
  background: #fffaf1;
}
.action-low {
  border-color: rgba(94, 195, 136, 0.2);
  background: #f5fbf7;
}
.top-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.resume-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}
.label {
  font-weight: 700;
  color: var(--app-text);
  white-space: nowrap;
}
.opt-meta {
  float: right;
  color: var(--app-muted);
  font-size: 12px;
  margin-left: 12px;
}
.top-actions {
  display: flex;
  gap: 8px;
}
.empty-hint {
  padding: 24px 0 8px;
}

/* 筛选栏 */
.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.salary-filter {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-label {
  font-size: 12px;
  color: var(--app-muted);
  white-space: nowrap;
}
.salary-val {
  font-size: 12px;
  color: var(--app-primary-dark, #1c8c5e);
  font-weight: 700;
  min-width: 30px;
}

/* 结果 */
.result-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 14px;
  color: var(--app-text);
}
.summary-filters {
  font-size: 12px;
  color: var(--app-muted);
}
.dismiss-btn {
  margin-left: auto;
  color: var(--app-muted);
}
.dismiss-btn:hover {
  color: var(--app-danger);
}
.suppressed-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--app-muted);
}
.suppressed-title {
  font-size: 14px;
  color: var(--app-text);
}
.suppressed-sub {
  font-size: 12px;
  color: var(--app-muted);
}
.suppressed-reason {
  font-size: 12px;
  color: var(--app-muted);
}
.suppressed-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--app-muted);
}

/* 卡片网格 */
.card-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.job-card {
  position: relative;
  overflow: hidden;
}

/* 匹配度徽标 */
.score-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #fff;
  z-index: 1;
}
.score-num {
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}
.score-unit {
  font-size: 10px;
  opacity: 0.9;
}

/* 卡片内容 */
.card-body {
  padding-right: 10px;
}

.job-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}
.job-title {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
  color: var(--app-text);
}
.job-company {
  font-size: 13px;
  color: var(--app-muted);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.source-tag {
  border-color: var(--app-line);
  color: var(--app-primary);
}

.match-reason {
  font-size: 13px;
  color: var(--app-muted);
  line-height: 1.5;
  margin: 8px 0;
}

/* 技能标签 */
.skill-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 10px 0;
}
.skill-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.skill-label {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  color: #fff;
  margin-right: 4px;
}
.overlap-label {
  background: #2ea866;
}
.gap-label {
  background: #d46e6e;
}

/* 匹配详情 */
.match-details {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}
.detail-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 2px;
}
.dt-ok {
  background: #eff8f1;
  color: #2ea866;
}
.dt-no {
  background: #fff3f0;
  color: #d46e6e;
}

/* 操作 */
.card-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--app-line);
}
.feedback-btns {
  display: flex;
  gap: 2px;
}

@media (max-width: 768px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
  .top-row {
    flex-direction: column;
    align-items: stretch;
  }
  .stats-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .insight-grid,
  .secondary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
