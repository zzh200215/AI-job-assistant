<template>
  <div v-loading="loading" class="workspace-page">
    <section class="workspace-header">
      <div>
        <p class="eyebrow">Resume workspace</p>
        <h1>简历工作台</h1>
        <p class="header-copy">编辑、核对并导出当前投递版本</p>
      </div>
      <div class="header-actions">
        <el-button :loading="generating" @click="onGenerate">
          <el-icon><MagicStick /></el-icon>
          AI 优化
        </el-button>
        <el-button type="primary" :loading="saving" @click="onSave">
          <el-icon><DocumentChecked /></el-icon>
          {{ isOriginal ? '另存为版本' : '保存修改' }}
        </el-button>
      </div>
    </section>

    <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" />

    <section class="version-strip">
      <div class="version-picker">
        <span class="field-label">当前版本</span>
        <el-select v-model="selectedId" class="version-select" @change="onVersionChange">
          <el-option label="原始简历" value="original">
            <span>原始简历</span>
            <small>解析内容</small>
          </el-option>
          <el-option
            v-for="version in persistedVersions"
            :key="version.id"
            :label="versionLabel(version)"
            :value="version.id"
          >
            <span>{{ versionLabel(version) }}</span>
            <small>{{ versionTypeLabel(version.version_type) }}</small>
          </el-option>
        </el-select>
        <el-tag :type="versionTagType(selectedVersion.version_type)" effect="plain">
          {{ versionTypeLabel(selectedVersion.version_type) }}
        </el-tag>
      </div>
      <div class="version-meta">
        <span v-if="selectedVersion.target_jd_id">已关联目标 JD</span>
        <span v-else>未关联目标 JD</span>
        <span v-if="selectedVersion.created_at">{{ monthDay(selectedVersion.created_at) }}</span>
      </div>
    </section>

    <section class="workspace-grid">
      <main class="editor-surface">
        <div class="surface-title-row">
          <div>
            <p class="surface-kicker">Version content</p>
            <h2>Markdown 编辑</h2>
          </div>
          <el-input
            v-model="labelDraft"
            class="label-input"
            maxlength="120"
            aria-label="版本名称"
          />
        </div>
        <el-input
          v-model="contentDraft"
          class="resume-editor"
          type="textarea"
          :rows="25"
          resize="none"
          spellcheck="false"
          aria-label="简历 Markdown 内容"
        />
        <div class="editor-footer">
          <span>{{ contentDraft.length }} 字符</span>
          <span v-if="isOriginal">原始简历编辑后会保存为新版本</span>
          <span v-else>保存后会更新当前版本并清除旧的 ATS 快照</span>
        </div>
      </main>

      <aside class="side-rail">
        <section class="rail-panel jd-panel">
          <div class="panel-heading">
            <div>
              <p class="surface-kicker">Target role</p>
              <h2>目标 JD</h2>
            </div>
            <el-icon><Aim /></el-icon>
          </div>
          <el-select
            v-model="selectedJdId"
            clearable
            placeholder="选择目标岗位"
            class="full-control"
          >
            <el-option v-for="jd in jobs" :key="jd.id" :label="jobLabel(jd)" :value="jd.id" />
          </el-select>
          <AppLoadError
            v-if="jobsError"
            title="岗位列表拉取失败"
            :message="jobsError"
            @retry="loadJobs"
          />
          <el-button
            class="full-control"
            :loading="tailoring"
            :disabled="!selectedJdId"
            @click="onTailor"
          >
            <el-icon><EditPen /></el-icon>
            按 JD 生成定制版
          </el-button>
          <el-button
            text
            class="recommend-button"
            :loading="recommending"
            :disabled="!selectedJdId"
            @click="onRecommendVersion"
          >
            推荐投递版本
          </el-button>
          <p v-if="recommendedVersion" class="recommendation-note">
            推荐：{{ recommendedVersion.label }}，关键词覆盖
            {{ recommendedVersion.keyword_coverage }}%
            <span v-if="recommendedVersion.sample_size"
              >，已有 {{ recommendedVersion.sample_size }} 次投递样本</span
            >
          </p>
        </section>

        <section class="rail-panel ats-panel">
          <div class="panel-heading">
            <div>
              <p class="surface-kicker">Screening preview</p>
              <h2>ATS 预览</h2>
            </div>
            <el-button text :loading="atsLoading" @click="onPreviewAts">
              <el-icon><RefreshRight /></el-icon>
            </el-button>
          </div>
          <template v-if="atsResult">
            <div class="ats-score-row">
              <strong>{{ atsResult.score }}</strong>
              <div>
                <span>/ 100</span>
                <el-tag size="small" :type="atsTagType">{{ atsResult.grade }} 级</el-tag>
              </div>
            </div>
            <el-progress :percentage="atsResult.score" :stroke-width="7" :show-text="false" />
            <ul class="check-list">
              <li
                v-for="check in atsResult.checks"
                :key="check.key"
                :class="{ passed: check.passed }"
              >
                <el-icon><CircleCheckFilled v-if="check.passed" /><WarningFilled v-else /></el-icon>
                {{ check.label }}
              </li>
            </ul>
            <p v-if="atsResult.keyword_coverage.total" class="keyword-note">
              已覆盖 {{ atsResult.keyword_coverage.matched.length }}/{{
                atsResult.keyword_coverage.total
              }}
              个 JD 关键词
            </p>
          </template>
          <p v-else class="empty-hint">运行预览以检查当前内容的可读性与关键词覆盖。</p>
        </section>
      </aside>
    </section>

    <section class="insight-grid">
      <section class="insight-panel diff-panel">
        <div class="panel-heading">
          <div>
            <p class="surface-kicker">Change review</p>
            <h2>版本差异</h2>
          </div>
          <el-select
            v-model="baseVersionId"
            size="small"
            class="baseline-select"
            :disabled="isOriginal"
            @change="loadDiff"
          >
            <el-option label="原始简历" value="original" />
            <el-option
              v-for="version in baseCandidates"
              :key="version.id"
              :label="versionLabel(version)"
              :value="version.id"
            />
          </el-select>
        </div>
        <template v-if="!isOriginal && diffResult">
          <div class="diff-summary">
            <span class="added">+{{ diffResult.summary.added_lines }}</span>
            <span class="removed">-{{ diffResult.summary.removed_lines }}</span>
            <span>{{ diffResult.summary.unchanged_lines }} 行未变</span>
          </div>
          <div class="diff-lines">
            <div
              v-for="(line, index) in visibleDiffLines"
              :key="index"
              :class="['diff-line', line.type]"
            >
              <span>{{ line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' ' }}</span
              >{{ line.content || ' ' }}
            </div>
          </div>
        </template>
        <p v-else class="empty-hint">选择已保存版本后，可查看它与基准版本的逐行差异。</p>
      </section>

      <section class="insight-panel suggestion-panel">
        <div class="panel-heading">
          <div>
            <p class="surface-kicker">AI review</p>
            <h2>改写建议</h2>
          </div>
          <el-tag size="small" effect="plain">{{ suggestions.length }}</el-tag>
        </div>
        <div v-if="suggestions.length" class="suggestion-list">
          <article
            v-for="(suggestion, index) in suggestions"
            :key="suggestion.id"
            class="suggestion-item"
          >
            <div>
              <strong>{{ suggestion.title }}</strong>
              <p>{{ suggestion.detail }}</p>
            </div>
            <div class="suggestion-actions" v-if="!isOriginal">
              <el-button
                circle
                size="small"
                :type="suggestionDecision(index) === 'accepted' ? 'success' : 'default'"
                :aria-label="`采纳建议 ${index + 1}`"
                @click="setSuggestionDecision(index, 'accepted')"
                ><el-icon><Check /></el-icon
              ></el-button>
              <el-button
                circle
                size="small"
                :type="suggestionDecision(index) === 'ignored' ? 'info' : 'default'"
                :aria-label="`忽略建议 ${index + 1}`"
                @click="setSuggestionDecision(index, 'ignored')"
                ><el-icon><Close /></el-icon
              ></el-button>
            </div>
          </article>
        </div>
        <p v-else class="empty-hint">AI 优化或 JD 定制后，改写说明会显示在这里。</p>
      </section>

      <section class="insight-panel export-panel">
        <div>
          <p class="surface-kicker">Delivery</p>
          <h2>导出当前版本</h2>
          <p class="export-copy">导出的内容与当前已保存版本一致。</p>
        </div>
        <div class="export-actions">
          <el-button :loading="exporting" @click="onExport('docx')"
            ><el-icon><Document /></el-icon>Word</el-button
          >
          <el-button :loading="exporting" @click="onExport('pdf')"
            ><el-icon><Files /></el-icon>PDF</el-button
          >
        </div>
      </section>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import {
  Aim,
  Check,
  CircleCheckFilled,
  Close,
  Document,
  DocumentChecked,
  EditPen,
  Files,
  MagicStick,
  RefreshRight,
  WarningFilled,
} from '@element-plus/icons-vue'
import { getJDList } from '@/api/jd'
import { scoreToneTagType } from '@/utils/scoreTone'
import { recommendPipelineResumeVersion } from '@/api/targets'
import {
  createResumeVersion,
  downloadResumeExport,
  generateOptimized,
  getResumeVersionDiff,
  getResumeVersions,
  previewResumeAts,
  saveResumeSuggestionDecision,
  tailorResume,
  updateResumeVersion,
} from '@/api/resume'
import { monthDay } from '@/utils/format/date'
import AppLoadError from '@/components/ui/AppLoadError.vue'

