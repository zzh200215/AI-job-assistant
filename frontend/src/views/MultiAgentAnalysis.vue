<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>多智能体协作分析</h2>
        <div class="page-header-sub">说出你的需求，AI 自动决定调用哪些智能体</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-body">
        <el-alert
          title="调度 Agent 会识别你的意图并自动编排子智能体"
          type="success"
          :closable="false"
          show-icon
          class="mb"
        >
          <template #default>
            调度 Agent 会识别你的意图 -> 自动选择并编排子智能体（简历诊断 / 岗位分析 / 匹配评估 /
            面试辅导 / 职业规划）-> 汇总报告<br />
            <small>无需手动选流程，依赖关系由系统自动补齐</small>
          </template>
        </el-alert>

        <el-input
          v-model="form.user_request"
          type="textarea"
          :rows="3"
          placeholder="用一句话说说你想要什么，例如：&#10;· 帮我看看这份简历适合投什么岗位，顺便准备一下面试&#10;· 我想转行做后端，给我一份职业规划&#10;· 诊断一下我的简历有什么问题"
        />

        <div class="start-row">
          <el-button type="primary" size="large" :loading="starting" @click="onStart">
            {{ starting ? '智能分析中...' : '开始智能分析' }}
          </el-button>
          <el-text type="info" size="small">
            将使用你最近上传的简历与 JD（如需指定可展开下方高级选项）
          </el-text>
        </div>

        <el-collapse class="adv">
          <el-collapse-item title="高级：手动指定简历 / JD ID（可选）">
            <el-form :inline="true">
              <el-form-item label="简历 ID">
                <el-input-number v-model="form.resume_id" :min="1" />
              </el-form-item>
              <el-form-item label="JD ID">
                <el-input-number v-model="form.jd_id" :min="1" />
              </el-form-item>
              <el-form-item>
                <el-button @click="fillLast">填充最近 ID</el-button>
              </el-form-item>
            </el-form>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>

    <div class="panel" v-if="runId && dispatch">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>智能调度决策</h3>
        </div>
      </div>
      <div class="panel-body">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="识别意图">
            <el-tag size="small" type="primary">{{ intentLabel(dispatch.intent) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="调度理由">{{ dispatch.reason || '-' }}</el-descriptions-item>
          <el-descriptions-item v-if="dispatch.user_profile" label="用户画像">{{
            dispatch.user_profile
          }}</el-descriptions-item>
          <el-descriptions-item label="本次调用">
            <el-tag
              v-for="n in selectedAgents"
              :key="n"
              size="small"
              effect="plain"
              style="margin: 2px"
              >{{ agentLabel(n) }}</el-tag
            >
          </el-descriptions-item>
          <el-descriptions-item v-if="dispatch.notes" label="提示">
            <el-text type="warning">{{ dispatch.notes }}</el-text>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <div class="panel" v-if="runId">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>运行 #{{ runId }}</h3>
          <el-tag :type="statusTag" size="small">{{ statusLabel }}</el-tag>
        </div>
      </div>
      <div class="panel-body">
        <el-row :gutter="12">
          <el-col :span="8" v-for="agent in agents" :key="agent.name" class="mb">
            <div :class="['agent-card', 'panel', agent.status]">
              <div class="panel-header">
                <div class="panel-title-row">
                  <el-tag :type="agentStatusTag(agent)" size="small" effect="dark">
                    {{ agentLabel(agent.name) }}
                  </el-tag>
                  <span v-if="agent.duration_ms" class="agent-time">{{ agent.duration_ms }}ms</span>
                </div>
              </div>
              <div class="panel-body">
                <div class="agent-status">
                  <el-icon v-if="agent.status === 'completed'" class="s-green"
                    ><SuccessFilled
                  /></el-icon>
                  <el-icon v-else-if="agent.status === 'running'" class="is-loading s-warning"
                    ><Loading
                  /></el-icon>
                  <el-icon v-else-if="agent.status === 'failed'" class="s-danger"
                    ><WarningFilled
                  /></el-icon>
                  <el-icon v-else class="s-info"><Clock /></el-icon>
                  <span>{{ agentStatusText(agent) }}</span>
                </div>

                <div v-if="agent.summary" class="agent-summary">{{ agent.summary }}</div>

                <el-button
                  v-if="agent.output_data && Object.keys(agent.output_data).length"
                  size="small"
                  text
                  type="primary"
                  @click="showAgentDetail(agent)"
                >
                  查看详情
                </el-button>

                <div v-if="agent.error_msg" class="agent-error">{{ agent.error_msg }}</div>
              </div>
            </div>
          </el-col>
        </el-row>

        <div class="dep-graph">
          <el-tag size="small" type="info" effect="plain">依赖关系</el-tag>
          <span class="dep-line"
            >ResumeAgent + JobAgent -> MatchAgent -> InterviewAgent + CareerAgent ->
            SummaryAgent</span
          >
        </div>
      </div>
    </div>

    <div class="panel" v-if="summaryReport">
      <div class="panel-header">
        <div class="panel-title-row">
          <h3>{{ summaryReport.report_title || '最终汇总报告' }}</h3>
        </div>
      </div>
      <div class="panel-body">
        <el-tabs>
          <el-tab-pane label="总览">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="候选人">{{
                summaryReport.summary?.candidate || '-'
              }}</el-descriptions-item>
              <el-descriptions-item label="目标岗位">{{
                summaryReport.summary?.target_position || '-'
              }}</el-descriptions-item>
              <el-descriptions-item label="匹配度">
                <el-tag :type="scoreToneTagType(summaryReport.summary?.match_score)">
                  {{ summaryReport.summary?.match_score }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="结论">{{
                summaryReport.summary?.verdict || '-'
              }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <el-tab-pane label="简历诊断">
            <p><b>评分：</b>{{ summaryReport.resume_diagnosis?.score }}</p>
            <ul>
              <li v-for="(f, i) in summaryReport.resume_diagnosis?.key_findings || []" :key="i">
                {{ f }}
              </li>
            </ul>
          </el-tab-pane>

          <el-tab-pane label="岗位分析">
            <p><b>核心技能：</b></p>
            <el-tag
              v-for="(s, i) in summaryReport.job_analysis?.core_skills || []"
              :key="i"
              style="margin: 2px"
              >{{ s }}</el-tag
            >
          </el-tab-pane>

          <el-tab-pane label="面试准备">
            <p>
              共 <b>{{ summaryReport.interview_preparation?.questions_count || 0 }}</b> 道题
            </p>
            <p>重点领域：</p>
            <el-tag
              v-for="(f, i) in summaryReport.interview_preparation?.focus_areas || []"
              :key="i"
              style="margin: 2px"
              type="warning"
              >{{ f }}</el-tag
            >
          </el-tab-pane>

          <el-tab-pane label="职业规划">
            <el-collapse>
              <el-collapse-item title="短期（1-3个月）">
                <p>{{ summaryReport.career_plan?.short_term || '暂无' }}</p>
              </el-collapse-item>
              <el-collapse-item title="中期（3-12个月）">
                <p>{{ summaryReport.career_plan?.mid_term || '暂无' }}</p>
              </el-collapse-item>
              <el-collapse-item title="长期（1-3年）">
                <p>{{ summaryReport.career_plan?.long_term || '暂无' }}</p>
              </el-collapse-item>
            </el-collapse>
          </el-tab-pane>

          <el-tab-pane label="行动项">
            <el-table :data="summaryReport.action_items || []" size="small">
              <el-table-column prop="priority" label="优先级" width="80">
                <template #default="{ row }">
                  <el-tag
                    :type="
                      row.priority === '高' ? 'danger' : row.priority === '中' ? 'warning' : 'info'
                    "
                    size="small"
                  >
                    {{ row.priority }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="action" label="行动" />
              <el-table-column prop="reason" label="原因" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <el-dialog
      v-model="detailVisible"
      :title="`${agentLabel(detailAgent?.name)} — 完整输出`"
      width="800px"
      top="5vh"
    >
      <pre class="json-preview">{{ JSON.stringify(detailAgent?.output_data, null, 2) }}</pre>
    </el-dialog>

    <div class="panel" v-if="runId && !isComplete">
      <div class="panel-body">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            分析中... {{ completedCount }} / {{ selectedAgents.length }} 个智能体已完成
          </template>
        </el-alert>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from '@/plugins/element-services'
import { SuccessFilled, WarningFilled, Loading, Clock } from '@element-plus/icons-vue'
import { startAutoAgent, getMultiAgentDetail } from '@/api/multi_agent'
import { scoreToneTagType } from '@/utils/scoreTone'
import { TASK_STATUS_TAGS, tagTypeFor } from '@/utils/statusTone'
import { readJDId, readResumeId } from '@/utils/lastSelection'

const starting = ref(false)
const runId = ref(null)
const run = ref(null)
const messages = ref([])
const results = ref([])
const detailVisible = ref(false)
const detailAgent = ref(null)
let pollTimer = null
let pollCount = 0
let pollErrors = 0
const MAX_POLLS = 400 // 1.5s * 400 = 10 minutes upper limit
const MAX_POLL_ERRORS = 5 // 5 consecutive request failures to give up

const form = reactive({ user_request: '', resume_id: null, jd_id: null })

const ALL_AGENT_NAMES = [
  'ResumeAgent',
  'JobAgent',
  'MatchAgent',
  'InterviewAgent',
  'CareerAgent',
  'SummaryAgent',
]

// ---- computed ----
const isComplete = computed(() => ['completed', 'failed'].includes(run.value?.status))
const statusLabel = computed(
  () =>
    ({
      pending: '等待中',
      running: '执行中',
      completed: '已完成',
      failed: '失败',
    })[run.value?.status] ||
    run.value?.status ||
    ''
)
const statusTag = computed(() => tagTypeFor(TASK_STATUS_TAGS, run.value?.status))
const summaryReport = computed(() => run.value?.summary_report || null)

// Dispatch decision: prefer full output from Dispatcher message, fallback to run fields
const dispatch = computed(() => {
  const dm = messages.value.find((m) => m.agent_name === 'Dispatcher')
  if (dm && dm.output_data && Object.keys(dm.output_data).length) return dm.output_data
  if (run.value?.intent || (run.value?.selected_agents || []).length) {
    return {
      intent: run.value.intent,
      reason: run.value.dispatch_reason,
      target_agents: run.value.selected_agents,
    }
  }
  return null
})

// Actually invoked agents (written back by backend after dispatch; use full list as placeholder until ready)
const selectedAgents = computed(() => {
  const sel = run.value?.selected_agents
  return sel && sel.length ? sel : ALL_AGENT_NAMES
})

const completedCount = computed(
  () =>
    messages.value.filter((m) => m.status === 'completed' && m.agent_name !== 'Dispatcher').length
)

// Merge messages into agents list (only show dispatched agents)
const agents = computed(() => {
  return selectedAgents.value.map((name) => {
    const msg = messages.value.find((m) => m.agent_name === name)
    const res = results.value.find((r) => r.agent_name === name)
    return {
      name,
      status: msg?.status || 'pending',
      depends_on: msg?.depends_on || [],
      input_data: msg?.input_data || {},
      output_data: msg?.output_data || {},
      error_msg: msg?.error_msg,
      started_at: msg?.started_at,
      completed_at: msg?.completed_at,
      duration_ms: msg?.duration_ms,
      summary: res?.summary || '',
    }
  })
})

// ---- methods ----
const fillLast = () => {
  const rid = readResumeId()
  const jid = readJDId()
  if (rid) form.resume_id = rid
  if (jid) form.jd_id = jid
}

const onStart = async () => {
  if (!form.user_request && !form.resume_id) {
    ElMessage.warning('请描述你的需求（或在高级选项中指定简历 ID）')
    return
  }
  starting.value = true
  try {
    const payload = { user_request: form.user_request }
    if (form.resume_id) payload.resume_id = form.resume_id
    if (form.jd_id) payload.jd_id = form.jd_id
    const data = await startAutoAgent(payload)
    runId.value = data.run_id
    pollCount = 0
    pollErrors = 0
    ElMessage.success('智能分析已启动')
    pollDetail()
  } catch {
    /* request.js */
  } finally {
    starting.value = false
  }
}

const intentLabel = (intent) =>
  ({
    resume_diagnosis: '简历诊断',
    job_matching: '岗位匹配',
    interview_prep: '面试准备',
    career_planning: '职业规划',
    full: '全面分析',
  })[intent] ||
  intent ||
  '全面分析'

const pollDetail = async () => {
  if (!runId.value) return
  try {
    const data = await getMultiAgentDetail(runId.value)
    run.value = data.run
    messages.value = data.messages || []
    results.value = data.results || []
    pollErrors = 0
  } catch {
    pollErrors++
    if (pollErrors >= MAX_POLL_ERRORS) {
      ElMessage.error('获取分析进度多次失败，已停止刷新，请稍后重试')
      return
    }
  }
  if (isComplete.value) return
  if (++pollCount >= MAX_POLLS) {
    ElMessage.warning('分析耗时过长，已停止自动刷新，可刷新页面查看最新进度')
    return
  }
  pollTimer = setTimeout(pollDetail, 1500)
}

const showAgentDetail = (agent) => {
  detailAgent.value = agent
  detailVisible.value = true
}

// ---- helpers ----
const agentLabel = (name) =>
  ({
    ResumeAgent: '简历诊断',
    JobAgent: '岗位分析',
    MatchAgent: '匹配度评估',
    InterviewAgent: '面试辅导',
    CareerAgent: '职业规划',
    SummaryAgent: '汇总报告',
  })[name] || name

const agentStatusTag = (agent) => {
  if (agent.status === 'completed') return 'success'
  if (agent.status === 'running') return 'warning'
  if (agent.status === 'failed') return 'danger'
  return 'info'
}

const agentStatusText = (agent) => {
  if (agent.status === 'completed') return '完成'
  if (agent.status === 'running') return '执行中...'
  if (agent.status === 'failed') return '失败'
  return '等待'
}


// ---- lifecycle ----
onMounted(fillLast)
onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<style scoped>
.mb {
  margin-bottom: 8px;
}
.start-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
  flex-wrap: wrap;
}
.adv {
  margin-top: 4px;
}
.agent-card {
  margin-bottom: 8px;
}
.agent-card.pending {
  opacity: 0.7;
}
.agent-card.running {
  border-color: var(--app-warning);
}
.agent-card.completed {
  border-color: var(--app-success);
}
.agent-card.failed {
  border-color: var(--app-danger);
}
.agent-time {
  color: var(--app-muted);
  font-size: 11px;
}
.agent-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  margin-bottom: 6px;
}
.agent-summary {
  font-size: 12px;
  color: var(--app-muted);
  background: var(--app-bg);
  padding: 4px 8px;
  border-radius: var(--app-radius-xs, 8px);
}
.agent-error {
  color: var(--app-danger);
  font-size: 12px;
  margin-top: 4px;
}
.dep-graph {
  margin-top: 12px;
  text-align: center;
  font-size: 12px;
  color: var(--app-muted);
}
.dep-line {
  margin-left: 6px;
}
.s-green {
  color: var(--app-success);
}
.s-warning {
  color: var(--app-warning);
}
.s-danger {
  color: var(--app-danger);
}
.s-info {
  color: var(--app-muted);
}
.json-preview {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: var(--app-radius-xs, 8px);
  font-size: 12px;
  max-height: 500px;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
