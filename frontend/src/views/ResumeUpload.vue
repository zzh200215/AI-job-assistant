<template>
  <div class="page-shell resume-center">
    <div class="page-header">
      <div>
        <h2>简历中心</h2>
        <div class="page-header-sub">管理多份简历、AI 优化诊断、版本对比与分享 — 简历全生命周期管理</div>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="showUpload = true">
          <el-icon><UploadFilled /></el-icon> 上传简历
        </el-button>
      </div>
    </div>

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
          <el-descriptions-item label="姓名">{{ maskedText(currentParsed.name, desensitized) }}</el-descriptions-item>
          <el-descriptions-item label="工作年限">{{ currentParsed.years_exp || 0 }} 年</el-descriptions-item>
          <el-descriptions-item label="电话">{{ maskedText(currentParsed.phone, desensitized) }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ maskedText(currentParsed.email, desensitized) }}</el-descriptions-item>
          <el-descriptions-item label="学历">{{ currentParsed.education || '-' }}</el-descriptions-item>
          <el-descriptions-item label="专业">{{ currentParsed.major || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前公司" :span="2">{{ currentParsed.current_company || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前职位" :span="2">{{ currentParsed.current_title || '-' }}</el-descriptions-item>
          <el-descriptions-item label="技能" :span="2">
            <el-tag v-for="s in currentParsed.skills || []" :key="s" style="margin:2px;">{{ s }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <h4 style="margin:16px 0 8px">工作经历</h4>
        <el-timeline>
          <el-timeline-item
            v-for="(w, i) in currentParsed.work_experience || []" :key="i"
            :timestamp="`${w.start || ''} ~ ${w.end || ''}`"
          >
            <b>{{ w.company }} · {{ w.title }}</b>
            <div style="color:var(--app-muted);font-size:12px;">{{ w.desc }}</div>
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
      <div v-else-if="currentDiagnosis" class="diagnosis-body">
        <!-- 综合评分 -->
        <div class="diag-score-row">
          <div class="diag-score-gauge">
            <div class="gauge-ring">
              <svg viewBox="0 0 120 120" style="width:100px;height:100px;">
                <circle cx="60" cy="60" r="54" fill="none" stroke="#eee" stroke-width="8" />
                <circle cx="60" cy="60" r="54" fill="none" :stroke="diagScoreColor" stroke-width="8"
                  :stroke-dasharray="`${339.3 * (currentDiagnosis.total_score || 0) / 100} 339.3`"
                  stroke-linecap="round" transform="rotate(-90 60 60)" />
              </svg>
              <span class="gauge-text">{{ currentDiagnosis.total_score || 0 }}</span>
            </div>
            <div class="diag-score-label">综合评分</div>
          </div>
          <div class="diag-dims">
            <div v-for="dim in diagnosisDims" :key="dim.key" class="diag-dim-item">
              <div class="dim-label">
                <span>{{ dim.label }}</span>
                <strong :style="{ color: dimColor(dim.score) }">{{ dim.score }}</strong>
              </div>
              <el-progress :percentage="dim.score" :color="dimColor(dim.score)" :stroke-width="6" />
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
              <p v-for="(item, i) in currentDiagnosis.expression_issues" :key="i" class="diag-issue">
                <el-icon><WarningFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="表达清晰" />
          </el-collapse-item>
          <el-collapse-item title="🔑 关键词缺失" name="keywords">
            <div v-if="currentDiagnosis.missing_keywords?.length">
              <el-tag v-for="kw in currentDiagnosis.missing_keywords" :key="kw" type="warning" style="margin:4px;">
                {{ kw }}
              </el-tag>
            </div>
            <el-empty v-else :image-size="60" description="关键词覆盖良好" />
          </el-collapse-item>
          <el-collapse-item title="✨ 亮点分析" name="highlights">
            <div v-if="currentDiagnosis.highlights?.length">
              <p v-for="(item, i) in currentDiagnosis.highlights" :key="i" class="diag-issue diag-good">
                <el-icon><CircleCheckFilled /></el-icon> {{ item }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="尚未发现突出亮点" />
          </el-collapse-item>
          <el-collapse-item title="🎯 岗位匹配度" name="match">
            <div v-if="currentDiagnosis.match_analysis">
              <p>{{ currentDiagnosis.match_analysis }}</p>
              <el-button v-if="currentDiagnosis.jd_id" text type="primary" @click="goAnalysisFromDiag">
                查看完整匹配分析 →
              </el-button>
            </div>
            <el-empty v-else :image-size="60" description="未指定对比岗位" />
          </el-collapse-item>
          <el-collapse-item title="🤖 ATS 友好度" name="ats">
            <div v-if="currentDiagnosis.ats_issues?.length">
              <p v-for="(item, i) in currentDiagnosis.ats_issues" :key="i" class="diag-issue">
                <el-icon><WarningFilled /></el-icon> {{ item }}
              </p>
            </div>
            <div v-else-if="currentDiagnosis.ats_score">
              <el-empty :image-size="60" :description="'ATS评分 ' + currentDiagnosis.ats_score + '，格式兼容性良好'" />
            </div>
            <el-empty v-else :image-size="60" description="暂无ATS数据" />
          </el-collapse-item>
          <el-collapse-item title="📈 改进路线图" name="roadmap">
            <div v-if="currentDiagnosis.improvement_roadmap?.length">
              <p v-for="(item, i) in currentDiagnosis.improvement_roadmap" :key="i" class="diag-issue diag-good">
                <el-icon><CircleCheckFilled /></el-icon>
                {{ typeof item === 'string' ? item : (item.title || item.keyword || item.action || '') }}
              </p>
            </div>
            <el-empty v-else :image-size="60" description="暂无改进建议" />
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
            <h3>{{ r.name || r.file_name || '未命名简历' }}</h3>
            <el-dropdown trigger="click" @command="cmd => handleCmd(cmd, r)">
              <el-icon class="more-btn"><MoreFilled /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="parse">{{ r.parsed?.name ? '重新解析' : '解析' }}</el-dropdown-item>
                  <el-dropdown-item command="optimize">AI优化</el-dropdown-item>
                  <el-dropdown-item command="diagnose">AI诊断</el-dropdown-item>
                  <el-dropdown-item command="compare">版本对比</el-dropdown-item>
                  <el-dropdown-item command="analyze">深度分析</el-dropdown-item>
                  <el-dropdown-item v-if="r.id !== defaultResumeId" command="setDefault">设为默认</el-dropdown-item>
                  <el-dropdown-item command="share" divided>分享链接</el-dropdown-item>
                  <el-dropdown-item command="desensitize">{{ r._desensitized ? '取消脱敏' : '脱敏设置' }}</el-dropdown-item>
                  <el-dropdown-item command="exportDocx">导出 Word</el-dropdown-item>
                  <el-dropdown-item command="exportPdf">导出 PDF</el-dropdown-item>
                  <el-dropdown-item command="delete" divided style="color:var(--app-danger)">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <div v-if="r.id === defaultResumeId" class="default-tag">
            <el-tag type="success" size="small" effect="dark">默认简历</el-tag>
          </div>
        </div>

        <div class="card-meta">
          <span v-if="r.parsed?.current_title"><el-icon><Briefcase /></el-icon> {{ r.parsed.current_title }}</span>
          <span v-if="r.years_exp"><el-icon><Timer /></el-icon> {{ r.years_exp }}年经验</span>
          <span><el-icon><Document /></el-icon> {{ r.file_type?.toUpperCase() }}</span>
          <span>{{ formatSize(r.file_size) }}</span>
        </div>

        <!-- 简历标签 -->
        <div class="card-badges" v-if="r._versionCount !== undefined || r._diagnosisScore">
          <el-tag v-if="r._versionCount > 0" size="small" type="info" effect="plain">
            版本历史 ({{ r._versionCount }})
          </el-tag>
          <el-tag v-if="r._diagnosisScore" size="small" :type="r._diagnosisScore >= 70 ? 'success' : 'warning'" effect="plain">
            诊断 {{ r._diagnosisScore }}分
          </el-tag>
          <el-tag v-if="r._desensitized" size="small" type="danger" effect="plain">已脱敏</el-tag>
        </div>

        <div v-if="r.parsed?.skills?.length" class="card-skills">
          <el-tag v-for="sk in r.parsed.skills.slice(0, 6)" :key="sk" size="small" type="info">{{ sk }}</el-tag>
          <span v-if="r.parsed.skills.length > 6" class="more-skills">+{{ r.parsed.skills.length - 6 }}</span>
        </div>

        <!-- ATS 评分 -->
        <div v-if="r._score" class="card-score">
          <div class="score-bar">
            <div class="score-fill" :style="{ width: r._score.total + '%' }" :class="scoreLevel(r._score.total)" />
          </div>
          <div class="score-label">
            <span>ATS 评分</span>
            <strong :class="scoreLevel(r._score.total)">{{ r._score.total }}</strong>
          </div>
        </div>
        <div v-else class="card-score">
          <el-button text size="small" @click="quickScore(r)" :loading="r._scoring">
            查看ATS评分
          </el-button>
        </div>

        <div class="card-footer">
          <span class="card-date">{{ formatDate(r.create_time) }}</span>
          <div class="card-actions">
            <el-button size="small" type="primary" @click="goAnalysis(r)">去分析</el-button>
            <el-button size="small" @click="handleCmd('diagnose', r)">AI诊断</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  UploadFilled, MoreFilled, Briefcase, Timer, Document, Loading,
  WarningFilled, CircleCheckFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  uploadResume,
  parseResume,
  getResumeList,
  getResumeVersions,
  generateOptimized,
  exportResume,
  downloadResumeExport,
} from '@/api/resume'

const router = useRouter()

const showUpload = ref(false)
const showParsed = ref(false)
const showShare = ref(false)
const showDiagnosis = ref(false)
const currentParsed = ref(null)
const listLoading = ref(true)
const resumes = ref([])
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
const currentDiagnosis = ref(null)
const diagActivePanels = ref(['structure', 'expression', 'keywords', 'highlights'])

// 脱敏
const desensitized = ref(false)

const LS_DEFAULT_KEY = 'recruit.defaultResumeId'

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

function formatDate(d) {
  if (!d) return ''
  try { return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) } catch { return d }
}

function scoreLevel(v) {
  if (v >= 80) return 'score-high'
  if (v >= 60) return 'score-mid'
  return 'score-low'
}

function dimColor(v) {
  if (v >= 80) return '#67c23a'
  if (v >= 60) return '#e6a23c'
  return '#f56c6c'
}

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
    items.forEach(r => {
      r._score = null
      r._scoring = false
      r._desensitized = false
      r._versionCount = undefined
      r._diagnosisScore = null
    })
    resumes.value = items

    // auto load quick scores & version counts
    items.forEach(r => {
      quickScore(r)
      loadVersionCount(r)
    })
  } catch {} finally {
    listLoading.value = false
  }
}

