<template>
  <div class="page-shell resume-center">
    <div class="page-header">
      <div>
        <h2>简历中心</h2>
        <div class="page-header-sub">
          管理多份简历、AI 优化诊断、版本对比与分享 — 简历全生命周期管理
        </div>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="showUpload = true">
          <el-icon><UploadFilled /></el-icon> 上传简历
        </el-button>
      </div>
    </div>

    <section v-if="!listLoading && resumes.length" class="resume-workflow" aria-label="简历工作流">
      <div class="workflow-summary">
        <span class="workflow-eyebrow">当前投递版本</span>
        <strong>{{ activeResume?.name || activeResume?.file_name || '选择一份简历开始' }}</strong>
        <span class="workflow-caption">
          {{
            activeResume
              ? `更新于 ${monthDay(activeResume.create_time)}`
              : '上传后可进行诊断与匹配'
          }}
        </span>
      </div>
      <div class="workflow-steps">
        <div class="workflow-step is-current">
          <span class="workflow-index">01</span>
          <div>
            <b>确认版本</b><small>{{ resumes.length }} 份简历</small>
          </div>
        </div>
        <div class="workflow-step" :class="{ 'is-ready': scoredResumeCount > 0 }">
          <span class="workflow-index">02</span>
          <div>
            <b>检查可投递性</b
            ><small>{{
              scoredResumeCount ? `${scoredResumeCount} 份已完成度检查` : '待检查'
            }}</small>
          </div>
        </div>
        <div class="workflow-step" :class="{ 'is-ready': activeResume }">
          <span class="workflow-index">03</span>
          <div>
            <b>匹配目标岗位</b><small>{{ activeResume ? '进入深度分析' : '先选择简历' }}</small>
          </div>
        </div>
      </div>
      <el-button type="primary" class="workflow-action" @click="goAnalysis(activeResume)">
        开始匹配
      </el-button>
    </section>

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
        <el-progress :percentage="uploadProgress" :stroke-width="10" :text-inside="true" />
        <p class="progress-text">{{ uploadStatus }}</p>
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
    </el-dialog>

    <!-- 分享链接弹窗 -->
    <el-dialog v-model="showShare" title="分享简历" width="480px">
      <div class="share-body">
        <p>将以下链接发送给 HR，对方即可查看您的简历详情。</p>
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
      <el-alert v-else-if="diagnosisError" type="error" :closable="false" show-icon :title="diagnosisError" />
      <div v-else-if="currentDiagnosis" class="diagnosis-body">
        <!-- 综合评分 -->
        <div class="diag-score-row">
          <div class="diag-score-gauge">
            <div class="gauge-ring">
              <svg viewBox="0 0 120 120" style="width: 100px; height: 100px">
                <circle cx="60" cy="60" r="54" fill="none" stroke="#eee" stroke-width="8" />
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
            <div class="diag-score-label">综合评分</div>
          </div>
          <div class="diag-dims">
            <div v-for="dim in diagnosisDims" :key="dim.key" class="diag-dim-item">
              <div class="dim-label">
                <span>{{ dim.label }}</span>
                <strong :style="{ color: scoreToneColor(dim.score) }">{{
                  dim.score ?? '—'
                }}</strong>
              </div>
              <el-progress
                v-if="typeof dim.score === 'number'"
                :percentage="dim.score"
                :color="scoreToneColor(dim.score)"
                :stroke-width="6"
              />
              <p v-else class="dim-none">本次分析未给出该维度评分</p>
            </div>
          </div>
        </div>

        <!-- 诊断详情 -->
        <el-collapse v-model="diagActivePanels" class="diag-details">
          <el-collapse-item title="📐 结构问题" name="structure">
            <div v-if="currentDiagnosis.structure_issues?.length">
              <p v-for="(item, i) in currentDiagnosis.structure_issues" :key="i" class="diag-issue">
                <el-icon><WarningFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="结构良好" />
          </el-collapse-item>
          <el-collapse-item title="✏️ 表达问题" name="expression">
            <div v-if="currentDiagnosis.expression_issues?.length">
              <p
                v-for="(item, i) in currentDiagnosis.expression_issues"
                :key="i"
                class="diag-issue"
              >
                <el-icon><WarningFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="表达清晰" />
          </el-collapse-item>
          <el-collapse-item title="🔑 关键词缺失" name="keywords">
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
            <el-empty v-else :image-size="60" description="关键词覆盖良好" />
          </el-collapse-item>
          <el-collapse-item title="✨ 亮点分析" name="highlights">
            <div v-if="currentDiagnosis.highlights?.length">
              <p
                v-for="(item, i) in currentDiagnosis.highlights"
                :key="i"
                class="diag-issue diag-good"
              >
                <el-icon><CircleCheckFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="尚未发现突出亮点" />
          </el-collapse-item>
          <el-collapse-item title="🎯 岗位匹配度" name="match">
            <div v-if="currentDiagnosis.match_analysis">
              <p>{{ currentDiagnosis.match_analysis }}</p>
              <el-button
                v-if="currentDiagnosis.jd_id"
                text
                type="primary"
                @click="goAnalysisFromDiag"
              >
                查看完整匹配分析 →
              </el-button>
            </div>
            <el-empty v-else :image-size="60" description="未指定对比岗位" />
          </el-collapse-item>
          <el-collapse-item title="🤖 ATS 友好度" name="ats">
            <div v-if="typeof currentDiagnosis.ats_score === 'number'">
              <p class="diag-note">
                模型评分 {{ currentDiagnosis.ats_score }}，用于估计格式与关键词的可解析性。
              </p>
            </div>
            <el-empty v-else :image-size="60" description="本次分析未给出 ATS 维度评分" />
          </el-collapse-item>
          <el-collapse-item title="模块完整度（规则检查，非 AI）" name="completeness">
            <div v-if="currentDiagnosis.completeness_issues?.length">
              <p
                v-for="(item, i) in currentDiagnosis.completeness_issues"
                :key="i"
                class="diag-issue"
              >
                <el-icon><WarningFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="未检出缺失模块" />
          </el-collapse-item>
          <el-collapse-item title="📈 改进路线图" name="roadmap">
            <div v-if="currentDiagnosis.improvement_roadmap?.length">
              <p
                v-for="(item, i) in currentDiagnosis.improvement_roadmap"
                :key="i"
                class="diag-issue diag-good"
              >
                <el-icon><CircleCheckFilled /></el-icon>
                {{
                  typeof item === 'string' ? item : item.title || item.keyword || item.action || ''
                }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="暂无改进建议" />
          </el-collapse-item>
          <el-collapse-item name="rewrite">
            <template #title>
              <span>✏️ 行级改写（原文 → 改后）</span>
              <span v-if="rewrite.items.length" class="rw-count">{{ rewrite.items.length }} 条待处理</span>
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
              <span class="rw-hint">建议只覆盖你已写过的文字，逐条决定采纳哪几条；未采纳的不会写进简历。</span>
            </div>

            <el-alert v-if="rewrite.error" type="error" :closable="false" show-icon :title="rewrite.error" />

            <div v-if="rewrite.loading" class="rw-loading">
              <el-icon class="is-loading"><Loading /></el-icon> 正在逐条比对可改写的文本…
            </div>

            <template v-else>
              <div v-for="item in rewrite.items" :key="item.block_id" class="rw-item">
                <div class="rw-item-head">
                  <el-checkbox v-model="item._accepted">采纳</el-checkbox>
                  <span class="rw-item-label">{{ item.label }}</span>
                  <el-tag v-if="rewriteKindLabel(item.kind) !== item.label" size="small" effect="plain">
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
                已自动丢弃 {{ rewrite.dropped.length }} 条不可用建议：
                <span v-for="(d, i) in rewrite.dropped" :key="i" class="rw-drop-item">
                  {{ d.block_id || '未知位置' }} — {{ rejectLabel(d.reason) }}
                </span>
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
                <span v-if="rewriteScoreLine" class="rw-score">{{ rewriteScoreLine }}</span>
                <span v-else-if="rewrite.result?.changed" class="rw-score">
                  未指定目标岗位，本次不显示匹配分变化
                </span>
              </div>

              <p v-if="diagnosisStale" class="diag-note">
                简历内容已更新，上方的维度评分仍是改写前的结果；关闭后重新打开诊断即可刷新。
              </p>
            </template>
          </el-collapse-item>
        </el-collapse>
      </div>
      <div v-else class="empty-state">
        <el-empty :image-size="80" description="暂无诊断数据，请先解析简历" />
      </div>
    </el-dialog>

    <!-- 简历列表 -->
    <div v-if="listLoading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>
    <div v-else-if="listError" class="load-error">
      <div>
        <strong>简历列表加载失败</strong>
        <span>{{ listError }}</span>
      </div>
      <el-button @click="loadList">重新加载</el-button>
    </div>
    <div v-else-if="!resumes.length" class="empty-state">
      <el-empty :image-size="120" description="还没有简历，上传一份开始吧">
        <el-button type="primary" @click="showUpload = true">上传简历</el-button>
      </el-empty>
    </div>
    <div v-else class="resume-grid">
      <div
        v-for="r in resumes"
        :key="r.id"
        class="resume-card"
        :class="{ 'is-default': r.id === defaultResumeId }"
      >
        <div class="card-top">
          <div class="card-title-row">
            <span class="record-mark">{{ r.id === defaultResumeId ? '投递中' : '备选版本' }}</span>
            <h3>{{ r.name || r.file_name || '未命名简历' }}</h3>
            <el-dropdown trigger="click" @command="(cmd) => handleCmd(cmd, r)">
              <el-icon class="more-btn"><MoreFilled /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="parse">{{
                    r.parsed?.name ? '重新解析' : '解析'
                  }}</el-dropdown-item>
                  <el-dropdown-item command="optimize">AI优化</el-dropdown-item>
                  <el-dropdown-item command="diagnose">AI诊断</el-dropdown-item>
                  <el-dropdown-item command="compare">版本对比</el-dropdown-item>
                  <el-dropdown-item command="analyze">深度分析</el-dropdown-item>
                  <el-dropdown-item v-if="r.id !== defaultResumeId" command="setDefault"
                    >设为默认</el-dropdown-item
                  >
                  <el-dropdown-item command="share" divided>分享链接</el-dropdown-item>
                  <el-dropdown-item command="desensitize">{{
                    r._desensitized ? '取消脱敏' : '脱敏设置'
                  }}</el-dropdown-item>
                  <el-dropdown-item command="exportDocx">导出 Word</el-dropdown-item>
                  <el-dropdown-item command="exportPdf">导出 PDF</el-dropdown-item>
                  <el-dropdown-item command="delete" divided style="color: var(--app-danger)"
                    >删除</el-dropdown-item
                  >
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <div v-if="r.id === defaultResumeId" class="default-tag">
            <el-tag type="success" size="small" effect="dark">默认简历</el-tag>
          </div>
        </div>

        <div class="card-meta">
          <span v-if="r.parsed?.current_title"
            ><el-icon><Briefcase /></el-icon> {{ r.parsed.current_title }}</span
          >
          <span v-if="r.years_exp"
            ><el-icon><Timer /></el-icon> {{ r.years_exp }}年经验</span
          >
          <span
            ><el-icon><Document /></el-icon> {{ r.file_type?.toUpperCase() }}</span
          >
          <span>{{ formatSize(r.file_size) }}</span>
        </div>

        <!-- 简历标签 -->
        <div class="card-badges" v-if="r._versionCount !== undefined || r._diagnosisScore">
          <el-tag v-if="r._versionCount > 0" size="small" type="info" effect="plain">
            版本历史 ({{ r._versionCount }})
          </el-tag>
          <el-tag
            v-if="r._diagnosisScore"
            size="small"
            :type="diagnosisTagType(r._diagnosisScore)"
            effect="plain"
          >
            诊断 {{ r._diagnosisScore }}分
          </el-tag>
          <el-tag v-if="r._desensitized" size="small" type="danger" effect="plain">已脱敏</el-tag>
        </div>

        <div v-if="r.parsed?.skills?.length" class="card-skills">
          <el-tag v-for="sk in r.parsed.skills.slice(0, 6)" :key="sk" size="small" type="info">{{
            sk
          }}</el-tag>
          <span v-if="r.parsed.skills.length > 6" class="more-skills"
            >+{{ r.parsed.skills.length - 6 }}</span
          >
        </div>

        <!-- ATS 评分 -->
        <div v-if="r._completeness" class="card-score">
          <div class="score-bar">
            <div
              class="score-fill"
              :style="{ width: r._completeness.completeness_score + '%' }"
              :class="scoreToneFillClass(r._completeness.completeness_score)"
            />
          </div>
          <div class="score-label">
            <span>完整度</span>
            <strong :class="scoreToneClass(r._completeness.completeness_score)">{{
              r._completeness.completeness_score
            }}</strong>
          </div>
        </div>
        <div v-else class="card-score">
          <el-button text size="small" @click="quickScore(r)" :loading="r._scoring">
            查看完整度
          </el-button>
        </div>

        <div class="card-footer">
          <span class="card-date">版本记录 {{ monthDay(r.create_time) }}</span>
          <div class="card-actions">
            <el-button size="small" type="primary" @click="goAnalysis(r)">
              {{ r.id === defaultResumeId ? '匹配岗位' : '去分析' }}
            </el-button>
            <el-button size="small" @click="handleCmd('diagnose', r)">AI诊断</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  UploadFilled,
  MoreFilled,
  Briefcase,
  Timer,
  Document,
  Loading,
  WarningFilled,
  CircleCheckFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  uploadResume,
  parseResume,
  getResumeList,
  getResumeVersions,
  getResumeQuickScore,
  diagnoseResume,
  getRewriteSuggestions,
  applyResumeRewrites,
  deleteResume,
  generateOptimized,
  exportResume,
  downloadResumeExport,
} from '@/api/resume'
import {
  scoreToneAtLeast,
  scoreToneClass,
  scoreToneColor,
  scoreToneFillClass,
} from '@/utils/scoreTone'
import { monthDay } from '@/utils/format/date'

