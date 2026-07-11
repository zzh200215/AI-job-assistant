<template>
  <div class="page-shell">
    <section class="hero-card">
      <div>
        <span class="hero-kicker">HR Workspace</span>
        <h2>企业端筛选工作台</h2>
        <div class="page-header-sub">围绕单个岗位 JD 做批量比较、保存记录和导出结果，顶部只保留最关键的筛选动作。</div>
        <div class="hero-note">
          直接筛选、直接导出、直接复盘。岗位画像、候选人风险点和共性缺口会自动汇总到结果里。
        </div>
      </div>
      <div class="hero-metrics">
        <div class="metric-card">
          <span>已选候选人</span>
          <strong>{{ selectedResumeIds.length }}</strong>
        </div>
        <div class="metric-card">
          <span>历史记录</span>
          <strong>{{ sessions.length }}</strong>
        </div>
        <div class="metric-card">
          <span>当前结果</span>
          <strong>{{ result?.summary?.returned_candidates || 0 }}</strong>
        </div>
      </div>
    </section>

    <section class="workflow-strip">
      <div class="workflow-item">
        <span>1</span>
        <strong>选 JD</strong>
      </div>
      <div class="workflow-item">
        <span>2</span>
        <strong>选候选人</strong>
      </div>
      <div class="workflow-item">
        <span>3</span>
        <strong>生成结果</strong>
      </div>
      <div class="workflow-item">
        <span>4</span>
        <strong>导出复用</strong>
      </div>
    </section>

    <div class="panel rule-card">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>筛选规则说明</h3>
        </div>
      </div>
      <div class="panel-body">
        <div class="rule-grid">
          <div>
            <strong>岗位画像</strong>
            <p>系统会读取 JD 的技能、经验、学历、行业和薪资信息，形成统一评估基线。</p>
          </div>
          <div>
            <strong>评分逻辑</strong>
            <p>按技能命中、经验贴合、学历符合、行业契合与综合风险做排序，不依赖单一关键词。</p>
          </div>
          <div>
            <strong>复盘方式</strong>
            <p>导出报告会附上 Top 候选人、共性缺口和建议动作，便于 HR 二次筛选。</p>
          </div>
        </div>
      </div>
    </div>

    <section class="workspace-grid">
      <div class="left-column">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-row">
              <h3>筛选配置</h3>
              <el-button text @click="reloadAll">刷新</el-button>
            </div>
          </div>
          <div class="panel-body">
            <el-form label-position="top" class="config-form">
              <el-form-item label="记录名称">
                <el-input v-model="sessionName" maxlength="200" placeholder="例如：后端候选人初筛（6月）" />
              </el-form-item>

              <el-form-item label="岗位 JD">
                <el-select
                  v-model="jdId"
                  placement="bottom-start"
                  :fallback-placements="['bottom-start']"
                  filterable
                  clearable
                  placeholder="选择一个岗位 JD"
                >
                  <el-option
                    v-for="item in jdOptions"
                    :key="item.id"
                    :label="`${item.title}${item.company ? ` · ${item.company}` : ''}`"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="候选人">
                <el-select
                  v-model="selectedResumeIds"
                  placement="bottom-start"
                  :fallback-placements="['bottom-start']"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  filterable
                  placeholder="选择待筛选的候选人"
                >
                  <el-option
                    v-for="item in resumeOptions"
                    :key="item.id"
                    :label="resumeLabel(item)"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="返回人数">
                <el-input-number v-model="topK" :min="1" :max="100" />
              </el-form-item>

              <div class="config-actions">
                <el-button type="primary" :loading="loading" @click="runScreening">开始筛选</el-button>
                <el-button :loading="saving" :disabled="!result" @click="saveCurrentSession">保存记录</el-button>
                <el-button @click="quickSelectTop6" :disabled="resumeOptions.length === 0">选前 6 份</el-button>
                <el-button text @click="clearSelection">清空</el-button>
                <el-divider />
                <el-button :loading="seeding" type="warning" plain @click="seedDemoData">
                  <el-icon><Promotion /></el-icon>
                  补充演示数据
                </el-button>
              </div>
            </el-form>

            <el-divider />

            <div class="selection-preview">
              <div class="preview-title">已选候选人</div>
              <el-tag
                v-for="resume in selectedResumes"
                :key="resume.id"
                size="small"
                effect="plain"
                class="preview-tag"
              >
                {{ resumeLabel(resume) }}
              </el-tag>
              <el-empty v-if="selectedResumes.length === 0" description="还没有选择候选人" :image-size="60" />
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-row">
              <h3>记录</h3>
              <span class="panel-sub">{{ sessions.length }} 条</span>
            </div>
          </div>
          <div class="panel-body">
            <el-empty v-if="sessions.length === 0" description="保存后显示" :image-size="72" />

            <div v-else class="session-list">
              <button
                v-for="session in sessions"
                :key="session.id"
                type="button"
                class="session-item"
                :class="{ active: activeSessionId === session.id }"
                @click="loadSession(session.id)"
              >
                <div class="session-item-head">
                  <strong>{{ session.name || session.jd_title }}</strong>
                  <span>#{{ session.id }}</span>
                </div>
                <p>{{ session.jd_title }}{{ session.company ? ` · ${session.company}` : '' }}</p>
                <small>{{ session.candidate_count }} 人 · Top: {{ session.top_candidate_name || '暂无' }}</small>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="result-column">
        <div class="panel" v-if="result">
          <div class="panel-header">
            <div class="panel-title-row">
              <h3>摘要</h3>
              <div class="head-actions">
                <el-tag type="success" effect="plain">{{ result.summary.total_candidates }} 人参与</el-tag>
                <el-button size="small" @click="openPreview">预览</el-button>
                <template v-if="activeSessionId">
                  <el-button size="small" plain :loading="exporting === 'csv'" @click="exportActiveSession('csv')">
                    CSV
                  </el-button>
                  <el-button size="small" plain :loading="exporting === 'docx'" @click="exportActiveSession('docx')">
                    Word
                  </el-button>
                  <el-button size="small" plain :loading="exporting === 'pdf'" @click="exportActiveSession('pdf')">
                    PDF
                  </el-button>
                </template>
              </div>
            </div>
          </div>
          <div class="panel-body">
            <div class="summary-grid">
              <div class="summary-block">
                <span>JD</span>
                <strong>{{ result.summary.jd_title }}</strong>
                <small>{{ result.summary.company || '未填写公司' }}</small>
              </div>
              <div class="summary-block">
                <span>Top</span>
                <strong>{{ topCandidateName }}</strong>
                <small>{{ topCandidateScore }}</small>
              </div>
              <div class="summary-block">
                <span>共性缺口</span>
                <strong>{{ topSkillGap }}</strong>
                <small>按缺失频次排序</small>
              </div>
            </div>

            <div class="distribution-row" v-if="recommendationPairs.length">
              <div v-for="item in recommendationPairs" :key="item.label" class="distribution-chip">
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-row">
              <h3>排名</h3>
              <span class="panel-sub">{{ loading ? '正在计算中…' : `${rankedCandidates.length} 条结果` }}</span>
            </div>
          </div>
          <div class="panel-body">
            <el-empty v-if="!loading && rankedCandidates.length === 0" description="选择 JD 和候选人后开始筛选" :image-size="88" />

            <div v-else class="candidate-list">
              <article
                v-for="(item, index) in rankedCandidates"
                :key="item.resume_id"
                class="candidate-card"
              >
                <div class="candidate-head">
                  <div>
                    <div class="candidate-rank">#{{ index + 1 }}</div>
                    <h3>{{ item.candidate_name }}</h3>
                    <p>{{ item.file_name }} · {{ item.years_exp || 0 }} 年经验</p>
                  </div>
                  <div class="score-pill">
                    <strong>{{ item.overall_score }}</strong>
                    <span>{{ item.recommendation }}</span>
                  </div>
                </div>

                <div class="candidate-body">
                  <div class="skill-row">
                    <span class="label">命中技能</span>
                    <el-tag
                      v-for="skill in item.matched_skills.slice(0, 6)"
                      :key="skill"
                      size="small"
                      type="success"
                      effect="plain"
                    >
                      {{ skill }}
                    </el-tag>
                    <span v-if="item.matched_skills.length === 0" class="muted">暂无明显命中</span>
                  </div>

                  <div class="skill-row">
                    <span class="label">缺失核心技能</span>
                    <el-tag
                      v-for="skill in item.missing_required_skills.slice(0, 6)"
                      :key="skill"
                      size="small"
                      type="danger"
                      effect="plain"
                    >
                      {{ skill }}
                    </el-tag>
                    <span v-if="item.missing_required_skills.length === 0" class="muted">无明显硬缺口</span>
                  </div>

                  <div class="dimension-grid">
                    <div v-for="(label, key) in dimensionLabels" :key="key" class="dimension-item">
                      <span>{{ label }}</span>
                      <strong>{{ dimensionScore(item, key) }}</strong>
                    </div>
                  </div>

                  <div class="explain-block">
                    <div>
                      <span class="label">综合判断</span>
                      <p>{{ item.overall_reason || '暂无说明' }}</p>
                    </div>
                    <div>
                      <span class="label">风险点</span>
                      <ul>
                        <li v-for="risk in item.risk_points" :key="risk">{{ risk }}</li>
                      </ul>
                    </div>
                    <div>
                      <span class="label">建议</span>
                      <ul>
                        <li v-for="suggestion in item.optimization_suggestions" :key="suggestion">{{ suggestion }}</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </div>
      </div>
    </section>

    <el-dialog
      v-model="previewVisible"
      title="导出前预览"
      width="1100px"
      top="4vh"
      class="report-preview-dialog"
      destroy-on-close
    >
      <div v-if="previewContext" class="report-preview">
        <section class="preview-hero">
          <div class="preview-hero-main">
            <span class="preview-kicker">Screening Report</span>
            <h2>{{ previewContext.reportTitle }}</h2>
            <p>{{ previewContext.jdTitle }} · {{ previewContext.company }} · 生成于 {{ previewContext.generatedAt }}</p>
          </div>

          <div class="preview-summary-grid">
            <div class="preview-summary-card">
              <span>纳入候选人</span>
              <strong>{{ previewContext.totalCandidates }}</strong>
            </div>
            <div class="preview-summary-card">
              <span>实际返回</span>
              <strong>{{ previewContext.candidateCount }}</strong>
            </div>
            <div class="preview-summary-card">
              <span>平均分</span>
              <strong>{{ previewContext.averageScore }}</strong>
            </div>
            <div class="preview-summary-card">
              <span>推荐分布</span>
              <strong class="compact">{{ previewContext.recommendationText }}</strong>
            </div>
          </div>

          <div v-if="previewContext.topCandidate" class="preview-top-card">
            <div>
              <span class="preview-top-label">Top 候选人</span>
              <h3>#{{ previewContext.topCandidate.rank }} {{ previewContext.topCandidate.candidateName }}</h3>
              <p>{{ previewContext.topCandidate.recommendation }} · {{ previewContext.topCandidate.yearsExp }} 年经验</p>
              <p>命中技能：{{ previewContext.topCandidate.matchedSkillsText }}</p>
              <p>缺失技能：{{ previewContext.topCandidate.missingSkillsText }}</p>
            </div>
            <div class="preview-top-score">
              <strong>{{ previewContext.topCandidate.overallScore }}</strong>
              <span>{{ previewContext.topCandidate.scoreLevel }}</span>
            </div>
          </div>
        </section>

        <section class="preview-section">
          <div class="preview-section-head">
            <h3>共性技能缺口</h3>
            <span>{{ previewContext.skillGaps.length ? '按出现频次统计' : '无明显共性缺口' }}</span>
          </div>

          <div v-if="previewContext.skillGaps.length" class="preview-gap-table">
            <div class="preview-gap-row preview-gap-head">
              <span>技能项</span>
              <span>出现次数</span>
              <span>占比</span>
            </div>
            <div v-for="gap in previewContext.skillGaps" :key="gap.skill" class="preview-gap-row">
              <span>{{ gap.skill }}</span>
              <span>{{ gap.count }} 次</span>
              <span>{{ gap.ratio }}</span>
            </div>
          </div>
          <el-empty v-else description="本次筛选未发现显著共性技能缺口" :image-size="60" />
        </section>

        <section class="preview-section">
          <div class="preview-section-head">
            <h3>候选人明细</h3>
            <span>{{ previewContext.candidates.length }} 人</span>
          </div>

          <div class="preview-candidate-list">
            <article
              v-for="candidate in previewContext.candidates"
              :key="candidate.resumeId"
              class="preview-candidate-card"
            >
              <div class="preview-candidate-head">
                <div>
                  <div class="preview-rank">#{{ candidate.rank }}</div>
                  <h4>{{ candidate.candidateName }}</h4>
                  <p>{{ candidate.fileName || '未记录文件' }} · {{ candidate.yearsExp }} 年经验 · {{ candidate.recommendation }}</p>
                </div>
                <div class="preview-score-box">
                  <strong>{{ candidate.overallScore }}</strong>
                  <span>{{ candidate.scoreLevel }}</span>
                </div>
              </div>

              <div class="preview-chip-row">
                <span>技能画像：{{ candidate.skillsText }}</span>
                <span>命中技能：{{ candidate.matchedSkillsText }}</span>
                <span>缺失技能：{{ candidate.missingSkillsText }}</span>
              </div>

              <p class="preview-reason">{{ candidate.overallReason || '暂无综合判断说明' }}</p>

              <div class="preview-dimension-table">
                <div class="preview-dimension-row preview-dimension-head">
                  <span>评估维度</span>
                  <span>得分</span>
                  <span>说明</span>
                </div>
                <div
                  v-for="row in candidate.dimensionRows"
                  :key="`${candidate.resumeId}-${row.key}`"
                  class="preview-dimension-row"
                >
                  <span>{{ row.label }}</span>
                  <span>{{ row.score }}</span>
                  <span>{{ row.reason || '-' }}</span>
                </div>
              </div>

              <div class="preview-foot-grid">
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
      </div>

      <template #footer>
        <div class="preview-footer">
          <span class="preview-footer-tip">
            {{ activeSessionId ? '当前记录已保存，可直接导出。' : '当前结果尚未保存，保存后可导出 CSV / Word / PDF。' }}
          </span>
          <div class="preview-footer-actions">
            <el-button @click="openPrintPreview">打开打印版预览</el-button>
            <el-button v-if="!activeSessionId" :loading="saving" @click="saveCurrentSession">保存记录</el-button>
            <el-button plain :disabled="!activeSessionId" :loading="exporting === 'csv'" @click="exportActiveSession('csv')">
              导出 CSV
            </el-button>
            <el-button plain :disabled="!activeSessionId" :loading="exporting === 'docx'" @click="exportActiveSession('docx')">
              导出 Word
            </el-button>
            <el-button type="primary" :disabled="!activeSessionId" :loading="exporting === 'pdf'" @click="exportActiveSession('pdf')">
              导出 PDF
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Promotion } from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import { getJDList } from '@/api/jd'
import { getAccessibleResumeList, seedDemoResumes } from '@/api/resume'
import {
  exportScreeningSession,
  getScreeningSessionDetail,
  getScreeningSessions,
  saveScreeningSession,
  screenCandidates,
  seedDemoJobs,
} from '@/api/jobs'
import {
  buildScreeningPreviewContext,
  clearScreeningPreviewDraft,
  persistScreeningPreviewDraft,
} from '@/composables/useScreeningReportPreview'

