<template>
  <div class="page-shell resume-center">
    <div class="page-header">
      <div>
        <h2>简历管理</h2>
        <div class="page-header-sub">上传、解析、优化、导出 — 简历全生命周期管理</div>
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
          <el-descriptions-item label="姓名">{{ currentParsed.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="工作年限">{{ currentParsed.years_exp || 0 }} 年</el-descriptions-item>
          <el-descriptions-item label="电话">{{ currentParsed.phone || '-' }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ currentParsed.email || '-' }}</el-descriptions-item>
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
                  <el-dropdown-item command="compare">版本对比</el-dropdown-item>
                  <el-dropdown-item command="analyze">深度分析</el-dropdown-item>
                  <el-dropdown-item v-if="r.id !== defaultResumeId" command="setDefault">设为默认</el-dropdown-item>
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
            <el-button size="small" @click="optimizeResume(r)">AI优化</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { UploadFilled, MoreFilled, Briefcase, Timer, Document, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  uploadResume,
  parseResume,
  getResumeList,
  generateOptimized,
  exportResume,
  downloadResumeExport,
} from '@/api/resume'

const router = useRouter()

const showUpload = ref(false)
const showParsed = ref(false)
const currentParsed = ref(null)
const listLoading = ref(true)
const resumes = ref([])
const defaultResumeId = ref(null)

const uploading = ref(false)
const uploadProgress = ref(0)
const uploadStatus = ref('')
const uploadError = ref('')

const LS_DEFAULT_KEY = 'recruit.defaultResumeId'

onMounted(() => {
  defaultResumeId.value = Number(localStorage.getItem(LS_DEFAULT_KEY)) || null
  loadList()
})

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

async function loadList() {
  listLoading.value = true
  try {
    const data = await getResumeList({ page: 1, page_size: 50 })
    const items = data?.items || []
    // attach local state
    items.forEach(r => { r._score = null; r._scoring = false })
    resumes.value = items

    // auto load quick scores
    items.forEach(r => quickScore(r))
  } catch {} finally {
    listLoading.value = false
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
  } else if (cmd === 'compare') {
    router.push({ path: '/resume/compare', query: { resume_id: r.id } })
  } else if (cmd === 'analyze') {
    router.push({ path: '/resume/analysis', query: { resume_id: r.id } })
  } else if (cmd === 'setDefault') {
    defaultResumeId.value = r.id
    localStorage.setItem(LS_DEFAULT_KEY, String(r.id))
    ElMessage.success('已设为默认简历')
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
  margin-bottom: 10px;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title-row h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.more-btn {
  cursor: pointer;
  color: var(--app-muted);
  font-size: 16px;
}

.default-tag {
  margin-left: auto;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  color: var(--app-muted);
  margin-bottom: 10px;
}

.card-meta span {
  display: flex;
  align-items: center;
  gap: 3px;
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

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 12px;
  }
  .resume-grid {
    grid-template-columns: 1fr;
  }
}
</style>