const router = useRouter()

const showUpload = ref(false)
const showParsed = ref(false)
const showShare = ref(false)
const showDiagnosis = ref(false)
const currentParsed = ref(null)
const listLoading = ref(true)
const resumes = ref([])
const listError = ref('')
const defaultResumeId = ref(null)

const uploading = ref(false)
const uploadProgress = ref(0)
const uploadStatus = ref('')
const uploadError = ref('')

// 分享
const shareUrl = ref('')
const shareDesensitized = ref(false)
const currentShareResume = ref(null)

// 诊断
const diagnosisLoading = ref(false)
const diagnosisError = ref('')
const currentDiagnosis = ref(null)
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
})

const REJECT_LABELS = {
  unknown_block: '锚点不存在',
  original_mismatch: '原文与简历对不上',
  duplicate_block: '同一处重复建议',
  empty_proposal: '改后内容为空',
  unchanged: '与原文相同',
  proposal_too_long: '改动过长',
  over_limit: '超出条数上限',
  malformed_response: '模型返回格式异常',
  stale_anchor: '简历已更新，该条已失效',
  missing_block_id: '缺少锚点',
  empty_or_missing_text: '缺少改后内容',
  empty_skill_list: '技能被清空',
  not_an_object: '条目格式异常',
}

function rejectLabel(reason) {
  return REJECT_LABELS[reason] || reason || '已拒绝'
}