const jdOptions = ref([])
const resumeOptions = ref([])
const sessions = ref([])
const router = useRouter()

const jdId = ref(null)
const selectedResumeIds = ref([])
const topK = ref(10)
const sessionName = ref('')

const loading = ref(false)
const saving = ref(false)
const seeding = ref(false)
const exporting = ref('')
const previewVisible = ref(false)
const result = ref(null)
const activeSessionId = ref(null)

const dimensionLabels = {
  skills: '技能',
  project: '项目',
  experience: '经验',
  education: '学历',
  keyword: '关键词',
  bonus: '加分项',
}

const selectedResumes = computed(() => {
  const selected = new Set(selectedResumeIds.value)
  return resumeOptions.value.filter(item => selected.has(item.id))
})

const rankedCandidates = computed(() => result.value?.candidates || [])
const topCandidate = computed(() => rankedCandidates.value[0] || null)
const topCandidateName = computed(() => topCandidate.value?.candidate_name || '暂无')
const topCandidateScore = computed(() => topCandidate.value ? `${topCandidate.value.overall_score} 分` : '暂无')
const topSkillGap = computed(() => result.value?.summary?.most_common_skill_gaps?.[0]?.skill || '暂无')
const recommendationPairs = computed(() => {
  const dist = result.value?.summary?.recommendation_distribution || {}
  return Object.entries(dist).map(([label, count]) => ({ label, count }))
})
const currentJdOption = computed(() => jdOptions.value.find(item => item.id === jdId.value) || null)
const previewContext = computed(() => buildScreeningPreviewContext({
  result: result.value,
  sessionName: sessionName.value,
  jdTitle: currentJdOption.value?.title || '',
  company: currentJdOption.value?.company || '',
}))