const route = useRoute()
const resumeId = ref(null)
const loading = ref(true)
const saving = ref(false)
const generating = ref(false)
const tailoring = ref(false)
const exporting = ref(false)
const atsLoading = ref(false)
const recommending = ref(false)
const errorMsg = ref('')
const originalVersion = ref({
  id: 'original',
  version_type: 'original',
  label: '原始简历',
  content: '',
})
const persistedVersions = ref([])
const selectedId = ref('original')
const contentDraft = ref('')
const labelDraft = ref('原始简历')
const jobs = ref([])
const jobsError = ref('')
const selectedJdId = ref(null)
const atsResult = ref(null)
const baseVersionId = ref('original')
const diffResult = ref(null)
const recommendedVersion = ref(null)

const selectedVersion = computed(
  () =>
    persistedVersions.value.find((version) => version.id === selectedId.value) ||
    originalVersion.value
)
const isOriginal = computed(() => selectedId.value === 'original')
const baseCandidates = computed(() =>
  persistedVersions.value.filter((version) => version.id !== selectedId.value)
)
const visibleDiffLines = computed(() => (diffResult.value?.lines || []).slice(0, 180))
const atsTagType = computed(() => scoreToneTagType(atsResult.value?.score))
const suggestions = computed(() => normalizeSuggestions(selectedVersion.value.change_log))