function rewriteKindLabel(kind) {
  return { skills: '技能', self_evaluation: '自我评价', work: '工作经历', project: '项目经历' }[kind] || kind
}

const acceptedRewrites = computed(() => rewrite.items.filter((item) => item._accepted))

const rewriteScoreLine = computed(() => {
  const score = rewrite.result?.score
  const before = score?.before?.score
  const after = score?.after?.score
  if (typeof before !== 'number' || typeof after !== 'number') return ''
  return `匹配分 ${before} → ${after}`
})

async function generateRewrites() {
  const resumeId = currentDiagnosis.value?.resume_id
  if (!resumeId || rewrite.loading) return
  rewrite.loading = true
  rewrite.error = ''
  rewrite.result = null
  try {
    const data = await getRewriteSuggestions(resumeId, currentDiagnosis.value?.jd_id || null)
    rewrite.items = (data?.suggestions || []).map((s) => ({ ...s, _accepted: true }))
    rewrite.dropped = data?.rejected || []
    rewrite.loaded = true
    if (!rewrite.items.length) {
      ElMessage.info(data?.note || '模型没有给出值得采纳的改写；不是错误，可能这份简历这几处已经写清楚了')
    }
  } catch (e) {
    rewrite.items = []
    rewrite.dropped = []
    rewrite.error = e.userMessage || e.message || '改写建议生成失败'
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
    rewrite.error = e.userMessage || e.message || '应用改写失败'
  } finally {
    rewrite.applying = false
  }
}