function resumeLabel(item) {
  const name = item.parsed?.name || item.name || `简历 #${item.id}`
  const years = item.parsed?.years_exp ?? item.years_exp ?? 0
  return `${name} · ${years}年`
}

function dimensionScore(item, key) {
  return item?.dimension_scores?.[key]?.score ?? 0
}

async function loadResumes() {
  const data = await getAccessibleResumeList({ page: 1, page_size: 100 })
  resumeOptions.value = data.items || []
  if (resumeOptions.value.length === 0) {
    ElMessage.info('当前没有可筛选的候选人简历，请先生成或上传你自己的候选人简历')
  }
}

async function loadJds() {
  const data = await getJDList({ page: 1, page_size: 100 })
  jdOptions.value = data.items || []
}

async function loadSessions() {
  const data = await getScreeningSessions()
  sessions.value = data.items || []
}

async function reloadAll() {
  await Promise.all([loadResumes(), loadJds(), loadSessions()])
}

async function seedDemoData() {
  seeding.value = true
  try {
    // 先补充演示 JD
    const jdResult = await seedDemoJobs()
    ElMessage.success(`演示岗位: ${jdResult?.inserted || 0} 条`)
  } catch {
    ElMessage.warning('岗位种子可能已存在')
  }
  try {
    // 再补充演示简历
    const resumeResult = await seedDemoResumes()
    ElMessage.success(`演示简历: ${resumeResult?.inserted || 0} 条`)
  } catch {
    ElMessage.warning('简历种子可能已存在')
  }
  // 刷新下拉框
  await reloadAll()
  if (resumeOptions.value.length > 0 && jdOptions.value.length > 0) {
    ElMessage.success('演示数据已就绪，请选择 JD 和候选人开始筛选')
  }
  seeding.value = false
}

