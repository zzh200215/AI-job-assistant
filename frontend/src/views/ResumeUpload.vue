<template>
  <div class="page">
    <el-card>
      <template #header>
        <span><el-icon><UploadFilled /></el-icon> 上传简历</span>
      </template>

      <!-- 拖拽上传区域 -->
      <el-upload
        drag
        action="#"
        :http-request="customUpload"
        :show-file-list="false"
        :before-upload="beforeUpload"
        accept=".pdf,.docx,.doc,.png,.jpg,.jpeg"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 PDF / DOCX / 图片简历（PNG、JPG、JPEG），大小不超过 10MB
          </div>
        </template>
      </el-upload>

      <el-alert
        class="mt"
        :type="ocrEnabled ? 'success' : 'warning'"
        :closable="false"
        show-icon
        :title="ocrEnabled ? '当前环境已开启 OCR，可识别图片简历和扫描件 PDF。' : '当前环境未开启 OCR，图片简历和扫描件 PDF 可能无法解析。'"
      />

      <!-- 上传进度 -->
      <el-card v-if="uploading" class="mt">
        <div class="progress-info">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ uploadStatus }}</span>
        </div>
        <el-progress
          :percentage="uploadProgress"
          :status="uploadProgress === 100 ? 'success' : undefined"
          :stroke-width="12"
          :text-inside="true"
        />
        <div class="progress-sub" v-if="uploadProgress < 100">
          正在上传… {{ formatSize(uploadedBytes) }} / {{ formatSize(totalBytes) }}
        </div>
      </el-card>

      <!-- 上传失败 + 重试 -->
      <el-card v-if="uploadError" class="mt">
        <el-alert
          :title="uploadError"
          type="error"
          :closable="false"
          show-icon
        >
          <template #append>
            <el-button size="small" type="danger" @click="retryUpload" :loading="retrying">
              重新上传
            </el-button>
          </template>
        </el-alert>
      </el-card>
    </el-card>

    <!-- 已上传的简历列表 -->
    <el-card v-if="resumes.length" class="mt">
      <template #header>
        <span>本机已上传的简历（最新 {{ resumes.length }} 条）</span>
        <el-button size="small" type="danger" plain class="fr" @click="clearAll">清空</el-button>
      </template>

      <el-table :data="resumes" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="file_name" label="文件名" show-overflow-tooltip />
        <el-table-column prop="file_type" label="类型" width="80" />
        <el-table-column prop="file_size" label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="候选人" width="160">
          <template #default="{ row }">
            <span v-if="row.parsed?.name">{{ row.parsed.name }} · {{ row.parsed.years_exp }}年</span>
            <el-tag v-else type="info" size="small">未解析</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="goParse(row)" :loading="row.__loading">
              {{ row.parsed ? '重新解析' : '解析' }}
            </el-button>
            <el-button size="small" type="primary" @click="goAnalysis(row)">去分析</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

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
            <el-tag v-for="s in currentParsed.skills || []" :key="s" style="margin: 2px;">{{ s }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <h4>工作经历</h4>
        <el-timeline>
          <el-timeline-item
            v-for="(w, i) in currentParsed.work_experience || []" :key="i"
            :timestamp="`${w.start || ''} ~ ${w.end || ''}`"
          >
            <b>{{ w.company }} · {{ w.title }}</b>
            <div class="muted">{{ w.desc }}</div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { UploadFilled, Loading } from '@element-plus/icons-vue'
import { uploadResume, parseResume, getResume } from '@/api/resume'
import { getSystemStatus } from '@/api/system'

const router = useRouter()
const resumes = ref([])
const showParsed = ref(false)
const currentParsed = ref(null)
const ocrEnabled = ref(false)

// ---- 上传状态 ----
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadedBytes = ref(0)
const totalBytes = ref(0)
const uploadStatus = ref('准备上传…')
const uploadError = ref('')
const retrying = ref(false)

// 保存待重试的文件
let pendingFile = null

const LS_KEY = 'recruit.resumes'

const loadList = () => {
  try {
    resumes.value = JSON.parse(localStorage.getItem(LS_KEY) || '[]')
  } catch { resumes.value = [] }
}
const saveList = () => localStorage.setItem(LS_KEY, JSON.stringify(resumes.value))

onMounted(async () => {
  loadList()
  try {
    const status = await getSystemStatus()
    ocrEnabled.value = !!status?.capabilities?.ocr_resume_parse
  } catch {
    ocrEnabled.value = false
  }
})

const formatSize = (n) => {
  if (!n) return '-'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(2) + ' MB'
}

const beforeUpload = (file) => {
  // 前端预校验：文件类型
  const ext = file.name.split('.').pop().toLowerCase()
  if (!['pdf', 'docx', 'doc', 'png', 'jpg', 'jpeg'].includes(ext)) {
    ElMessage.error('仅支持 PDF / DOCX / 图片简历（PNG、JPG、JPEG）')
    return false
  }
  // 前端预校验：文件大小
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error(`文件超过 10MB（当前 ${(file.size / 1024 / 1024).toFixed(1)}MB），请压缩后重试`)
    return false
  }
  return true
}

const customUpload = async ({ file }) => {
  pendingFile = file
  uploading.value = true
  uploadError.value = ''
  uploadProgress.value = 0
  uploadedBytes.value = 0
  totalBytes.value = file.size
  uploadStatus.value = '正在上传…'

  try {
    // 上传（带进度回调）
    const data = await uploadResume(file, (event) => {
      const loaded = Number(event?.loaded || 0)
      const total = Number(event?.total || file.size || 0)
      const ratio = total > 0 ? loaded / total : 0
      uploadProgress.value = Math.max(0, Math.min(100, Math.round(ratio * 100)))
      uploadedBytes.value = loaded
    })

    uploadStatus.value = '上传完成，正在解析…'
    uploadProgress.value = 100

    // 上传成功后立即调一次解析
    const parsed = await parseResume(data.id)
    const item = { ...data, parsed: parsed.parsed, __loading: false }
    resumes.value.unshift(item)
    saveList()
    currentParsed.value = parsed.parsed
    showParsed.value = true
    ElMessage.success('上传并解析成功')
    uploadError.value = ''
    pendingFile = null
  } catch (e) {
    uploadError.value = e.message || '上传失败，请重试'
    uploadProgress.value = 0
  } finally {
    uploading.value = false
  }
}

const retryUpload = async () => {
  if (!pendingFile) {
    ElMessage.warning('没有可重试的文件')
    return
  }
  retrying.value = true
  // 模拟文件对象重新传入
  await customUpload({ file: pendingFile })
  retrying.value = false
}

const goParse = async (row) => {
  row.__loading = true
  try {
    const parsed = await parseResume(row.id)
    row.parsed = parsed.parsed
    saveList()
    currentParsed.value = parsed.parsed
    showParsed.value = true
    ElMessage.success('解析成功')
  } catch (e) {
    // request.js 已提示
  } finally {
    row.__loading = false
  }
}

const goAnalysis = (row) => {
  localStorage.setItem('recruit.lastResumeId', row.id)
  router.push('/analysis')
}

const clearAll = () => {
  resumes.value = []
  saveList()
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.mt   { margin-top: 0; }
.fr   { float: right; }
.muted{ color: #909399; font-size: 12px; }
h4    { margin: 16px 0 8px; }
.progress-info  { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.progress-sub   { color: #909399; font-size: 12px; margin-top: 6px; text-align: right; }
</style>
