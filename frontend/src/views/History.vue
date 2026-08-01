<template>
  <div class="page-shell history-page">
    <div class="page-header">
      <div>
        <h2>分析历史记录</h2>
        <div class="page-header-sub">回看过去的分析结果、定位面试题和删除无效记录</div>
      </div>
      <el-button @click="loadList">刷新</el-button>
    </div>

    <section v-if="list.length" class="history-focus-strip" aria-label="历史分析摘要">
      <div class="history-focus-main">
        <span class="history-focus-label">分析沉淀</span>
        <strong>最近 {{ list.length }} 条记录可继续复用</strong>
        <p>从过往分析回看匹配依据和优化建议，避免为相同岗位重复准备。</p>
      </div>
      <div class="history-focus-metrics">
        <div>
          <b>{{ total }}</b
          ><span>累计记录</span>
        </div>
        <div>
          <b>{{ averageMatchScore }}</b
          ><span>平均匹配分</span>
        </div>
        <div>
          <b>{{ highMatchCount }}</b
          ><span>高匹配记录</span>
        </div>
      </div>
      <div class="history-focus-action">
        <span class="history-focus-label">下一步</span>
        <p>优先打开高匹配记录，继续准备面试或生成优化版本。</p>
        <el-button size="small" type="primary" @click="$router.push('/resume-center')"
          >管理简历版本</el-button
        >
      </div>
    </section>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon><Clock /></el-icon>
          <h3>历史记录</h3>
        </div>
        <el-tag type="info" effect="plain">{{ total }} 条</el-tag>
      </div>
      <div class="panel-body">
        <el-alert
          v-if="listError"
          class="load-error"
          type="error"
          :closable="false"
          show-icon
          title="历史记录加载失败"
          description="暂时无法获取历史分析记录，请检查网络后重试。"
        >
          <template #default>
            <el-button size="small" type="primary" plain @click="loadList">重新加载</el-button>
          </template>
        </el-alert>

        <el-table v-else :data="list" v-loading="loading" stripe>
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
              <el-button size="small" type="primary" @click="goInterview(row)">面试题</el-button>
              <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-if="!listError"
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          class="pagination"
          @current-change="loadList"
          @size-change="loadList"
        />
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="showDetail" title="分析详情" width="900px" top="5vh">
      <div v-if="detail" v-loading="detailLoading">
        <!-- 概要信息 -->
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="记录 ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="匹配度">
            <el-tag :type="scoreType(detail.match_score)" size="small">{{
              detail.match_score
            }}</el-tag>
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
                      <el-tag
                        v-if="x.severity"
                        size="small"
                        :type="
                          x.severity === '高' ? 'danger' : x.severity === '中' ? 'warning' : 'info'
                        "
                        style="margin-left: 4px"
                        >{{ x.severity }}</el-tag
                      >
                    </li>
                    <li v-for="(x, i) in localizedRiskPoints" :key="'r' + i" class="risk">
                      {{ x }}
                    </li>
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
                type="success"
                :closable="false"
                show-icon
              />
              <el-collapse class="mt">
                <el-collapse-item
                  v-for="(s, i) in detail.optimize_suggestions.sections || []"
                  :key="i"
                  :title="`【${s.section}】`"
                >
                  <ul>
                    <li v-for="(x, j) in s.suggestions" :key="j">{{ x }}</li>
                  </ul>
                </el-collapse-item>
              </el-collapse>
              <div class="mt">
                <span>➕ 补充关键词：</span>
                <el-tag
                  v-for="k in detail.optimize_suggestions.keywords_to_add || []"
                  :key="k"
                  type="success"
                  size="small"
                  style="margin: 2px"
                  >{{ k }}</el-tag
                >
              </div>
              <div class="mt">
                <span>➖ 删除关键词：</span>
                <el-tag
                  v-for="k in detail.optimize_suggestions.keywords_to_remove || []"
                  :key="k"
                  type="danger"
                  size="small"
                  style="margin: 2px"
                  >{{ k }}</el-tag
                >
              </div>
            </template>
            <el-empty v-else description="暂无优化建议" />
          </el-tab-pane>

          <el-tab-pane label="💬 面试题">
            <template v-if="hasInterviewQuestions">
              <div v-for="key in interviewKeys" :key="key">
                <template v-if="detail.interview_questions[key]?.length">
                  <h4>{{ groupTitle(key) }}（{{ detail.interview_questions[key].length }} 题）</h4>
                  <el-card
                    v-for="(q, i) in detail.interview_questions[key]"
                    :key="i"
                    shadow="never"
                    class="q-card"
                  >
                    <div class="q">
                      <b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}
                    </div>
                    <div class="i">🎯 {{ q.focus || q.intent }}</div>
                    <div class="a">
                      💡 {{ q.suggested_answer || q.expected_answer || q.ref_answer }}
                    </div>
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
const loading = ref(false)
const listError = ref(false)
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
const localizedRecommendation = computed(() =>
  localizeRecommendationText(detail.value?.match_report?.recommendation || '')
)
const localizedSummary = computed(() => localizeSentence(detail.value?.match_report?.summary || ''))
const localizedStrengths = computed(() =>
  normalizeLocalizedObjectList(detail.value?.match_report?.strengths)
)
const localizedGaps = computed(() => normalizeLocalizedObjectList(detail.value?.match_report?.gaps))
const localizedRiskPoints = computed(() =>
  normalizeLocalizedTextList(detail.value?.match_report?.risk_points)
)
const averageMatchScore = computed(() => {
  const scores = list.value.map((item) => Number(item.match_score)).filter(Number.isFinite)
  if (!scores.length) return '--'
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length)
})
const highMatchCount = computed(
  () => list.value.filter((item) => Number(item.match_score) >= 80).length
)