function clearSelection() {
  jdId.value = null
  selectedResumeIds.value = []
  topK.value = 10
  sessionName.value = ''
  result.value = null
  activeSessionId.value = null
  previewVisible.value = false
  clearScreeningPreviewDraft()
}

function quickSelectTop6() {
  selectedResumeIds.value = resumeOptions.value.slice(0, 6).map(item => item.id)
}

function openPreview() {
  if (!result.value) {
    ElMessage.warning('请先生成筛选结果')
    return
  }
  previewVisible.value = true
}

function openPrintPreview() {
  if (!result.value) {
    ElMessage.warning('请先生成筛选结果')
    return
  }

  persistScreeningPreviewDraft({
    sessionName: sessionName.value,
    jdTitle: currentJdOption.value?.title || '',
    company: currentJdOption.value?.company || '',
    result: result.value,
  })

  const routeData = router.resolve(
    activeSessionId.value
      ? { name: 'enterprise-screening-preview', query: { sessionId: String(activeSessionId.value) } }
      : { name: 'enterprise-screening-preview', query: { draft: '1' } },
  )
  window.open(routeData.href, '_blank', 'noopener')
}

async function runScreening() {
  if (!jdId.value) {
    ElMessage.warning('请先选择一个岗位 JD')
    return
  }
  if (selectedResumeIds.value.length === 0) {
    ElMessage.warning('请至少选择一份候选人简历')
    return
  }

  loading.value = true
  try {
    const data = await screenCandidates({
      jd_id: jdId.value,
      resume_ids: selectedResumeIds.value,
      top_k: topK.value,
    })
    result.value = data
    activeSessionId.value = null
    clearScreeningPreviewDraft()
  } finally {
    loading.value = false
  }
}

