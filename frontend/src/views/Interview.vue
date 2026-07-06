<template>
  <div class="page">
    <el-card>
      <template #header>
        <span><el-icon><ChatLineSquare /></el-icon> 面试题</span>
        <el-button size="small" type="primary" class="fr" @click="regen" :loading="regenLoading">
          重新生成
        </el-button>
      </template>

      <el-form :inline="true">
        <el-form-item label="分析记录 ID">
          <el-input-number v-model="recordId" :min="1" />
        </el-form-item>
        <el-form-item>
          <el-button @click="loadById">加载</el-button>
          <el-button @click="useLast">使用最近一次</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <template v-if="data">
      <div v-for="(items, key) in groups" :key="key" class="block">
        <h3>{{ getInterviewGroupTitle(key) }}</h3>
        <el-empty v-if="!items.length" description="该类型暂时没有题目" />
        <el-card v-for="(q, i) in items" :key="i" shadow="never" class="q-card">
          <div class="q"><b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}</div>
          <div class="i">考察点：{{ q.focus || q.intent || '-' }}</div>
          <div class="a">参考答案：{{ q.suggested_answer || q.expected_answer || q.ref_answer || '-' }}</div>
        </el-card>
      </div>
    </template>

    <el-empty v-else description="请输入或选择一条分析记录 ID 以查看面试题" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChatLineSquare } from '@element-plus/icons-vue'

import { getAnalysis, regenInterview } from '@/api/analysis'
import { ElMessage } from '@/plugins/element-services'
import { getInterviewGroupTitle, normalizeInterviewQuestions } from '@/utils/interviewQuestions'

const route = useRoute()
const recordId = ref(null)
const data = ref(null)
const regenLoading = ref(false)

const groups = computed(() => normalizeInterviewQuestions(data.value?.interview_questions))

async function fetchRecord(id) {
  const rec = await getAnalysis(id)
  data.value = rec
  localStorage.setItem('recruit.lastRecordId', String(rec?.record_id || rec?.id || id))
}

async function loadById() {
  if (!recordId.value) {
    ElMessage.warning('请先填写记录 ID')
    return
  }
  try {
    await fetchRecord(recordId.value)
  } catch (error) {
    ElMessage.error(`加载失败：${error.message}`)
  }
}

function useLast() {
  const last = localStorage.getItem('recruit.lastRecordId')
  if (!last) {
    ElMessage.warning('暂无最近分析记录')
    return
  }
  recordId.value = Number(last)
  loadById()
}

async function regen() {
  if (!recordId.value) {
    ElMessage.warning('请先填写记录 ID')
    return
  }

  regenLoading.value = true
  try {
    const res = await regenInterview(recordId.value)
    data.value = {
      ...data.value,
      interview_questions: res.interview_questions,
    }
    ElMessage.success('已重新生成')
  } finally {
    regenLoading.value = false
  }
}

onMounted(() => {
  if (route.query.record_id) {
    recordId.value = Number(route.query.record_id)
    loadById()
    return
  }
  useLast()
})
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.fr { float: right; }
.block h3 { margin: 8px 0; }
.q-card { margin: 8px 0; }
.q { font-size: 14px; }
.i { color: #909399; font-size: 12px; margin: 4px 0; }
.a { color: #67c23a; font-size: 13px; }
</style>