const loadList = async () => {
  loading.value = true
  listError.value = false
  try {
    const data = await listHistory({ page: page.value, page_size: pageSize.value })
    list.value = data.items
    total.value = data.total
  } catch {
    listError.value = true
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
  } catch {
    // request.js 已提示
  } finally {
    detailLoading.value = false
  }
}

const onDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除记录 #${row.id} ？删除后可在列表中隐藏。`, '提示', {
      type: 'warning',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteHistory(row.id)
    ElMessage.success('已删除')
    loadList()
  } catch {
    // request.js 已提示
  }
}

const goInterview = (row) => router.push(`/interview?record_id=${row.id}`)

const scoreType = (s) => (s >= 80 ? 'success' : s >= 60 ? 'warning' : 'danger')
const recommendType = (r) => (r === '推荐' ? 'success' : r === '备选' ? 'warning' : 'info')
const groupTitle = getInterviewGroupTitle

onMounted(loadList)
</script>

<style scoped>
.history-focus-strip {
  display: grid;
  grid-template-columns: minmax(250px, 1.25fr) minmax(230px, 0.85fr) minmax(220px, 0.85fr);
  gap: 0;
  margin-bottom: 18px;
  background: #fff;
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}
.history-focus-strip > div {
  min-width: 0;
  padding: 18px 20px;
  border-left: 1px solid var(--app-line);
}
.history-focus-strip > div:first-child {
  border-left: 0;
}
.history-focus-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.history-focus-main strong {
  display: block;
  margin-top: 7px;
  color: var(--app-text);
  font-size: 18px;
}
.history-focus-strip p {
  margin: 7px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}
.history-focus-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.history-focus-metrics div {
  display: grid;
  gap: 4px;
  padding: 2px 10px;
  text-align: center;
}
.history-focus-metrics div + div {
  border-left: 1px solid var(--app-line);
}
.history-focus-metrics b {
  color: var(--app-primary-dark);
  font-size: 23px;
  line-height: 1;
}
.history-focus-metrics span {
  color: var(--app-muted);
  font-size: 12px;
}
.history-focus-action .el-button {
  margin-top: 12px;
}
.muted {
  color: var(--app-muted);
  font-size: 12px;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
  display: flex;
}
.q-card {
  margin: 8px 0;
}
.q {
  font-size: 14px;
}
.i {
  color: var(--app-muted);
  font-size: 12px;
  margin: 4px 0;
}
.a {
  color: var(--app-primary-dark);
  font-size: 13px;
}
.risk {
  color: #c96b6b;
}
h4 {
  margin: 12px 0 6px;
  color: var(--app-text);
}
ul {
  padding-left: 18px;
  margin: 4px 0;
}

@media (max-width: 768px) {
  .history-focus-strip,
  .history-focus-metrics {
    grid-template-columns: 1fr;
  }
  .history-focus-strip > div,
  .history-focus-strip > div:first-child {
    border-top: 1px solid var(--app-line);
    border-left: 0;
  }
  .history-focus-strip > div:first-child {
    border-top: 0;
  }
  .history-focus-metrics {
    gap: 8px;
  }
  .history-focus-metrics div,
  .history-focus-metrics div + div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
    text-align: left;
  }
  .history-focus-action .el-button {
    width: 100%;
  }
}
</style>