async function saveCurrentSession() {
  if (!result.value) {
    ElMessage.warning('请先生成筛选结果')
    return
  }

  saving.value = true
  try {
    const data = await saveScreeningSession({
      jd_id: jdId.value,
      resume_ids: selectedResumeIds.value,
      top_k: topK.value,
      name: sessionName.value,
    })
    activeSessionId.value = data.id
    sessionName.value = data.name || sessionName.value
    await loadSessions()
    ElMessage.success('筛选记录已保存')
  } finally {
    saving.value = false
  }
}

async function loadSession(sessionId) {
  const data = await getScreeningSessionDetail(sessionId)
  activeSessionId.value = data.id
  sessionName.value = data.name || ''
  jdId.value = data.jd_id || null
  selectedResumeIds.value = data.request_payload?.resume_ids || []
  topK.value = data.request_payload?.top_k || 10
  result.value = data.result_payload || null
  previewVisible.value = false
  clearScreeningPreviewDraft()
}

async function exportActiveSession(format) {
  if (!activeSessionId.value) {
    ElMessage.warning('请先保存筛选记录，再导出报告')
    return
  }

  exporting.value = format
  try {
    const blob = await exportScreeningSession(activeSessionId.value, format)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `screening_session_${activeSessionId.value}.${format}`
    link.click()
    window.URL.revokeObjectURL(url)
  } finally {
    exporting.value = ''
  }
}

