<template>
  <div class="preview-page">
    <header class="toolbar no-print">
      <div>
        <span class="toolbar-kicker">Enterprise Screening</span>
        <h1>筛选报告打印预览</h1>
      </div>
      <div class="toolbar-actions">
        <button type="button" class="ghost-btn" @click="goBack">返回</button>
        <button type="button" class="primary-btn" @click="printPage">打印 / 导出 PDF</button>
      </div>
    </header>

    <main v-if="previewContext" class="report-shell">
      <section class="report-hero">
        <div>
          <span class="report-kicker">Screening Report</span>
          <h2>{{ previewContext.reportTitle }}</h2>
          <p>{{ previewContext.jdTitle }} · {{ previewContext.company }} · 生成于 {{ previewContext.generatedAt }}</p>
        </div>

        <div class="hero-metrics">
          <div class="metric-card">
            <span>纳入候选人</span>
            <strong>{{ previewContext.totalCandidates }}</strong>
          </div>
          <div class="metric-card">
            <span>实际返回</span>
            <strong>{{ previewContext.candidateCount }}</strong>
          </div>
          <div class="metric-card">
            <span>平均分</span>
            <strong>{{ previewContext.averageScore }}</strong>
          </div>
          <div class="metric-card">
            <span>推荐分布</span>
            <strong class="metric-compact">{{ previewContext.recommendationText }}</strong>
          </div>
        </div>

        <div v-if="previewContext.topCandidate" class="top-card">
          <div>
            <span class="top-label">Top 候选人</span>
            <h3>#{{ previewContext.topCandidate.rank }} {{ previewContext.topCandidate.candidateName }}</h3>
            <p>{{ previewContext.topCandidate.recommendation }} · {{ previewContext.topCandidate.yearsExp }} 年经验</p>
            <p>命中技能：{{ previewContext.topCandidate.matchedSkillsText }}</p>
            <p>缺失技能：{{ previewContext.topCandidate.missingSkillsText }}</p>
          </div>
          <div class="top-score">
            <strong>{{ previewContext.topCandidate.overallScore }}</strong>
            <span>{{ previewContext.topCandidate.scoreLevel }}</span>
          </div>
        </div>
      </section>

      <section class="report-section">
        <div class="section-head">
          <h3>共性技能缺口</h3>
          <span>{{ previewContext.skillGaps.length ? '按出现频次统计' : '无明显共性缺口' }}</span>
        </div>

        <div v-if="previewContext.skillGaps.length" class="gap-table">
          <div class="gap-row gap-head">
            <span>技能项</span>
            <span>出现次数</span>
            <span>占比</span>
          </div>
          <div v-for="gap in previewContext.skillGaps" :key="gap.skill" class="gap-row">
            <span>{{ gap.skill }}</span>
            <span>{{ gap.count }} 次</span>
            <span>{{ gap.ratio }}</span>
          </div>
        </div>
        <div v-else class="empty-tip">本次筛选未发现显著共性技能缺口。</div>
      </section>

      <section class="report-section">
        <div class="section-head">
          <h3>候选人明细</h3>
          <span>{{ previewContext.candidates.length }} 人</span>
        </div>

        <div class="candidate-list">
          <article
            v-for="candidate in previewContext.candidates"
            :key="candidate.resumeId"
            class="candidate-card"
          >
            <div class="candidate-head">
              <div>
                <div class="candidate-rank">#{{ candidate.rank }}</div>
                <h4>{{ candidate.candidateName }}</h4>
                <p>{{ candidate.fileName || '未记录文件' }} · {{ candidate.yearsExp }} 年经验 · {{ candidate.recommendation }}</p>
              </div>
              <div class="score-box">
                <strong>{{ candidate.overallScore }}</strong>
                <span>{{ candidate.scoreLevel }}</span>
              </div>
            </div>

            <div class="chip-row">
              <span>技能画像：{{ candidate.skillsText }}</span>
              <span>命中技能：{{ candidate.matchedSkillsText }}</span>
              <span>缺失技能：{{ candidate.missingSkillsText }}</span>
            </div>

            <p class="reason">{{ candidate.overallReason || '暂无综合判断说明' }}</p>

            <div class="dimension-table">
              <div class="dimension-row dimension-head">
                <span>评估维度</span>
                <span>得分</span>
                <span>说明</span>
              </div>
              <div
                v-for="row in candidate.dimensionRows"
                :key="`${candidate.resumeId}-${row.key}`"
                class="dimension-row"
              >
                <span>{{ row.label }}</span>
                <span>{{ row.score }}</span>
                <span>{{ row.reason || '-' }}</span>
              </div>
            </div>

            <div class="foot-grid">
              <div>
                <span class="label">风险点</span>
                <ul>
                  <li v-for="risk in candidate.riskPoints" :key="risk">{{ risk }}</li>
                  <li v-if="candidate.riskPoints.length === 0" class="muted">暂无明显风险点</li>
                </ul>
              </div>
              <div>
                <span class="label">建议</span>
                <ul>
                  <li v-for="suggestion in candidate.suggestions" :key="suggestion">{{ suggestion }}</li>
                  <li v-if="candidate.suggestions.length === 0" class="muted">暂无补充建议</li>
                </ul>
              </div>
            </div>
          </article>
        </div>
      </section>
    </main>

    <section v-else class="empty-shell">
      <h2>没有可预览的筛选报告</h2>
      <p>请先在企业筛选页生成结果，或从已保存记录进入打印预览。</p>
      <button type="button" class="primary-btn" @click="goBack">返回企业筛选</button>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getScreeningSessionDetail } from '@/api/jobs'
