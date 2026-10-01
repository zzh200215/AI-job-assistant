<template>
  <div class="page-shell pipeline-page">
    <div class="page-header">
      <div>
        <h2>投递看板</h2>
        <div class="page-header-sub">拖拽卡片在阶段间移动，追踪每一步投递进展</div>
      </div>
      <div class="header-actions">
        <el-button-group class="view-toggle">
          <el-button
            :type="viewMode === 'kanban' ? 'primary' : ''"
            size="small"
            @click="viewMode = 'kanban'"
          >
            <el-icon><Grid /></el-icon> 看板
          </el-button>
          <el-button
            :type="viewMode === 'list' ? 'primary' : ''"
            size="small"
            @click="viewMode = 'list'"
          >
            <el-icon><List /></el-icon> 列表
          </el-button>
        </el-button-group>
        <el-button @click="showStats = !showStats" size="small">
          <el-icon><TrendCharts /></el-icon> {{ showStats ? '隐藏' : '查看' }}统计
        </el-button>
        <el-button @click="loadKanban">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button type="primary" @click="showAddDialog = true">
          <el-icon><Plus /></el-icon> 新增投递
        </el-button>
      </div>
    </div>

    <section v-if="totalCards > 0" class="pipeline-focus-strip" aria-label="投递行动摘要">
      <div class="focus-message">
        <span class="focus-label">本周重点</span>
        <strong>{{ pipelineFocusTitle }}</strong>
        <p>{{ pipelineFocusDescription }}</p>
      </div>
      <div class="focus-metrics">
        <div>
          <b>{{ followUpCount }}</b
          ><span>待跟进</span>
        </div>
        <div>
          <b>{{ counts.interview || 0 }}</b
          ><span>面试进行中</span>
        </div>
        <div>
          <b>{{ counts.offer || 0 }}</b
          ><span>待决 Offer</span>
        </div>
      </div>
      <div class="focus-actions">
        <el-button size="small" @click="showStats = !showStats">
          {{ showStats ? '收起转化分析' : '查看转化分析' }}
        </el-button>
        <el-button
          v-if="counts.offer"
          size="small"
          type="primary"
          @click="router.push('/offer/compare')"
        >
          进入 Offer 决策
        </el-button>
      </div>
    </section>

    <!-- 投递统计面板与简历版本表现：D62 出页成 components/StatsPane.vue（纯显示、无 emit） -->
    <StatsPane
      v-if="showStats"
      :counts="counts"
      :total-cards="totalCards"
      :avg-response-days="avgResponseDays"
      :version-performance="versionPerformance"
    />

    <!-- 看板列 -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>

    <div v-else-if="loadError" class="load-error">
      <div>
        <strong>投递记录加载失败</strong>
        <span>{{ loadError }}</span>
      </div>
      <el-button @click="loadKanban">重新加载</el-button>
    </div>

    <BoardPane
      v-else
      :kanban="kanban"
      :columns="columns"
      :total-cards="totalCards"
      :write-busy="writeBusy"
      :now="now()"
      @command="handleCardCmd"
      @move="moveCard"
      @go-recommend="router.push('/jobs/recommend')"
      @open-add="showAddDialog = true"
    />

    <!-- 列表视图：批量栏与那张 11 列的表，D64 出页成 components/ListPane.vue -->
    <ListPane
      v-if="viewMode === 'list' && totalCards > 0"
      :rows="allCards"
      :selected-count="selectedCards.size"
      :write-busy="writeBusy"
      :now="now()"
      @command="handleListCmd"
      @selection-change="onSelectionChange"
      @batch-move="batchMove"
      @clear-selection="clearSelection"
    />

    <!-- 新增投递对话框 -->
    <el-dialog
      v-model="showAddDialog"
      title="新增投递记录"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form ref="addFormRef" :model="addForm" :rules="addRules" label-position="top">
        <el-form-item label="岗位名称" prop="title">
          <el-input v-model="addForm.title" placeholder="如：高级前端工程师" />
        </el-form-item>
        <el-form-item label="公司名称" prop="company">
          <el-input v-model="addForm.company" placeholder="如：字节跳动" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="薪资范围">
            <el-input v-model="addForm.salary_range" placeholder="如：30-50K" />
          </el-form-item>
          <el-form-item label="来源">
            <el-input v-model="addForm.source" placeholder="如：Boss直聘" />
          </el-form-item>
        </div>
        <el-form-item label="备注">
          <el-input v-model="addForm.note" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="本次投递使用的简历版本">
          <el-select
            v-model="addForm.resume_version_id"
            clearable
            placeholder="选择已保存的简历版本"
            class="full-width"
          >
            <el-option
              v-for="version in resumeVersions"
              :key="version.id"
              :label="`${version.label} · ${version.resume_name}`"
              :value="version.id"
            />
          </el-select>
          <AppLoadError
            v-if="versionError"
            title="简历版本拉取失败"
            :message="versionError"
            @retry="loadResumeVersions"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addSubmitting" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>

    <!-- 投递详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="投递详情"
      width="560px"
      :close-on-click-modal="false"
    >
      <div v-if="detailCard">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="岗位" :span="2">{{
            detailCard.title || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="公司">{{ detailCard.company || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前阶段">
            <el-tag size="small">{{ stageLabel(detailCard.stage) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="薪资">{{
            detailCard.salary_range || '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ detailCard.source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="匹配度">{{
            detailCard.match_score ? Math.round(detailCard.match_score) + '分' : '-'
          }}</el-descriptions-item>
          <el-descriptions-item label="简历版本" :span="2">{{
            detailCard.resume_version_label || '未记录'
          }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">{{
            monthDayTime(detailCard.create_time)
          }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.note" label="备注" :span="2">{{
            detailCard.note
          }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.interview_at" label="面试时间" :span="2">{{
            monthDayTime(detailCard.interview_at)
          }}</el-descriptions-item>
          <el-descriptions-item v-if="detailCard.source_url" label="岗位链接" :span="2">
            <el-link :href="detailCard.source_url" target="_blank" type="primary">{{
              detailCard.source_url
            }}</el-link>
          </el-descriptions-item>
        </el-descriptions>
        <div class="feedback-entry">
          <strong>投递反馈</strong>
          <div class="feedback-controls">
            <el-select v-model="feedbackForm.feedback_type" placeholder="反馈类型" size="small">
              <el-option label="HR 回复" value="hr_reply" />
              <el-option label="面试反馈" value="interview" />
              <el-option label="拒绝原因" value="rejection" />
              <el-option label="Offer 反馈" value="offer" />
            </el-select>
            <el-rate v-model="feedbackForm.feedback_score" :max="5" />
          </div>
          <el-input
            v-model="feedbackForm.feedback_note"
            type="textarea"
            :rows="2"
            placeholder="记录关键信息、建议或拒绝原因"
          />
          <el-button size="small" type="primary" :loading="feedbackSaving" @click="saveFeedback"
            >保存反馈</el-button
          >
        </div>
        <div class="detail-actions">
          <el-button
            size="small"
            @click="
              router.push({
                path: '/smart-analysis',
                query: { jd_id: String(detailCard.jd_id || '') },
              })
            "
          >
            <el-icon><DataAnalysis /></el-icon> AI 分析
          </el-button>
          <el-button
            size="small"
            type="primary"
            @click="
              router.push({
                path: '/interview/setup',
                query: { jd_id: String(detailCard.jd_id || '') },
              })
            "
          >
            <el-icon><Microphone /></el-icon> 模拟面试
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  DataAnalysis,
  Grid,
  List,
  Loading,
  Microphone,
  Plus,
  Refresh,
  TrendCharts,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  getKanban,
  movePipelineStage,
  createJobPipelineEntry,
  deleteJobPipelineEntry,
  getPipelineResumeVersions,
  getPipelineResumeVersionStats,
  updateJobPipelineEntry,
} from '@/api/targets'
import { monthDayTime } from '@/utils/format/date'
import {
  avgResponseDays as boardAvgResponseDays,
  columns,
  flattenCards,
  followUpCount as boardFollowUpCount,
  pipelineFocusDescription as boardFocusDescription,
  pipelineFocusTitle as boardFocusTitle,
  stageCounts,
  stageLabel,
  totalCardCount,
} from '@/features/pipeline/lib/pipelineBoard'
import { useLatestCall } from '@/composables/useLatestCall'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import StatsPane from '@/features/pipeline/components/StatsPane.vue'
import BoardPane from '@/features/pipeline/components/BoardPane.vue'
import ListPane from '@/features/pipeline/components/ListPane.vue'

const router = useRouter()

const loading = ref(true)
const kanban = ref({})
const latestKanbanCall = useLatestCall()
const viewMode = ref('kanban')
const showStats = ref(false)
const selectedCards = ref(new Set())

/* 这一页对投递记录的写，一次只跑一趟。起因是批量移动：三个按钮此前谁都不吃守卫，可以连点、
   也可以点了「面试」再点「拒绝」——两个循环交叉发请求，卡片最终落在哪一列取决于返回顺序，
   而屏幕上那句 "成功将 N 项移至「面试」" 讲的是其中一趟的局部结果，它可能是假的。
   顺着这条判据把整页的写路径过了一遍，实测（探针见 D59）撞上来的不止批量：
   - 拖拽：看板列在列表模式下**也在 DOM 里**（`.kanban-board` 那层 `v-else` 只挡 loading/失败，
     不挡 `viewMode`），所以批量在飞时仍能把卡片拖出去——探针当场打出第二条 [1, 'withdrawn']；
   - 卡片下拉的「标记拒绝 / 放弃 / 删除」：批量在飞时发的是同一个 id 的第二发
     [1, 'rejected']，而批量的提示照样说"成功将 2/2 项移至「面试」"。
   守卫按各条路自己的形状给：有按钮的吃 `:loading` + `:disabled`（批量按钮、两个下拉的
   `:disabled`），拖拽没有按钮可禁，只能函数内提前返回。删除那趟的标记举在确认框**之后**：
   确认框开着不该把整页冻住。
   弹窗里那两条写（新增、反馈保存）各自已有 `:loading`，且 `el-dialog` 默认 `modal` ——
   弹窗开着时批量栏在遮罩背后点不到，所以这次没有把它们串进同一个标记。
   函数级的提前返回只留在拖拽那一条：批量按钮上的同类提前返回实测证不了承重
   （变异掉它六条用例照旧全绿），已删。 */
const writeBusy = ref(false)
const resumeVersions = ref([])
const versionError = ref('')
const versionPerformance = ref([])
const totalCards = computed(() => totalCardCount(kanban.value))

// 所有卡片扁平列表
const allCards = computed(() => flattenCards(kanban.value))

// 统计计算
const counts = computed(() => stageCounts(kanban.value))

/* 页面读时间的地方只有一个 `now()`：顶部那句摘要与平均响应在这里用它，两块面板（D63 看板列、
   D64 列表视图）通过 `:now="now()"` 拿同一份口径——模板里现调，所以取值时机和搬之前逐字一致。
   卡片那颗"几天未回复"的判据本身住在 lib 里，面板各自去调。 */
const now = () => Date.now()

const avgResponseDays = computed(() => boardAvgResponseDays(kanban.value.applied, now()))
const followUpCount = computed(() => boardFollowUpCount(allCards.value, now()))
const pipelineFocusTitle = computed(() => boardFocusTitle(counts.value, followUpCount.value))
const pipelineFocusDescription = computed(() =>
  boardFocusDescription(counts.value, followUpCount.value)
)

const showAddDialog = ref(false)
const addSubmitting = ref(false)
const addFormRef = ref(null)
const showDetailDialog = ref(false)
const detailCard = ref(null)
const feedbackSaving = ref(false)
const feedbackForm = ref({ feedback_type: '', feedback_score: 0, feedback_note: '' })
const loadError = ref('')

const addForm = ref({
  title: '',
  company: '',
  salary_range: '',
  source: '',
  note: '',
  resume_version_id: null,
})

const addRules = {
  title: [{ required: true, message: '请输入岗位名称', trigger: 'blur' }],
}

async function loadKanban() {
  // 「刷新」(`:28`) 没有 loading 也没有 disabled：连点两次就是两发在途，
  // 而 Promise.all 之后是三处直接写，晚到的旧快照会把卡片放回原列
  const isCurrent = latestKanbanCall()
  loading.value = true
  try {
    const [data, stats] = await Promise.all([getKanban(), getPipelineResumeVersionStats()])
    if (!isCurrent()) return
    kanban.value = data?.stages || data || {}
    versionPerformance.value = stats?.items || []
    loadError.value = ''
  } catch (error) {
    if (!isCurrent()) return
    kanban.value = {}
    loadError.value = error?.userMessage || '暂时无法获取投递记录，请检查网络后重试。'
  } finally {
    // 过期那一次不动 loading：转圈归更新的那一次
    if (isCurrent()) loading.value = false
  }
}

async function loadResumeVersions() {
  versionError.value = ''
  try {
    const data = await getPipelineResumeVersions()
    resumeVersions.value = data?.items || []
  } catch (e) {
    resumeVersions.value = []
    versionError.value = e?.userMessage || e?.message || '暂时无法读取简历版本列表'
  }
}

/* 面板把"拖的是哪张卡"发过来，这一趟的去留由页面判：同阶段不发、有写在飞不发（D59 那把锁），
   发出去之后乐观更新改的是页面的 `kanban`——所以这段不能跟着面板走。 */
async function moveCard(card, targetStage) {
  if (card.stage === targetStage) return
  if (writeBusy.value) return

  const oldStage = card.stage
  writeBusy.value = true
  try {
    await movePipelineStage(card.id, targetStage)
    // 乐观更新
    const fromList = kanban.value[oldStage] || []
    const toList = kanban.value[targetStage] || []
    const idx = fromList.findIndex((c) => c.id === card.id)
    if (idx >= 0) {
      fromList.splice(idx, 1)
      card.stage = targetStage
      toList.unshift(card)
    }
    ElMessage.success(`已移至「${columns.find((c) => c.key === targetStage)?.label}」`)
  } catch {
    loadKanban()
  } finally {
    writeBusy.value = false
  }
}

async function handleAdd() {
  try {
    await addFormRef.value?.validate()
  } catch {
    return
  }
  addSubmitting.value = true
  try {
    await createJobPipelineEntry({
      ...addForm.value,
      stage: 'todo',
      resume_id:
        resumeVersions.value.find((version) => version.id === addForm.value.resume_version_id)
          ?.resume_id || null,
    })
    ElMessage.success('投递记录已添加')
    showAddDialog.value = false
    addForm.value = {
      title: '',
      company: '',
      salary_range: '',
      source: '',
      note: '',
      resume_version_id: null,
    }
    loadKanban()
  } catch {
    // 失败消息由统一请求层提示。
  } finally {
    addSubmitting.value = false
  }
}

/* 卡片命令的实现只有这一份（D58）。之前看板视图与列表视图各写了一遍同样的
   "移动阶段 → 提示 → 重取"，两份还漂了一处文案（"已标记为拒绝" / "已标记拒绝"）。
   文案随视图传进来，**没有替谁统一**——那是候选人可见的措辞改动，不是一次搬家该定的事。 */
function openCardDetail(card) {
  detailCard.value = card
  feedbackForm.value = {
    feedback_type: card.feedback_type || '',
    feedback_score: card.feedback_score || 0,
    feedback_note: card.feedback_note || '',
  }
  showDetailDialog.value = true
}

function goAnalysisFor(card) {
  router.push(`/smart-analysis?jd_id=${card.jd_id || ''}`)
}

function goInterviewFor(card) {
  router.push(`/interview/setup?jd_id=${card.jd_id || ''}`)
}

async function markStage(card, stage, doneMessage) {
  writeBusy.value = true
  try {
    await movePipelineStage(card.id, stage)
    ElMessage.success(doneMessage)
    loadKanban()
  } catch {
    // 失败消息由统一请求层提示；看板保持原样
  } finally {
    writeBusy.value = false
  }
}

async function removeCard(card) {
  try {
    await ElMessageBox.confirm('确定删除此投递记录？', '删除确认', { type: 'warning' })
  } catch {
    return // 取消删除不是错误
  }
  writeBusy.value = true
  try {
    await deleteJobPipelineEntry(card.id)
    ElMessage.success('已删除')
    loadKanban()
  } catch {
    // 失败消息由统一请求层提示
  } finally {
    writeBusy.value = false
  }
}

async function runCardCommand(cmd, card, labels) {
  if (cmd === 'detail') return openCardDetail(card)
  if (cmd === 'analyze') return goAnalysisFor(card)
  if (cmd === 'interview') return goInterviewFor(card)
  if (cmd === 'reject') return markStage(card, 'rejected', labels.rejected)
  if (cmd === 'abandon') return markStage(card, 'withdrawn', labels.abandon)
  if (cmd === 'delete') return removeCard(card)
}

const KANBAN_COMMAND_LABELS = { rejected: '已标记为拒绝', abandon: '已放弃' }
const LIST_COMMAND_LABELS = { rejected: '已标记拒绝', abandon: '已放弃' }

async function handleCardCmd(cmd, card) {
  await runCardCommand(cmd, card, KANBAN_COMMAND_LABELS)
}

// === 列表视图方法 ===
async function saveFeedback() {
  if (!detailCard.value || (!feedbackForm.value.feedback_type && !feedbackForm.value.feedback_note))
    return
  feedbackSaving.value = true
  try {
    await updateJobPipelineEntry(detailCard.value.id, feedbackForm.value)
    ElMessage.success('反馈已保存')
    await loadKanban()
  } catch {
    // 失败消息由统一请求层提示。这里没有 catch 的话，保存失败的 reject 会一路冒出
    // `@click` 变成未处理的 Promise 拒绝——控制台报错、界面上什么都没说。
  } finally {
    feedbackSaving.value = false
  }
}

async function handleListCmd(cmd, card) {
  await runCardCommand(cmd, card, LIST_COMMAND_LABELS)
}

function onSelectionChange(rows) {
  selectedCards.value = new Set(rows.map((r) => r.id))
}

function clearSelection() {
  selectedCards.value = new Set()
}

async function batchMove(targetStage) {
  const ids = [...selectedCards.value]
  if (!ids.length) return
  writeBusy.value = true
  let success = 0
  try {
    for (const id of ids) {
      try {
        await movePipelineStage(id, targetStage)
        success++
      } catch {
        // 继续处理剩余投递，并在结束后汇总结果。
      }
    }
    const message = `成功将 ${success}/${ids.length} 项移至「${stageLabel(targetStage)}」`
    if (success === ids.length) ElMessage.success(message)
    else ElMessage.warning(message)
    selectedCards.value = new Set()
    loadKanban()
  } finally {
    writeBusy.value = false
  }
}

onMounted(() => {
  loadKanban()
  loadResumeVersions()
})
</script>

<style scoped>
.page-shell {
  color: var(--app-text);
}

.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
  border: 1px solid #f2c5bf;
  border-radius: 8px;
  background: var(--app-accent-soft);
}
.load-error strong,
.load-error span {
  display: block;
}
.load-error strong {
  color: var(--app-danger);
  font-size: 15px;
}
.load-error span {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.pipeline-focus-strip {
  display: grid;
  grid-template-columns: minmax(260px, 1.4fr) minmax(240px, 0.9fr) auto;
  gap: 20px;
  align-items: center;
  margin-bottom: 16px;
  padding: 18px 20px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.focus-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.focus-message strong {
  display: block;
  margin-top: 6px;
  color: var(--app-text);
  font-size: 17px;
}

.focus-message p {
  margin: 6px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}

.focus-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-right: 1px solid var(--app-line);
  border-left: 1px solid var(--app-line);
}

.focus-metrics div {
  display: grid;
  gap: 4px;
  padding: 2px 14px;
  text-align: center;
}

.focus-metrics div + div {
  border-left: 1px solid var(--app-line);
}

.focus-metrics b {
  color: var(--app-primary-dark);
  font-size: 23px;
  line-height: 1;
}

.focus-metrics span {
  color: var(--app-muted);
  font-size: 12px;
}

.focus-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.version-performance {
  margin-bottom: 16px;
  border: 1px solid var(--app-line);
  border-top: 3px solid var(--app-primary);
  border-radius: 8px;
  background: var(--app-surface-strong);
}

.version-performance-title > span,
.version-name span,
.version-metric span,
.version-name,
.version-metric {
  align-items: flex-end;
}

.version-outcomes {
  grid-column: 1 / -1;
  display: flex;
  gap: 10px;
}

/* Board */
.kanban-board {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 16px;
}

/* Form */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.full-width {
  width: 100%;
}

.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 20px;
  justify-content: center;
}

.feedback-entry {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--app-line);
  font-size: 13px;
}

.feedback-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* View toggle */
.view-toggle {
  margin-right: 4px;
}

@media (max-width: 1024px) {
  .pipeline-focus-strip {
    grid-template-columns: 1fr 1fr;
  }

  .focus-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
    padding-top: 12px;
    border-top: 1px solid var(--app-line);
  }

  .kanban-board {
    flex-wrap: wrap;
  }
  .kanban-col {
    max-width: none;
    min-width: 200px;
  }
}

@media (max-width: 768px) {
  .pipeline-focus-strip,
  .focus-metrics {
    grid-template-columns: 1fr;
  }

  .focus-metrics {
    gap: 8px;
    border: 0;
  }

  .focus-metrics div,
  .focus-metrics div + div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
    text-align: left;
  }

  .load-error {
    align-items: flex-start;
    flex-direction: column;
  }
  .page-shell .page-header {
    flex-direction: column;
    gap: 12px;
  }
  .kanban-col {
    min-width: 180px;
  }
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
