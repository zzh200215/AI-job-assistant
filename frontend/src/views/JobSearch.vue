<template>
  <div class="market-page">
    <section class="hero">
      <div class="hero-copy">
        <div class="hero-title-row">
          <h1>岗位市场</h1>
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
          <small>寰呮姇閫掑埌宸茬害闈㈢粺涓€璺熻釜</small>
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
                <template #prefix><el-icon><Search /></el-icon></template>
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
                <el-option v-for="item in cities" :key="item.code || item.name" :label="item.name" :value="item.name" />
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
            </div>
          </div>

          <div class="preset-row">
            <span class="preset-label">快速搜索</span>
            <button
              v-for="item in presetKeywords"
              :key="item"
              type="button"
              class="preset-chip"
              @click="usePresetKeyword(item)"
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
              @click="reuseSearch(item)"
            >
              {{ item }}
            </button>
          </div>

          <div class="rewrite-row">
            <div class="rewrite-head">
              <div>
                <span class="history-label">AI 改写搜索词</span>
                <p class="rewrite-note">结合当前简历和搜索意图，生成更贴近招聘平台检索习惯的词组。</p>
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
                @click="applyRewriteSuggestion(item)"
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
                  <el-button size="small" plain :disabled="compareSelection.length < 2" @click="openComparePanel">
                    对比 {{ compareSelection.length }} 个岗位
                  </el-button>
                  <el-tag v-if="resultMode && !isDemo" type="info" effect="plain">{{ searchStateText }}</el-tag>
                  <el-tag v-if="isDemo" type="warning" effect="plain">当前为演示数据</el-tag>
                  <el-tag v-if="searchError && !isDemo" type="danger" effect="plain">{{ searchError }}</el-tag>
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
                      {{ job.priorityLabel }} 路 {{ job.priorityScore }}
                    </el-tag>
                    <span class="priority-reason">{{ job.priorityReason }}</span>
                  </div>

                  <div class="job-tags" v-if="job.skillTags.length">
                    <el-tag v-for="tag in job.skillTags.slice(0, 8)" :key="tag" size="small" effect="plain">
                      {{ tag }}
                    </el-tag>
                  </div>

                  <p class="job-summary">{{ job.summary || '暂无职位摘要' }}</p>

                  <div class="job-actions">
                    <el-button size="small" @click="openJobDetail(job, 'search')">查看详情</el-button>
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

              <el-empty v-else-if="hasSearched" description="没有找到更贴近的岗位，换个关键词或城市试试。" />
              <el-empty v-else description="先发起一次搜索，系统会把结果同步到你的岗位工作台。" />
            </el-tab-pane>

            <el-tab-pane label="岗位仓库" name="warehouse">
              <div class="warehouse-toolbar">
                <el-input
                  v-model="warehouseFilters.keyword"
                  clearable
                  size="small"
                  class="warehouse-search"
                  placeholder="按职位名、公司、城市筛选本地 JD"
                />
                <el-select
                  v-model="warehouseFilters.source"
                  placement="bottom-start"
                  :fallback-placements="['bottom-start']"
                  clearable
                  size="small"
                  placeholder="来源"
                >
                  <el-option label="全部来源" value="" />
                  <el-option label="导入" value="imported" />
                  <el-option label="爬取" value="crawled" />
                  <el-option label="API" value="api" />
                  <el-option label="手工创建" value="manual" />
                </el-select>
                <el-select
                  v-model="warehouseFilters.industry"
                  placement="bottom-start"
                  :fallback-placements="['bottom-start']"
                  clearable
                  size="small"
                  placeholder="行业"
                >
                  <el-option label="互联网 / 科技" value="互联网" />
                  <el-option label="人工智能" value="人工智能" />
                  <el-option label="电商" value="电商" />
                  <el-option label="通信" value="通信" />
                </el-select>
                <el-button text @click="loadLocalJobs">刷新仓库</el-button>
              </div>

              <div v-if="localLoading" class="state-box">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在加载本地岗位仓库...</span>
              </div>

              <div v-else-if="filteredLocalJobs.length" class="warehouse-list">
                <div v-for="job in filteredLocalJobs" :key="job.uid" class="warehouse-item">
                  <div class="warehouse-main">
                    <div class="warehouse-title-row">
                      <h3>{{ job.title }}</h3>
                      <el-tag size="small" effect="plain">{{ sourceText(job.source) }}</el-tag>
                      <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
                        {{ job.priorityLabel }}
                      </el-tag>
                    </div>
                    <p class="warehouse-meta">{{ job.company }} / {{ job.location || '地点待补充' }} / {{ job.salary }}</p>
                    <p class="warehouse-summary">{{ job.summary || '暂无摘要' }}</p>
                  </div>
                  <div class="warehouse-actions">
                    <el-button size="small" @click="openJobDetail(job, 'warehouse')">详情</el-button>
                    <el-button size="small" @click="handlePipelineAction(job)">
                      {{ pipelineStatusText(job) || '加入流程' }}
                    </el-button>
                    <el-button size="small" @click="toggleCompare(job)">
                      {{ isCompared(job) ? '取消对比' : '加入对比' }}
                    </el-button>
                    <el-button size="small" @click="prefillAnalysis(job)">带入分析</el-button>
                    <el-button size="small" type="primary" @click="startAnalysisForJob(job)">分析</el-button>
                  </div>
                </div>
              </div>

              <el-empty v-else description="岗位仓库还是空的，可以先搜索外部岗位或导入演示数据。" />
            </el-tab-pane>

            <el-tab-pane label="智能推荐" name="recommend">
              <div class="recommend-toolbar">
                <div class="recommend-left">
                  <span class="toolbar-title">以当前简历为中心的岗位匹配</span>
                  <span class="toolbar-sub" v-if="selectedResumeName">{{ selectedResumeName }}</span>
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
                  <el-button size="small" type="primary" @click="loadRecommendations" :disabled="!selectedResumeId">
                    更新推荐
                  </el-button>
                </div>
              </div>

              <div v-if="recommendLoading" class="state-box">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在根据简历生成匹配结果...</span>
              </div>

              <div v-else-if="normalizedRecommendations.length" class="recommend-grid">
                <article v-for="job in normalizedRecommendations" :key="job.uid" class="recommend-card">
                  <div class="recommend-score">
                    <strong>{{ job.matchScore }}</strong>
                    <span>匹配分</span>
                  </div>
                  <div class="recommend-body">
                    <div class="job-title-row">
                      <h3>{{ job.title }}</h3>
                      <el-tag :type="recommendTagType(job.recommendationType)" effect="dark" size="small">
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
                        <el-tag v-for="tag in job.skillOverlap.slice(0, 6)" :key="tag" size="small" type="success" effect="plain">
                          {{ tag }}
                        </el-tag>
                      </div>
                      <div v-if="job.skillGap.length" class="tag-group">
                        <span class="tag-label gap">缺口</span>
                        <el-tag v-for="tag in job.skillGap.slice(0, 6)" :key="tag" size="small" type="danger" effect="plain">
                          {{ tag }}
                        </el-tag>
                      </div>
                    </div>

                    <div class="recommend-signals">
                      <span :class="signalClass(job.salaryMatch)">薪资{{ job.salaryMatch ? '匹配' : '待评估' }}</span>
                      <span :class="signalClass(job.locationMatch)">地点{{ job.locationMatch ? '匹配' : '待协商' }}</span>
                      <span :class="signalClass(job.experienceMatch)">经验{{ job.experienceMatch ? '合适' : '有偏差' }}</span>
                    </div>

                    <div class="job-actions">
                      <el-button size="small" @click="openJobDetail(job, 'recommend')">查看详情</el-button>
                      <el-button size="small" @click="handlePipelineAction(job)">
                        {{ pipelineStatusText(job) || '加入流程' }}
                      </el-button>
                      <el-button size="small" @click="toggleCompare(job)">
                        {{ isCompared(job) ? '取消对比' : '加入对比' }}
                      </el-button>
                      <el-button size="small" @click="toggleShortlist(job)">
                        {{ isShortlisted(job) ? '已在清单' : '加入清单' }}
                      </el-button>
                      <el-button size="small" type="primary" @click="startAnalysisForJob(job)">直接分析</el-button>
                    </div>
                  </div>
                </article>
              </div>

              <el-empty
                v-else
                :description="selectedResumeId ? '还没有足够贴合的推荐结果，可以先补充岗位池。' : '先选择一份简历，再获取推荐岗位。'"
              />
            </el-tab-pane>

            <el-tab-pane label="投递流程" name="pipeline">
              <div class="pipeline-toolbar">
                <div class="recommend-left">
                  <span class="toolbar-title">用一个看板推进真实投递流程</span>
                  <span class="toolbar-sub">
                    {{ pipelineEntries.length }} 条记录，{{ pipelineActiveCount }} 条仍在推进
                  </span>
                </div>
                <div class="recommend-actions">
                  <el-input
                    v-model="pipelineFilters.keyword"
                    clearable
                    size="small"
                    placeholder="搜索岗位、公司、备注或下一步动作"
                    class="pipeline-search"
                  />
                  <el-select
                    v-model="pipelineFilters.stage"
                    placement="bottom-start"
                    :fallback-placements="['bottom-start']"
                    size="small"
                    class="pipeline-stage-select"
                  >
                    <el-option label="全部阶段" value="all" />
                    <el-option
                      v-for="stage in pipelineStages"
                      :key="stage.key"
                      :label="stage.label"
                      :value="stage.key"
                    />
                  </el-select>
                  <el-button text :disabled="!pipelineStats.rejected" @click="clearRejectedPipeline">
                    清理已淘汰
                  </el-button>
                </div>
              </div>

              <div class="pipeline-overview">
                <button
                  v-for="stage in pipelineStages"
                  :key="stage.key"
                  type="button"
                  class="pipeline-stage-pill"
                  :class="{ active: pipelineFilters.stage === stage.key }"
                  @click="pipelineFilters.stage = pipelineFilters.stage === stage.key ? 'all' : stage.key"
                >
                  <strong>{{ pipelineStats[stage.key] || 0 }}</strong>
                  <span>{{ stage.label }}</span>
                </button>
              </div>

              <div class="pipeline-board">
                <section v-for="stage in visiblePipelineStages" :key="stage.key" class="pipeline-column">
                  <div class="pipeline-column-head">
                    <div>
                      <strong>{{ stage.label }}</strong>
                      <small>{{ pipelineByStage[stage.key]?.length || 0 }} 个岗位</small>
                    </div>
                    <el-tag size="small" effect="plain">{{ stage.hint }}</el-tag>
                  </div>
                  <p class="pipeline-column-note">{{ stage.description }}</p>

                  <div v-if="pipelineByStage[stage.key]?.length" class="pipeline-cards">
                    <article v-for="entry in pipelineByStage[stage.key]" :key="entry.entryId" class="pipeline-card">
                      <div class="pipeline-card-head">
                        <div>
                          <h3>{{ entry.title }}</h3>
                          <p>{{ entry.company }} 路 {{ entry.salary }}</p>
                        </div>
                        <el-tag :type="priorityTagType(entry.priorityLabel)" effect="dark" size="small">
                          {{ entry.priorityLabel || '跟进中' }}
                        </el-tag>
                      </div>

                      <div class="pipeline-meta">
                        <span>{{ entry.location || '地点待补充' }}</span>
                        <span v-if="entry.resumeName">{{ entry.resumeName }}</span>
                        <span>更新于 {{ formatPipelineTime(entry.updatedAt) }}</span>
                      </div>

                      <el-input
                        v-model="entry.nextAction"
                        size="small"
                        placeholder="下一步动作，例如：周四前完成定制简历"
                        @change="touchPipelineEntry(entry)"
                      />

                      <div class="pipeline-form-row">
                        <el-date-picker
                          v-model="entry.followUpAt"
                          type="date"
                          value-format="YYYY-MM-DD"
                          size="small"
                          placeholder="下次跟进日期"
                          class="pipeline-date"
                          @change="touchPipelineEntry(entry)"
                        />
                        <el-select
                          :model-value="entry.stage"
                          placement="bottom-start"
                          :fallback-placements="['bottom-start']"
                          size="small"
                          class="pipeline-stage-select"
                          @change="(value) => updatePipelineStage(entry, value)"
                        >
                          <el-option
                            v-for="option in pipelineStages"
                            :key="option.key"
                            :label="option.label"
                            :value="option.key"
                          />
                        </el-select>
                      </div>

                      <el-input
                        v-model="entry.note"
                        type="textarea"
                        :rows="3"
                        resize="none"
                        placeholder="记录内推、沟通反馈、风险点或面试结论"
                        @change="touchPipelineEntry(entry)"
                      />

                      <div class="pipeline-history" v-if="entry.stageHistory.length">
                        <span>{{ pipelineHistoryText(entry.stageHistory) }}</span>
                      </div>

                      <div class="pipeline-actions">
                        <el-button size="small" @click="openPipelineJob(entry)">详情</el-button>
                        <el-button size="small" @click="prefillAnalysis(pipelineEntryToJob(entry))">带入分析</el-button>
                        <el-button size="small" type="primary" @click="startAnalysisForJob(pipelineEntryToJob(entry))">
                          直接分析
                        </el-button>
                        <el-button text type="danger" @click="removePipelineEntry(entry.entryId)">移除</el-button>
                      </div>
                    </article>
                  </div>

                  <el-empty v-else :image-size="68" :description="stage.emptyText" />
                </section>
              </div>

              <el-empty
                v-if="!pipelineEntries.length"
                description="先从实时搜索、岗位仓库或智能推荐里把岗位加入流程，页面会自动保存你的跟进记录。"
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
            <span class="board-label">甯傚満瑙傚療</span>
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
              <button type="button" class="text-btn" @click="activeTab = 'pipeline'">打开看板</button>
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
                <span>{{ pipelineStageLabel(entry.stage) }} 路 {{ entry.company }}</span>
              </button>
            </div>
            <el-empty v-else :image-size="70" description="流程里还没有岗位" />
          </div>

          <div class="board-block">
            <div class="board-row">
              <span class="board-label">待跟进清单</span>
              <button type="button" class="text-btn" @click="clearShortlist" v-if="shortlist.length">清空</button>
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
                <strong>{{ job.title }} 路 {{ job.priorityScore }}</strong>
                <span>{{ job.priorityLabel }} 路 {{ job.company }}</span>
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

    <el-drawer v-model="detailVisible" size="48%" :title="detailJob?.title || '职位详情'">
      <div v-if="detailLoading" class="drawer-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在加载职位详情...</span>
      </div>
      <template v-else-if="detailJob">
        <div class="drawer-header">
          <div>
            <p class="drawer-company">{{ detailJob.company }}</p>
            <div class="job-facts compact">
              <span class="fact-emphasis">{{ detailJob.salary }}</span>
              <span>{{ detailJob.location || '地点待补充' }}</span>
              <span>{{ detailJob.experience || '经验不限' }}</span>
              <span>{{ detailJob.education || '学历不限' }}</span>
            </div>
          </div>
          <div class="drawer-actions">
            <el-button size="small" @click="toggleShortlist(detailJob)">
              {{ isShortlisted(detailJob) ? '移出清单' : '加入清单' }}
            </el-button>
            <el-button size="small" @click="handlePipelineAction(detailJob)">
              {{ pipelineStatusText(detailJob) || '加入流程' }}
            </el-button>
            <el-button size="small" @click="toggleCompare(detailJob)">
              {{ isCompared(detailJob) ? '取消对比' : '加入对比' }}
            </el-button>
            <el-button size="small" @click="explainCurrentJob" :loading="explainLoading">
              投递解读
            </el-button>
            <el-button size="small" type="primary" @click="startAnalysisForJob(detailJob)">
              直接分析
            </el-button>
          </div>
        </div>

        <div v-if="detailJob.skillTags.length" class="drawer-tags">
          <el-tag v-for="tag in detailJob.skillTags" :key="tag" effect="plain" size="small">{{ tag }}</el-tag>
        </div>

        <div class="drawer-section">
          <h4>岗位摘要</h4>
          <p>{{ detailJob.summary || '暂无岗位摘要' }}</p>
        </div>

        <div v-if="explainResult" class="drawer-section">
          <h4>投递判断</h4>
          <div class="explain-box">
            <div class="explain-top">
              <el-tag :type="priorityTagType(explainResult.recommendation)" effect="dark">
                {{ explainResult.recommendation }}
              </el-tag>
              <strong>{{ explainResult.overall_score }} 分</strong>
            </div>
            <p>{{ explainResult.overall_reason }}</p>
            <div v-if="explainResult.risk_points?.length" class="explain-list">
              <span>风险点</span>
              <ul>
                <li v-for="item in explainResult.risk_points.slice(0, 3)" :key="item">{{ item }}</li>
              </ul>
            </div>
            <div v-if="explainResult.optimization_suggestions?.length" class="explain-list">
              <span>寤鸿</span>
              <ul>
                <li v-for="item in explainResult.optimization_suggestions.slice(0, 3)" :key="item">{{ item }}</li>
              </ul>
            </div>
          </div>
        </div>

        <div class="drawer-section">
          <h4>完整 JD</h4>
          <pre class="drawer-content">{{ detailJob.rawText || detailJob.summary || '暂无完整内容' }}</pre>
        </div>

        <div v-if="detailJob.sourceUrl" class="drawer-section">
          <h4>来源链接</h4>
          <el-link :href="detailJob.sourceUrl" target="_blank" type="primary">
            打开原始职位链接
          </el-link>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="compareVisible" width="980px" title="岗位对比">
      <div v-if="comparedJobs.length" class="compare-grid">
        <div v-for="job in comparedJobs" :key="job.uid" class="compare-card">
          <div class="compare-head">
            <h3>{{ job.title }}</h3>
            <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
              {{ job.priorityLabel }} 路 {{ job.priorityScore }}
            </el-tag>
          </div>
          <p class="compare-company">{{ job.company }}</p>
          <div class="compare-meta">
            <span>{{ job.salary }}</span>
            <span>{{ job.location || '地点待补充' }}</span>
            <span>{{ job.experience || '经验不限' }}</span>
          </div>
          <p class="compare-reason">{{ job.priorityReason }}</p>
          <div class="compare-tags" v-if="job.skillTags?.length">
            <el-tag v-for="tag in job.skillTags.slice(0, 8)" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
          </div>
          <p class="compare-summary">{{ job.summary || '暂无摘要' }}</p>
          <div class="compare-actions">
            <el-button size="small" @click="openJobDetail(job, 'compare')">详情</el-button>
            <el-button size="small" @click="handlePipelineAction(job)">
              {{ pipelineStatusText(job) || '加入流程' }}
            </el-button>
            <el-button size="small" @click="toggleCompare(job)">移出对比</el-button>
            <el-button size="small" type="primary" @click="startAnalysisForJob(job)">分析</el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import {
  ArrowRight,
  Loading,
  Location,
  OfficeBuilding,
  Promotion,
  RefreshRight,
  Search,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { getResume, getResumeList } from '@/api/resume'
import { explainMatch } from '@/api/analysis'
import { queryRewriteTest } from '@/api/knowledge'
import {
  clearRejectedJobPipeline,
  createJobPipelineEntry,
  getCities,
  getJobDetail,
  getJobList,
  getJobPipelineList,
  getJobRecommendations,
  searchExternalJobs,
  seedDemoJobs,
  startFullAnalysis,
  deleteJobPipelineEntry,
  updateJobPipelineEntry,
} from '@/api/jobs'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeTab = ref('search')
const keyword = ref('Python')
const city = ref('')
const source = ref('boss')
const cities = ref([])
const selectedResumeId = ref(null)
const resumeList = ref([])
const selectedResumeDetail = ref(null)

const searching = ref(false)
const hasSearched = ref(false)
const searchHint = ref('姝ｅ湪鎼滅储鏈€鏂板矖浣?..')
const searchError = ref('')
const isDemo = ref(false)
const resultMode = ref('')
const savedCount = ref(0)
const externalJobs = ref([])

const localLoading = ref(false)
const localJobs = ref([])

const recommendLoading = ref(false)
const recommendations = ref([])

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

const searchFilters = ref({
  experience: '',
  education: '',
  skill: '',
})
const searchSort = ref('default')

const warehouseFilters = ref({
  keyword: '',
  source: '',
  industry: '',
})

const recommendFilters = ref({
  location: '',
  industry: '',
})

const presetKeywords = ['Python 后端', '前端架构', '大模型应用', '算法工程师', '数据分析', 'DevOps']
const pipelineStages = [
  {
    key: 'todo',
    label: '待投递',
    hint: '准备材料',
    description: '简历、作品集、渠道和联系人都还在准备阶段。',
    emptyText: '还没有待投递岗位',
  },
  {
    key: 'applied',
    label: '已投递',
    hint: '等待反馈',
    description: '已经完成投递，重点是补记录、盯进度和安排跟进。',
    emptyText: '还没有已投递岗位',
  },
  {
    key: 'interview',
    label: '已约面',
    hint: '面试推进',
    description: '进入面试流程后，把面试时间、反馈和风险点沉淀下来。',
    emptyText: '还没有进入面试的岗位',
  },
  {
    key: 'rejected',
    label: '已淘汰',
    hint: '复盘沉淀',
    description: '保留失败原因和复盘结论，方便后续调整投递策略。',
    emptyText: '当前没有淘汰岗位',
  },
]
const pipelineStageMap = Object.fromEntries(pipelineStages.map((item) => [item.key, item]))

const marketStorageKey = (key) => `recruit.market.${key}.${authStore.user?.id || 'guest'}`

const shortlist = ref(loadLocalArray(marketStorageKey('shortlist')))
const recentSearches = ref(loadLocalArray(marketStorageKey('history')))
const pipelineEntries = ref([])
const pipelineFilters = ref({
  keyword: '',
  stage: 'all',
})

const selectedResumeName = computed(() => {
  const resume = resumeList.value.find((item) => item.id === selectedResumeId.value)
  return resume?.file_name || resume?.name || ''
})

const selectedResumeSummary = computed(() => {
  const parsed = selectedResumeDetail.value?.parsed_json || selectedResumeDetail.value?.parsed || {}
  const skills = Array.isArray(parsed.skills)
    ? parsed.skills.map((item) => (typeof item === 'string' ? item : item?.skill)).filter(Boolean).slice(0, 8)
    : []
  const currentTitle = parsed.current_title || parsed.target_position || selectedResumeDetail.value?.name || ''
  return [currentTitle, skills.join(' / ')].filter(Boolean).join('，')
})

const activeTabLabel = computed(() => ({
  search: '实时搜索',
  warehouse: '岗位仓库',
  recommend: '智能推荐',
  pipeline: '投递流程',
}[activeTab.value] || '实时搜索'))

const pipelineStats = computed(() =>
  pipelineStages.reduce((acc, stage) => {
    acc[stage.key] = pipelineEntries.value.filter((item) => item.stage === stage.key).length
    return acc
  }, {})
)

const pipelineActiveCount = computed(() =>
  pipelineEntries.value.filter((item) => item.stage !== 'rejected').length
)

const filteredPipelineEntries = computed(() => {
  const keywordNeedle = pipelineFilters.value.keyword.trim().toLowerCase()
  return [...pipelineEntries.value]
    .filter((entry) => pipelineFilters.value.stage === 'all' || entry.stage === pipelineFilters.value.stage)
    .filter((entry) => {
      if (!keywordNeedle) return true
      const text = [
        entry.title,
        entry.company,
        entry.location,
        entry.note,
        entry.nextAction,
        entry.resumeName,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return text.includes(keywordNeedle)
    })
    .sort(comparePipelineEntries)
})

const visiblePipelineStages = computed(() =>
  pipelineFilters.value.stage === 'all'
    ? pipelineStages
    : pipelineStages.filter((item) => item.key === pipelineFilters.value.stage)
)

const pipelineByStage = computed(() => {
  const grouped = Object.fromEntries(pipelineStages.map((item) => [item.key, []]))
  filteredPipelineEntries.value.forEach((entry) => {
    if (grouped[entry.stage]) {
      grouped[entry.stage].push(entry)
    }
  })
  return grouped
})

const pipelineFocusList = computed(() =>
  [...pipelineEntries.value]
    .filter((entry) => entry.stage !== 'rejected')
    .sort(comparePipelineEntries)
    .slice(0, 5)
)

const searchStateText = computed(() => {
  if (searching.value) return '抓取中'
  if (!hasSearched.value) return '未搜索'
  if (resultMode.value === 'local_fallback') return '本地职位库'
  if (resultMode.value === 'demo_fallback') return '演示数据'
  return isDemo.value ? '演示数据' : '最新结果'
})

const sourceBannerTitle = computed(() => {
  if (searching.value) return '正在获取岗位数据'
  if (!hasSearched.value) return '优先展示真实岗位结果'
  if (resultMode.value === 'local_fallback') return '当前展示本地职位库'
  if (resultMode.value === 'demo_fallback' || isDemo.value) return '当前展示演示岗位数据'
  return '当前展示实时搜索结果'
})

const sourceBannerDesc = computed(() => {
  if (searching.value) return '系统会优先抓取外部岗位，失败时再回退到本地或演示数据。'
  if (!hasSearched.value) return '点击“搜索最新岗位”后，系统会优先使用外部搜索结果。'
  if (resultMode.value === 'local_fallback') return '外部抓取未返回可用结果，已切换到本地职位库，适合继续做分析和筛选。'
  if (resultMode.value === 'demo_fallback' || isDemo.value) return '当前结果主要用于演示流程，建议补充真实搜索或导入岗位后再做判断。'
  return '这些岗位来自当前搜索渠道，可直接加入流程、对比或带入分析。'
})

const sourceBannerClass = computed(() => {
  if (resultMode.value === 'demo_fallback' || isDemo.value) return 'is-demo'
  if (resultMode.value === 'local_fallback') return 'is-local'
  if (searching.value) return 'is-loading'
  return 'is-live'
})

const filteredExternalJobs = computed(() => {
  const skillNeedle = searchFilters.value.skill.trim().toLowerCase()
  const list = externalJobs.value.filter((job) => {
    const exp = job.experience || ''
    const edu = job.education || ''
    const skillText = job.skillTags.join(' ').toLowerCase()
    const expOk = !searchFilters.value.experience || exp.includes(searchFilters.value.experience.replace('+', ''))
    const eduOk = !searchFilters.value.education || edu.includes(searchFilters.value.education)
    const skillOk = !skillNeedle || skillText.includes(skillNeedle) || (job.summary || '').toLowerCase().includes(skillNeedle)
    return expOk && eduOk && skillOk
  })

  const sorted = [...list]
  if (searchSort.value === 'salary_desc') {
    sorted.sort((a, b) => salaryMid(b.salary) - salaryMid(a.salary))
  } else if (searchSort.value === 'salary_asc') {
    sorted.sort((a, b) => salaryMid(a.salary) - salaryMid(b.salary))
  } else if (searchSort.value === 'skill_desc') {
    sorted.sort((a, b) => b.skillTags.length - a.skillTags.length)
  }
  return sorted
})

const filteredLocalJobs = computed(() => {
  const keywordNeedle = warehouseFilters.value.keyword.trim().toLowerCase()
  return localJobs.value.filter((job) => {
    const text = `${job.title} ${job.company} ${job.location} ${job.summary}`.toLowerCase()
    const sourceOk = !warehouseFilters.value.source || job.source === warehouseFilters.value.source
    const industryOk = !warehouseFilters.value.industry || (job.industry || '').includes(warehouseFilters.value.industry)
    const keywordOk = !keywordNeedle || text.includes(keywordNeedle)
    return sourceOk && industryOk && keywordOk
  })
})

const normalizedRecommendations = computed(() =>
  recommendations.value.map((item, index) => {
    const normalized = {
      uid: `recommend-${item.jd_id || index}`,
      id: item.jd_id || null,
      title: item.job_title || '推荐岗位',
      company: item.company || '未知公司',
      location: item.location || '',
      salary: item.salary_range || '薪资面议',
      industry: item.industry || '',
      summary: item.match_reason || '',
      rawText: '',
      source: 'recommend',
      sourceUrl: '',
      local: true,
      experience: '',
      education: '',
      skillTags: uniqueList([...(item.skill_overlap || []), ...(item.skill_gap || [])]),
      skillOverlap: item.skill_overlap || [],
      skillGap: item.skill_gap || [],
      matchScore: item.match_score || 0,
      recommendationType: item.recommendation_type || '值得一试',
      matchReason: item.match_reason || '',
      salaryMatch: item.salary_match !== false,
      locationMatch: item.location_match !== false,
      experienceMatch: item.experience_match !== false,
      compareText: item.match_reason || '',
    }
    const priority = calculateApplicationPriority(normalized)
    return { ...normalized, ...priority }
  })
)

const comparedJobs = computed(() => {
  const map = new Map(marketDataset.value.map((job) => [job.uid, job]))
  return compareSelection.value.map((uid) => map.get(uid)).filter(Boolean)
})

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

async function loadCities() {
  try {
    const data = await getCities()
    cities.value = data?.cities || []
  } catch {
    cities.value = [
      { name: '北京', code: '101010100' },
      { name: '上海', code: '101020100' },
      { name: '深圳', code: '101280600' },
      { name: '杭州', code: '101210100' },
      { name: '广州', code: '101280100' },
      { name: '全国', code: '' },
    ]
  }
}

async function loadResumes() {
  try {
    const data = await getResumeList()
    resumeList.value = data?.items || (Array.isArray(data) ? data : [])
    if (!selectedResumeId.value && resumeList.value.length) {
      selectedResumeId.value = resumeList.value[0].id
    }
    if (selectedResumeId.value) {
      await loadResumeDetail(selectedResumeId.value)
    }
  } catch {
    resumeList.value = []
  }
}

async function loadResumeDetail(resumeId) {
  if (!resumeId) {
    selectedResumeDetail.value = null
    return
  }
  try {
    selectedResumeDetail.value = await getResume(resumeId)
  } catch {
    selectedResumeDetail.value = null
  }
}

async function loadLocalJobs() {
  localLoading.value = true
  try {
    const data = await getJobList({ page: 1, page_size: 100 })
    localJobs.value = (data?.items || []).map((item, index) => normalizeJob(item, `local-${index}`))
  } catch {
    localJobs.value = []
  } finally {
    localLoading.value = false
  }
}

async function loadPipelineEntries() {
  try {
    const data = await getJobPipelineList()
    pipelineEntries.value = (data?.items || []).map((item) => normalizePipelineEntry(item))
  } catch {
    pipelineEntries.value = []
  }
}

async function loadRecommendations() {
  if (!selectedResumeId.value) {
    recommendations.value = []
    return
  }
  recommendLoading.value = true
  try {
    const params = {
      resume_id: selectedResumeId.value,
      limit: 12,
    }
    if (recommendFilters.value.location) params.location = recommendFilters.value.location
    if (recommendFilters.value.industry) params.industry = recommendFilters.value.industry

    const data = await getJobRecommendations(params)
    recommendations.value = data?.recommendations || []
  } catch {
    recommendations.value = []
  } finally {
    recommendLoading.value = false
  }
}

async function runSearch() {
  if (!keyword.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  searching.value = true
  hasSearched.value = true
  searchError.value = ''
  isDemo.value = false
  resultMode.value = ''
  searchHint.value = `正在搜索 ${sourceText(source.value)} 的 ${keyword.value} 岗位...`

  try {
    const data = await searchExternalJobs({
      keyword: keyword.value.trim(),
      city: city.value,
      source: source.value,
      page: 1,
    })
    externalJobs.value = (data?.jobs || []).map((item, index) => normalizeJob(item, `search-${index}`))
    savedCount.value = data?.saved_count || 0
    searchError.value = data?.error || ''
    isDemo.value = !!data?.is_demo
    resultMode.value = data?.result_mode || 'external'
    pushRecentSearch(keyword.value.trim())
  } catch {
    externalJobs.value = []
    searchError.value = '搜索失败，请稍后重试'
    resultMode.value = ''
  } finally {
    searching.value = false
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
    recommendations.value = []
    selectedResumeDetail.value = null
    return
  }
  await loadResumeDetail(selectedResumeId.value)
  await loadRecommendations()
  await loadPipelineEntries()
}

function usePresetKeyword(value) {
  keyword.value = value
  runSearch()
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
      original_query: keyword.value.trim() || `为我推荐适合 ${selectedResumeName.value || '当前简历'} 的岗位`,
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

function applyRewriteSuggestion(value) {
  keyword.value = value
  runSearch()
}

function reuseSearch(value) {
  keyword.value = value
  runSearch()
}

function resetSearchFilters() {
  searchFilters.value = {
    experience: '',
    education: '',
    skill: '',
  }
  searchSort.value = 'default'
}

function normalizeJob(item, seed) {
  const salary = item.salary || item.salary_range || '钖祫闈㈣'
  const skillTags = uniqueList(item.skill_tags || item.skillTags || [])
  const normalized = {
    uid: `${seed}-${item.id || item.external_id || item.title || 'job'}`,
    id: item.id || null,
    title: item.title || item.job_title || '鏈煡宀椾綅',
    company: item.company || '鏈煡鍏徃',
    location: item.location || '',
    salary,
    experience: item.experience || item.experience_requirement || '',
    education: item.education || item.education_requirement || '',
    industry: item.industry || '',
    skillTags,
    summary: item.jd_summary || item.match_reason || '',
    rawText: item.raw_text || '',
    source: item.source || 'local',
    sourceUrl: item.source_url || '',
    local: !!item._local_db || ['local', 'imported', 'api', 'manual', 'crawled'].includes(item.source),
  }
  return { ...normalized, ...calculateApplicationPriority(normalized) }
}

async function openJobDetail(job, origin) {
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
        `${origin}-detail`
      ),
    }
  } catch {
    detailJob.value = { ...job }
  } finally {
    detailLoading.value = false
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
      router.push(`/agent?task_id=${data.task_id}`)
      return
    }
  } catch {
    ElMessage.warning('自动启动失败，已带你进入分析页继续处理')
  }

  router.push('/smart-analysis')
}