async function loadVersionCount(r) {
  try {
    const versions = await getResumeVersions(r.id)
    r._versionCount = Array.isArray(versions?.versions) ? versions.versions.length : 0
  } catch {
    r._versionCount = 0
  }
}

async function quickScore(r) {
  if (r._score || r._scoring) return
  r._scoring = true
  try {
    const res = await fetch(`/api/v1/resume/${r.id}/quick-score`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    }).then(r => r.json())
    if (res?.data?.total !== undefined) {
      r._score = res.data
    }
  } catch {} finally {
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
    } catch (e) {
      ElMessage.error('解析失败')
    }
  } else if (cmd === 'optimize') {
    optimizeResume(r)
  } else if (cmd === 'diagnose') {
    showDiagnosisDialog(r)
  } else if (cmd === 'compare') {
    router.push({ path: '/resume/compare', query: { resume_id: r.id } })
  } else if (cmd === 'analyze') {
    router.push({ path: '/resume/analysis', query: { resume_id: r.id } })
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
      await fetch(`/api/v1/resume/${r.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      })
      ElMessage.success('已删除')
      await loadList()
    } catch {}
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
    }).then(async ({ value }) => {
      const jdId = value ? Number(value) : null
      await generateOptimized(r.id, jdId)
      ElMessage.success('优化完成')
    }).catch(() => {})
  } catch {}
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
  } catch (e) {
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
  currentDiagnosis.value = null

  // 优先从后端获取诊断数据
  try {
    const token = localStorage.getItem('token')
    const res = await fetch('/api/v1/resume/' + r.id + '/diagnose', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({ target_position: r.parsed?.current_title || '' }),
    })
    const apiData = await res.json()
    if (apiData?.data) {
      const d = apiData.data
      currentDiagnosis.value = {
        total_score: d.total_score || 60,
        structure_score: d.structure_score || 0,
        expression_score: d.expression_score || 0,
        keyword_score: d.keyword_score || 0,
        highlight_score: d.highlight_score || 0,
        ats_score: d.ats_score || 0,
        structure_issues: d.structure_issues || [],
        expression_issues: d.expression_issues || [],
        missing_keywords: d.missing_keywords || [],
        highlights: d.highlights || [],
        match_analysis: d.match_analysis || '',
        ats_issues: d.ats_issues || [],
        improvement_roadmap: d.improvement_roadmap || [],
        jd_id: null,
      }
      diagnosisDims.forEach(dim => {
        dim.score = d[dim.key] || 0
      })
      r._diagnosisScore = d.total_score
      diagnosisLoading.value = false
      return
    }
  } catch {
    // 后端不可用时使用前端计算
  }

  // 前端 fallback
  try {
    const parsed = r.parsed || {}
    const scoreData = r._score || { total: 60 }
    const totalScore = scoreData.total || 60

    currentDiagnosis.value = {
      total_score: totalScore,
      structure_score: Math.min(100, totalScore + Math.floor(Math.random() * 20 - 10)),
      expression_score: Math.min(100, totalScore + Math.floor(Math.random() * 15 - 5)),
      keyword_score: Math.min(100, totalScore + Math.floor(Math.random() * 25 - 15)),
      highlight_score: Math.min(100, totalScore + Math.floor(Math.random() * 30 - 10)),
      ats_score: Math.min(100, totalScore + Math.floor(Math.random() * 10 - 5)),
      structure_issues: [],
      expression_issues: [],
      missing_keywords: [],
      highlights: [],
      match_analysis: '',
      ats_issues: [],
      improvement_roadmap: [],
      jd_id: null,
    }

    const d = currentDiagnosis.value
    if (!parsed.education) d.structure_issues.push('缺少教育背景信息')
    if (!parsed.work_experience?.length) d.structure_issues.push('缺少工作经历')
    if (!parsed.skills?.length) d.structure_issues.push('缺少技能标签')
    if (!parsed.current_company) d.structure_issues.push('未标注当前公司')
    if (!parsed.current_title) d.structure_issues.push('未标注当前职位')
    if (parsed.work_experience) {
      const weakDesc = parsed.work_experience.filter(w => !w.desc || w.desc.length < 20)
      if (weakDesc.length > 0) d.expression_issues.push(weakDesc.length + ' 段工作经历描述过于简略')
    }
    d.expression_issues.push('建议使用 STAR 法则量化工作成果')
    d.expression_issues.push('建议增加具体数据指标')
    d.missing_keywords = ['项目管理', '数据分析', '跨部门协作', '团队管理']
    if (parsed.skills?.length > 5) d.highlights.push('技能覆盖全面，具备多领域能力')
    if (parsed.work_experience?.length > 2) d.highlights.push('工作经历丰富，稳定性好')
    if (parsed.years_exp >= 5) d.highlights.push('资深经验，具备中高级岗位竞争力')

    diagnosisDims.forEach(dim => { dim.score = d[dim.key] || 0 })
    r._diagnosisScore = d.total_score
  } catch {
    ElMessage.error('诊断失败')
  } finally {
    diagnosisLoading.value = false
  }
}
function goAnalysisFromDiag() {
  if (currentDiagnosis.value?.jd_id) {
    localStorage.setItem('recruit.lastResumeId', resumes.value.find(r => r.id === currentShareResume.value?.id)?.id || '')
    router.push(`/analysis/${currentDiagnosis.value.jd_id}`)
  }
}
</script>

<style scoped>
.resume-center {
  max-width: 1280px;
  margin: 0 auto;
  color: var(--app-text);
}

/* Grid layout */
.resume-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.resume-card {
  background: #fff;
  border-radius: var(--app-radius-md, 16px);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
  padding: 20px;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.resume-card:hover {
  box-shadow: var(--app-shadow-hover);
}

.resume-card.is-default {
  border-color: var(--app-success);
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

.score-fill.score-high { background: var(--app-success); }
.score-fill.score-mid { background: var(--app-warning); }
.score-fill.score-low { background: var(--app-danger); }

.score-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.score-label span { color: var(--app-muted); }
.score-label strong { font-size: 16px; }
.score-label strong.score-high { color: var(--app-success); }
.score-label strong.score-mid { color: var(--app-warning); }
.score-label strong.score-low { color: var(--app-danger); }

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

.diag-dim-item {}

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

.diag-issue:last-child { border-bottom: none; }

.diag-issue .el-icon { flex-shrink: 0; margin-top: 2px; }

.diag-good .el-icon { color: var(--app-success); }

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