import {
  buildScreeningPreviewContext,
  clearScreeningPreviewDraft,
  readScreeningPreviewDraft,
} from '@/composables/useScreeningReportPreview'
import { ElMessage } from '@/plugins/element-services'

const route = useRoute()
const router = useRouter()

const sessionDetail = ref(null)
const draftPayload = ref(null)

const previewContext = computed(() => {
  if (sessionDetail.value?.result_payload) {
    return buildScreeningPreviewContext({
      result: sessionDetail.value.result_payload,
      sessionName: sessionDetail.value.name || '',
      jdTitle: sessionDetail.value.jd_title || '',
      company: sessionDetail.value.company || '',
    })
  }

  if (draftPayload.value?.result) {
    return buildScreeningPreviewContext({
      result: draftPayload.value.result,
      sessionName: draftPayload.value.sessionName || '',
      jdTitle: draftPayload.value.jdTitle || '',
      company: draftPayload.value.company || '',
    })
  }

  return null
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
    return
  }
  router.push({ name: 'enterprise-screening' })
}

function printPage() {
  window.print()
}

async function loadPreview() {
  const sessionId = route.query.sessionId ? Number(route.query.sessionId) : null
  const useDraft = route.query.draft === '1'

  sessionDetail.value = null
  draftPayload.value = null

  if (sessionId) {
    try {
      sessionDetail.value = await getScreeningSessionDetail(sessionId)
      return
    } catch {
      ElMessage.error('加载筛选记录失败')
      return
    }
  }

  if (useDraft) {
    draftPayload.value = readScreeningPreviewDraft()
    if (!draftPayload.value) {
      ElMessage.warning('未找到可预览的临时筛选结果')
    }
    return
  }

  clearScreeningPreviewDraft()
}

watch(
  () => [route.query.sessionId, route.query.draft],
  async () => {
    await loadPreview()
  },
  { immediate: true },
)
</script>

<style scoped>
.preview-page {
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(166, 216, 255, 0.18), transparent 28%),
    linear-gradient(180deg, #f7fbff 0%, #eef5fb 100%);
  color: #20324a;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin: 0 auto 20px;
  max-width: 1120px;
  padding: 20px 24px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(210, 223, 238, 0.95);
  box-shadow: 0 14px 28px rgba(161, 178, 201, 0.14);
}

.toolbar-kicker,
.report-kicker,
.top-label {
  display: inline-block;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #7387a3;
}

.toolbar h1,
.report-hero h2,
.top-card h3,
.candidate-card h4,
.section-head h3 {
  margin: 8px 0 0;
}

.toolbar-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.primary-btn,
.ghost-btn {
  border: none;
  border-radius: 999px;
  padding: 12px 18px;
  font-size: 14px;
  cursor: pointer;
}

.primary-btn {
  background: #1f5eff;
  color: #fff;
}