function persistAnalysisContext(job) {
  const userId = authStore.user?.id || 'guest'
  localStorage.setItem(`recruit.lastResumeId.${userId}`, String(selectedResumeId.value))
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

function toggleShortlist(job) {
  const existing = shortlist.value.findIndex((item) => item.uid === job.uid || (job.id && item.id === job.id))
  if (existing >= 0) {
    shortlist.value.splice(existing, 1)
  } else {
    shortlist.value.unshift({
      uid: job.uid,
      id: job.id || null,
      title: job.title,
      company: job.company,
      location: job.location,
      salary: job.salary,
      summary: job.summary,
      rawText: job.rawText,
      source: job.source,
      sourceUrl: job.sourceUrl,
      skillTags: job.skillTags || [],
      experience: job.experience || '',
      education: job.education || '',
      local: job.local,
    })
  }
  shortlist.value = shortlist.value.slice(0, 20)
  saveLocalArray(marketStorageKey('shortlist'), shortlist.value)
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

function isShortlisted(job) {
  return shortlist.value.some((item) => item.uid === job.uid || (job.id && item.id === job.id))
}

function openShortlistedJob(job) {
  openJobDetail(job, 'shortlist')
}

function clearShortlist() {
  shortlist.value = []
  saveLocalArray(marketStorageKey('shortlist'), shortlist.value)
}

async function handlePipelineAction(job) {
  const existing = findPipelineEntry(job)
  if (existing) {
    activeTab.value = 'pipeline'
    pipelineFilters.value.stage = existing.stage
    pipelineFilters.value.keyword = ''
    ElMessage.info(`该岗位已在 ${pipelineStageLabel(existing.stage)} 阶段`)
    return
  }

  try {
    const created = await createJobPipelineEntry(createPipelineEntryPayload(job))
    pipelineEntries.value = [normalizePipelineEntry(created), ...pipelineEntries.value]
    activeTab.value = 'pipeline'
    pipelineFilters.value.stage = 'todo'
    pipelineFilters.value.keyword = ''
    ElMessage.success('已加入投递流程')
  } catch {
    // request interceptor already surfaced the error
  }
}

function createPipelineEntryPayload(job, stage = 'todo') {
  const now = new Date().toISOString()
  return {
    resume_id: selectedResumeId.value || null,
    jd_id: job.id || null,
    title: job.title,
    company: job.company,
    location: job.location,
    salary_range: job.salary,
    summary: job.summary,
    raw_text: job.rawText,
    source: job.source,
    source_url: job.sourceUrl,
    experience_requirement: job.experience || '',
    education_requirement: job.education || '',
    industry: job.industry || '',
    skill_tags: job.skillTags || [],
    priority_score: job.priorityScore || 0,
    priority_label: job.priorityLabel || '',
    stage,
    note: '',
    next_action: defaultNextAction(stage),
    follow_up_at: null,
    resume_name: selectedResumeName.value || '',
    stage_history: [{ stage, at: now }],
  }
}

function normalizePipelineEntry(item) {
  const stage = pipelineStageMap[item?.stage] ? item.stage : 'todo'
  const createdAt = item?.createdAt || item?.create_time || item?.updatedAt || item?.update_time || new Date().toISOString()
  const updatedAt = item?.updatedAt || item?.update_time || createdAt
  const rawHistory = item?.stageHistory || item?.stage_history
  const stageHistory = Array.isArray(rawHistory) && rawHistory.length
    ? rawHistory.map((historyItem) => ({
        stage: pipelineStageMap[historyItem?.stage] ? historyItem.stage : stage,
        at: historyItem?.at || updatedAt,
      }))
    : [{ stage, at: updatedAt }]

  return {
    entryId: item?.entryId || item?.id || `pipeline-${item?.jobId || item?.jd_id || createdAt}`,
    uid: item?.uid || `pipeline-${item?.jobId || item?.jd_id || item?.id || createdAt}`,
    jobId: item?.jobId || item?.jd_id || null,
    title: item?.title || '未知岗位',
    company: item?.company || '未知公司',
    location: item?.location || '',
    salary: item?.salary || item?.salary_range || '薪资面议',
    summary: item?.summary || '',
    rawText: item?.rawText || item?.raw_text || '',
    source: item?.source || 'local',
    sourceUrl: item?.sourceUrl || item?.source_url || '',
    experience: item?.experience || item?.experience_requirement || '',
    education: item?.education || item?.education_requirement || '',
    industry: item?.industry || '',
    skillTags: uniqueList(item?.skillTags || item?.skill_tags || []),
    local: item?.local !== undefined ? !!item.local : !!item?.jd_id,
    priorityScore: item?.priorityScore || item?.priority_score || 0,
    priorityLabel: item?.priorityLabel || item?.priority_label || '',
    stage,
    note: item?.note || '',
    nextAction: item?.nextAction || defaultNextAction(stage),
    followUpAt: item?.followUpAt || item?.follow_up_at || '',
    resumeId: item?.resumeId || item?.resume_id || null,
    resumeName: item?.resumeName || item?.resume_name || '',
    createdAt,
    updatedAt,
    stageHistory,
  }
}

function findPipelineEntry(job) {
  if (!job) return null
  return pipelineEntries.value.find((item) => {
    if (
      job.id &&
      item.jobId &&
      item.jobId === job.id &&
      (!selectedResumeId.value || !item.resumeId || item.resumeId === selectedResumeId.value)
    ) {
      return true
    }
    return item.uid === job.uid
  }) || null
}

function pipelineStatusText(job) {
  const entry = findPipelineEntry(job)
  return entry ? pipelineStageLabel(entry.stage) : ''
}

function pipelineStageLabel(stage) {
  return pipelineStageMap[stage]?.label || '投递流程'
}

function pipelineEntryToJob(entry) {
  return {
    uid: entry.uid,
    id: entry.jobId,
    title: entry.title,
    company: entry.company,
    location: entry.location,
    salary: entry.salary,
    summary: entry.summary,
    rawText: entry.rawText,
    source: entry.source,
    sourceUrl: entry.sourceUrl,
    experience: entry.experience,
    education: entry.education,
    industry: entry.industry,
    skillTags: entry.skillTags || [],
    local: entry.local,
    priorityScore: entry.priorityScore,
    priorityLabel: entry.priorityLabel,
    priorityReason: entry.note || entry.nextAction || '',
  }
}

function openPipelineJob(entry) {
  openJobDetail(pipelineEntryToJob(entry), 'pipeline')
}

async function touchPipelineEntry(entry) {
  const index = pipelineEntries.value.findIndex((item) => item.entryId === entry.entryId)
  if (index < 0) return
  try {
    const updated = await updateJobPipelineEntry(entry.entryId, {
      resume_id: entry.resumeId,
      jd_id: entry.jobId,
      title: entry.title,
      company: entry.company,
      location: entry.location,
      salary_range: entry.salary,
      source: entry.source,
      source_url: entry.sourceUrl,
      summary: entry.summary,
      raw_text: entry.rawText,
      experience_requirement: entry.experience,
      education_requirement: entry.education,
      industry: entry.industry,
      skill_tags: entry.skillTags || [],
      priority_score: entry.priorityScore || 0,
      priority_label: entry.priorityLabel || '',
      stage: entry.stage,
      note: entry.note || '',
      next_action: entry.nextAction || '',
      follow_up_at: entry.followUpAt || null,
      resume_name: entry.resumeName || '',
      stage_history: entry.stageHistory || [],
    })
    pipelineEntries.value[index] = normalizePipelineEntry(updated)
  } catch {
    await loadPipelineEntries()
  }
}

async function updatePipelineStage(entry, stage) {
  const index = pipelineEntries.value.findIndex((item) => item.entryId === entry.entryId)
  if (index < 0 || !pipelineStageMap[stage]) return

  const current = pipelineEntries.value[index]
  if (current.stage === stage) {
    await touchPipelineEntry(current)
    return
  }

  const now = new Date().toISOString()
  const nextEntry = normalizePipelineEntry({
    ...current,
    stage,
    nextAction: current.nextAction || defaultNextAction(stage),
    updatedAt: now,
    stageHistory: [...current.stageHistory, { stage, at: now }],
  })
  pipelineEntries.value[index] = nextEntry
  await touchPipelineEntry(nextEntry)
}

async function removePipelineEntry(entryId) {
  try {
    await deleteJobPipelineEntry(entryId)
    pipelineEntries.value = pipelineEntries.value.filter((item) => item.entryId !== entryId)
  } catch {
    // request interceptor already surfaced the error
  }
}

async function clearRejectedPipeline() {
  try {
    await clearRejectedJobPipeline()
    pipelineEntries.value = pipelineEntries.value.filter((item) => item.stage !== 'rejected')
  } catch {
    // request interceptor already surfaced the error
  }
}

function defaultNextAction(stage) {
  return {
    todo: '补齐定制简历并确认投递渠道',
    applied: '记录投递时间，并在 3-5 天后安排一次跟进',
    interview: '整理面试重点和追问项，准备复盘记录',
    rejected: '补充淘汰原因，复盘后调整投递策略',
  }[stage] || '继续跟进'
}

function comparePipelineEntries(a, b) {
  const followUpA = a.followUpAt ? new Date(a.followUpAt).getTime() : Number.MAX_SAFE_INTEGER
  const followUpB = b.followUpAt ? new Date(b.followUpAt).getTime() : Number.MAX_SAFE_INTEGER
  if (followUpA !== followUpB) {
    return followUpA - followUpB
  }
  return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
}

function formatPipelineTime(value) {
  if (!value) return '--'
  try {
    return new Date(value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

function pipelineHistoryText(history) {
  if (!Array.isArray(history) || !history.length) return ''
  return history
    .slice(-3)
    .map((item) => `${pipelineStageLabel(item.stage)} ${formatPipelineTime(item.at)}`)
    .join(' / ')
}

function goToSmartAnalysis() {
  router.push('/smart-analysis')
}

function pushRecentSearch(value) {
  const next = [value, ...recentSearches.value.filter((item) => item !== value)].slice(0, 8)
  recentSearches.value = next
  saveLocalArray(marketStorageKey('history'), next)
}

function recommendTagType(value) {
  if ((value || '').includes('楂樺害')) return 'success'
  if ((value || '').includes('鍊煎緱')) return 'warning'
  return 'info'
}

function priorityTagType(value) {
  if ((value || '').includes('浼樺厛') || (value || '').includes('寮虹儓')) return 'success'
  if ((value || '').includes('鍊煎緱') || (value || '').includes('鍙互')) return 'warning'
  if ((value || '').includes('璋ㄦ厧')) return 'danger'
  return 'info'
}

function signalClass(flag) {
  return flag ? 'signal positive' : 'signal neutral'
}

function sourceText(value) {
  return {
    boss: 'BOSS',
    all: '全平台',
    crawled: '爬取',
    imported: '导入',
    api: '接口',
    manual: '手工',
    local: '本地',
    recommend: '推荐',
  }[value] || value || '未知'
}

function calculateApplicationPriority(job) {
  let score = 45
  const reasons = []

  const salaryScore = salaryMid(job.salary)
  if (salaryScore >= 35) {
    score += 16
    reasons.push('薪资带更强')
  } else if (salaryScore >= 25) {
    score += 10
    reasons.push('薪资有竞争力')
  }

  if ((job.skillTags || []).length >= 6) {
    score += 10
    reasons.push('技能画像完整')
  } else if ((job.skillTags || []).length >= 3) {
    score += 6
  }

  if (job.location && city.value && job.location.includes(city.value)) {
    score += 8
    reasons.push('城市匹配')
  }

  if (job.local) {
    score += 6
    reasons.push('已落库可直接分析')
  }

  if (typeof job.matchScore === 'number' && job.matchScore > 0) {
    score += Math.round(job.matchScore * 0.28)
    reasons.push('推荐匹配度较高')
  }

  if (job.salaryMatch) score += 4
  if (job.locationMatch) score += 4
  if (job.experienceMatch) score += 4

  const finalScore = Math.max(0, Math.min(100, score))
  const label = finalScore >= 82 ? '优先投递' : finalScore >= 66 ? '值得投递' : '先观察'
  return {
    priorityScore: finalScore,
    priorityLabel: label,
    priorityReason: reasons.slice(0, 3).join(' / ') || '信息尚不完整，建议先观察',
  }
}

function salaryMid(value) {
  if (!value) return 0
  const normalized = String(value).replace(/\s/g, '').replace(/路/g, '').toLowerCase()
  const nums = normalized.match(/\d+(\.\d+)?/g)?.map(Number) || []
  if (!nums.length) return 0

  let [min, max] = nums.length >= 2 ? [nums[0], nums[1]] : [nums[0], nums[0]]
  if (normalized.includes('w')) {
    min *= 10
    max *= 10
  }
  return Math.round((min + max) / 2)
}

function rankMap(list) {
  const map = new Map()
  list.forEach((item) => {
    const key = String(item).trim()
    if (!key) return
    map.set(key, (map.get(key) || 0) + 1)
  })
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, count]) => ({ label, count }))
}

function uniqueList(list) {
  return [...new Set((Array.isArray(list) ? list : []).map((item) => String(item).trim()).filter(Boolean))]
}

function loadLocalArray(key) {
  try {
    const raw = localStorage.getItem(key)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveLocalArray(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}
</script>

<style scoped>
.market-page {
  --paper: #eef4ff;
  --ink: #18222f;
  --muted: #6f7b88;
  --line: rgba(24, 34, 47, 0.1);
  --orange: #7c6cff;
  --blue: #3b82f6;
  --green: #14b8a6;
  --sand: #dfe9fb;
  --deep: #15202b;
  max-width: 1480px;
  margin: 0 auto;
  padding: 18px 0 28px;
  color: var(--ink);
}

.hero {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 18px;
  padding: 26px;
  border-radius: 28px;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at left bottom, rgba(255, 255, 255, 0.72), transparent 30%),
    radial-gradient(circle at top right, rgba(124, 108, 255, 0.22), transparent 38%),
    linear-gradient(135deg, #f4f8ff 0%, #eaf1ff 48%, #dce8fb 100%);
  border: 1px solid rgba(24, 34, 47, 0.08);
  box-shadow: 0 20px 40px rgba(21, 32, 43, 0.08);
}

.hero::before {
  content: '';
  position: absolute;
  inset: 18px auto auto 18px;
  width: 120px;
  height: 120px;
  border-radius: 32px;
  border: 1px solid rgba(21, 32, 43, 0.08);
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
  border: 1px dashed rgba(21, 32, 43, 0.16);
  pointer-events: none;
}

.hero h1 {
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
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.52);
  border: 1px solid rgba(21, 32, 43, 0.08);
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
  background: linear-gradient(135deg, #7c6cff, #9ca1ff);
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
  border-radius: 16px;
  border: 1px solid rgba(24, 34, 47, 0.08);
  background: rgba(255, 255, 255, 0.58);
}

.source-banner strong,
.result-source-note strong {
  font-size: 13px;
  color: var(--ink);
}

.source-banner span,
.result-source-note span {
  color: var(--muted);
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
  border-radius: 20px;
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

.accent-orange { background: linear-gradient(135deg, #7c6cff, #9b8cff); }
.accent-blue { background: linear-gradient(135deg, #3b82f6, #6aa6ff); }
.accent-green { background: linear-gradient(135deg, #14b8a6, #39d2bf); }
.accent-dark { background: linear-gradient(135deg, #15202b, #314456); }

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
  border-radius: 24px;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(240, 245, 255, 0.94));
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
  color: var(--muted);
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
  border-radius: 18px;
  background: rgba(21, 32, 43, 0.035);
}

.rewrite-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.rewrite-note,
.rewrite-meta,
.priority-reason,
.compare-reason,
.compare-summary,
.compare-company {
  color: var(--muted);
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
  border: 1px solid rgba(24, 34, 47, 0.14);
  background: #fff;
  border-radius: 999px;
  padding: 8px 12px;
  color: var(--ink);
  cursor: pointer;
  transition: 0.2s ease;
}

.preset-chip:hover,
.history-chip:hover,
.bookmark-btn:hover,
.short-item:hover,
.cta-item:hover {
  transform: translateY(-1px);
  border-color: rgba(24, 34, 47, 0.28);
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
.drawer-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

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
.recommend-reason,
.drawer-company,
.drawer-section p {
  color: var(--muted);
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
  border-radius: 18px;
  background: rgba(21, 32, 43, 0.03);
  color: var(--muted);
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
  border-radius: 22px;
  border: 1px solid rgba(24, 34, 47, 0.08);
  background:
    radial-gradient(circle at top right, rgba(124, 108, 255, 0.08), transparent 34%),
    linear-gradient(180deg, #fff, #f5f8ff);
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
  color: var(--blue);
}

.local-pill {
  background: rgba(44, 143, 105, 0.12);
  color: var(--green);
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
  background: rgba(21, 32, 43, 0.05);
  font-size: 13px;
}

.job-facts.compact {
  margin-top: 10px;
}

.fact-emphasis {
  color: var(--orange);
  font-weight: 700;
}

.job-tags,
.drawer-tags,
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
  border: 1px solid rgba(24, 34, 47, 0.1);
  background: #fff;
  border-radius: 14px;
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
  border-radius: 18px;
  background: rgba(21, 32, 43, 0.03);
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
  border-radius: 18px;
  background: linear-gradient(180deg, #18222f, #304151);
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
  color: var(--green);
}

.tag-label.gap {
  background: rgba(217, 111, 50, 0.12);
  color: var(--orange);
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
  color: var(--green);
}

.signal.neutral {
  background: rgba(21, 32, 43, 0.06);
  color: var(--muted);
}

.board-card {
  position: sticky;
  top: 18px;
}

.board-block + .board-block {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}

.board-label {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.insight-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.insight-item {
  padding: 12px;
  border-radius: 16px;
  background: rgba(21, 32, 43, 0.04);
}

.insight-item strong {
  display: block;
  font-size: 18px;
}

.insight-item small {
  color: var(--muted);
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
  color: var(--muted);
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

.drawer-loading {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--muted);
}

.drawer-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.drawer-section + .drawer-section {
  margin-top: 18px;
}

.drawer-section h4 {
  margin: 0 0 10px;
}

.drawer-content {
  margin: 0;
  padding: 14px;
  border-radius: 16px;
  background: rgba(21, 32, 43, 0.04);
  white-space: pre-wrap;
  line-height: 1.7;
  font-family: inherit;
}

.explain-box {
  padding: 14px;
  border-radius: 16px;
  background: rgba(21, 32, 43, 0.04);
}

.explain-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.explain-list span {
  display: block;
  margin-top: 10px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--muted);
}

.compare-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.compare-card {
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, #fff, #f3f7ff);
  border: 1px solid var(--line);
}

.compare-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.compare-head h3 {
  margin: 0;
  font-size: 18px;
}

.compare-company {
  margin: 8px 0 0;
}

.compare-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.compare-meta span {
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(21, 32, 43, 0.05);
  font-size: 12px;
}

.compare-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.compare-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
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
  border-radius: 18px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.82);
}

.pipeline-stage-pill {
  text-align: left;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.pipeline-stage-pill strong,
.pipeline-summary-item strong {
  display: block;
  font-size: 24px;
}

.pipeline-stage-pill span,
.pipeline-summary-item span {
  color: var(--muted);
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
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(238, 244, 255, 0.92));
  border: 1px solid rgba(24, 34, 47, 0.08);
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
  color: var(--muted);
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
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--line);
  box-shadow: 0 10px 24px rgba(21, 32, 43, 0.05);
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
  color: var(--muted);
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
  .compare-grid,
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
  .market-page {
    padding-top: 8px;
  }

  .hero {
    padding: 16px;
  }

  .hero-title-row {
    padding: 16px;
  }

  .hero h1 {
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
  .drawer-header,
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