watch(selectedId, () => setDraftsFromSelected())

onMounted(async () => {
  resumeId.value = Number(route.params.id)
  await Promise.all([loadWorkspace(), loadJobs()])
})

async function loadWorkspace(preferredVersionId = null) {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await getResumeVersions(resumeId.value)
    originalVersion.value = {
      id: 'original',
      version_type: 'original',
      label: '原始简历',
      content: data.original?.content || '',
      created_at: data.original?.created_at,
      change_log: [],
      suggestion_decisions: {},
    }
    persistedVersions.value = (data.versions || []).filter((version) => version.format === 'md')
    const preferred = persistedVersions.value.find((version) => version.id === preferredVersionId)
    if (preferred) selectedId.value = preferred.id
    else if (
      selectedId.value !== 'original' &&
      !persistedVersions.value.some((version) => version.id === selectedId.value)
    ) {
      selectedId.value = persistedVersions.value[0]?.id || 'original'
    }
    setDraftsFromSelected()
  } catch (error) {
    errorMsg.value = error.message || '加载简历工作台失败'
  } finally {
    loading.value = false
  }
}

async function loadJobs() {
  jobsError.value = ''
  try {
    const data = await getJDList({ page: 1, page_size: 100 })
    jobs.value = data.items || []
  } catch (e) {
    jobs.value = []
    jobsError.value = e?.userMessage || e?.message || '暂时无法读取岗位列表'
  }
}