// 脱敏
const desensitized = ref(false)

const LS_DEFAULT_KEY = 'recruit.defaultResumeId'

const activeResume = computed(
  () => resumes.value.find((item) => item.id === defaultResumeId.value) || resumes.value[0] || null
)
const scoredResumeCount = computed(
  () => resumes.value.filter((item) => item._completeness?.completeness_score !== undefined).length
)

onMounted(() => {
  defaultResumeId.value = Number(localStorage.getItem(LS_DEFAULT_KEY)) || null
  loadList()
})

const diagnosisDims = [
  { key: 'structure_score', label: '结构', score: 0 },
  { key: 'expression_score', label: '表达', score: 0 },
  { key: 'keyword_score', label: '关键词覆盖', score: 0 },
  { key: 'highlight_score', label: '亮点', score: 0 },
  { key: 'ats_score', label: 'ATS友好度', score: 0 },
]

function formatSize(n) {
  if (!n) return '-'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(2) + ' MB'
}

// 诊断分标签只有两档：至少到 good 档才算 success，其余 warning。
// 分界交给 scoreTone 的 85/70/50，不再在本页抄一份 70。
const diagnosisTagType = (v) => (scoreToneAtLeast(v, 'good') ? 'success' : 'warning')

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

    // auto load quick scores & version counts
    items.forEach((r) => {
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
  uploadStatus.value = '正在上传…'
  uploadError.value = ''

  try {
    const data = await uploadResume(file, (event) => {
      const loaded = Number(event?.loaded || 0)
      const total = Number(event?.total || file.size || 0)
      const ratio = total > 0 ? loaded / total : 0
      uploadProgress.value = Math.max(0, Math.min(100, Math.round(ratio * 100)))
    })

    uploadStatus.value = '上传完成，正在解析…'
    uploadProgress.value = 100

    const parsed = await parseResume(data.id)
    currentParsed.value = parsed.parsed
    showParsed.value = true
    ElMessage.success('上传并解析成功')
    showUpload.value = false
    await loadList()
  } catch (e) {
    uploadError.value = e.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

async function handleCmd(cmd, r) {
  if (cmd === 'parse') {
    try {
      const parsed = await parseResume(r.id)
      r.parsed = parsed.parsed
      currentParsed.value = parsed.parsed
      showParsed.value = true
      ElMessage.success('解析成功')
    } catch {
      ElMessage.error('解析失败')
    }
  } else if (cmd === 'optimize') {
    optimizeResume(r)
  } else if (cmd === 'diagnose') {
    showDiagnosisDialog(r)
  } else if (cmd === 'compare') {
    router.push(`/resume/compare/${r.id}`)
  } else if (cmd === 'analyze') {
    goAnalysis(r)
  } else if (cmd === 'setDefault') {
    defaultResumeId.value = r.id
    localStorage.setItem(LS_DEFAULT_KEY, String(r.id))
    ElMessage.success('已设为默认简历')
  } else if (cmd === 'share') {
    showShareDialog(r)
  } else if (cmd === 'desensitize') {
    r._desensitized = !r._desensitized
    ElMessage.success(r._desensitized ? '已脱敏，联系方式已隐藏' : '已取消脱敏')
  } else if (cmd === 'exportDocx') {
    doExport(r, 'docx')
  } else if (cmd === 'exportPdf') {
    doExport(r, 'pdf')
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm('确定删除该简历？', '删除确认', { type: 'warning' })
      await deleteResume(r.id)
      ElMessage.success('已删除')
      await loadList()
    } catch {
      // 用户取消删除时不显示错误；请求失败由统一请求层提示。
    }
  }
}

function goAnalysis(r) {
  localStorage.setItem('recruit.lastResumeId', r.id)
  router.push('/analysis')
}

async function optimizeResume(r) {
  try {
    await ElMessageBox.prompt('可选：输入目标岗位ID以生成定制简历', 'AI优化简历', {
      confirmButtonText: '开始优化',
      cancelButtonText: '取消',
      inputPlaceholder: '留空则通用优化',
    })
      .then(async ({ value }) => {
        const jdId = value ? Number(value) : null
        await generateOptimized(r.id, jdId)
        ElMessage.success('优化完成')
      })
      .catch(() => undefined)
  } catch {
    // 用户取消优化弹窗时不执行后续操作。
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
async function showDiagnosisDialog(r) {
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
    structure_score: d.structure_score ?? null,
    expression_score: d.expression_score ?? null,
    keyword_score: d.keyword_score ?? null,
    highlight_score: d.highlight_score ?? null,
    ats_score: d.ats_score ?? null,
    structure_issues: d.structure_issues || [],
    expression_issues: d.expression_issues || [],
    missing_keywords: d.missing_keywords || [],
    highlights: d.highlights || [],
    match_analysis: d.match_analysis || '',
    completeness_issues: d.completeness_issues || [],
    completeness_score: d.completeness_score ?? null,
    module_check: d.module_check || {},
    improvement_roadmap: d.improvement_roadmap || [],
    // /diagnose scores against a target *position string*, not a stored JD, so
    // this is normally null and the jump-to-analysis action stays hidden.
    jd_id: d.jd_id ?? null,
  }
  diagnosisDims.forEach((dim) => {
    dim.score = d[dim.key] ?? null
  })
  r._diagnosisScore = d.total_score
  diagnosisLoading.value = false
}
function goAnalysisFromDiag() {
  if (currentDiagnosis.value?.jd_id) {
    localStorage.setItem(
      'recruit.lastResumeId',
      resumes.value.find((r) => r.id === currentShareResume.value?.id)?.id || ''
    )
    router.push(`/analysis/${currentDiagnosis.value.jd_id}`)
  }
}
</script>

<style scoped>
.resume-center {
  width: 100%;
  color: var(--app-text);
}

.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
  border: 1px solid #f2c5bf;
  border-radius: 8px;
  background: var(--app-accent-soft);
}
.load-error strong,
.load-error span {
  display: block;
}
.load-error strong {
  color: var(--app-danger);
  font-size: 15px;
}
.load-error span {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
}

/* Grid layout */
.resume-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.resume-workflow {
  display: grid;
  grid-template-columns: minmax(210px, 0.9fr) minmax(0, 1.8fr) auto;
  align-items: center;
  gap: 22px;
  margin-bottom: 18px;
  padding: 18px 20px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.workflow-summary {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.workflow-eyebrow,
.workflow-caption,
.workflow-step small {
  color: var(--app-muted);
  font-size: 12px;
}

.workflow-eyebrow {
  font-weight: 700;
  letter-spacing: 0.08em;
}

.workflow-summary strong {
  overflow: hidden;
  color: var(--app-text);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding-left: 10px;
  border-left: 1px solid var(--app-line);
}

.workflow-step:first-child {
  border-left: 0;
}

.workflow-index {
  display: grid;
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  place-items: center;
  border-radius: 50%;
  background: var(--app-bg);
  color: var(--app-muted);
  font-size: 11px;
  font-weight: 700;
}

.workflow-step.is-current .workflow-index,
.workflow-step.is-ready .workflow-index {
  background: var(--app-primary);
  color: #fff;
}

.workflow-step div {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.workflow-step b {
  overflow: hidden;
  color: var(--app-text);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-action {
  min-width: 104px;
}

.resume-card {
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
  padding: 18px;
  transition:
    box-shadow 0.2s,
    border-color 0.2s;
}

.resume-card:hover {
  box-shadow: var(--app-shadow-hover);
}

.resume-card.is-default {
  border-color: var(--app-primary);
  box-shadow: 0 8px 20px rgba(20, 86, 68, 0.1);
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 8px;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.record-mark {
  flex: 0 0 auto;
  padding: 3px 6px;
  border-radius: 3px;
  background: var(--app-bg);
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.2;
}

.is-default .record-mark {
  background: var(--app-primary-soft);
  color: var(--app-primary-dark);
}

.card-title-row h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.more-btn {
  cursor: pointer;
  color: var(--app-muted);
  font-size: 16px;
  flex-shrink: 0;
}

.default-tag {
  margin-left: auto;
  flex-shrink: 0;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  color: var(--app-muted);
  margin-bottom: 8px;
}

.card-meta span {
  display: flex;
  align-items: center;
  gap: 3px;
}

.card-badges {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.card-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
}

.more-skills {
  font-size: 12px;
  color: var(--app-muted);
  line-height: 24px;
}

/* ATS score */
.card-score {
  margin-bottom: 12px;
}

.score-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--el-fill-color);
  overflow: hidden;
  margin-bottom: 6px;
}

.score-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s;
}

.score-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.score-label span {
  color: var(--app-muted);
}
.score-label strong {
  font-size: 16px;
}
/* Footer */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}

.card-date {
  font-size: 12px;
  color: var(--app-muted);
}

.card-actions {
  display: flex;
  gap: 6px;
}

@media (max-width: 960px) {
  .resume-workflow {
    grid-template-columns: 1fr auto;
  }

  .workflow-steps {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}

@media (max-width: 640px) {
  .resume-workflow,
  .workflow-steps {
    grid-template-columns: 1fr;
  }

  .workflow-action {
    width: 100%;
  }

  .workflow-step,
  .workflow-step:first-child {
    padding: 9px 0 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
  }
}

/* Upload progress */
.upload-progress {
  margin-top: 16px;
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
  border-bottom: 1px solid var(--el-border-color-lighter);
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
.rw-drop-item {
  display: block;
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
  .load-error {
    align-items: flex-start;
    flex-direction: column;
  }

  .page-header {
    flex-direction: column;
    gap: 12px;
  }
  .resume-grid {
    grid-template-columns: 1fr;
  }
  .diag-score-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
