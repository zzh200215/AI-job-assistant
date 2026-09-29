<template>
  <div class="page-shell">
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
              <div class="result-toolbar">
                <div>
                  <strong>{{ filteredExternalJobs.length }}</strong>
                  <span class="toolbar-sub">个岗位</span>
                  <span v-if="savedCount" class="toolbar-meta">其中 {{ savedCount }} 个已落库</span>
                </div>
                <div class="toolbar-actions">
                  <el-button
                    size="small"
                    plain
                    :disabled="compareSelection.length < 2"
                    @click="openComparePanel"
                  >
                    对比 {{ compareSelection.length }} 个岗位
                  </el-button>
                  <el-tag v-if="resultMode && !isDemo" type="info" effect="plain">{{
                    searchStateText
                  }}</el-tag>
                  <el-tag v-if="isDemo" type="warning" effect="plain">当前为演示数据</el-tag>
                  <el-tag v-if="searchError && !isDemo" type="danger" effect="plain">{{
                    searchError
                  }}</el-tag>
                </div>
              </div>

              <div v-if="hasSearched" class="result-source-note" :class="sourceBannerClass">
                <strong>{{ sourceBannerTitle }}</strong>
                <span>{{ sourceBannerDesc }}</span>
              </div>

              <div v-if="searching" class="state-box">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>{{ searchHint }}</span>
              </div>

              <div v-else-if="filteredExternalJobs.length" class="result-grid">
                <article v-for="job in filteredExternalJobs" :key="job.uid" class="job-shell">
                  <div class="job-shell-top">
                    <div>
                      <div class="job-title-row">
                        <h3>{{ job.title }}</h3>
                        <span class="source-pill">{{ sourceText(job.source) }}</span>
                        <span v-if="job.local" class="local-pill">已落库</span>
                      </div>
                      <p class="job-company">
                        <el-icon><OfficeBuilding /></el-icon>
                        {{ job.company }}
                      </p>
                    </div>
                    <button type="button" class="bookmark-btn" @click="toggleShortlist(job)">
                      {{ isShortlisted(job) ? '移出清单' : '加入清单' }}
                    </button>
                  </div>

                  <div class="job-facts">
                    <span class="fact-emphasis">{{ job.salary }}</span>
                    <span>{{ job.location || '地点待补充' }}</span>
                    <span>{{ job.experience || '经验不限' }}</span>
                    <span>{{ job.education || '学历不限' }}</span>
                  </div>

                  <div class="priority-row">
                    <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
                      {{ job.priorityLabel }} · {{ job.priorityScore }}
                    </el-tag>
                    <span class="priority-reason">{{ job.priorityReason }}</span>
                  </div>

                  <div class="job-tags" v-if="job.skillTags.length">
                    <el-tag
                      v-for="tag in job.skillTags.slice(0, 8)"
                      :key="tag"
                      size="small"
                      effect="plain"
                    >
                      {{ tag }}
                    </el-tag>
                  </div>

                  <p class="job-summary">{{ job.summary || '暂无职位摘要' }}</p>

                  <div class="job-actions">
                    <el-button size="small" @click="openJobDetail(job, 'search')"
                      >查看详情</el-button
                    >
                    <el-button size="small" @click="handlePipelineAction(job)">
                      {{ pipelineStatusText(job) || '加入流程' }}
                    </el-button>
                    <el-button size="small" @click="toggleCompare(job)">
                      {{ isCompared(job) ? '取消对比' : '加入对比' }}
                    </el-button>
                    <el-button size="small" @click="prefillAnalysis(job)">带入分析</el-button>
                    <el-button size="small" type="primary" @click="startAnalysisForJob(job)">
                      直接分析
                    </el-button>
                  </div>
                </article>
              </div>

              <el-empty
                v-else-if="hasSearched"
                description="没有找到更贴近的岗位，换个关键词或城市试试。"
              />
              <el-empty v-else description="先发起一次搜索，系统会把结果同步到你的岗位工作台。" />
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
              <div class="recommend-toolbar">
                <div class="recommend-left">
                  <span class="toolbar-title">以当前简历为中心的岗位匹配</span>
                  <span class="toolbar-sub" v-if="selectedResumeName">{{
                    selectedResumeName
                  }}</span>
                </div>
                <div class="recommend-actions">
                  <el-input
                    v-model="recommendFilters.location"
                    clearable
                    size="small"
                    placeholder="地点偏好"
                    class="mini-input"
                  />
                  <el-input
                    v-model="recommendFilters.industry"
                    clearable
                    size="small"
                    placeholder="行业偏好"
                    class="mini-input"
                  />
                  <el-button
                    size="small"
                    type="primary"
                    @click="loadRecommendations"
                    :disabled="!selectedResumeId"
                  >
                    更新推荐
                  </el-button>
                </div>
              </div>

              <div v-if="recommendLoading" class="state-box">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在根据简历生成匹配结果...</span>
              </div>

              <AppLoadError
                v-else-if="recommendError"
                title="推荐结果拉取失败"
                :message="recommendError"
                @retry="loadRecommendations"
              />

              <div v-else-if="normalizedRecommendations.length" class="recommend-grid">
                <article
                  v-for="job in normalizedRecommendations"
                  :key="job.uid"
                  class="recommend-card"
                >
                  <div class="recommend-score">
                    <strong>{{ job.matchScore }}</strong>
                    <span>匹配分</span>
                  </div>
                  <div class="recommend-body">
                    <div class="job-title-row">
                      <h3>{{ job.title }}</h3>
                      <el-tag
                        :type="recommendTagType(job.recommendationType)"
                        effect="dark"
                        size="small"
                      >
                        {{ job.recommendationType }}
                      </el-tag>
                    </div>

                    <p class="job-company">
                      <el-icon><OfficeBuilding /></el-icon>
                      {{ job.company }} / {{ job.location || '地点待补充' }}
                    </p>

                    <div class="job-facts compact">
                      <span class="fact-emphasis">{{ job.salary }}</span>
                      <span>{{ job.industry || '行业待补充' }}</span>
                    </div>

                    <div class="priority-row compact">
                      <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
                        {{ job.priorityLabel }} / {{ job.priorityScore }}
                      </el-tag>
                      <span class="priority-reason">{{ job.priorityReason }}</span>
                    </div>

                    <p class="recommend-reason">{{ job.matchReason }}</p>

                    <div class="recommend-tags">
                      <div v-if="job.skillOverlap.length" class="tag-group">
                        <span class="tag-label ok">重合</span>
                        <el-tag
                          v-for="tag in job.skillOverlap.slice(0, 6)"
                          :key="tag"
                          size="small"
                          type="success"
                          effect="plain"
                        >
                          {{ tag }}
                        </el-tag>
                      </div>
                      <div v-if="job.skillGap.length" class="tag-group">
                        <span class="tag-label gap">缺口</span>
                        <el-tag
                          v-for="tag in job.skillGap.slice(0, 6)"
                          :key="tag"
                          size="small"
                          type="danger"
                          effect="plain"
                        >
                          {{ tag }}
                        </el-tag>
                      </div>
                    </div>

                    <div class="recommend-signals">
                      <span :class="signalClass(job.salaryMatch)"
                        >薪资{{ job.salaryMatch ? '匹配' : '待评估' }}</span
                      >
                      <span :class="signalClass(job.locationMatch)"
                        >地点{{ job.locationMatch ? '匹配' : '待协商' }}</span
                      >
                      <span :class="signalClass(job.experienceMatch)"
                        >经验{{ job.experienceMatch ? '合适' : '有偏差' }}</span
                      >
                    </div>

                    <div class="job-actions">
                      <el-button size="small" @click="openJobDetail(job, 'recommend')"
                        >查看详情</el-button
                      >
                      <el-button size="small" @click="handlePipelineAction(job)">
                        {{ pipelineStatusText(job) || '加入流程' }}
                      </el-button>
                      <el-button size="small" @click="toggleCompare(job)">
                        {{ isCompared(job) ? '取消对比' : '加入对比' }}
                      </el-button>
                      <el-button size="small" @click="toggleShortlist(job)">
                        {{ isShortlisted(job) ? '已在清单' : '加入清单' }}
                      </el-button>
                      <el-button size="small" type="primary" @click="startAnalysisForJob(job)"
                        >直接分析</el-button
                      >
                    </div>
                  </div>
                </article>
              </div>

              <el-empty
                v-else
                :description="
                  selectedResumeId
                    ? '还没有足够贴合的推荐结果，可以先补充岗位池。'
                    : '先选择一份简历，再获取推荐岗位。'
                "
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
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import {
  ArrowRight,
  Loading,
  OfficeBuilding,
  Promotion,
  RefreshRight,
  Search,
} from '@element-plus/icons-vue'
import { getResume, getResumeList } from '@/api/resume'
import { explainMatch } from '@/api/analysis'
import { queryRewriteTest } from '@/api/knowledge'
import { getJobDetail, seedDemoJobs, startFullAnalysis } from '@/api/jobs'
import { priorityTagType } from '@/utils/statusTone'
import { rememberResume } from '@/utils/lastSelection'
import { useLatestCall } from '@/composables/useLatestCall'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import JobCompareDialog from '@/features/jobs/components/JobCompareDialog.vue'
import JobDetailDrawer from '@/features/jobs/components/JobDetailDrawer.vue'
import PipelinePane from '@/features/jobs/components/PipelinePane.vue'
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
  recommendTagType,
  salaryMid,
  signalClass,
  sourceText,
} from '@/features/jobs/lib/jobModel'

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
    resumesError.value = e?.userMessage || e?.message || '暂时无法读取你的简历列表'
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
    resumeDetailError.value = e?.userMessage || e?.message || '暂时读不到这份简历的详情'
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
  rememberResume(selectedResumeId.value)
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