function setDraftsFromSelected() {
  const version = selectedVersion.value
  contentDraft.value = version.content || ''
  labelDraft.value = version.label || versionTypeLabel(version.version_type)
  selectedJdId.value = version.target_jd_id || null
  atsResult.value = version.ats_snapshot || null
  baseVersionId.value = 'original'
  diffResult.value = null
  if (!isOriginal.value) loadDiff()
}

function onVersionChange() {
  errorMsg.value = ''
}

async function onSave() {
  if (!contentDraft.value.trim()) {
    ElMessage.warning('简历内容不能为空')
    return
  }
  saving.value = true
  try {
    let saved
    if (isOriginal.value) {
      saved = await createResumeVersion(resumeId.value, {
        content: contentDraft.value,
        label: labelDraft.value || '手动编辑版',
        version_type: 'manual',
        target_jd_id: selectedJdId.value || null,
      })
      await loadWorkspace(saved.id)
      ElMessage.success('已保存为新的可编辑版本')
    } else {
      saved = await updateResumeVersion(resumeId.value, selectedVersion.value.id, {
        content: contentDraft.value,
        label: labelDraft.value,
        target_jd_id: selectedJdId.value || null,
      })
      await loadWorkspace(saved.id)
      ElMessage.success('版本已保存')
    }
  } catch (error) {
    errorMsg.value = error.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function onGenerate() {
  generating.value = true
  try {
    const result = await generateOptimized(resumeId.value, selectedJdId.value || null)
    await loadWorkspace(result.version_id)
    ElMessage.success('AI 优化版已生成')
  } catch (error) {
    errorMsg.value = error.message || 'AI 优化失败'
  } finally {
    generating.value = false
  }
}

async function onTailor() {
  tailoring.value = true
  try {
    await tailorResume(resumeId.value, selectedJdId.value)
    await loadWorkspace()
    const tailored = persistedVersions.value.find(
      (version) =>
        version.version_type === 'tailored' && version.target_jd_id === selectedJdId.value
    )
    if (tailored) selectedId.value = tailored.id
    ElMessage.success('已生成目标岗位定制版')
  } catch (error) {
    errorMsg.value = error.message || '定制失败'
  } finally {
    tailoring.value = false
  }
}

async function onRecommendVersion() {
  recommending.value = true
  try {
    const result = await recommendPipelineResumeVersion(selectedJdId.value)
    recommendedVersion.value = result.recommended
    if (!result.recommended) {
      ElMessage.info('暂无可用于推荐的已保存版本')
      return
    }
    const local = persistedVersions.value.find(
      (version) => version.id === result.recommended.resume_version_id
    )
    if (local) {
      selectedId.value = local.id
      ElMessage.success('已切换到推荐版本')
    }
  } catch (error) {
    errorMsg.value = error.message || '获取版本推荐失败'
  } finally {
    recommending.value = false
  }
}

async function onPreviewAts() {
  atsLoading.value = true
  try {
    if (!isOriginal.value && contentDraft.value !== selectedVersion.value.content) {
      ElMessage.warning('请先保存当前修改，再运行 ATS 预览')
      return
    }
    atsResult.value = await previewResumeAts(resumeId.value, {
      version_id: isOriginal.value ? null : selectedVersion.value.id,
      jd_id: selectedJdId.value || null,
    })
    if (!isOriginal.value) {
      const version = persistedVersions.value.find((item) => item.id === selectedVersion.value.id)
      if (version) version.ats_snapshot = atsResult.value
    }
  } catch (error) {
    errorMsg.value = error.message || 'ATS 预览失败'
  } finally {
    atsLoading.value = false
  }
}

async function loadDiff() {
  if (isOriginal.value) return
  try {
    diffResult.value = await getResumeVersionDiff(
      resumeId.value,
      selectedVersion.value.id,
      baseVersionId.value === 'original' ? null : baseVersionId.value
    )
  } catch (error) {
    errorMsg.value = error.message || '加载版本差异失败'
  }
}

async function setSuggestionDecision(index, decision) {
  if (isOriginal.value) return
  try {
    const result = await saveResumeSuggestionDecision(resumeId.value, selectedVersion.value.id, {
      suggestion_id: String(index),
      decision,
    })
    const version = persistedVersions.value.find((item) => item.id === result.id)
    if (version) version.suggestion_decisions = result.suggestion_decisions
    ElMessage.success(decision === 'accepted' ? '已标记为采纳' : '已标记为忽略')
  } catch (error) {
    errorMsg.value = error.message || '保存建议状态失败'
  }
}

function suggestionDecision(index) {
  return selectedVersion.value.suggestion_decisions?.[String(index)] || 'pending'
}

async function onExport(format) {
  if (!isOriginal.value && contentDraft.value !== selectedVersion.value.content) {
    ElMessage.warning('请先保存当前修改，再导出')
    return
  }
  exporting.value = true
  try {
    const version = isOriginal.value ? 'original' : selectedVersion.value.version_type
    const blob = await downloadResumeExport(
      resumeId.value,
      format,
      version,
      isOriginal.value ? null : selectedVersion.value.id
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `resume_${resumeId.value}_${selectedVersion.value.id}.${format}`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`${format.toUpperCase()} 已导出`)
  } catch (error) {
    errorMsg.value = error.message || '导出失败'
  } finally {
    exporting.value = false
  }
}

function versionLabel(version) {
  return (
    version.label || `${versionTypeLabel(version.version_type)} ${monthDay(version.created_at)}`
  )
}

function versionTypeLabel(type) {
  return (
    { original: '原始简历', optimized: 'AI 优化版', tailored: 'JD 定制版', manual: '手动编辑版' }[
      type
    ] || '简历版本'
  )
}

function versionTagType(type) {
  return { original: 'info', optimized: 'success', tailored: 'warning', manual: '' }[type] || 'info'
}

function jobLabel(job) {
  return [job.title, job.company].filter(Boolean).join(' · ')
}

function normalizeSuggestions(changeLog) {
  if (Array.isArray(changeLog)) {
    return changeLog.map((item, index) => ({
      id: String(index),
      title: item.section || item.title || `建议 ${index + 1}`,
      detail: item.reason || item.optimized || item.description || '已根据建议调整内容。',
    }))
  }
  if (changeLog && typeof changeLog === 'object') {
    return Object.entries(changeLog).map(([key, value], index) => ({
      id: key,
      title: key,
      detail:
        typeof value === 'string'
          ? value
          : value?.reason || value?.description || JSON.stringify(value),
      index,
    }))
  }
  return []
}
</script>

<style scoped>
.workspace-page {
  --ink: #182230;
  --muted: #637083;
  --line: #dbe2ea;
  --canvas: #f6f8fb;
  --accent: #0f766e;
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--ink);
}

.workspace-header,
.version-strip,
.workspace-grid,
.insight-grid {
  min-width: 0;
}

.workspace-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 0 12px;
  border-bottom: 2px solid var(--ink);
}

