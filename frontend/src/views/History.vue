<template>
  <div class="page history-page">
    <section class="history-hero">
      <div>
        <span class="hero-kicker">History Center</span>
        <h1>分析历史记录</h1>
        <p>回看过去的分析结果、定位面试题和删除无效记录，保证工作台上下文始终干净。</p>
      </div>
      <div class="hero-actions">
        <el-button @click="loadList">刷新</el-button>
      </div>
    </section>

    <el-card class="history-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span><el-icon><Clock /></el-icon> 历史记录</span>
          <el-tag type="info" effect="plain">{{ total }} 条</el-tag>
        </div>
      </template>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="简历" min-width="180">
          <template #default="{ row }">
            <div>{{ row.resume_name || '-' }}</div>
            <div class="muted">{{ row.resume_file }}</div>
          </template>
        </el-table-column>
        <el-table-column label="岗位" min-width="180">
          <template #default="{ row }">
            <div>{{ row.jd_title || '-' }}</div>
            <div class="muted">{{ row.jd_company }}</div>
          </template>
        </el-table-column>
        <el-table-column label="匹配度" width="120">
          <template #default="{ row }">
            <el-tag :type="scoreType(row.match_score)">{{ row.match_score ?? '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" />
        <el-table-column prop="create_time" label="时间" width="180" />
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">查看</el-button>
            <el-button v-if="!authStore.isRecruiter" size="small" type="primary" @click="goInterview(row)">面试题</el-button>
            <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @current-change="loadList"
        @size-change="loadList"
      />
    </el-card>

    <!-- 详情弹窗 (优化布局) -->
    <el-dialog v-model="showDetail" title="分析详情" width="900px" top="5vh">
      <div v-if="detail" v-loading="detailLoading">
        <!-- 概要信息 -->
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="记录 ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="匹配度">
            <el-tag :type="scoreType(detail.match_score)" size="small">{{ detail.match_score }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="分析时间">{{ detail.create_time }}</el-descriptions-item>
          <el-descriptions-item label="简历">
            {{ detail.resume?.name || '-' }}（{{ detail.resume?.file_name || '-' }}）
          </el-descriptions-item>
          <el-descriptions-item label="岗位">
            {{ detail.jd?.title || '-' }} @ {{ detail.jd?.company || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- Tab 切换：匹配度 / 优化建议 / 面试题 -->
        <el-tabs class="mt">
          <el-tab-pane label="📊 匹配度报告">
            <template v-if="detail.match_report">
              <el-alert
                :title="`综合推荐：${localizedRecommendation || '--'}`"
                :type="recommendType(localizedRecommendation)"
                :closable="false"
                show-icon
              />
              <p class="mt">{{ localizedSummary }}</p>
              <el-descriptions :column="4" border size="small" class="mt">
                <el-descriptions-item label="技能">
                  <b>{{ detail.match_report.dimension_scores?.skills?.score ?? 0 }}</b>
                </el-descriptions-item>
                <el-descriptions-item label="经验">
                  <b>{{ detail.match_report.dimension_scores?.experience?.score ?? 0 }}</b>
                </el-descriptions-item>
                <el-descriptions-item label="学历">
                  <b>{{ detail.match_report.dimension_scores?.education?.score ?? 0 }}</b>
                </el-descriptions-item>
                <el-descriptions-item label="行业">
                  <b>{{ detail.match_report.dimension_scores?.industry?.score ?? 0 }}</b>
                </el-descriptions-item>
              </el-descriptions>
              <el-row :gutter="16" class="mt">
                <el-col :span="12">
                  <h4>✅ 优势</h4>
                  <ul>
                    <li v-for="(x, i) in localizedStrengths" :key="i">
                      <b>{{ x.item || x }}</b>
                      <span v-if="x.impact">：{{ x.impact }}</span>
                      <span v-if="x.evidence" class="muted">（{{ x.evidence }}）</span>
                    </li>
                  </ul>
                </el-col>
                <el-col :span="12">
                  <h4>⚠️ 差距 / 风险</h4>
                  <ul>
                    <li v-for="(x, i) in localizedGaps" :key="i">
                      <b>{{ x.item || x }}</b>
                      <span v-if="x.action">：{{ x.action }}</span>
                      <span v-if="x.impact && !x.action">：{{ x.impact }}</span>
                      <el-tag v-if="x.severity" size="small" :type="x.severity === '高' ? 'danger' : x.severity === '中' ? 'warning' : 'info'" style="margin-left:4px;">{{ x.severity }}</el-tag>
                    </li>
                    <li v-for="(x, i) in localizedRiskPoints" :key="'r'+i" class="risk">{{ x }}</li>
                  </ul>
                </el-col>
              </el-row>
            </template>
            <el-empty v-else description="暂无匹配度报告" />
          </el-tab-pane>

          <el-tab-pane label="📝 简历优化建议">
            <template v-if="detail.optimize_suggestions">
              <el-alert
                :title="detail.optimize_suggestions.overall || ''"
                type="success" :closable="false" show-icon
              />
              <el-collapse class="mt">
                <el-collapse-item
                  v-for="(s, i) in detail.optimize_suggestions.sections || []" :key="i"
                  :title="`【${s.section}】`"
                >
                  <ul><li v-for="(x, j) in s.suggestions" :key="j">{{ x }}</li></ul>
                </el-collapse-item>
              </el-collapse>
              <div class="mt">
                <span>➕ 补充关键词：</span>
                <el-tag v-for="k in detail.optimize_suggestions.keywords_to_add || []" :key="k" type="success" size="small" style="margin:2px;">{{ k }}</el-tag>
              </div>
              <div class="mt">
                <span>➖ 删除关键词：</span>
                <el-tag v-for="k in detail.optimize_suggestions.keywords_to_remove || []" :key="k" type="danger" size="small" style="margin:2px;">{{ k }}</el-tag>
              </div>
            </template>
            <el-empty v-else description="暂无优化建议" />
          </el-tab-pane>

          <el-tab-pane label="💬 面试题">
            <template v-if="hasInterviewQuestions">
              <div v-for="key in interviewKeys" :key="key">
                <template v-if="detail.interview_questions[key]?.length">
                  <h4>{{ groupTitle(key) }}（{{ detail.interview_questions[key].length }} 题）</h4>
                  <el-card v-for="(q, i) in detail.interview_questions[key]" :key="i" shadow="never" class="q-card">
                    <div class="q"><b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}</div>
                    <div class="i">🎯 {{ q.focus || q.intent }}</div>
                    <div class="a">💡 {{ q.suggested_answer || q.expected_answer || q.ref_answer }}</div>
                    <div v-if="q.preparation_tips" class="tip">📝 {{ q.preparation_tips }}</div>
                  </el-card>
                </template>
              </div>
            </template>
            <el-empty v-else description="暂无面试题" />
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { listHistory, getHistoryDetail, deleteHistory } from '@/api/history'
import { useAuthStore } from '@/stores/auth'
import {
  getInterviewGroupTitle,
  hasInterviewQuestions as checkHasInterviewQuestions,
  normalizeInterviewQuestions,
} from '@/utils/interviewQuestions'
import {
  localizeRecommendationText,
  localizeSentence,
  normalizeLocalizedObjectList,
  normalizeLocalizedTextList,
} from '@/utils/analysisLocalization'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const detailLoading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

const showDetail = ref(false)
const detail = ref(null)

const interviewKeys = ['hr_questions', 'tech_questions', 'project_questions', 'scenario_questions']

const hasInterviewQuestions = computed(() => {
  return checkHasInterviewQuestions(detail.value?.interview_questions)
})
const localizedRecommendation = computed(() => localizeRecommendationText(detail.value?.match_report?.recommendation || ''))
const localizedSummary = computed(() => localizeSentence(detail.value?.match_report?.summary || ''))
const localizedStrengths = computed(() => normalizeLocalizedObjectList(detail.value?.match_report?.strengths))
const localizedGaps = computed(() => normalizeLocalizedObjectList(detail.value?.match_report?.gaps))
const localizedRiskPoints = computed(() => normalizeLocalizedTextList(detail.value?.match_report?.risk_points))

const loadList = async () => {
  loading.value = true
  try {
    const data = await listHistory({ page: page.value, page_size: pageSize.value })
    list.value = data.items
    total.value = data.total
  } catch (e) {
    // request.js 已提示
  } finally {
    loading.value = false
  }
}

const openDetail = async (row) => {
  showDetail.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const detailData = await getHistoryDetail(row.id)
    detail.value = {
      ...detailData,
      interview_questions: normalizeInterviewQuestions(detailData?.interview_questions),
    }
  } catch (e) {
    // request.js 已提示
  } finally {
    detailLoading.value = false
  }
}

const onDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除记录 #${row.id} ？删除后可在列表中隐藏。`, '提示', { type: 'warning' })
  } catch {
    return // 用户取消
  }
  try {
    await deleteHistory(row.id)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    // request.js 已提示
  }
}

const goInterview = (row) => router.push(`/interview?record_id=${row.id}`)

const scoreType = (s) => s >= 80 ? 'success' : s >= 60 ? 'warning' : 'danger'
const recommendType = (r) => r === '推荐' ? 'success' : r === '备选' ? 'warning' : 'info'
const groupTitle = getInterviewGroupTitle

onMounted(loadList)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }
.history-page { max-width: 1480px; margin: 0 auto; padding: 18px 0 32px; }
.history-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  padding: 24px 26px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, rgba(223, 185, 122, 0.16), transparent 28%),
    linear-gradient(135deg, rgba(255, 251, 245, 0.96), rgba(245, 251, 246, 0.98));
  border: 1px solid rgba(210, 223, 214, 0.92);
}
.hero-kicker {
  display: inline-block;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--app-muted);
}
.history-hero h1 {
  margin: 8px 0 8px;
  font-size: 32px;
  color: var(--app-text);
}
.history-hero p {
  margin: 0;
  max-width: 760px;
  color: var(--app-muted);
  line-height: 1.8;
}
.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.history-card { border-radius: 26px; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.mt   { margin-top: 16px; }
.muted{ color: var(--app-muted); font-size: 12px; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }
.q-card { margin: 8px 0; border-radius: 18px; }
.q { font-size: 14px; }
.i { color: var(--app-muted); font-size: 12px; margin: 4px 0; }
.a { color: var(--app-primary-dark); font-size: 13px; }
.risk { color: #c96b6b; }
h4 { margin: 12px 0 6px; color: var(--app-text); }
ul { padding-left: 18px; margin: 4px 0; }

@media (max-width: 768px) {
  .history-hero {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
