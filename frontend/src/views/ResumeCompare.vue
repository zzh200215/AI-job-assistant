<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span class="title">
            <el-icon><CopyDocument /></el-icon>
            简历对比
          </span>
          <div class="actions">
            <el-button size="small" type="primary" :loading="exporting" @click="onExport('docx')">
              <el-icon><Document /></el-icon>
              导出 Word
            </el-button>
            <el-button size="small" type="success" :loading="exporting" @click="onExport('pdf')">
              <el-icon><Document /></el-icon>
              导出 PDF
            </el-button>
          </div>
        </div>
      </template>

      <el-alert v-if="errorMsg" type="error" :closable="false" show-icon class="mb" :title="errorMsg" />

      <el-radio-group v-model="viewMode" class="mb">
        <el-radio-button value="side-by-side">左右对比</el-radio-button>
        <el-radio-button value="markdown">Markdown</el-radio-button>
        <el-radio-button value="structured">结构化数据</el-radio-button>
        <el-radio-button value="changes">修改日志</el-radio-button>
      </el-radio-group>

      <template v-if="viewMode === 'side-by-side'">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-card shadow="never" class="original-card">
              <template #header>
                <b>原简历</b>
                <el-tag v-if="originalATSScore" size="small" :type="originalATSScore >= 70 ? 'success' : 'warning'" style="margin-left:8px;">
                  ATS {{ originalATSScore }}分
                </el-tag>
              </template>
              <div class="md-preview original-bg">{{ originalContent || '暂无原始内容' }}</div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never" class="optimized-card">
              <template #header>
                <b>优化版</b>
                <el-tag v-if="optimizedATSScore" size="small" :type="optimizedATSScore >= 70 ? 'success' : 'warning'" style="margin-left:8px;">
                  ATS {{ optimizedATSScore }}分
                  <span v-if="atsImprovement" style="margin-left:4px;">(+{{ atsImprovement }})</span>
                </el-tag>
                <el-tag size="small" type="success" style="margin-left:4px;">AI 优化</el-tag>
              </template>
              <div class="md-preview optimized-bg">{{ optimizedContent || '暂无优化内容' }}</div>
            </el-card>
          </el-col>
        </el-row>
      </template>

      <template v-else-if="viewMode === 'markdown'">
        <el-card shadow="never">
          <template #header><b>Markdown 内容</b></template>
          <pre class="md-source">{{ optimizedContent || '暂无内容' }}</pre>
        </el-card>
      </template>

      <template v-else-if="viewMode === 'structured'">
        <el-card shadow="never" v-if="structuredData">
          <template #header><b>结构化数据</b></template>

          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="姓名">{{ structuredData.name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="电话">{{ structuredData.phone || '-' }}</el-descriptions-item>
            <el-descriptions-item label="邮箱" :span="2">{{ structuredData.email || '-' }}</el-descriptions-item>
            <el-descriptions-item label="个人简介" :span="2">{{ structuredData.summary || '-' }}</el-descriptions-item>
          </el-descriptions>

          <h4 class="mt">技能清单</h4>
          <el-tag v-for="skill in structuredData.skills || []" :key="skill" style="margin:2px;">{{ skill }}</el-tag>

          <h4 class="mt">工作经历</h4>
          <el-collapse>
            <el-collapse-item
              v-for="(item, index) in structuredData.experience || []"
              :key="index"
              :title="`${item.company} · ${item.position} (${item.period})`"
            >
              <ul>
                <li v-for="(highlight, hi) in item.highlights" :key="hi">{{ highlight }}</li>
              </ul>
            </el-collapse-item>
          </el-collapse>

          <h4 class="mt">项目经验</h4>
          <el-collapse>
            <el-collapse-item
              v-for="(item, index) in structuredData.projects || []"
              :key="index"
              :title="`${item.name} · ${item.role}`"
            >
              <div v-if="item.tech_stack">
                技术栈：
                <el-tag v-for="tech in item.tech_stack" :key="tech" size="small" style="margin:2px;">{{ tech }}</el-tag>
              </div>
              <ul>
                <li v-for="(highlight, hi) in item.highlights" :key="hi">{{ highlight }}</li>
              </ul>
            </el-collapse-item>
          </el-collapse>
        </el-card>
        <el-empty v-else description="暂无结构化数据" />
      </template>

      <template v-else>
        <el-card shadow="never" v-if="changesLog && changesLog.length">
          <template #header><b>修改日志（共 {{ changesLog.length }} 处）</b></template>
          <el-timeline>
            <el-timeline-item v-for="(item, index) in changesLog" :key="index" type="primary">
              <template #timestamp>{{ item.section || '' }}</template>
              <div class="change-item">
                <div class="change-label">原文</div>
                <div class="change-original">{{ item.original }}</div>
                <div class="change-label">优化</div>
                <div class="change-optimized">{{ item.optimized }}</div>
                <div class="change-reason">原因：{{ item.reason }}</div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
        <el-empty v-else description="暂无修改记录" />
      </template>
    </el-card>

    <el-card v-if="!optimizedContent && !loading" class="mt">
      <el-alert type="info" :closable="false" show-icon>
        <template #title>暂无优化版简历，点击下方按钮生成</template>
        <template #append>
          <el-button type="primary" :loading="generating" @click="onGenerate">
            {{ generating ? '生成中…' : '生成优化版简历' }}
          </el-button>
        </template>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { CopyDocument, Document } from '@element-plus/icons-vue'
import {
  downloadResumeExport,
  generateOptimized,
  getResume,
  getResumeVersions,
} from '@/api/resume'

const route = useRoute()
const resumeId = ref(null)

const loading = ref(true)
const generating = ref(false)
const exporting = ref(false)
const errorMsg = ref('')

const viewMode = ref('side-by-side')
const originalContent = ref('')
const optimizedContent = ref('')
const structuredData = ref(null)
const changesLog = ref([])
const originalATSScore = ref(null)
const optimizedATSScore = ref(null)

const atsImprovement = computed(() => {
  if (originalATSScore.value !== null && optimizedATSScore.value !== null) {
    const diff = optimizedATSScore.value - originalATSScore.value
    return diff > 0 ? diff : 0
  }
  return null
})

onMounted(async () => {
  resumeId.value = Number(route.params.id)
  await loadData()
})

const loadData = async () => {
  loading.value = true
  try {
    const versions = await getResumeVersions(resumeId.value)
    originalContent.value = versions.original?.content || ''

    const list = versions.versions || []
    const markdownVersion = list.find(item => item.format === 'md')
    if (markdownVersion) {
      optimizedContent.value = markdownVersion.content
    }

    const jsonVersion = list.find(item => item.format === 'json')
    if (jsonVersion) {
      try {
        structuredData.value = JSON.parse(jsonVersion.content)
      } catch {
        structuredData.value = null
      }
    }

    try {
      const resume = await getResume(resumeId.value)
      if (!originalContent.value && resume.parsed) {
        originalContent.value = JSON.stringify(resume.parsed, null, 2)
      }
    } catch {
      // Ignore fallback load failure.
    }
  } catch (error) {
    errorMsg.value = error.message || '加载失败'
  } finally {
    loading.value = false
  }
}

const onGenerate = async () => {
  generating.value = true
  errorMsg.value = ''
  try {
    const result = await generateOptimized(resumeId.value)
    optimizedContent.value = result.markdown_content || ''
    structuredData.value = result.structured_data || null
    changesLog.value = result.changes_log || []
    ElMessage.success('优化版简历生成成功')
    viewMode.value = 'side-by-side'
  } catch (error) {
    errorMsg.value = error.message || '生成失败'
  } finally {
    generating.value = false
  }
}

const onExport = async (format) => {
  if (!optimizedContent.value) {
    ElMessage.warning('请先生成优化版简历')
    return
  }

  exporting.value = true
  try {
    const blob = await downloadResumeExport(resumeId.value, format, 'optimized')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `resume_${resumeId.value}_optimized.${format}`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`${format.toUpperCase()} 导出成功`)
  } catch (error) {
    ElMessage.error(error.message || '导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.header-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.title { display: inline-flex; align-items: center; gap: 8px; }
.actions { display: flex; gap: 8px; }
.mt { margin-top: 16px; }
.mb { margin-bottom: 16px; }
.original-card { border-color: #dcdfe6; }
.optimized-card { border-color: #67C23A; }
.md-preview { padding: 16px; border-radius: 4px; font-size: 13px; line-height: 1.7; white-space: pre-wrap; }
.original-bg { background: #f5f7fa; color: #606266; }
.optimized-bg { background: #f0f9eb; color: #303133; }
.md-source {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 600px;
  overflow: auto;
  white-space: pre-wrap;
}
.change-item { font-size: 13px; }
.change-label { font-weight: 600; margin-top: 6px; color: #909399; font-size: 12px; }
.change-original { color: #F56C6C; background: #fef0ef; padding: 4px 8px; border-radius: 3px; }
.change-optimized { color: #67C23A; background: #f0f9eb; padding: 4px 8px; border-radius: 3px; }
.change-reason { color: #409EFF; font-size: 12px; margin-top: 2px; }
h4 { margin: 12px 0 6px; }
</style>