.eyebrow,
.surface-kicker {
  margin: 0 0 4px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 4px;
  font-size: 26px;
  line-height: 1.2;
}

h2 {
  margin-bottom: 0;
  font-size: 16px;
  line-height: 1.35;
}

.header-copy,
.empty-hint,
.export-copy,
.keyword-note {
  margin-bottom: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.55;
}

.header-actions,
.export-actions,
.version-picker,
.version-meta,
.panel-heading,
.editor-footer,
.ats-score-row,
.diff-summary,
.suggestion-actions {
  display: flex;
  align-items: center;
}

.header-actions,
.export-actions,
.suggestion-actions {
  gap: 8px;
}

.version-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--app-surface-strong);
}

.version-picker {
  min-width: 0;
  gap: 10px;
}

.field-label,
.version-meta,
.editor-footer {
  color: var(--muted);
  font-size: 12px;
}

.version-select {
  width: min(330px, 50vw);
}

:deep(.el-select-dropdown__item) {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

:deep(.el-select-dropdown__item small) {
  color: #8491a4;
}

.version-meta {
  justify-content: flex-end;
  gap: 12px;
  text-align: right;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(270px, 0.32fr);
  gap: 16px;
}

.editor-surface,
.rail-panel,
.insight-panel {
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--app-surface-strong);
}