.panel-header,
.board-header,
.result-toolbar,
.warehouse-toolbar,
.recommend-toolbar,
.board-row,
.panel-header h2,
.board-header h3 {
  margin: 0;
  font-size: 20px;
}

.panel-header p,
.board-header p,
.board-note,
.toolbar-sub,
.toolbar-meta,
.job-summary,
.warehouse-summary,
.recommend-reason {
  color: var(--app-muted);
}

.result-toolbar,
.warehouse-toolbar,
.recommend-toolbar {
  margin-bottom: 14px;
}

.toolbar-actions,
.recommend-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.mini-input {
  width: 140px;
}

.state-box {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 140px;
  justify-content: center;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  color: var(--app-muted);
}

.result-grid,
.recommend-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.job-shell,
.recommend-card {
  position: relative;
  padding: 18px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.98);
}

.job-shell-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.job-title-row,
.warehouse-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.job-title-row h3,
.warehouse-title-row h3 {
  margin: 0;
  font-size: 20px;
}

.source-pill,
.local-pill {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 12px;
}

.source-pill {
  background: rgba(45, 108, 223, 0.1);
  color: var(--app-primary, #3b82f6);
}

.local-pill {
  background: rgba(44, 143, 105, 0.12);
  color: var(--app-success, #14b8a6);
}

.job-company,
.warehouse-meta {
  margin: 8px 0 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.job-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.job-facts span {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--app-bg);
  font-size: 13px;
}

.job-facts.compact {
  margin-top: 10px;
}

.fact-emphasis {
  color: var(--app-primary, #7c6cff);
  font-weight: 700;
}

.job-tags,
.recommend-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.priority-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.priority-row.compact {
  margin-top: 10px;
}

.job-summary {
  margin: 14px 0 0;
  line-height: 1.7;
  min-height: 48px;
}

.job-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
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

.bookmark-btn {
  padding: 8px 12px;
}

.warehouse-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.warehouse-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 16px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.warehouse-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
}

.warehouse-search {
  width: 260px;
}

.recommend-card {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 14px;
}

.recommend-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(180deg, var(--app-text, #18222f), #304151);
  color: #fff;
  min-height: 94px;
}

.recommend-score strong {
  font-size: 28px;
  line-height: 1;
}

.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.tag-label {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 999px;
}

.tag-label.ok {
  background: rgba(44, 143, 105, 0.12);
  color: var(--app-success, #14b8a6);
}

.tag-label.gap {
  background: rgba(217, 111, 50, 0.12);
  color: var(--app-warning, #7c6cff);
}

.recommend-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.signal {
  font-size: 12px;
  padding: 5px 8px;
  border-radius: 999px;
}

.signal.positive {
  background: rgba(44, 143, 105, 0.12);
  color: var(--app-success, #14b8a6);
}

.signal.neutral {
  background: var(--app-bg);
  color: var(--app-muted);
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

.pipeline-toolbar,
.pipeline-form-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.pipeline-toolbar {
  justify-content: space-between;
  margin-bottom: 14px;
}

.pipeline-search {
  width: 260px;
}

.pipeline-stage-select {
  width: 150px;
}

.pipeline-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.pipeline-stage-pill,
.pipeline-summary-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.82);
}

.pipeline-stage-pill {
  text-align: left;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
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

.pipeline-stage-pill.active,
.pipeline-stage-pill:hover {
  transform: translateY(-1px);
  border-color: rgba(45, 108, 223, 0.28);
  box-shadow: 0 12px 24px rgba(21, 32, 43, 0.08);
}

.pipeline-board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}

.pipeline-column {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--app-line);
}

.pipeline-column-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.pipeline-column-head strong {
  display: block;
  font-size: 18px;
}

.pipeline-column-head small,
.pipeline-column-note,
.pipeline-meta,
.pipeline-history span {
  color: var(--app-muted);
}

.pipeline-column-note {
  margin: 8px 0 14px;
  line-height: 1.6;
  font-size: 13px;
}

.pipeline-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pipeline-card {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
}

.pipeline-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}

.pipeline-card-head h3 {
  margin: 0;
  font-size: 17px;
}

.pipeline-card-head p {
  margin: 6px 0 0;
  color: var(--app-muted);
  font-size: 13px;
}

.pipeline-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12px;
}

.pipeline-form-row,
.pipeline-actions {
  margin-top: 10px;
}

.pipeline-date {
  flex: 1;
}

.pipeline-history {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.6;
}

.pipeline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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
  .panel-header,
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

  .job-title-row h3,
  .warehouse-title-row h3,
  .pipeline-card-head h3 {
    font-size: 18px;
  }

  .pipeline-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
