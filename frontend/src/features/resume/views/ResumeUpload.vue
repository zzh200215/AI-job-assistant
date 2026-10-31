<template>
  <div class="page-shell resume-center">
    <ReturnToBanner />
    <PageHeader
      title="简历中心"
      subtitle="管理、诊断和优化你的简历，准备下一次投递。"
      eyebrow="求职资料"
    >
      <template #actions>
        <el-button v-if="selectedResume" @click="openCompareRow(selectedResume)">
          版本对比
        </el-button>
        <el-button :type="selectedResume ? 'default' : 'primary'" @click="showUpload = true">
          <el-icon><UploadFilled /></el-icon> 上传简历
        </el-button>
      </template>
    </PageHeader>

    <!-- 上传对话框 -->
    <el-dialog v-model="showUpload" title="上传简历" width="560px" :close-on-click-modal="false">
      <el-upload
        drag
        action="#"
        :http-request="customUpload"
        :show-file-list="false"
        :before-upload="beforeUpload"
        accept=".pdf,.docx,.doc,.png,.jpg,.jpeg"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 PDF / DOCX / 图片简历，大小不超过 10MB</div>
        </template>
      </el-upload>

      <div v-if="uploading" class="upload-progress">
        <el-steps class="upload-steps" :active="uploadStageIndex" finish-status="success" simple>
          <el-step title="上传" />
          <el-step title="解析" />
          <el-step title="诊断" />
        </el-steps>
        <el-progress
          v-if="uploadStage === 'uploading'"
          :percentage="uploadProgress"
          :stroke-width="10"
          :text-inside="true"
        />
        <p
          class="progress-text"
          :class="{ 'parse-progress': uploadStage === 'parsing' }"
          role="status"
        >
          <el-icon v-if="uploadStage === 'parsing'" class="is-loading"><Loading /></el-icon>
          {{ uploadStatus }}
        </p>
      </div>
      <div v-if="uploadError" class="upload-error">
        <el-alert :title="uploadError" type="error" :closable="false" show-icon />
      </div>
    </el-dialog>

    <!-- 解析结果弹窗 -->
    <el-dialog v-model="showParsed" title="简历解析结果" width="720px">
      <div v-if="currentParsed">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="姓名">{{
            maskedText(currentParsed.name, desensitized)
          }}</el-descriptions-item>
          <el-descriptions-item label="工作年限"
            >{{ currentParsed.years_exp || 0 }} 年</el-descriptions-item
          >
          <el-descriptions-item label="电话">{{
            maskedText(currentParsed.phone, desensitized)
          }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{
            maskedText(currentParsed.email, desensitized)
          }}</el-descriptions-item>
          <el-descriptions-item label="学历">{{
            currentParsed.education || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="专业">{{ currentParsed.major || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前公司" :span="2">{{
            currentParsed.current_company || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="当前职位" :span="2">{{
            currentParsed.current_title || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="技能" :span="2">
            <el-tag v-for="s in currentParsed.skills || []" :key="s" style="margin: 2px">{{
              s
            }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <h4 style="margin: 16px 0 8px">工作经历</h4>
        <el-timeline>
          <el-timeline-item
            v-for="(w, i) in currentParsed.work_experience || []"
            :key="i"
            :timestamp="`${w.start || ''} ~ ${w.end || ''}`"
          >
            <b>{{ w.company }} · {{ w.title }}</b>
            <div style="color: var(--app-muted); font-size: 12px">{{ w.desc }}</div>
          </el-timeline-item>
        </el-timeline>
      </div>
      <template #footer>
        <el-button @click="showParsed = false">关闭</el-button>
        <el-button type="primary" :disabled="!parsedResumeId" @click="diagnoseParsed">
          开始 AI 诊断
        </el-button>
      </template>
    </el-dialog>

    <!-- 分享链接弹窗 -->
    <el-dialog v-model="showShare" title="分享简历" width="480px">
      <div class="share-body">
        <p>将以下链接发送给 HR，对方即可查看你的简历详情。</p>
        <el-input ref="shareUrlRef" v-model="shareUrl" readonly :rows="3">
          <template #append>
            <el-button @click="copyShareUrl">复制链接</el-button>
          </template>
        </el-input>
        <div class="share-options">
          <el-checkbox v-model="shareDesensitized">分享时隐藏联系方式</el-checkbox>
        </div>
      </div>
    </el-dialog>

    <!-- AI 诊断报告弹窗 -->
    <el-dialog v-model="showDiagnosis" title="简历诊断报告" width="720px">
      <div v-if="diagnosisLoading" class="loading-state">
        <el-icon class="is-loading"><Loading /></el-icon> AI 诊断中...
      </div>
      <el-alert
        v-else-if="diagnosisError"
        type="error"
        :closable="false"
        show-icon
        :title="diagnosisError"
      />
      <div v-else-if="currentDiagnosis" class="diagnosis-body">
        <!-- 七维合计与逐维（满分各不相同，所以条与色调都按"拿到该维满皮的几成"画） -->
        <div class="diag-score-row">
          <div class="diag-score-gauge">
            <div class="gauge-ring">
              <svg viewBox="0 0 120 120" style="width: 100px; height: 100px">
                <circle
                  cx="60"
                  cy="60"
                  r="54"
                  fill="none"
                  stroke="var(--app-line)"
                  stroke-width="8"
                />
                <circle
                  cx="60"
                  cy="60"
                  r="54"
                  fill="none"
                  :stroke="diagScoreColor"
                  stroke-width="8"
                  :stroke-dasharray="`${(339.3 * (currentDiagnosis.total_score || 0)) / 100} 339.3`"
                  stroke-linecap="round"
                  transform="rotate(-90 60 60)"
                />
              </svg>
              <!-- 0 would read as a terrible score; say we do not know instead -->
              <span class="gauge-text">{{ currentDiagnosis.total_score ?? '未评分' }}</span>
            </div>
            <div class="diag-score-label">
              {{ currentDiagnosis.grade ? `${currentDiagnosis.grade} 级 · 七项合计` : '七项合计' }}
            </div>
          </div>
          <div class="diag-dims">
            <div v-for="dim in currentDiagnosis.dimensions" :key="dim.key" class="diag-dim-item">
              <div class="dim-label">
                <span>{{ dim.label }}</span>
                <strong :style="{ color: scoreToneTextColor(dimRate(dim)) }"
                  >{{ dim.score ?? '—' }} / {{ dim.full }}</strong
                >
              </div>
              <el-progress
                v-if="typeof dim.score === 'number'"
                :percentage="dimRate(dim)"
                :color="scoreToneColor(dimRate(dim))"
                :stroke-width="6"
              />
              <p v-else class="dim-none">本次分析未给出该项评分</p>
            </div>
          </div>
        </div>

        <p v-if="currentDiagnosis.verdict?.direction" class="diag-note">
          方向定位：{{ currentDiagnosis.verdict.direction }}
          <template v-if="currentDiagnosis.verdict.target_level">
            ｜目标等级：{{ currentDiagnosis.verdict.target_level }}</template
          >
          <template v-if="currentDiagnosis.report_date">
            ｜日期：{{ currentDiagnosis.report_date }}</template
          >
        </p>
        <p v-if="currentDiagnosis.grade_desc" class="diag-note">
          {{ currentDiagnosis.grade_scale }}。{{
            currentDiagnosis.grade_desc
          }}——分数代表的是现在这份简历的竞争力，不是你的能力上限。
        </p>

        <!-- 诊断详情 -->
        <el-collapse v-model="diagActivePanels" class="diag-details">
          <el-collapse-item title="七项待优化点" name="notes">
            <div v-if="dimensionNotes.length">
              <p v-for="dim in dimensionNotes" :key="dim.key" class="diag-issue">
                <el-icon><WarningFilled /></el-icon>
                <strong>{{ dim.label }}</strong
                >：{{ dim.note }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="本次分析没有逐项写出待优化点" />
          </el-collapse-item>
          <el-collapse-item title="距上一档还差什么" name="next">
            <div v-if="currentDiagnosis.to_next_grade?.length">
              <p
                v-for="(item, i) in currentDiagnosis.to_next_grade"
                :key="i"
                class="diag-issue diag-good"
              >
                <el-icon><CircleCheckFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="本次分析未给出升档项" />
          </el-collapse-item>
          <el-collapse-item title="关键词缺失" name="keywords">
            <div v-if="currentDiagnosis.missing_keywords?.length">
              <el-tag
                v-for="kw in currentDiagnosis.missing_keywords"
                :key="kw"
                type="warning"
                style="margin: 4px"
              >
                {{ kw }}
              </el-tag>
            </div>
            <el-empty v-else :image-size="60" description="本次分析未点名缺失关键词" />
          </el-collapse-item>
          <el-collapse-item title="竞争分析" name="competition">
            <div v-if="hasCompetition">
              <p class="diag-note">
                竞争力档位：<strong>{{ currentDiagnosis.competition.positioning_badge }}</strong>
              </p>
              <p v-if="currentDiagnosis.competition.positioning_note" class="diag-issue">
                {{ currentDiagnosis.competition.positioning_note }}
              </p>
              <p
                v-for="(item, i) in currentDiagnosis.competition.cards"
                :key="`c${i}`"
                class="diag-issue diag-good"
              >
                <el-icon><CircleCheckFilled /></el-icon> 能打的牌：{{ item }}
              </p>
              <p
                v-for="(item, i) in currentDiagnosis.competition.gaps"
                :key="`g${i}`"
                class="diag-issue"
              >
                <el-icon><WarningFilled /></el-icon> 要补的短板：{{ item }}
              </p>
              <p
                v-for="(item, i) in currentDiagnosis.competition.advice"
                :key="`a${i}`"
                class="diag-issue diag-good"
              >
                <el-icon><CircleCheckFilled /></el-icon> 针对性建议：{{ item }}
              </p>
              <p v-if="currentDiagnosis.competition.salary_note" class="diag-issue">
                期望薪资：{{ currentDiagnosis.competition.salary_note }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="本次分析未给出竞争分析" />
          </el-collapse-item>
          <el-collapse-item title="简历内容完整度（系统检查，非 AI）" name="completeness">
            <div v-if="currentDiagnosis.completeness_issues?.length">
              <p
                v-for="(item, i) in currentDiagnosis.completeness_issues"
                :key="i"
                class="diag-issue"
              >
                <el-icon><WarningFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="未检出缺失内容" />
          </el-collapse-item>
          <el-collapse-item name="rewrite">
            <template #title>
              <span>行级改写（原文 → 改后）</span>
              <span v-if="rewrite.items.length" class="rw-count"
                >{{ rewrite.items.length }} 条待处理</span
              >
            </template>

            <div class="rw-head">
              <el-button
                size="small"
                :loading="rewrite.loading"
                :disabled="!currentDiagnosis.resume_id"
                @click="generateRewrites"
              >
                {{ rewrite.loaded ? '重新生成建议' : '生成改写建议' }}
              </el-button>
              <span class="rw-hint"
                >建议只覆盖你已写过的文字，逐条决定采纳哪几条；未采纳的不会写进简历。</span
              >
            </div>

            <el-alert
              v-if="rewrite.error"
              type="error"
              :closable="false"
              show-icon
              :title="rewrite.error"
            />

            <div v-if="rewrite.loading" class="rw-loading">
              <el-icon class="is-loading"><Loading /></el-icon> 正在逐条比对可改写的文本…
            </div>

            <template v-else>
              <div v-for="item in rewrite.items" :key="item.block_id" class="rw-item">
                <div class="rw-item-head">
                  <el-checkbox v-model="item._accepted">采纳</el-checkbox>
                  <span class="rw-item-label">{{ item.label }}</span>
                  <el-tag
                    v-if="rewriteKindLabel(item.kind) !== item.label"
                    size="small"
                    effect="plain"
                  >
                    {{ rewriteKindLabel(item.kind) }}
                  </el-tag>
                </div>
                <div class="rw-compare">
                  <div class="rw-col">
                    <div class="rw-col-title">原文</div>
                    <p class="rw-text">{{ item.original }}</p>
                  </div>
                  <div class="rw-col">
                    <div class="rw-col-title">改后</div>
                    <p class="rw-text rw-text-new">{{ item.proposed_text }}</p>
                  </div>
                </div>
                <p v-if="item.reason" class="rw-reason">依据：{{ item.reason }}</p>
              </div>

              <el-empty
                v-if="rewrite.loaded && !rewrite.items.length"
                :image-size="60"
                description="没有可展示的改写建议"
              />

              <div v-if="rewrite.dropped.length" class="rw-dropped">
                有 {{ rewrite.dropped.length }} 条建议无法安全应用，已自动跳过。
              </div>

              <div v-if="acceptedRewrites.length || rewrite.result" class="rw-actions">
                <el-button
                  type="primary"
                  size="small"
                  :loading="rewrite.applying"
                  :disabled="!acceptedRewrites.length"
                  @click="applyRewrites"
                >
                  应用已采纳的 {{ acceptedRewrites.length }} 条
                </el-button>
                <!-- 快照从 B1.3 就在写，按钮到今天才有 -->
                <el-button
                  v-if="rewrite.snapshotId"
                  size="small"
                  type="warning"
                  plain
                  :loading="rewrite.applying"
                  @click="revertRewrite"
                >
                  {{ rewrite.lastAction === 'reverted' ? '撤销这次撤销' : '撤销这次应用' }}
                </el-button>
                <span v-if="rewriteScoreLine" class="rw-score">{{ rewriteScoreLine }}</span>
                <span v-else-if="rewrite.result?.changed" class="rw-score">
                  未指定目标岗位，本次不显示匹配分变化
                </span>
              </div>

              <p v-if="diagnosisStale" class="diag-note">
                简历内容已更新，上方的各项评分仍是改写前的结果；关闭后重新打开诊断即可刷新。
              </p>
            </template>
          </el-collapse-item>
        </el-collapse>
      </div>
      <div v-else class="empty-state">
        <el-empty :image-size="80" description="暂无诊断数据，请先解析简历" />
      </div>
    </el-dialog>

    <!-- AI 优化弹窗 -->
    <el-dialog v-model="showOptimize" title="AI 优化简历" width="480px">
      <p class="optimize-copy">选择目标岗位后，优化会更有针对性；不选则做通用优化。</p>
      <el-select
        v-model="optimizeJdId"
        clearable
        filterable
        placeholder="选择目标岗位（可选）"
        :loading="optimizeJdLoading"
        class="optimize-select"
      >
        <el-option
          v-for="jd in optimizeJdOptions"
          :key="jd.id"
          :label="jdLabel(jd)"
          :value="jd.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="showOptimize = false">取消</el-button>
        <el-button type="primary" :loading="optimizeSubmitting" @click="confirmOptimize">
          开始优化
        </el-button>
      </template>
    </el-dialog>

    <!-- 简历工作台 -->
    <div v-if="listLoading" class="resume-workspace resume-workspace--loading">
      <aside class="resume-list">
        <div class="resume-list-head"><strong>我的简历</strong><span>读取中…</span></div>
        <div v-for="i in 3" :key="i" class="resume-list-skeleton">
          <div class="app-skeleton" style="height: 14px; width: 62%" />
          <div class="app-skeleton" style="height: 10px; width: 78%; margin-top: 8px" />
          <div class="app-skeleton" style="height: 24px; width: 100%; margin-top: 12px" />
        </div>
      </aside>
      <section class="resume-detail">
        <div class="resume-detail-head">
          <div class="app-skeleton" style="height: 26px; width: 180px" />
        </div>
        <div class="resume-detail-body">
          <div class="resume-preview"><div class="app-skeleton" style="height: 460px" /></div>
          <aside class="resume-audit">
            <div class="app-skeleton" style="height: 72px; width: 72px; border-radius: 50%" />
            <div class="app-skeleton" style="height: 14px; width: 70%; margin-top: 16px" />
            <div class="app-skeleton" style="height: 14px; width: 55%; margin-top: 10px" />
          </aside>
        </div>
      </section>
    </div>

    <div v-else-if="listError" class="app-inline-error">
      <span>{{ listError }}</span>
      <el-button size="small" text type="primary" @click="loadList">重新加载</el-button>
    </div>

    <EmptyState
      v-else-if="!resumes.length"
      :icon="Document"
      title="还没有简历"
      description="上传一份简历，我们会先做解析和内容完整度检查。"
    >
      <template #action>
        <button type="button" class="app-link" @click="showUpload = true">上传一份简历</button>
      </template>
    </EmptyState>

    <div v-else class="resume-workspace">
      <aside class="resume-list">
        <div class="resume-list-head">
          <strong>我的简历</strong>
          <span>{{ resumes.length }} 个版本</span>
        </div>
        <button
          v-for="r in resumes"
          :key="r.id"
          type="button"
          class="resume-list-item"
          :class="{ 'is-active': r.id === selectedResumeId, 'is-default': isDefaultResume(r) }"
          @click="selectResume(r)"
        >
          <span class="resume-doc">{{ fileTypeLabel(r) }}</span>
          <span class="resume-list-main">
            <span class="resume-list-title">
              <strong>{{ resumeTitle(r) }}</strong>
              <span v-if="isDefaultResume(r)" class="resume-default">默认</span>
            </span>
            <span class="resume-list-sub">
              {{ r.parsed?.current_title || '尚未解析' }} · {{ monthDay(r.create_time) }}
            </span>
            <span class="resume-list-score">
              <span class="resume-score-track">
                <i
                  v-if="scoreOf(r) !== null"
                  class="score-fill"
                  :style="{ width: scoreOf(r) + '%' }"
                  :class="scoreToneFillClass(scoreOf(r))"
                />
              </span>
              <b :class="scoreOf(r) !== null ? scoreToneClass(scoreOf(r)) : ''">
                {{ scoreOf(r) ?? (r._scoring ? '…' : '—') }}
              </b>
            </span>
          </span>
        </button>
        <div class="resume-list-foot">
          <el-button @click="showUpload = true">上传新版本</el-button>
        </div>
      </aside>

      <section v-if="selectedResume" class="resume-detail">
        <header class="resume-detail-head">
          <div class="resume-detail-copy">
            <div class="resume-detail-title">
              <h2>{{ resumeTitle(selectedResume) }}</h2>
              <el-tag
                v-if="isDefaultResume(selectedResume)"
                size="small"
                type="primary"
                effect="light"
                >默认</el-tag
              >
              <el-tag v-if="hasParsed(selectedResume)" size="small" type="success" effect="light"
                >已解析</el-tag
              >
              <el-tag v-else size="small" type="warning" effect="light">待解析</el-tag>
              <el-tag v-if="selectedVersionCount" size="small" type="info" effect="plain">
                版本 {{ selectedVersionCount }}
              </el-tag>
            </div>
            <p class="resume-detail-sub">
              {{ fileTypeLabel(selectedResume) }} · {{ formatSize(selectedResume.file_size) }} ·
              {{ monthDay(selectedResume.create_time) }} 更新
            </p>
          </div>
          <div class="resume-detail-actions">
            <el-button
              v-if="hasParsed(selectedResume)"
              size="small"
              @click="handleCmd('diagnose', selectedResume)"
            >
              优化建议
            </el-button>
            <el-dropdown trigger="click" @command="(cmd) => handleCmd(cmd, selectedResume)">
              <button class="more-button" type="button" aria-label="更多操作">
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="parse">{{
                    hasParsed(selectedResume) ? '重新解析' : '解析简历'
                  }}</el-dropdown-item>
                  <el-dropdown-item command="optimize">AI 优化</el-dropdown-item>
                  <el-dropdown-item command="diagnose">AI 诊断</el-dropdown-item>
                  <el-dropdown-item command="report" divided>评估报告</el-dropdown-item>
                  <el-dropdown-item command="project">项目分析</el-dropdown-item>
                  <el-dropdown-item command="portfolio">组合分析</el-dropdown-item>
                  <el-dropdown-item command="compare">版本对比</el-dropdown-item>
                  <el-dropdown-item
                    v-if="!isDefaultResume(selectedResume)"
                    command="setDefault"
                    divided
                    >设为默认</el-dropdown-item
                  >
                  <el-dropdown-item command="share" :divided="isDefaultResume(selectedResume)"
                    >分享链接</el-dropdown-item
                  >
                  <el-dropdown-item command="desensitize">{{
                    selectedResume._desensitized ? '取消脱敏' : '脱敏设置'
                  }}</el-dropdown-item>
                  <el-dropdown-item command="exportDocx">导出 Word</el-dropdown-item>
                  <el-dropdown-item command="exportPdf">导出 PDF</el-dropdown-item>
                  <el-dropdown-item
                    command="delete"
                    divided
                    style="color: color-mix(in srgb, var(--app-danger), black 20%)"
                    >删除</el-dropdown-item
                  >
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-if="hasParsed(selectedResume)"
              type="primary"
              size="small"
              @click="goAnalysis(selectedResume)"
              >去分析</el-button
            >
            <el-button v-else type="primary" size="small" @click="parseResumeRow(selectedResume)">
              解析简历
            </el-button>
          </div>
        </header>

        <div class="resume-detail-body">
          <div class="resume-preview">
            <el-alert
              v-if="parseDegraded(selectedResume)"
              class="resume-alert"
              type="warning"
              title="解析不完整，建议检查原文格式"
              :closable="false"
              show-icon
            />
            <p v-if="parseDropped(selectedResume).length" class="resume-parse-note">
              有 {{ parseDropped(selectedResume).length }} 段内容未纳入解析（{{
                parseDropped(selectedResume).join('、')
              }}），建议检查原文格式
            </p>
            <article class="resume-paper" :class="{ 'is-empty': !hasParsed(selectedResume) }">
              <template v-if="hasParsed(selectedResume)">
                <div class="paper-head">
                  <strong class="paper-name">{{ selectedParsed.name || '未命名' }}</strong>
                  <span class="paper-role">
                    {{
                      [
                        selectedParsed.current_title,
                        selectedParsed.years_exp ? `${selectedParsed.years_exp} 年经验` : '',
                        selectedParsed.location,
                      ]
                        .filter(Boolean)
                        .join(' · ')
                    }}
                  </span>
                  <span v-if="maskedContact(selectedParsed)" class="paper-contact">
                    {{ maskedContact(selectedParsed) }}
                  </span>
                </div>
                <div class="paper-rule" />

                <section v-if="selectedParsed.work_experience?.length" class="paper-section">
                  <h4>工作经历</h4>
                  <div
                    v-for="(work, i) in selectedParsed.work_experience"
                    :key="i"
                    class="paper-entry"
                  >
                    <div class="paper-entry-head">
                      <strong>{{ work.company || work.project || '—' }}</strong>
                      <span>{{ [work.start, work.end].filter(Boolean).join(' – ') }}</span>
                    </div>
                    <p v-if="work.title" class="paper-entry-role">{{ work.title }}</p>
                    <p v-if="work.desc" class="paper-entry-desc">{{ work.desc }}</p>
                  </div>
                </section>

                <section v-if="selectedParsed.project_experience?.length" class="paper-section">
                  <h4>项目经历</h4>
                  <div
                    v-for="(project, i) in selectedParsed.project_experience"
                    :key="i"
                    class="paper-entry"
                  >
                    <div class="paper-entry-head">
                      <strong>{{ project.name || project.title || '项目' }}</strong>
                      <span>{{ [project.start, project.end].filter(Boolean).join(' – ') }}</span>
                    </div>
                    <p v-if="project.role" class="paper-entry-role">{{ project.role }}</p>
                    <p v-if="project.desc" class="paper-entry-desc">{{ project.desc }}</p>
                  </div>
                </section>

                <section
                  v-if="selectedParsed.education || selectedParsed.major"
                  class="paper-section"
                >
                  <h4>教育经历</h4>
                  <p class="paper-entry-desc">
                    {{
                      [selectedParsed.education, selectedParsed.major].filter(Boolean).join(' · ')
                    }}
                  </p>
                </section>

                <section v-if="selectedParsed.skills?.length" class="paper-section">
                  <h4>技能</h4>
                  <div class="paper-skills">
                    <span v-for="skill in selectedParsed.skills" :key="skill">{{ skill }}</span>
                  </div>
                </section>

                <section v-if="selectedParsed.self_evaluation" class="paper-section">
                  <h4>自我评价</h4>
                  <p class="paper-entry-desc">{{ selectedParsed.self_evaluation }}</p>
                </section>
              </template>

              <div v-else class="paper-empty">
                <el-icon :size="28"><Document /></el-icon>
                <strong>这份简历还没有解析</strong>
                <p>解析后才能生成文档预览、完整度检查和匹配分析。</p>
                <el-button size="small" type="primary" @click="parseResumeRow(selectedResume)">
                  解析简历
                </el-button>
              </div>
            </article>
          </div>

          <aside class="resume-audit">
            <div class="audit-score">
              <ScoreRing :score="selectedScore" :size="72" :stroke-width="6" />
              <div class="audit-score-copy">
                <strong>{{
                  selectedScore !== null ? `完整度 ${selectedGrade || ''}` : '还没有体检'
                }}</strong>
                <span>{{
                  selectedScore !== null ? '系统检查结果，不是 AI 评分' : '解析后自动检查'
                }}</span>
              </div>
            </div>

            <template v-if="selectedCompleteness">
              <h3>待优化</h3>
              <div v-if="selectedIssues.length" class="audit-issues">
                <div v-for="(issue, i) in selectedIssues" :key="i" class="audit-issue">
                  <i>!</i><span>{{ issue }}</span>
                </div>
              </div>
              <p v-else class="audit-empty">本次检查没有发现明显缺失。</p>

              <h3>内容检查</h3>
              <div class="audit-checks">
                <div
                  v-for="item in moduleChecklist"
                  :key="item.key"
                  class="audit-check"
                  :class="{ 'is-done': item.done }"
                >
                  <i>{{ item.done ? '✓' : '!' }}</i
                  ><span>{{ item.label }}</span>
                </div>
              </div>
            </template>
            <p v-else class="audit-empty">解析完成后，这里会给出完整度和缺失项。</p>

            <div class="audit-target">
              <span>下一步</span>
              <strong>{{
                hasParsed(selectedResume) ? '用这份简历做一次匹配分析' : '先解析这份简历'
              }}</strong>
              <button
                type="button"
                class="app-link"
                @click="
                  hasParsed(selectedResume)
                    ? goAnalysis(selectedResume)
                    : parseResumeRow(selectedResume)
                "
              >
                {{ hasParsed(selectedResume) ? '去分析' : '解析简历' }}
              </button>
            </div>
            <p v-if="selectedVersionCount" class="audit-version">
              版本历史 {{ selectedVersionCount }} 个
            </p>
          </aside>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { userErrorCopy } from '@/utils/requestTracing'
import { computed, reactive, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { createAgentTaskPoller } from '@/utils/agentTaskPolling'
import ReturnToBanner from '@/components/ui/ReturnToBanner.vue'
import {
  UploadFilled,
  MoreFilled,
  Document,
  Loading,
  WarningFilled,
  CircleCheckFilled,
} from '@element-plus/icons-vue'
import { useLatestCall } from '@/composables/useLatestCall'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import ScoreRing from '@/components/ui/ScoreRing.vue'
import {
  uploadResume,
  parseResume,
  getResumeList,
  getResumeVersions,
  getResumeQuickScore,
  diagnoseResume,
  createRewriteSuggestionJob,
  getRewriteSuggestionJob,
  applyResumeRewrites,
  revertResumeRewrite,
  deleteResume,
  generateOptimized,
  exportResume,
  downloadResumeExport,
} from '@/api/resume'
import { getJDList } from '@/api/jd'
import {
  scoreToneClass,
  scoreToneColor,
  // 分数当文字读的那一处走文字档 token
  scoreToneTextColor,
  scoreToneFillClass,
} from '@/utils/scoreTone'
import { monthDay } from '@/utils/format/date'
import { useSelectionStore } from '@/stores/selection'
const selection = useSelectionStore()

const router = useRouter()

const showUpload = ref(false)
const showParsed = ref(false)
const showShare = ref(false)
const showDiagnosis = ref(false)
const showOptimize = ref(false)
const optimizeResumeRow = ref(null)
const optimizeJdId = ref(null)
const optimizeJdOptions = ref([])
const optimizeJdLoading = ref(false)
const optimizeSubmitting = ref(false)
const currentParsed = ref(null)
const parsedResumeId = ref(null)
const listLoading = ref(true)
const resumes = ref([])
const listError = ref('')
const defaultResumeId = ref(null)
const selectedResumeId = ref(null)
const go = (path) => router.push(path)

const uploading = ref(false)
const uploadProgress = ref(0)
const uploadStatus = ref('')
const uploadError = ref('')
// 上传与解析共用 uploading；这个字段只负责把"现在卡在哪一步"说清楚。
const uploadStage = ref('idle')
const uploadStageIndex = computed(() => {
  if (uploadStage.value === 'parsing') return 1
  if (uploadStage.value === 'parsed') return 2
  if (uploadStage.value === 'error') return uploadProgress.value >= 100 ? 1 : 0
  return 0
})

// 分享
const shareUrl = ref('')
const shareDesensitized = ref(false)
const currentShareResume = ref(null)

// 诊断
const diagnosisLoading = ref(false)
const diagnosisError = ref('')
const currentDiagnosis = ref(null)
// 关掉弹窗不会取消已发出的诊断，再看另一份简历时旧响应会给错人打分
const latestDiagnosisCall = useLatestCall()
const latestParseCall = useLatestCall()
const diagnosisStale = ref(false)
const diagActivePanels = ref(['structure', 'expression', 'keywords', 'highlights'])

// 行级改写（B1）：建议只在打开面板后按需生成，采纳才写回简历
const rewrite = reactive({
  loading: false,
  applying: false,
  error: '',
  loaded: false,
  items: [],
  dropped: [],
  result: null,
  /* B1 的撤销：`snapshot_version_id` 从 B1.3 起就在返回，但一直没人在这里接住它，
     所以后端存的那份改写前原文从没被读回来过。`lastAction` 只决定按钮上那两个字。 */
  snapshotId: null,
  lastAction: '',
})

function rewriteKindLabel(kind) {
  return (
    { skills: '技能', self_evaluation: '自我评价', work: '工作经历', project: '项目经历' }[kind] ||
    kind
  )
}

const acceptedRewrites = computed(() => rewrite.items.filter((item) => item._accepted))

const rewriteScoreLine = computed(() => {
  const score = rewrite.result?.score
  const before = score?.before?.score
  const after = score?.after?.score
  if (typeof before !== 'number' || typeof after !== 'number') return ''
  return `匹配分 ${before} → ${after}`
})

/* 改写建议的轮询：**复用**那条既有的 `createAgentTaskPoller`，不另写第二个轮询器。
   这个作业没有分步日志（它就是一次模型调用），所以 `getAgentSteps` 给一个空数组——
   那条链的 `steps` 只喂 `onProgress`，这里没人用它。
   预算 = 75 × 2000ms = 150 秒，与被它替掉的那条 per-request 超时同一个数；不一样的是
   这 150 秒里浏览器没有挂着的请求、服务端也没有占着 anyio 那 20 根线程中的一根。 */
const REWRITE_JOB_POLL_INTERVAL_MS = 2000
const REWRITE_JOB_POLL_MAX_ATTEMPTS = 75

const rewritePoller = createAgentTaskPoller(
  {
    getAgentTask: (jobId) => getRewriteSuggestionJob(jobId),
    getAgentSteps: async () => ({ steps: [] }),
  },
  {
    // 卸载即落地：不打开的话 `stopPolling()` 只清表，那个 `await` 永不返回、下面 `finally`
    // 里的 `loading = false` 也永不执行（D204 量到的）。默认关闭，这里按需要开。
    rejectOnStop: true,
    setPollingState(value) {
      // 与"应用/撤销"共用同一把 `applying` 之外，这一位只管按钮上那个 spinner。
      rewrite.loading = value
    },
  }
)

onUnmounted(() => rewritePoller.stopPolling())

async function generateRewrites() {
  const resumeId = currentDiagnosis.value?.resume_id
  if (!resumeId || rewrite.loading) return
  rewrite.error = ''
  rewrite.result = null
  rewrite.snapshotId = null
  rewrite.lastAction = ''
  rewrite.items = []
  rewrite.dropped = []
  try {
    rewrite.loading = true
    const created = await createRewriteSuggestionJob(
      resumeId,
      currentDiagnosis.value?.jd_id || null
    )
    const job = await rewritePoller.pollTask(created.job_id, {
      maxPollCount: REWRITE_JOB_POLL_MAX_ATTEMPTS,
      intervalMs: REWRITE_JOB_POLL_INTERVAL_MS,
      timeoutMessage: '改写建议这次没跑完，稍后再试',
      // 轮询器失败那一支会优先念载荷里那句"服务端写的失败原因"；作业端点**不给**那个键
      // （它可能带模型返回的原文），所以这里这句通用措辞就是候选人实际看到的那一句。
      failedMessage: '改写建议这次没生成成功，稍后再试',
    })
    rewrite.items = (job?.suggestions || []).map((s) => ({ ...s, _accepted: true }))
    rewrite.dropped = job?.rejected || []
    rewrite.loaded = true
    if (!rewrite.items.length) {
      ElMessage.info(job?.note || '这次没有给出可用的改写，可以再问一次')
    }
  } catch (e) {
    rewrite.items = []
    rewrite.dropped = []
    rewrite.error = userErrorCopy(e, '改写建议生成失败')
  } finally {
    rewrite.loading = false
  }
}

async function applyRewrites() {
  const resumeId = currentDiagnosis.value?.resume_id
  const edits = acceptedRewrites.value.map((s) => ({
    block_id: s.block_id,
    proposed_text: s.proposed_text,
    expected_original: s.original,
  }))
  if (!resumeId || !edits.length || rewrite.applying) return

  rewrite.applying = true
  rewrite.error = ''
  try {
    const data = await applyResumeRewrites(resumeId, edits, currentDiagnosis.value?.jd_id || null)
    rewrite.result = data
    // 撤销的入口只跟着"真的改了"这一步出现；被拒的那些没有覆盖任何原文，也就没有东西可撤
    rewrite.snapshotId = data?.changed ? (data?.snapshot_version_id ?? null) : null
    rewrite.lastAction = data?.changed ? 'applied' : ''
    // Only the rows that actually landed leave the list; refused ones stay with
    // their reason, so a no-op cannot read as success.
    const appliedIds = new Set((data?.applied || []).map((a) => a.block_id))
    rewrite.items = rewrite.items.filter((s) => !appliedIds.has(s.block_id))
    rewrite.dropped = data?.rejected || []
    if (data?.changed) {
      diagnosisStale.value = true
      ElMessage.success(`已应用 ${appliedIds.size} 处改写，简历已更新`)
    } else {
      ElMessage.warning('没有改动被应用')
    }
  } catch (e) {
    rewrite.error = userErrorCopy(e, '应用改写失败')
  } finally {
    rewrite.applying = false
  }
}

/* B1 的撤销。三件事值得写下来：
   1. 复用 `rewrite.applying` 这一把锁，不给撤销另立一个 busy 位。"应用"与"撤销"写的是同一坨
      `parsed_json`，两个按钮各自一把锁就是允许它们并发；服务端虽然逐块校验过当前文本，
      但那只会把后发的那次变成一次拒绝，界面上不该出现那一幕。
   2. 撤销被拒是 code 0 + `stale_blocks`，不是错误：候选人应用之后自己又改过那几块时，
      吃掉他们后写的文字才是事故，所以整单不动，只把那几处的种类说出来（block_id 是
      `work[0].desc` 这种锚点，候选人读不懂，所以要的是 kind）。
   3. 撤销成功后按钮不消失，改成"撤销这次撤销"：服务端把撤销前那一刻又存了一份快照，
      撤销因此不是这个流程里的第二个不可逆动作。 */
async function revertRewrite() {
  const resumeId = currentDiagnosis.value?.resume_id
  if (!resumeId || !rewrite.snapshotId || rewrite.applying) return

  rewrite.applying = true
  rewrite.error = ''
  try {
    const data = await revertResumeRewrite(resumeId, rewrite.snapshotId)
    if (!data?.changed) {
      const kinds = (data?.stale_blocks || []).map((item) => rewriteKindLabel(item.kind))
      rewrite.error = kinds.length
        ? `「${[...new Set(kinds)].join('、')}」在应用之后又被改过，整单撤销没有执行`
        : '这次撤销没有可恢复的内容'
      return
    }
    rewrite.result = data
    rewrite.snapshotId = data?.undo_version_id ?? null
    rewrite.lastAction = 'reverted'
    diagnosisStale.value = true
    ElMessage.success(`已撤销 ${(data?.restored_blocks || []).length} 处改写，简历已恢复`)
  } catch (e) {
    rewrite.error = userErrorCopy(e, '撤销改写失败')
  } finally {
    rewrite.applying = false
  }
}

// 脱敏
const desensitized = ref(false)

/* 默认版本走 `utils/lastSelection`：与 lastResumeId 同一套按登录用户分槽的机制（D102）。
   顺序是"默认 → 最近 → 提示"：存过的默认还在就用它；否则自动选最近更新的一份并记住，
   不让候选人每次进来都先做一次选择。 */
function isDefaultResume(r) {
  return r.id === defaultResumeId.value
}

function ensureDefaultResume(items) {
  if (!items.length) return
  if (items.some((item) => item.id === defaultResumeId.value)) return
  const recent = [...items].sort(
    (a, b) => new Date(b.create_time || 0).getTime() - new Date(a.create_time || 0).getTime()
  )[0]
  if (!recent) return
  defaultResumeId.value = recent.id
  selection.rememberDefaultResume(recent.id)
}

const HEX_FILE = /^[0-9a-f-]{16,}$/i

function displayFileName(r) {
  return r.name || r.file_name || ''
}

/* 存储名可能是 UUID（历史数据或自动化上传留下的），直接上屏就是一行机器串。
   优先用原文件名（去掉扩展名）；UUID 才退回解析出来的姓名/职位，最后才用日期兜底。 */
function resumeTitle(r) {
  const raw = displayFileName(r)
  const base = raw.replace(/\.[^.]+$/, '')
  if (base && !HEX_FILE.test(base)) return base
  if (r.parsed?.name) return `${r.parsed.name}的简历`
  if (r.parsed?.current_title) return `${r.parsed.current_title}简历`
  return `我的简历 · ${monthDay(r.create_time)}`
}

const selectedResume = computed(
  () => resumes.value.find((item) => item.id === selectedResumeId.value) || resumes.value[0] || null
)
const selectedParsed = computed(() => selectedResume.value?.parsed || {})
const selectedCompleteness = computed(() => selectedResume.value?._completeness || null)
const selectedScore = computed(() => scoreOf(selectedResume.value))
const selectedGrade = computed(() => selectedCompleteness.value?.completeness_grade || '')
const selectedVersionCount = computed(() => selectedResume.value?._versionCount || 0)
const selectedIssues = computed(() =>
  (selectedCompleteness.value?.issues || [])
    .map((item) => (typeof item === 'string' ? item : item?.title || item?.message || ''))
    .filter(Boolean)
)

const MODULE_LABELS = {
  basic_info: '基本信息',
  work_experience: '工作经历',
  projects: '项目经历',
  skills: '技能标签',
  education: '教育经历',
  summary: '自我评价',
}
const moduleChecklist = computed(() => {
  const check = selectedCompleteness.value?.module_check
  if (!check) return []
  return Object.entries(MODULE_LABELS).map(([key, label]) => ({
    key,
    label,
    done: Boolean(check[key]),
  }))
})

function hasParsed(r) {
  return Boolean(r?.parsed && Object.keys(r.parsed).length)
}

function scoreOf(r) {
  const value = r?._completeness?.completeness_score
  return Number.isFinite(Number(value)) ? Number(value) : null
}

function fileTypeLabel(r) {
  return (r?.file_type || '').toUpperCase() || '文档'
}

function selectResume(r) {
  selectedResumeId.value = r.id
}

function maskedContact(parsed) {
  const values = [parsed?.phone, parsed?.email]
    .map((value) => maskedText(value, selectedResume.value?._desensitized))
    .filter((value) => value && value !== '-')
  return values.join(' · ')
}

function ensureSelectedResume(items) {
  if (!items.length) {
    selectedResumeId.value = null
    return
  }
  if (!items.some((item) => item.id === selectedResumeId.value)) {
    selectedResumeId.value = defaultResumeId.value || items[0].id
  }
}

onMounted(() => {
  defaultResumeId.value = selection.defaultResumeId()
  selectedResumeId.value = defaultResumeId.value
  loadList()
})

/* 七维的满分各不相同（5 到 20），所以色调与进度条都按"拿到该维满皮的几成"算：
   直接拿原始分上色，个人优势那一档最高也只有 5 分，会被读成一个大红项。 */
function dimRate(dim) {
  if (typeof dim?.score !== 'number' || !dim?.full) return 0
  return Math.round((dim.score / dim.full) * 100)
}

const dimensionNotes = computed(() =>
  (currentDiagnosis.value?.dimensions || []).filter((dim) => dim.note)
)

const hasCompetition = computed(() => {
  const c = currentDiagnosis.value?.competition
  if (!c) return false
  return Boolean(
    c.positioning_badge ||
    c.positioning_note ||
    c.cards?.length ||
    c.gaps?.length ||
    c.advice?.length ||
    c.salary_note
  )
})

function formatSize(n) {
  if (!n) return '-'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(2) + ' MB'
}

// 诊断分标签只有两档：至少到 good 档才算 success，其余 warning。
// 分界交给 scoreTone 的 85/70/50，不再在本页抄一份 70。

/* 解析质量提示的取数处。两个判据都只读后端 `_meta`，那两个标记由
   `app/services/parse_guard.py` 独家盖——前端不重推"这份是不是被截断了"。 */
const parseDropped = (r) => r.parsed?._meta?.truncation?.dropped_sections || []
const parseDegraded = (r) => Boolean(r.parsed?._meta?.parse_degraded)

const diagScoreColor = 'var(--app-primary)'

function maskedText(val, mask) {
  if (!mask || !val) return val || '-'
  if (typeof val !== 'string') return val
  if (val.length <= 3) return val[0] + '***'
  return val.slice(0, 2) + '****' + val.slice(-2)
}

async function loadList() {
  listLoading.value = true
  try {
    const data = await getResumeList({ page: 1, page_size: 50 })
    const items = data?.items || []
    // attach local state
    items.forEach((r) => {
      r._completeness = null
      r._scoring = false
      r._desensitized = false
      r._versionCount = undefined
      r._diagnosisScore = null
    })
    resumes.value = items
    ensureDefaultResume(items)
    ensureSelectedResume(items)

    // auto load quick scores & version counts（遍历 ref 里的代理对象：
    // 直接改 items 的裸对象不会触发 Vue 更新，列表会永远停在"读取中"）
    resumes.value.forEach((r) => {
      quickScore(r)
      loadVersionCount(r)
    })
    listError.value = ''
  } catch (error) {
    listError.value = error?.userMessage || '暂时无法获取简历列表，请检查网络后重试。'
  } finally {
    listLoading.value = false
  }
}

async function loadVersionCount(r) {
  try {
    const versions = await getResumeVersions(r.id)
    r._versionCount = Array.isArray(versions?.versions) ? versions.versions.length : 0
  } catch {
    // 数不出来是"不知道"，不是"0 个版本"：卡片上不写数字，也不写 0
    r._versionCount = null
  }
}

async function quickScore(r) {
  if (r._completeness || r._scoring) return
  r._scoring = true
  try {
    const score = await getResumeQuickScore(r.id, { notifyError: false })
    if (score?.completeness_score !== undefined) {
      r._completeness = score
    }
  } catch {
    // 列表仍可使用，评分卡保留为空。
  } finally {
    r._scoring = false
  }
}

const beforeUpload = (file) => {
  const ext = file.name.split('.').pop().toLowerCase()
  if (!['pdf', 'docx', 'doc', 'png', 'jpg', 'jpeg'].includes(ext)) {
    ElMessage.error('仅支持 PDF / DOCX / 图片简历')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('文件超过 10MB')
    return false
  }
  return true
}

const customUpload = async ({ file }) => {
  uploading.value = true
  uploadProgress.value = 0
  uploadStatus.value = '正在上传文件…'
  uploadError.value = ''
  uploadStage.value = 'uploading'
  parsedResumeId.value = null

  try {
    const data = await uploadResume(file, (event) => {
      const loaded = Number(event?.loaded || 0)
      const total = Number(event?.total || file.size || 0)
      const ratio = total > 0 ? loaded / total : 0
      uploadProgress.value = Math.max(0, Math.min(100, Math.round(ratio * 100)))
    })

    uploadStage.value = 'parsing'
    uploadStatus.value = '上传完成，正在解析简历…'
    uploadProgress.value = 100

    const parsed = await parseResume(data.id)
    uploadStage.value = 'parsed'
    currentParsed.value = parsed.parsed
    parsedResumeId.value = data.id
    showParsed.value = true
    ElMessage.success('解析完成，可在卡片上点 AI 诊断')
    showUpload.value = false
    await loadList()
  } catch (e) {
    const failedStage = uploadStage.value
    uploadStage.value = 'error'
    uploadError.value = userErrorCopy(
      e,
      failedStage === 'parsing' ? '解析失败，请稍后在简历卡片上重试' : '上传失败'
    )
  } finally {
    uploading.value = false
  }
}

// ---- 行下拉的 12 个命令：一个分支一个函数，再由 handleCmd 查表派发 ----
/* 原来 11 个分支共用一个函数体，D32 要给「解析」加竞态令牌时卡在这里：令牌得按分支领，
   而分支们挤在同一个 if-else 链里，谁都说不清自己那一份的意图边界。拆开之后每个分支都能
   单独决定自己要不要令牌——现在只有 parse 需要（它写的是全局唯一的那个抽屉）。 */
async function parseResumeRow(r) {
  const isCurrent = latestParseCall()
  try {
    const parsed = await parseResume(r.id)
    // 这一行自己的解析结果是真的，不因为用户后来点了别的行而作废（D29 分的正是这两类）
    r.parsed = parsed.parsed
    if (!isCurrent()) return
    currentParsed.value = parsed.parsed
    parsedResumeId.value = r.id
    showParsed.value = true
    ElMessage.success('解析成功')
  } catch {
    if (!isCurrent()) return
    ElMessage.error('解析失败')
  }
}

function setDefaultResumeRow(r) {
  defaultResumeId.value = r.id
  selectedResumeId.value = r.id
  selection.rememberDefaultResume(r.id)
  ElMessage.success('已设为默认简历')
}

function toggleDesensitizeRow(r) {
  r._desensitized = !r._desensitized
  ElMessage.success(r._desensitized ? '已脱敏，联系方式已隐藏' : '已取消脱敏')
}

function openCompareRow(r) {
  router.push(`/resume/compare/${r.id}`)
}

/* 六模块评估报告是**另一条链**（异步作业 + 轮询），不在这个弹窗里嵌第二套渲染：
   那一页拿到 resume_id 后自己决定是接住已有作业还是新建一次。 */
function openReportRow(r) {
  router.push({ name: 'resume-report', query: { resume_id: r.id } })
}

/* 单项目分析也是另一条链（异步作业 + 轮询），量程是**一个项目**：
   带 resume_id 过去，那一页自己读项目列表、挑第几个、拼位次。 */
function openProjectRow(r) {
  router.push({ name: 'project-report', query: { resume_id: r.id } })
}

// 组合分析（四大节，量的是一组项目叠在一起）：不带 project_index，
// 进页面后再勾"哪几个项目放在一起看"，默认全选。
function openPortfolioRow(r) {
  router.push({ name: 'portfolio-report', query: { resume_id: r.id } })
}

const ROW_COMMANDS = {
  parse: parseResumeRow,
  optimize: optimizeResume,
  diagnose: showDiagnosisDialog,
  report: openReportRow,
  project: openProjectRow,
  portfolio: openPortfolioRow,
  compare: openCompareRow,
  setDefault: setDefaultResumeRow,
  share: showShareDialog,
  desensitize: toggleDesensitizeRow,
  exportDocx: (r) => doExport(r, 'docx'),
  exportPdf: (r) => doExport(r, 'pdf'),
  delete: async (r) => {
    try {
      await ElMessageBox.confirm('确定删除该简历？', '删除确认', { type: 'warning' })
      await deleteResume(r.id)
      ElMessage.success('已删除')
      await loadList()
    } catch {
      // 用户取消删除时不显示错误；请求失败由统一请求层提示。
    }
  },
}

async function handleCmd(cmd, r) {
  const run = ROW_COMMANDS[cmd]
  if (run) await run(r)
}

function goAnalysis(r) {
  selection.rememberResume(r.id)
  router.push('/smart-analysis')
}

function jdLabel(jd) {
  return [jd?.title, jd?.company].filter(Boolean).join(' · ') || '未命名岗位'
}

async function loadOptimizeJdOptions() {
  optimizeJdLoading.value = true
  try {
    const data = await getJDList({ page: 1, page_size: 100 })
    optimizeJdOptions.value = data?.items || []
  } catch (error) {
    optimizeJdOptions.value = []
    console.warn('读取岗位列表失败', error)
  } finally {
    optimizeJdLoading.value = false
  }
}

function optimizeResume(r) {
  optimizeResumeRow.value = r
  optimizeJdId.value = null
  showOptimize.value = true
  loadOptimizeJdOptions()
}

async function confirmOptimize() {
  const row = optimizeResumeRow.value
  if (!row || optimizeSubmitting.value) return
  optimizeSubmitting.value = true
  try {
    await generateOptimized(row.id, optimizeJdId.value || null)
    showOptimize.value = false
    ElMessage.success('优化完成')
  } catch (error) {
    console.warn('生成优化版简历失败', error)
  } finally {
    optimizeSubmitting.value = false
  }
}

async function doExport(r, format) {
  try {
    await exportResume(r.id, format, 'optimized')
    const blob = await downloadResumeExport(r.id, format, 'optimized')
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${r.name || r.file_name || 'resume'}_optimized.${format}`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

// ---- 分享功能 ----
function showShareDialog(r) {
  currentShareResume.value = r
  const baseUrl = window.location.origin
  shareUrl.value = `${baseUrl}/shared/resume/${r.id}?token=${Date.now()}`
  shareDesensitized.value = r._desensitized || false
  showShare.value = true
}

async function copyShareUrl() {
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    ElMessage.success('链接已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

// ---- AI 诊断 ----
function diagnoseParsed() {
  if (!parsedResumeId.value) return
  const resumeId = parsedResumeId.value
  showParsed.value = false
  showDiagnosisDialog({ id: resumeId, parsed: currentParsed.value })
}

async function showDiagnosisDialog(r) {
  const isCurrent = latestDiagnosisCall()
  showDiagnosis.value = true
  diagnosisLoading.value = true
  diagnosisError.value = ''
  diagnosisStale.value = false
  currentDiagnosis.value = null
  rewrite.loading = false
  rewrite.applying = false
  rewrite.error = ''
  rewrite.loaded = false
  rewrite.items = []
  rewrite.dropped = []
  rewrite.result = null

  let d = null
  try {
    d = await diagnoseResume(
      r.id,
      { target_position: r.parsed?.current_title || '' },
      { notifyError: false }
    )
  } catch {
    d = null
  }

  if (!isCurrent()) return
  if (!d) {
    // A diagnosis we could not compute must not be replaced with invented
    // numbers. The previous fallback derived five dimension scores from
    // `totalScore + Math.random()` and pushed a fixed keyword list, so a failed
    // request rendered as a confident, entirely fabricated report.
    diagnosisError.value = '诊断服务暂时不可用，未能获取该简历的分析结果。'
    diagnosisLoading.value = false
    return
  }

  currentDiagnosis.value = {
    resume_id: r.id,
    total_score: d.total_score ?? null,
    grade: d.grade ?? null,
    grade_desc: d.grade_desc || '',
    grade_scale: d.grade_scale || '',
    dimensions: Array.isArray(d.dimensions) ? d.dimensions : [],
    verdict: d.verdict || {},
    to_next_grade: d.to_next_grade || [],
    missing_keywords: d.missing_keywords || [],
    competition: d.competition || {},
    completeness_issues: d.completeness_issues || [],
    completeness_score: d.completeness_score ?? null,
    completeness_grade: d.completeness_grade ?? null,
    module_check: d.module_check || {},
    report_date: d.report_date || '',
    // /diagnose 打分的是**一个岗位名称字符串**，不是库里存的 JD：响应里没有 jd_id，
    // 也没有分析记录。这个字段只为行级改写接口保留"无目标 JD"的入参形状，
    // 不能拿来跳分析详情页（那条路由要的是 AnalysisRecord 的 id）。
    jd_id: d.jd_id ?? null,
  }
  r._diagnosisScore = d.total_score
  diagnosisLoading.value = false
}
</script>

<style scoped>
.resume-center {
  width: 100%;
  color: var(--app-text);
}

/* ===== Resume workspace ===== */
.resume-workspace {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  min-height: 680px;
  overflow: hidden;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
}

.resume-workspace--loading {
  grid-template-columns: 280px minmax(0, 1fr);
}

.resume-list {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid var(--app-line);
  background: color-mix(in srgb, var(--app-surface-muted), var(--app-surface-strong) 45%);
}

.resume-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 16px;
  border-bottom: 1px solid var(--app-line);
}

.resume-list-head strong {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 650;
}

.resume-list-head span {
  color: var(--app-muted);
  font-size: 11px;
}

.resume-list-item {
  position: relative;
  display: flex;
  width: 100%;
  gap: 10px;
  padding: 14px 16px;
  border: 0;
  border-bottom: 1px solid var(--app-line);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.resume-list-item:hover {
  background: var(--app-surface-strong);
}

.resume-list-item.is-active {
  background: var(--app-surface-strong);
  box-shadow: inset 3px 0 0 var(--app-primary);
}

.resume-doc {
  display: grid;
  width: 32px;
  height: 40px;
  flex-shrink: 0;
  place-items: center;
  border: 1px solid var(--app-line);
  border-radius: 4px;
  background: var(--app-surface-strong);
  color: var(--app-muted);
  font-size: 9px;
  font-weight: 600;
}

.resume-list-item.is-active .resume-doc {
  border-color: color-mix(in srgb, var(--app-primary), white 55%);
  color: var(--app-primary);
}

.resume-list-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.resume-list-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.resume-list-title strong {
  overflow: hidden;
  color: var(--app-text);
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-default {
  flex-shrink: 0;
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--app-primary), white 92%);
  color: var(--app-primary);
  font-size: 9px;
  font-weight: 600;
}

.resume-list-sub {
  overflow: hidden;
  color: var(--app-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-list-score {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 7px;
}

.resume-score-track {
  flex: 1;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--app-surface-muted);
}

.resume-score-track i {
  display: block;
  height: 100%;
  border-radius: 999px;
}

.resume-list-score b {
  color: var(--app-muted);
  font-family: var(--app-font-mono);
  font-size: 10px;
  font-weight: 600;
}

.resume-list-foot {
  margin-top: auto;
  padding: 14px 16px;
}

.resume-list-foot .el-button {
  width: 100%;
}

.resume-list-skeleton {
  padding: 14px 16px;
  border-bottom: 1px solid var(--app-line);
}

.resume-detail {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.resume-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  border-bottom: 1px solid var(--app-line);
}

.resume-detail-copy {
  min-width: 0;
}

.resume-detail-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.resume-detail-title h2 {
  overflow: hidden;
  margin: 0;
  color: var(--app-text);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-detail-sub {
  margin: 6px 0 0;
  color: var(--app-muted);
  font-size: 12px;
}

.resume-detail-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.more-button {
  display: grid;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  place-items: center;
  border: 0;
  border-radius: var(--app-radius-xs);
  background: transparent;
  color: var(--app-muted);
  font-size: 15px;
  cursor: pointer;
}

.more-button:hover {
  background: var(--app-surface-muted);
  color: var(--app-text);
}

.resume-detail-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  flex: 1;
  min-height: 0;
}

.resume-preview {
  min-width: 0;
  padding: 22px;
  border-right: 1px solid var(--app-line);
  background: var(--app-surface-muted);
}

.resume-alert {
  max-width: 520px;
  margin: 0 auto 12px;
}

.resume-parse-note {
  max-width: 520px;
  margin: 0 auto 12px;
  color: color-mix(in srgb, var(--app-warning), black 30%);
  font-size: 12px;
  line-height: 1.6;
}

.resume-paper {
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
  padding: 32px 36px;
  border: 1px solid var(--app-line);
  border-radius: 4px;
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow);
}

.resume-paper.is-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.paper-head {
  margin-bottom: 12px;
}

.paper-name {
  display: block;
  color: var(--app-text);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 1.2;
}

.paper-role {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 11px;
}

.paper-contact {
  display: block;
  margin-top: 2px;
  color: var(--app-muted);
  font-size: 10px;
}

.paper-rule {
  height: 2px;
  margin: 4px 0 4px;
  background: var(--app-text);
}

.paper-section {
  margin-top: 16px;
}

.paper-section h4 {
  margin: 0 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--app-line-strong);
  color: var(--app-text);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.paper-entry {
  margin-top: 10px;
}

.paper-entry-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--app-text);
  font-size: 12px;
}

.paper-entry-head strong {
  font-weight: 600;
}

.paper-entry-head span {
  color: var(--app-muted);
  font-size: 10px;
  white-space: nowrap;
}

.paper-entry-role {
  margin: 3px 0 0;
  color: var(--app-muted);
  font-size: 10px;
}

.paper-entry-desc {
  margin: 3px 0 0;
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.7;
}

.paper-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.paper-skills span {
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--app-surface-muted);
  color: var(--app-muted);
  font-size: 10px;
}

.paper-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 420px;
  color: var(--app-muted);
  text-align: center;
}

.paper-empty strong {
  color: var(--app-text);
  font-size: 14px;
}

.paper-empty p {
  max-width: 260px;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}

.resume-audit {
  position: sticky;
  top: 0;
  align-self: start;
  padding: 20px 18px;
}

.audit-score {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--app-line);
}

.audit-score-copy strong {
  display: block;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 650;
}

.audit-score-copy span {
  display: block;
  margin-top: 3px;
  color: var(--app-muted);
  font-size: 10px;
  line-height: 1.5;
}

.resume-audit h3 {
  margin: 16px 0 8px;
  color: var(--app-text);
  font-size: 12px;
  font-weight: 650;
}

.audit-issues,
.audit-checks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.audit-issue {
  display: flex;
  gap: 8px;
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.5;
}

.audit-issue i,
.audit-check i {
  display: grid;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--app-warning), white 92%);
  color: color-mix(in srgb, var(--app-warning), black 30%);
  font-size: 9px;
  font-style: normal;
}

.audit-check {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--app-muted);
  font-size: 11px;
}

.audit-check.is-done i {
  background: color-mix(in srgb, var(--app-success), white 92%);
  color: color-mix(in srgb, var(--app-success), black 35%);
}

.audit-empty {
  margin: 0;
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.6;
}

.audit-target {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 16px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--app-primary), white 75%);
  border-radius: 8px;
  background: color-mix(in srgb, var(--app-primary), white 96%);
}

.audit-target span {
  color: var(--app-primary);
  font-size: 10px;
}

.audit-target strong {
  color: var(--app-primary);
  font-size: 12px;
}

.audit-target .app-link {
  align-self: flex-start;
  margin-top: 4px;
  color: var(--app-primary);
  font-size: 11px;
}

.audit-version {
  margin: 12px 0 0;
  color: var(--app-muted);
  font-size: 10px;
}

@media (max-width: 1180px) {
  .resume-workspace {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .resume-detail-body {
    grid-template-columns: 1fr;
  }

  .resume-preview {
    border-right: 0;
    border-bottom: 1px solid var(--app-line);
  }

  .resume-audit {
    position: static;
  }
}

@media (max-width: 900px) {
  .resume-workspace {
    grid-template-columns: 1fr;
  }

  .resume-list {
    border-right: 0;
    border-bottom: 1px solid var(--app-line);
  }

  .resume-list-item {
    padding: 12px 14px;
  }
}

@media (max-width: 768px) {
  .resume-detail-head {
    flex-direction: column;
  }

  .resume-detail-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .resume-preview,
  .resume-audit {
    padding: 14px;
  }

  .resume-paper {
    padding: 22px 20px;
  }
}

/* Upload progress */
.upload-progress {
  margin-top: 16px;
}

.upload-steps {
  margin-bottom: 12px;
}

.parse-progress {
  display: flex;
  align-items: center;
  gap: 6px;
}

.progress-text {
  margin-top: 8px;
  font-size: 13px;
  color: var(--app-muted);
}

.upload-error {
  margin-top: 12px;
}

/* Share dialog */
.share-body p {
  margin-bottom: 12px;
  color: var(--app-muted);
  font-size: 14px;
}

.share-options {
  margin-top: 12px;
}

.optimize-copy {
  margin: 0 0 12px;
  color: var(--app-muted);
  font-size: 14px;
}

.optimize-select {
  width: 100%;
}

/* Diagnosis dialog */
.diagnosis-body {
  max-height: 60vh;
  overflow-y: auto;
}

.diag-score-row {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
  align-items: center;
}

.diag-score-gauge {
  text-align: center;
  flex-shrink: 0;
}

.gauge-ring {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.gauge-text {
  position: absolute;
  font-size: 28px;
  font-weight: 800;
  color: var(--app-primary);
}

.diag-score-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-muted);
}

.diag-dims {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.diag-dim-item {
}

.dim-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 4px;
}

.dim-label strong {
  font-size: 14px;
  font-weight: 700;
}

.diag-details {
  margin-top: 4px;
}

.diag-issue {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 0;
  margin: 0;
  font-size: 14px;
  border-bottom: 1px solid var(--app-line);
}

.diag-issue:last-child {
  border-bottom: none;
}

.diag-note {
  margin: 0;
  padding: 6px 0;
  font-size: 14px;
  color: var(--app-muted);
}
.dim-none {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--app-muted);
}

.rw-count {
  margin-left: 8px;
  font-size: 12px;
  color: var(--app-muted);
}
.rw-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}
.rw-hint {
  font-size: 12px;
  color: var(--app-muted);
}
.rw-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--app-muted);
}
.rw-item {
  padding: 10px 0;
  border-top: 1px solid var(--app-line);
}
.rw-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.rw-item-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}
.rw-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.rw-col-title {
  margin-bottom: 2px;
  font-size: 12px;
  color: var(--app-muted);
}
.rw-text {
  margin: 0;
  padding: 6px 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--app-text);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--app-surface-muted);
  border-radius: var(--app-radius-sm);
}
.rw-text-new {
  border-left: 2px solid var(--app-success);
}
.rw-reason {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--app-muted);
}
.rw-dropped {
  margin-top: 10px;
  padding: 8px;
  font-size: 12px;
  color: var(--app-muted);
  background: var(--app-surface-muted);
  border-radius: var(--app-radius-sm);
}
.rw-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.rw-score {
  font-size: 13px;
  color: var(--app-muted);
}

@media (max-width: 768px) {
  .rw-compare {
    grid-template-columns: 1fr;
  }
}

.diag-issue .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.diag-good .el-icon {
  color: var(--app-success);
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 60px 0;
  color: var(--app-muted);
  font-size: 14px;
}

.empty-state {
  padding: 40px 0;
  display: flex;
  justify-content: center;
}

@media (max-width: 768px) {
  .diag-score-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