onMounted(async () => {
  await reloadAll()
})
</script>

<style scoped>
.hero-card {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
  padding: 24px 26px;
  border-radius: var(--app-radius-md, 16px);
  background:
    radial-gradient(circle at top right, rgba(225, 178, 105, 0.16), transparent 28%),
    linear-gradient(135deg, rgba(255, 251, 245, 0.96), rgba(245, 251, 246, 0.98));
  border: 1px solid var(--app-line);
}

.hero-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-card h2 {
  margin: 8px 0 8px;
  font-size: 32px;
  color: var(--app-text);
}

.hero-note {
  margin-top: 14px;
  max-width: 720px;
  color: var(--app-muted);
  line-height: 1.7;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.workflow-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.workflow-item {
  padding: 16px 18px;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(247, 251, 248, 0.98));
  border: 1px solid var(--app-line);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.workflow-item span {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: #edf7f0;
  color: var(--app-primary-dark);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
}

.workflow-item strong {
  color: var(--app-text);
  font-size: 14px;
}

.metric-card {
  padding: 16px 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--app-line);
}

.metric-card span,
.metric-card strong {
  display: block;
}

.metric-card span {
  color: var(--app-muted);
  font-size: 12px;
}

.metric-card strong {
  margin-top: 10px;
  font-size: 22px;
  color: var(--app-text);
}

.workspace-grid {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 16px;
}

.left-column,
.result-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-sub {
  color: var(--app-muted);
  font-size: 12px;
}

.config-form :deep(.el-select),
.config-form :deep(.el-input-number),
.config-form :deep(.el-input) {
  width: 100%;
}

.config-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.selection-preview {
  min-height: 72px;
}

.preview-title {
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--app-muted);
}

