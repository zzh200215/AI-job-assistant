<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>面试作战室</h2>
        <div class="page-header-sub">所有面试准备、实战记录和复盘集中管理</div>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="$router.push('/interview/setup')">
          <el-icon><Microphone /></el-icon> 开始模拟面试
        </el-button>
      </div>
    </div>

    <!-- 即将到来的面试 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-violet)"><Clock /></el-icon>
          <h3>即将面试</h3>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="upcomingLoading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-else-if="!upcomingInterviews.length" class="empty-inline">
          暂无即将到来的面试
        </div>
        <div v-else class="interview-list">
          <div
            v-for="item in upcomingInterviews"
            :key="item.id"
            class="interview-row upcoming"
            @click="goToPipeline(item)"
          >
            <div class="interview-dot violet" />
            <div class="interview-info">
              <strong>{{ item.company || '' }} - {{ item.title || '' }}</strong>
              <span>第{{ item.interview_round || 1 }}轮 · {{ formatDate(item.interview_at) }}</span>
            </div>
            <div class="interview-actions">
              <el-button size="small" @click.stop="startPrep(item)">AI准备</el-button>
              <el-button size="small" type="primary" @click.stop="$router.push('/interview/setup')">模拟面试</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 面试历史 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-primary)"><ChatLineSquare /></el-icon>
          <h3>面试记录</h3>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="sessionsLoading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-else-if="!sessions.length" class="empty-inline">
          还没有面试记录，开始一次模拟面试吧
        </div>
        <div v-else class="interview-list">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="interview-row"
            @click="$router.push(`/interview/report/${s.id}`)"
          >
            <div class="interview-dot" :class="s.status === 'completed' ? 'green' : 'amber'" />
            <div class="interview-info">
              <strong>{{ s.jd_title || s.position || '模拟面试' }}</strong>
              <span>{{ formatDate(s.created_at) }} · {{ s.status === 'completed' ? '已完成' : '进行中' }}</span>
            </div>
            <div v-if="s.overall_score" class="interview-score">
              <strong>{{ s.overall_score }}</strong>
              <span>分</span>
            </div>
            <el-icon class="interview-arrow"><ArrowRight /></el-icon>
          </div>
        </div>
      </div>
    </div>

    <!-- 面试题浏览 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-success)"><Document /></el-icon>
          <h3>面试题库</h3>
        </div>
        <el-button size="small" @click="useLast">
          加载最近分析
        </el-button>
      </div>
      <div class="panel-body">
        <div v-if="!questionData" class="question-load">
          <el-input-number v-model="recordId" :min="1" placeholder="分析记录ID" />
          <el-button @click="loadById" :loading="questionLoading">加载</el-button>
          <span class="hint">输入分析记录ID查看面试题</span>
        </div>
        <div v-else>
          <div v-for="(items, key) in questionGroups" :key="key" class="question-group">
            <h4>{{ getInterviewGroupTitle(key) }}</h4>
            <div v-if="!items.length" class="empty-inline">该类型暂时没有题目</div>
            <div v-for="(q, i) in items" :key="i" class="question-card">
              <div class="q-text"><b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}</div>
              <div class="q-focus">考察点：{{ q.focus || q.intent || '-' }}</div>
              <div class="q-answer">参考答案：{{ q.suggested_answer || q.expected_answer || q.ref_answer || '-' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  ChatLineSquare,
  Clock,
  Document,
  Loading,
  Microphone,
} from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import { getInterviewList } from '@/api/interview'
import { getAnalysis } from '@/api/analysis'
import { getJobPipelineList } from '@/api/jobs'
import { getInterviewGroupTitle, normalizeInterviewQuestions } from '@/utils/interviewQuestions'

const router = useRouter()

const upcomingLoading = ref(true)
const upcomingInterviews = ref([])
const sessionsLoading = ref(true)
const sessions = ref([])

const recordId = ref(null)
const questionData = ref(null)
const questionLoading = ref(false)

const questionGroups = computed(() => normalizeInterviewQuestions(questionData.value?.interview_questions))

function formatDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return d
  }
}

function goToPipeline(item) {
  router.push(`/jobs/pipeline/${item.id}`)
}

function startPrep(item) {
  router.push({
    path: '/interview/setup',
    query: { jd_id: item.jd_id ? String(item.jd_id) : undefined },
  })
}

async function loadUpcoming() {
  upcomingLoading.value = true
  try {
    const data = await getJobPipelineList({ stage: 'interview', limit: 10 })
    upcomingInterviews.value = (data?.items || data || []).filter(
      p => p.interview_at && new Date(p.interview_at) >= new Date()
    )
  } catch {} finally {
    upcomingLoading.value = false
  }
}

async function loadSessions() {
  sessionsLoading.value = true
  try {
    const data = await getInterviewList()
    sessions.value = Array.isArray(data) ? data : (data?.items || [])
  } catch {} finally {
    sessionsLoading.value = false
  }
}

async function loadById() {
  if (!recordId.value) {
    ElMessage.warning('请先填写记录 ID')
    return
  }
  questionLoading.value = true
  try {
    const rec = await getAnalysis(recordId.value)
    questionData.value = rec
    localStorage.setItem('recruit.lastRecordId', String(rec?.record_id || rec?.id || recordId.value))
  } catch (e) {
    ElMessage.error(`加载失败：${e.message}`)
  } finally {
    questionLoading.value = false
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

onMounted(() => {
  loadUpcoming()
  loadSessions()
})
</script>

<style scoped>
/* Component-specific styles only — panel/page-shell classes come from panels.css */

.empty-inline {
  text-align: center;
  padding: 16px 0;
  color: var(--app-muted);
  font-size: 14px;
}

/* Interview list */
.interview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.interview-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--app-radius-xs, 8px);
  cursor: pointer;
  transition: background 0.15s;
}

.interview-row:hover {
  background: var(--el-fill-color-light);
}

.interview-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.interview-dot.violet { background: var(--app-violet); }
.interview-dot.green { background: var(--app-success); }
.interview-dot.amber { background: var(--app-warning); }

.interview-info {
  flex: 1;
  min-width: 0;
}

.interview-info strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
}

.interview-info span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
  margin-top: 2px;
}

.interview-actions {
  display: flex;
  gap: 6px;
}

.interview-score {
  text-align: center;
  padding: 4px 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-primary-light);
}

.interview-score strong {
  font-size: 18px;
  font-weight: 700;
  color: var(--app-primary);
}

.interview-score span {
  font-size: 11px;
  color: var(--app-muted);
}

.interview-arrow {
  color: var(--app-muted);
}

/* Question section */
.question-load {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hint {
  font-size: 13px;
  color: var(--app-muted);
}

.question-group {
  margin-bottom: 16px;
}

.question-group h4 {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 700;
}

.question-card {
  padding: 12px 14px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--app-line);
  margin-bottom: 8px;
}

.q-text {
  font-size: 14px;
  font-weight: 500;
}

.q-focus {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-muted);
}

.q-answer {
  margin-top: 4px;
  font-size: 13px;
  color: var(--app-primary);
  line-height: 1.6;
}

@media (max-width: 768px) {
  .interview-actions {
    flex-direction: column;
  }
}
</style>