.ghost-btn {
  background: rgba(237, 243, 250, 0.96);
  color: #29415f;
}

.report-shell,
.empty-shell {
  max-width: 1120px;
  margin: 0 auto;
}

.report-shell {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.report-hero,
.report-section,
.empty-shell {
  padding: 24px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(210, 223, 238, 0.95);
  box-shadow: 0 12px 24px rgba(161, 178, 201, 0.12);
}

.report-hero p,
.top-card p,
.candidate-card p,
.empty-shell p {
  color: #61758f;
  line-height: 1.7;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.metric-card,
.top-card,
.candidate-card,
.gap-table,
.dimension-table {
  border-radius: 20px;
  overflow: hidden;
}

.metric-card {
  padding: 14px 16px;
  background: #f7faff;
  border: 1px solid rgba(219, 228, 241, 0.96);
}

.metric-card span,
.metric-card strong,
.score-box strong,
.score-box span,
.top-score strong,
.top-score span {
  display: block;
}

.metric-card span {
  font-size: 12px;
  color: #72839c;
}

.metric-card strong {
  margin-top: 8px;
  font-size: 22px;
  color: #1e3761;
}

.metric-compact {
  font-size: 14px !important;
  line-height: 1.5;
}

.top-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  padding: 18px;
  background: linear-gradient(135deg, #f4f8ff, #eef7ff);
  border: 1px solid rgba(214, 226, 243, 0.98);
}

.top-score,
.score-box {
  min-width: 100px;
  text-align: center;
  border-radius: 18px;
}

.top-score {
  padding: 14px 16px;
  background: #1e3761;
  color: #fff;
}

.top-score strong {
  font-size: 32px;
}

.top-score span {
  margin-top: 6px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.82);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}

.section-head span {
  color: #7387a3;
  font-size: 13px;
}

.gap-row,
.dimension-row {
  display: grid;
}

.gap-row {
  grid-template-columns: 1.5fr 1fr 1fr;
}

.dimension-row {
  grid-template-columns: 1.1fr 90px 2fr;
}

.gap-row span,
.dimension-row span {
  padding: 11px 12px;
  border-bottom: 1px solid rgba(219, 228, 241, 0.96);
  background: rgba(255, 255, 255, 0.96);
}

.gap-head span,
.dimension-head span {
  background: #edf4ff;
  color: #1e3761;
  font-weight: 600;
}

.gap-table .gap-row:last-child span,
.dimension-table .dimension-row:last-child span {
  border-bottom: none;
}

.empty-tip {
  padding: 16px 18px;
  border-radius: 18px;
  background: #f7faff;
  color: #61758f;
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.candidate-card {
  padding: 18px;
  background: linear-gradient(135deg, rgba(250, 253, 255, 0.98), rgba(244, 248, 252, 0.98));
  border: 1px solid rgba(216, 226, 238, 0.96);
}

.candidate-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.candidate-rank {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: #159387;
}

.score-box {
  padding: 12px 14px;
  background: #eef4ff;
  color: #1e3761;
}

.score-box strong {
  font-size: 28px;
}

.score-box span {
  margin-top: 4px;
  font-size: 12px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.chip-row span {
  display: inline-flex;
  padding: 8px 12px;
  border-radius: 999px;
  background: #f3f7fd;
  color: #476077;
  border: 1px solid rgba(220, 230, 245, 0.96);
}

.reason {
  margin: 14px 0;
}

.foot-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.label {
  color: #52677f;
  font-size: 13px;
}

.foot-grid ul {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #556d7a;
}

.muted {
  color: #8ea0b5;
}

.empty-shell {
  text-align: center;
}

@media (max-width: 900px) {
  .toolbar,
  .top-card,
  .candidate-head {
    flex-direction: column;
  }

  .hero-metrics,
  .foot-grid {
    grid-template-columns: 1fr;
  }

  .gap-row,
  .dimension-row {
    grid-template-columns: 1fr;
  }
}

@media print {
  .preview-page {
    padding: 0;
    background: #fff;
  }

  .no-print {
    display: none !important;
  }

  .report-shell,
  .report-shell * {
    box-shadow: none !important;
  }

  .report-hero,
  .report-section,
  .candidate-card {
    break-inside: avoid;
    page-break-inside: avoid;
  }
}
</style>