.preview-tag {
  margin: 0 8px 8px 0;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-item {
  padding: 14px;
  text-align: left;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.session-item.active {
  background: linear-gradient(135deg, #f7fbf6, #eef6f0);
  border-color: rgba(118, 176, 138, 0.92);
  box-shadow: var(--app-shadow-soft);
}

.session-item:hover {
  transform: translateY(-1px);
}

.session-item-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.session-item strong {
  color: var(--app-text);
}

.session-item p,
.session-item small {
  display: block;
  margin: 6px 0 0;
  color: var(--app-muted);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.summary-block {
  padding: 12px 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(135deg, #fbfdfb, #f2f7f3);
  border: 1px solid var(--app-line);
}

.summary-block span,
.summary-block strong,
.summary-block small {
  display: block;
}

.summary-block span,
.summary-block small {
  color: var(--app-muted);
}

.summary-block strong {
  margin: 8px 0 4px;
  color: var(--app-text);
}

.distribution-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.distribution-chip {
  padding: 10px 14px;
  border-radius: 999px;
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.distribution-chip span {
  margin-right: 8px;
  color: var(--app-muted);
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.candidate-card {
  padding: 16px;
  border-radius: var(--app-radius-md, 16px);
  background: linear-gradient(135deg, rgba(252, 253, 251, 0.96), rgba(244, 248, 245, 0.98));
  border: 1px solid var(--app-line);
}

.candidate-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.candidate-rank {
  color: var(--app-primary);
  font-size: 12px;
  letter-spacing: 0.08em;
}

.candidate-head h3 {
  margin: 6px 0 4px;
  color: var(--app-text);
}

.candidate-head p {
  margin: 0;
  color: var(--app-muted);
}

.score-pill {
  min-width: 92px;
  padding: 12px 14px;
  text-align: center;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(135deg, var(--app-primary-dark), #204635);
  color: #f3faf5;
}

.score-pill strong,
.score-pill span {
  display: block;
}

.score-pill strong {
  font-size: 24px;
}

.score-pill span {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(243, 250, 245, 0.82);
}

.candidate-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 16px;
}

.skill-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.label {
  min-width: 88px;
  color: var(--app-muted);
  font-size: 13px;
}

.muted {
  color: var(--app-muted);
  font-size: 13px;
}

.dimension-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
}

.dimension-item {
  padding: 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid var(--app-line);
}

.dimension-item span,
.dimension-item strong {
  display: block;
}

.dimension-item span {
  color: var(--app-muted);
  font-size: 12px;
}

.dimension-item strong {
  margin-top: 6px;
  color: var(--app-text);
}

.explain-block {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 12px;
}

.explain-block p,
.explain-block ul {
  margin: 6px 0 0;
  color: var(--app-muted);
  line-height: 1.6;
}

.explain-block ul {
  padding-left: 18px;
}

:deep(.report-preview-dialog) {
  max-width: min(1100px, 92vw);
}

.report-preview {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--app-text);
}

.preview-hero {
  padding: 24px;
  border-radius: var(--app-radius-md, 16px);
  background: linear-gradient(135deg, #f4f7fb, #e8f0ff);
  border: 1px solid var(--app-line);
}

.preview-kicker {
  display: inline-block;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.preview-hero-main h2 {
  margin: 10px 0 8px;
  font-size: 28px;
  color: var(--app-text);
}

.preview-hero-main p {
  margin: 0;
  color: var(--app-muted);
}

.preview-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 16px;
}

.preview-summary-card {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid var(--app-line);
}

.preview-summary-card span,
.preview-summary-card strong {
  display: block;
}

.preview-summary-card span {
  color: var(--app-muted);
  font-size: 12px;
}

.preview-summary-card strong {
  margin-top: 8px;
  font-size: 22px;
  color: var(--app-text);
}

.preview-summary-card .compact {
  font-size: 14px;
  line-height: 1.5;
}

.preview-top-card {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  margin-top: 16px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--app-line);
}

.preview-top-label {
  display: inline-block;
  font-size: 12px;
  color: var(--app-muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.preview-top-card h3 {
  margin: 8px 0 6px;
  color: var(--app-text);
  font-size: 22px;
}

.preview-top-card p {
  margin: 6px 0 0;
  color: var(--app-muted);
}

.preview-top-score {
  min-width: 104px;
  padding: 14px 16px;
  border-radius: var(--app-radius-sm, 12px);
  text-align: center;
  background: var(--app-text);
  color: #fff;
}

.preview-top-score strong,
.preview-top-score span {
  display: block;
}

.preview-top-score strong {
  font-size: 32px;
}

.preview-top-score span {
  margin-top: 4px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.82);
}

.preview-section {
  padding: 18px;
  border-radius: var(--app-radius-md, 16px);
  background: linear-gradient(135deg, rgba(250, 253, 255, 0.96), rgba(244, 248, 252, 0.96));
  border: 1px solid var(--app-line);
}

.preview-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.preview-section-head h3 {
  margin: 0;
  font-size: 18px;
  color: var(--app-text);
}

.preview-section-head span {
  color: var(--app-muted);
  font-size: 13px;
}

.preview-gap-table,
.preview-dimension-table {
  border-radius: var(--app-radius-sm, 12px);
  overflow: hidden;
  border: 1px solid var(--app-line);
}

.preview-gap-row,
.preview-dimension-row {
  display: grid;
  align-items: stretch;
}

.preview-gap-row {
  grid-template-columns: 1.5fr 1fr 1fr;
}

.preview-dimension-row {
  grid-template-columns: 1.1fr 80px 2fr;
}

.preview-gap-row span,
.preview-dimension-row span {
  padding: 11px 12px;
  border-bottom: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.92);
}

.preview-gap-head span,
.preview-dimension-head span {
  background: #eef4ff;
  color: var(--app-text);
  font-weight: 600;
}

.preview-gap-table .preview-gap-row:last-child span,
.preview-dimension-table .preview-dimension-row:last-child span {
  border-bottom: none;
}

.preview-candidate-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.preview-candidate-card {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--app-line);
}

.preview-candidate-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.preview-rank {
  color: #129a92;
  font-size: 12px;
  letter-spacing: 0.08em;
}

.preview-candidate-head h4 {
  margin: 6px 0 4px;
  font-size: 20px;
  color: var(--app-text);
}

.preview-candidate-head p {
  margin: 0;
  color: var(--app-muted);
}

.preview-score-box {
  min-width: 88px;
  padding: 12px;
  border-radius: var(--app-radius-sm, 12px);
  background: #eff4ff;
  text-align: center;
  color: var(--app-text);
}

.preview-score-box strong,
.preview-score-box span {
  display: block;
}

.preview-score-box strong {
  font-size: 28px;
}

.preview-score-box span {
  margin-top: 4px;
  font-size: 12px;
}

.preview-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.preview-chip-row span {
  display: inline-flex;
  padding: 8px 12px;
  border-radius: 999px;
  background: #f3f7fd;
  color: var(--app-muted);
  border: 1px solid var(--app-line);
}

.preview-reason {
  margin: 14px 0;
  color: var(--app-muted);
  line-height: 1.7;
}

.preview-foot-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.preview-foot-grid ul {
  margin: 6px 0 0;
  padding-left: 18px;
  color: var(--app-muted);
}

.preview-footer {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.preview-footer-tip {
  color: var(--app-muted);
  font-size: 13px;
}

.preview-footer-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

@media (max-width: 1200px) {
  .workspace-grid,
  .hero-card,
  .summary-grid,
  .explain-block,
  .preview-summary-grid,
  .preview-foot-grid {
    grid-template-columns: 1fr;
  }

  .workflow-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dimension-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .hero-card {
    padding: 20px;
  }

  .hero-card h2 {
    font-size: 28px;
  }

  .hero-metrics,
  .dimension-grid,
  .workflow-strip {
    grid-template-columns: 1fr 1fr;
  }

  .workspace-grid {
    gap: 14px;
  }

  .head-actions,
  .config-actions,
  .preview-footer-actions {
    width: 100%;
  }

  .head-actions .el-button,
  .config-actions .el-button,
  .preview-footer-actions .el-button {
    flex: 1 1 calc(50% - 10px);
  }

  .candidate-head,
  .preview-candidate-head,
  .preview-top-card,
  .preview-footer {
    flex-direction: column;
  }

  .preview-gap-row,
  .preview-dimension-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .hero-metrics,
  .dimension-grid,
  .workflow-strip {
    grid-template-columns: 1fr;
  }

  .head-actions .el-button,
  .config-actions .el-button,
  .preview-footer-actions .el-button {
    flex-basis: 100%;
  }

  .summary-grid,
  .preview-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