.editor-surface {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 18px;
}

.surface-title-row,
.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.label-input {
  width: min(250px, 42%);
}

.resume-editor {
  margin-top: 16px;
}

:deep(.resume-editor .el-textarea__inner) {
  min-height: 520px !important;
  border-color: #cdd8e4;
  border-radius: 4px;
  background: var(--canvas);
  color: #253245;
  font-family: Consolas, 'Microsoft YaHei', monospace;
  font-size: 13px;
  line-height: 1.75;
}

.editor-footer {
  justify-content: space-between;
  gap: 10px;
  padding-top: 10px;
}

.side-rail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rail-panel,
.insight-panel {
  padding: 16px;
}

.rail-panel .panel-heading > .el-icon {
  color: var(--accent);
  font-size: 20px;
}

.full-control {
  width: 100%;
  margin-top: 14px;
}

.recommend-button {
  width: 100%;
  margin-top: 6px;
}

.recommendation-note {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.ats-panel {
  border-top: 3px solid var(--accent);
}

.ats-score-row {
  align-items: flex-end;
  gap: 8px;
  margin: 14px 0 10px;
}

.ats-score-row strong {
  color: var(--accent);
  font-size: 38px;
  line-height: 0.95;
}

.ats-score-row div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--muted);
  font-size: 12px;
}

.check-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 14px 0;
  padding: 0;
  list-style: none;
}

.check-list li {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #a25d18;
  font-size: 12px;
}

.check-list .passed {
  color: #26754e;
}

.insight-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr) minmax(220px, 0.5fr);
  gap: 16px;
}

.baseline-select {
  width: 148px;
}

.diff-summary {
  gap: 10px;
  margin: 14px 0 8px;
  color: var(--muted);
  font-size: 12px;
}

.added {
  color: #20734b;
}

.removed {
  color: #bc3c3c;
}

.diff-lines {
  max-height: 280px;
  overflow: auto;
  border: 1px solid #e4eaf1;
  border-radius: 4px;
  background: #fafbfd;
  font-family: Consolas, 'Microsoft YaHei', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.diff-line {
  padding: 1px 8px;
  white-space: pre-wrap;
}

.diff-line > span {
  display: inline-block;
  width: 14px;
  color: #8591a3;
}

.diff-line.added {
  background: #e8f5ee;
}

.diff-line.removed {
  background: #fff0f0;
}

.suggestion-list {
  display: flex;
  max-height: 300px;
  flex-direction: column;
  overflow: auto;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #edf1f5;
}

.suggestion-item:last-child {
  border-bottom: 0;
}

.suggestion-item strong {
  font-size: 13px;
}

.suggestion-item p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.export-panel {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border-left: 3px solid #425f9c;
}

.export-actions {
  flex-wrap: wrap;
  margin-top: 18px;
}

@media (max-width: 1050px) {
  .workspace-grid,
  .insight-grid {
    grid-template-columns: 1fr;
  }

  .side-rail {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 680px) {
  .workspace-header,
  .version-strip,
  .version-picker,
  .editor-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .header-actions,
  .version-meta {
    justify-content: flex-start;
  }

  .version-select,
  .label-input {
    width: 100%;
    max-width: none;
  }

  .side-rail {
    grid-template-columns: 1fr;
  }

  .check-list {
    grid-template-columns: 1fr;
  }
}
</style>
