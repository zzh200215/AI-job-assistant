<template>
  <div class="eval-container">
    <el-card class="hero-card" shadow="never">
      <div class="hero-row">
        <div>
          <p class="eyebrow">Recommendation Evaluation</p>
          <h1>推荐评测看板</h1>
          <p class="hero-desc">
            基于用户 `like / dislike` 反馈评估推荐排序质量、分数校准和调优优先级。
          </p>
        </div>
        <div class="hero-actions">
          <el-switch
            v-model="anomalyOnly"
            inline-prompt
            active-text="仅异常"
            inactive-text="全部样本"
            @change="loadAll"
          />
          <el-button @click="router.push('/jobs/recommend/config')">调整权重</el-button>
          <el-button @click="router.push('/jobs/recommend')">返回岗位推荐</el-button>
          <el-button :loading="exporting === 'json'" @click="downloadSamples('json')">导出 JSON</el-button>
          <el-button :loading="exporting === 'csv'" type="primary" plain @click="downloadSamples('csv')">导出 CSV</el-button>
          <el-button type="primary" :loading="loading" @click="loadEvaluation">刷新</el-button>
        </div>
      </div>
    </el-card>

    <el-empty v-if="!loading && !evaluationData?.total" :image-size="120" description="暂无推荐反馈，先去岗位推荐页积累点赞/点踩样本">
      <el-button type="primary" @click="router.push('/jobs/recommend')">去岗位推荐</el-button>
    </el-empty>

    <template v-else-if="evaluationData">
      <div class="summary-grid">
        <el-card class="summary-card" shadow="never">
          <div class="summary-value">{{ evaluationData.evaluation?.alignment_score ?? 0 }}</div>
          <div class="summary-label">排序对齐分</div>
        </el-card>
        <el-card class="summary-card" shadow="never">
          <div class="summary-value">{{ evaluationData.total || 0 }}</div>
          <div class="summary-label">反馈总数</div>
        </el-card>
        <el-card class="summary-card" shadow="never">
          <div class="summary-value">{{ percentText(evaluationData.like_rate || 0) }}</div>
          <div class="summary-label">点赞率</div>
        </el-card>
        <el-card class="summary-card" shadow="never">
          <div class="summary-value">{{ evaluationData.avg_match_score ?? '-' }}</div>
          <div class="summary-label">平均匹配分</div>
        </el-card>
        <el-card class="summary-card" shadow="never">
          <div class="summary-value">{{ evaluationData.evaluation?.coverage?.active_days ?? 0 }}</div>
          <div class="summary-label">活跃天数</div>
        </el-card>
      </div>

      <div class="grid-two">
        <el-card class="panel-card" shadow="never">
          <template #header>
            <div class="card-head">
              <span>样本覆盖</span>
              <el-tag :type="evaluationData.evaluation?.sample_health?.enough_for_tuning ? 'success' : 'warning'" effect="plain">
                {{ evaluationData.evaluation?.sample_health?.enough_for_tuning ? '可用于调优' : '样本仍偏少' }}
              </el-tag>
            </div>
          </template>
          <div class="coverage-grid">
            <div class="coverage-item">
              <span>简历数</span>
              <strong>{{ evaluationData.evaluation?.coverage?.unique_resume_count ?? 0 }}</strong>
            </div>
            <div class="coverage-item">
              <span>岗位数</span>
              <strong>{{ evaluationData.evaluation?.coverage?.unique_job_count ?? 0 }}</strong>
            </div>
            <div class="coverage-item">
              <span>行业数</span>
              <strong>{{ evaluationData.evaluation?.coverage?.unique_industry_count ?? 0 }}</strong>
            </div>
            <div class="coverage-item">
              <span>近 7 天反馈</span>
              <strong>{{ recentTrendTotal }}</strong>
            </div>
          </div>
        </el-card>

        <el-card class="panel-card" shadow="never">
          <template #header><span>调优优先级</span></template>
          <div v-if="evaluationData.tuning_signals?.action_items?.length" class="action-list">
            <div
              v-for="item in evaluationData.tuning_signals.action_items"
              :key="`${item.type}-${item.title}`"
              class="action-item"
              :class="`severity-${item.severity || 'low'}`"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.detail }}</span>
            </div>
          </div>
          <el-empty v-else :image-size="70" description="暂无调优建议" />
        </el-card>
      </div>

      <div class="grid-two">
        <el-card class="panel-card" shadow="never">
          <template #header><span>分数校准分桶</span></template>
          <div v-if="calibrationBuckets.length" class="bucket-list">
            <div v-for="item in calibrationBuckets" :key="item.bucket" class="bucket-item">
              <div class="bucket-head">
                <strong>{{ item.bucket }}</strong>
                <span>{{ item.total }} 条</span>
              </div>
              <div class="bucket-bar">
                <span class="bucket-like" :style="segmentStyle(item.like, item.total)" />
                <span class="bucket-dislike" :style="segmentStyle(item.dislike, item.total)" />
              </div>
              <div class="bucket-meta">
                点赞率 {{ percentText(item.like_rate || 0) }}
                <span v-if="item.avg_match_score !== null">· 均分 {{ item.avg_match_score }}</span>
              </div>
            </div>
          </div>
          <el-empty v-else :image-size="70" description="暂无校准数据" />
        </el-card>

        <el-card class="panel-card" shadow="never">
          <template #header><span>异常信号</span></template>
          <div class="anomaly-grid">
            <div class="anomaly-card">
              <div class="anomaly-value">{{ evaluationData.evaluation?.calibration?.high_score_dislike_count ?? 0 }}</div>
              <div class="anomaly-label">高分点踩</div>
            </div>
            <div class="anomaly-card">
              <div class="anomaly-value">{{ evaluationData.evaluation?.calibration?.low_score_like_count ?? 0 }}</div>
              <div class="anomaly-label">低分点赞</div>
            </div>
          </div>
          <div class="signal-columns">
            <div>
              <div class="signal-title">高分点踩样本</div>
              <div v-if="evaluationData.tuning_signals?.high_score_dislikes?.length" class="signal-list">
                <div
                  v-for="item in evaluationData.tuning_signals.high_score_dislikes"
                  :key="`high-${item.resume_id}-${item.jd_id}-${item.created_at}`"
                  class="signal-item"
                >
                  <strong>{{ item.jd_title || '未命名岗位' }}</strong>
                  <span>{{ item.resume_title }} · {{ item.match_score }} 分</span>
                </div>
              </div>
              <el-empty v-else :image-size="60" description="暂无" />
            </div>
            <div>
              <div class="signal-title">低分点赞样本</div>
              <div v-if="evaluationData.tuning_signals?.low_score_likes?.length" class="signal-list">
                <div
                  v-for="item in evaluationData.tuning_signals.low_score_likes"
                  :key="`low-${item.resume_id}-${item.jd_id}-${item.created_at}`"
                  class="signal-item"
                >
                  <strong>{{ item.jd_title || '未命名岗位' }}</strong>
                  <span>{{ item.resume_title }} · {{ item.match_score }} 分</span>
                </div>
              </div>
              <el-empty v-else :image-size="60" description="暂无" />
            </div>
          </div>
        </el-card>
      </div>

      <div class="grid-two">
        <el-card class="panel-card" shadow="never">
          <template #header><span>问题岗位 / 简历</span></template>
          <div class="focus-section">
            <div>
              <div class="section-title">岗位侧</div>
              <div v-if="evaluationData.evaluation?.mismatch_focus?.jobs?.length" class="focus-list">
                <div v-for="item in evaluationData.evaluation.mismatch_focus.jobs" :key="`job-${item.jd_id}`" class="focus-item">
                  <strong>{{ item.jd_title || '未命名岗位' }}</strong>
                  <span>{{ item.total }} 条反馈 · 点踩率 {{ percentText(item.dislike_rate || 0) }}</span>
                </div>
              </div>
              <el-empty v-else :image-size="60" description="暂无明显问题岗位" />
            </div>
            <div>
              <div class="section-title">简历侧</div>
              <div v-if="evaluationData.evaluation?.mismatch_focus?.resumes?.length" class="focus-list">
                <div v-for="item in evaluationData.evaluation.mismatch_focus.resumes" :key="`resume-${item.resume_id}`" class="focus-item">
                  <strong>{{ item.resume_title }}</strong>
                  <span>{{ item.total }} 条反馈 · 点踩率 {{ percentText(item.dislike_rate || 0) }}</span>
                </div>
              </div>
              <el-empty v-else :image-size="60" description="暂无明显问题简历" />
            </div>
          </div>
        </el-card>

        <el-card class="panel-card" shadow="never">
          <template #header><span>行业与近期样本</span></template>
          <div class="focus-section">
            <div>
              <div class="section-title">行业偏差</div>
              <div v-if="evaluationData.evaluation?.mismatch_focus?.industries?.length" class="focus-list">
                <div v-for="item in evaluationData.evaluation.mismatch_focus.industries" :key="item.industry" class="focus-item">
                  <strong>{{ item.industry }}</strong>
                  <span>{{ item.total }} 条反馈 · 点踩率 {{ percentText(item.dislike_rate || 0) }}</span>
                </div>
              </div>
              <el-empty v-else :image-size="60" description="暂无明显行业偏差" />
            </div>
            <div>
              <div class="section-title">最近反馈</div>
              <div v-if="evaluationData.recent_feedback?.length" class="focus-list">
                <div v-for="item in evaluationData.recent_feedback.slice(0, 6)" :key="`recent-${item.id}`" class="focus-item">
                  <strong>{{ item.jd_title || '未命名岗位' }}</strong>
                  <span>{{ item.feedback_type }} · {{ item.resume_title }}</span>
                </div>
              </div>
              <el-empty v-else :image-size="60" description="暂无最近反馈" />
            </div>
          </div>
        </el-card>
      </div>

      <el-card class="panel-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span>调优样本预览</span>
            <span class="muted">{{ tuningSamples.length }} 条</span>
          </div>
        </template>
        <el-table :data="tuningSamples" stripe>
          <el-table-column prop="feedback_type" label="反馈" min-width="90">
            <template #default="{ row }">
              <el-tag :type="row.feedback_type === 'like' ? 'success' : 'danger'" effect="plain">
                {{ row.feedback_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="jd_title" label="岗位" min-width="180" show-overflow-tooltip />
          <el-table-column prop="resume_title" label="简历" min-width="140" show-overflow-tooltip />
          <el-table-column prop="match_score" label="分数" min-width="80" />
          <el-table-column label="规则拆解" min-width="180">
            <template #default="{ row }">
              向量 {{ row.vector_score }} / 规则 {{ row.rule_score }}
            </template>
          </el-table-column>
          <el-table-column label="调优标签" min-width="220">
            <template #default="{ row }">
              <div class="tag-row">
                <el-tag
                  v-for="tag in row.tuning_tags"
                  :key="`${row.feedback_id}-${tag}`"
                  size="small"
                  effect="plain"
                >
                  {{ tag }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { exportJobTuningSamples, getJobFeedbackEvaluation, getJobTuningSamples } from '@/api/jobs'

const router = useRouter()
const loading = ref(false)
const exporting = ref('')
const anomalyOnly = ref(true)
const evaluationData = ref(null)
const tuningSamplePayload = ref({ items: [] })

const calibrationBuckets = computed(() => evaluationData.value?.evaluation?.calibration?.buckets || [])
const recentTrendTotal = computed(() =>
  (evaluationData.value?.trend || []).reduce((sum, item) => sum + Number(item.total || 0), 0),
)
const tuningSamples = computed(() => tuningSamplePayload.value?.items || [])

onMounted(() => {
  loadAll()
})

async function loadAll() {
  await Promise.all([loadEvaluation(), loadTuningSamples()])
}

async function loadEvaluation() {
  loading.value = true
  try {
    evaluationData.value = await getJobFeedbackEvaluation()
  } finally {
    loading.value = false
  }
}

async function loadTuningSamples() {
  tuningSamplePayload.value = await getJobTuningSamples({ anomaly_only: anomalyOnly.value })
}

async function downloadSamples(format) {
  exporting.value = format
  try {
    const blob = await exportJobTuningSamples({
      format,
      anomaly_only: anomalyOnly.value,
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `recommend_tuning_samples.${format}`
    link.click()
    window.URL.revokeObjectURL(url)
  } finally {
    exporting.value = ''
  }
}

function percentText(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function segmentStyle(value, total) {
  const safeTotal = Number(total) || 0
  const width = safeTotal > 0 ? Math.max((Number(value) || 0) / safeTotal * 100, 0) : 0
  return { width: `${width}%` }
}
</script>

<style scoped>
.eval-container {
  max-width: 1120px;
  margin: 0 auto;
  padding: 12px 0 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card,
.summary-card,
.panel-card {
  border-radius: 24px;
}

.hero-row,
.hero-actions,
.summary-grid,
.grid-two,
.coverage-grid,
.card-head,
.bucket-head,
.anomaly-grid,
.signal-columns,
.focus-section {
  display: flex;
  gap: 12px;
}

.hero-row,
.card-head,
.bucket-head {
  justify-content: space-between;
}

.hero-row,
.hero-actions,
.card-head {
  align-items: center;
  flex-wrap: wrap;
}

.muted {
  color: var(--app-muted);
  font-size: 12px;
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-desc {
  color: var(--app-muted);
  line-height: 1.8;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.summary-card {
  padding: 4px;
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--app-text);
}

.summary-label {
  margin-top: 6px;
  color: var(--app-muted);
  font-size: 12px;
}

.grid-two {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.coverage-item,
.anomaly-card {
  padding: 14px;
  border-radius: 16px;
  background: #f7fbf8;
  border: 1px solid rgba(217, 231, 222, 0.94);
}

.coverage-item span,
.anomaly-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.coverage-item strong,
.anomaly-value {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  color: var(--app-text);
}

.action-list,
.bucket-list,
.signal-list,
.focus-list,
.tag-row {
  display: flex;
  gap: 10px;
}

.action-list,
.bucket-list,
.signal-list,
.focus-list {
  flex-direction: column;
}

.tag-row {
  flex-wrap: wrap;
}

.action-item,
.bucket-item,
.signal-item,
.focus-item {
  padding: 12px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(223, 233, 227, 0.95);
}

.action-item strong,
.action-item span,
.signal-item strong,
.signal-item span,
.focus-item strong,
.focus-item span {
  display: block;
}

.action-item span,
.signal-item span,
.focus-item span,
.bucket-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-muted);
}

.severity-high {
  border-color: rgba(223, 106, 106, 0.24);
  background: #fff7f5;
}

.severity-medium {
  border-color: rgba(220, 156, 63, 0.22);
  background: #fffaf1;
}

.severity-low {
  border-color: rgba(94, 195, 136, 0.22);
  background: #f5fbf7;
}

.bucket-bar {
  display: flex;
  width: 100%;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf2ee;
  margin-top: 8px;
}

.bucket-like {
  display: block;
  background: linear-gradient(90deg, #2ea866, #5ec388);
}

.bucket-dislike {
  display: block;
  background: linear-gradient(90deg, #df8d72, #d96a6a);
}

.signal-columns,
.focus-section {
  margin-top: 14px;
  align-items: flex-start;
}

.signal-columns > div,
.focus-section > div {
  flex: 1;
  min-width: 0;
}

.section-title,
.signal-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text);
}

@media (max-width: 960px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .grid-two,
  .signal-columns,
  .focus-section {
    grid-template-columns: 1fr;
    flex-direction: column;
  }
}
</style>
