<template>
  <div class="page">
    <el-card>
      <template #header>
        <span
          ><el-icon><Document /></el-icon> 输入岗位 JD</span
        >
      </template>

      <el-form :model="form" label-position="top" class="jd-form">
        <div class="form-grid">
          <el-form-item label="岗位名称">
            <el-input v-model="form.title" placeholder="如：Python 后端开发工程师" />
          </el-form-item>
          <el-form-item label="公司">
            <el-input v-model="form.company" placeholder="可选，如：示例科技" />
          </el-form-item>
        </div>
        <el-form-item label="JD 文本" class="wide-field">
          <el-input
            v-model="form.raw_text"
            type="textarea"
            :rows="10"
            placeholder="粘贴岗位 JD 完整内容…"
          />
        </el-form-item>
        <el-form-item class="wide-field">
          <el-button type="primary" :loading="loading" @click="onSubmit">
            <el-icon><Promotion /></el-icon> {{ loading ? '创建并解析中…' : '创建并解析' }}
          </el-button>
          <el-button @click="onClear">清空</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 解析结果 -->
    <el-card v-if="parsed" class="mt">
      <template #header>
        <span>解析结果（JD ID = {{ createdId }}）</span>
        <el-button type="primary" size="small" class="fr" @click="goAnalysis">
          <el-icon><DataAnalysis /></el-icon> 去分析
        </el-button>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="岗位">{{ parsed.title || '-' }}</el-descriptions-item>
        <el-descriptions-item label="公司">{{ parsed.company || '-' }}</el-descriptions-item>
        <el-descriptions-item label="地点">{{ parsed.location || '-' }}</el-descriptions-item>
        <el-descriptions-item label="薪资">{{ parsed.salary_range || '-' }}</el-descriptions-item>
        <el-descriptions-item label="经验">{{
          parsed.experience_requirement || '-'
        }}</el-descriptions-item>
        <el-descriptions-item label="学历">{{
          parsed.education_requirement || '-'
        }}</el-descriptions-item>
        <el-descriptions-item label="关键词" :span="2">
          <el-tag v-for="k in parsed.keywords || []" :key="k" type="success" style="margin: 2px">{{
            k
          }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="必备技能" :span="2">
          <el-tag v-for="s in parsed.required_skills || []" :key="s" style="margin: 2px">{{
            s
          }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="加分项" :span="2">
          <el-tag v-for="s in parsed.nice_to_have || []" :key="s" type="info" style="margin: 2px">{{
            s
          }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="岗位职责" :span="2">
          <ul style="padding-left: 18px; margin: 0">
            <li v-for="(r, i) in parsed.responsibilities || []" :key="i">{{ r }}</li>
          </ul>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { createJD, parseJD } from '@/api/jd'

const router = useRouter()
const loading = ref(false)
const createdId = ref(null)
const parsed = ref(null)

const form = reactive({ title: '', company: '', raw_text: '' })

const onClear = () => {
  form.title = ''
  form.company = ''
  form.raw_text = ''
  parsed.value = null
  createdId.value = null
}

const onSubmit = async () => {
  // 前端校验
  if (!form.title || !form.title.trim()) {
    ElMessage.warning('请填写岗位名称')
    return
  }
  if (!form.raw_text || !form.raw_text.trim()) {
    ElMessage.warning('JD 内容不能为空')
    return
  }

  loading.value = true
  try {
    // 1) 创建 JD
    const jd = await createJD({
      title: form.title,
      company: form.company || null,
      raw_text: form.raw_text,
    })
    // 2) 解析 JD
    const res = await parseJD(jd.id)
    createdId.value = jd.id
    parsed.value = res.parsed
    localStorage.setItem('recruit.lastJDId', jd.id)
    ElMessage.success('创建并解析成功')
  } catch {
    // request.js 已显示错误信息
  } finally {
    loading.value = false
  }
}

const goAnalysis = () => router.push('/analysis')
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}
.jd-form {
  width: 100%;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.wide-field :deep(.el-textarea__inner) {
  min-height: 320px !important;
}
.fr {
  float: right;
}
@media (max-width: 680px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
