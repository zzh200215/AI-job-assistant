<template>
  <div class="page-shell pr-page">
    <div class="page-header">
      <div>
        <h2>项目分析</h2>
        <div class="page-header-sub">
          {{
            report
              ? `${reportName} · 六维评分卡、四张图、使用建议、面试准备`
              : '量的是一个项目：六维 + 位次 + 六条一票否决，与整份简历那份七维报告不是一把尺'
          }}
        </div>
      </div>
      <div class="pr-actions">
        <el-button @click="backToCenter">返回简历中心</el-button>
        <el-button type="primary" :loading="downloading" :disabled="!report" @click="doDownload">
          下载独立 HTML
        </el-button>
      </div>
    </div>

    <el-alert v-if="pageError" :title="pageError" type="error" show-icon :closable="false" />

    <section v-if="!report" class="pr-card">
      <h3 class="pr-h3">开始一次项目分析</h3>
      <p class="pr-lead">
        先挑简历，再挑这份简历里的第几个项目。前三节（项目档案、项目图解、使用建议）一次跑完；
        面试准备那二十道题不在这次里——它要单独花一发模型调用，页面出来后再点按钮生成。
      </p>
      <div class="pr-form">
        <label class="pr-field">
          <span class="pr-field-label">简历</span>
          <el-select
            v-model="form.resumeId"
            placeholder="选择一份简历"
            :loading="optionsLoading"
            @change="loadProjects"
          >
            <el-option v-for="r in resumes" :key="r.id" :label="resumeLabel(r)" :value="r.id" />
          </el-select>
        </label>
        <label class="pr-field">
          <span class="pr-field-label">项目</span>
          <el-select
            v-model="form.projectIndex"
            placeholder="选择其中一个项目"
            :disabled="!projects.length"
          >
            <el-option
              v-for="p in projects"
              :key="p.index"
              :label="`第 ${p.index + 1} 个 · ${p.name}`"
              :value="p.index"
            />
          </el-select>
        </label>
        <label class="pr-field">
          <span class="pr-field-label">目标岗位（可选）</span>
          <el-select
            v-model="form.jdId"
            clearable
            placeholder="不选则按项目自己写到的技术栈判断方向"
          >
            <el-option
              v-for="j in jdOptions"
              :key="j.id"
              :label="j.title || '未命名岗位'"
              :value="j.id"
            />
          </el-select>
        </label>
      </div>
      <div class="pr-start-row">
        <el-button
          type="primary"
          :loading="job.loading"
          :disabled="!canStart"
          @click="startAnalysis"
        >
          {{ job.id ? '重新生成前三节' : '开始生成前三节' }}
        </el-button>
        <span v-if="job.loading" class="pr-loading">正在逐节生成，请稍候</span>
        <span v-else-if="job.status === 'failed'" class="pr-loading"
          >这一份项目分析没能生成，可以再点一次</span
        >
        <span v-else-if="!projects.length && form.resumeId" class="pr-loading"
          >这份简历里没解析出项目经历</span
        >
      </div>
    </section>

    <template v-if="report">
      <nav class="pr-nav">
        <a
          v-for="item in visibleSections"
          :key="item.anchor"
          :href="`#${item.anchor}`"
          :class="{ on: activeAnchor === item.anchor }"
        >
          {{ item.label }}
        </a>
      </nav>

      <div v-if="report.excluded" class="pr-redline">
        <b>这一份不给总分与等级。</b>{{ report.excluded_note }}
        <ul>
          <li v-for="line in report.excluded_by" :key="line.key">
            <b>{{ line.label }}</b
            >——逐字证据「{{ line.quote }}」：{{ line.why }}
          </li>
        </ul>
      </div>

      <section id="p-profile" class="pr-card">
        <h2 class="pr-ct">一、项目档案</h2>
        <div class="pr-pills">
          <span class="pr-pill"><b>项目</b>{{ reportName }}</span>
          <span v-if="portrait.main_line" class="pr-pill"><b>主线</b>{{ portrait.main_line }}</span>
          <span class="pr-pill"><b>贡献定位</b>{{ contributionText }}</span>
          <span class="pr-pill"><b>难度</b>{{ report.difficulty?.level || '未定级' }}</span>
          <span class="pr-pill"><b>评分</b>{{ scoreText }}</span>
        </div>

        <h3>1.1 六维评分卡</h3>
        <table class="pr-table scorecard">
          <thead>
            <tr>
              <th>维度</th>
              <th class="n">得分</th>
              <th class="n">满分</th>
              <th>落档</th>
              <th>主要扣分理由</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.dimensions" :key="row.key" :class="{ hot: isLow(row) }">
              <td>
                <b>{{ row.label }}</b>
              </td>
              <td class="n">
                <b>{{ row.score === null ? '—' : row.score }}</b>
              </td>
              <td class="n">{{ row.full }}</td>
              <td>{{ bandOf(row) }}</td>
              <td>
                <ProjectTodoText v-if="row.note" :text="row.note" />
                <span v-else class="pr-muted">本次分析没有为这一维写出待优化点</span>
              </td>
            </tr>
            <tr class="total">
              <td>合计</td>
              <td class="n">
                <b id="score-total">{{ report.score_cell }}</b>
              </td>
              <td class="n">100</td>
              <td>{{ report.grade || (report.excluded ? '出局' : '—') }}</td>
              <td>{{ report.grade_desc || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="pr-concl">
          评级档位：{{ report.grade_scale }}。这一档说的是这一个项目，不是这份简历。
        </p>

        <h3>1.2 简历原始档案</h3>
        <p class="pr-note">
          以下逐字摘录自简历中该项目条目，未作改写、未作润色；仅公司名 / 客户名 /
          真实人名按脱敏规则处理。
        </p>
        <div class="pr-paper">
          <div v-for="section in report.excerpt?.sections || []" :key="section.label">
            <h4 class="pr-sl">{{ section.label }}</h4>
            <p v-for="(line, i) in section.lines" :key="i" class="pr-vl">{{ line }}</p>
          </div>
        </div>

        <h3>1.3 亮点指标（已脱敏）</h3>
        <table v-if="report.highlights?.length" class="pr-table">
          <thead>
            <tr>
              <th>指标</th>
              <th>数值</th>
              <th>口径</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in report.highlights" :key="item.metric">
              <td>
                <b>{{ item.metric }}</b>
              </td>
              <td><ProjectTodoText :text="item.value" /></td>
              <td><ProjectTodoText :text="item.basis" /></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="pr-muted">这一份项目原文里没有可摘出来的量化亮点。</p>

        <h3>1.4 面试钩子（可深挖的技术决策点）</h3>
        <ul class="pr-ul">
          <li v-for="(hook, i) in report.hooks || []" :key="i">{{ hook }}</li>
        </ul>

        <h3>1.5 难度分级</h3>
        <p class="pr-concl" v-if="report.difficulty?.level">
          {{ report.difficulty.level }}——{{ report.difficulty.name }}：{{
            report.difficulty.reason
          }}
        </p>
        <p v-else class="pr-muted">这一份没有定级。</p>

        <h3>1.6 风险提示（哪里一问就穿）</h3>
        <table v-if="report.risks?.length" class="pr-table">
          <thead>
            <tr>
              <th>风险点</th>
              <th>说明</th>
              <th>补齐建议</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="risk in report.risks" :key="risk.point">
              <td>
                <b>{{ risk.point }}</b>
              </td>
              <td>{{ risk.detail }}</td>
              <td><ProjectTodoText :text="risk.fix" /></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="pr-muted">这一份没有写出「哪里一问就穿」。</p>
      </section>

      <section v-if="report.diagrams" id="p-diagrams" class="pr-card">
        <h2 class="pr-ct">二、项目图解</h2>
        <h3>2.1 项目背景</h3>
        <p>{{ report.diagrams.background }}</p>
        <h3>2.2 核心需求</h3>
        <ul class="pr-ul">
          <li v-for="need in report.diagrams.needs?.items || []" :key="need.title">
            <b>{{ need.title }}</b
            >——{{ need.detail }}
          </li>
        </ul>
        <table class="pr-table">
          <tbody>
            <tr>
              <td><b>使用角色</b></td>
              <td>{{ report.diagrams.needs?.roles }}</td>
            </tr>
            <tr>
              <td><b>交付形态</b></td>
              <td>{{ report.diagrams.needs?.delivery }}</td>
            </tr>
            <tr>
              <td><b>约束条件</b></td>
              <td>{{ report.diagrams.needs?.constraints }}</td>
            </tr>
          </tbody>
        </table>

        <template v-if="report.diagrams.function_arch">
          <h3>2.3 产品功能架构</h3>
          <table class="pr-table">
            <tbody>
              <tr v-for="layer in report.diagrams.function_arch.layers" :key="layer.name">
                <td>
                  <b>{{ layer.name }}</b>
                  <span v-if="layer.mine" class="pr-mine">★ 我负责</span>
                </td>
                <td>
                  <span v-for="cell in layer.cells" :key="cell.title">
                    <b>{{ cell.title }}</b
                    ><span v-for="(line, i) in cell.lines" :key="i"><br />{{ line }}</span>
                    <br />
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <p class="pr-concl">{{ report.diagrams.function_arch.boundary }}</p>
          <table class="pr-table">
            <thead>
              <tr>
                <th>看哪里</th>
                <th>深挖点（面试官会顺着图问）</th>
                <th>出处</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.diagrams.function_arch.deep_dive || []" :key="row.where">
                <td>
                  <b>{{ row.where }}</b>
                </td>
                <td>{{ row.point }}</td>
                <td>{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <template v-if="report.diagrams.core_flow">
          <h3>2.4 核心流程</h3>
          <div class="pr-flow">
            <div class="pr-node">
              <b>{{ report.diagrams.core_flow.input?.title }}</b
              ><br /><span
                v-for="(line, i) in report.diagrams.core_flow.input?.lines || []"
                :key="i"
                >{{ line }}<br
              /></span>
            </div>
            <div v-for="node in report.diagrams.core_flow.nodes" :key="node.no" class="pr-node">
              <b>{{ node.no }} {{ node.title }}</b
              ><br />
              <span v-for="(line, i) in node.lines" :key="i">{{ line }}<br /></span>
            </div>
            <div class="pr-node pr-exit">
              <b>{{ report.diagrams.core_flow.exit?.title }}</b
              ><br /><span v-for="(line, i) in report.diagrams.core_flow.exit?.lines || []" :key="i"
                >{{ line }}<br
              /></span>
            </div>
          </div>
          <p class="pr-concl">{{ report.diagrams.core_flow.state }}</p>
          <p class="pr-note">虚线为回退路径：</p>
          <ul class="pr-ul">
            <li v-for="(fb, i) in report.diagrams.core_flow.fallbacks" :key="i">{{ fb }}</li>
          </ul>
          <table class="pr-table">
            <thead>
              <tr>
                <th>看哪里</th>
                <th>深挖点（面试官会顺着图问）</th>
                <th>出处</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.diagrams.core_flow.deep_dive || []" :key="row.where">
                <td>
                  <b>{{ row.where }}</b>
                </td>
                <td>{{ row.point }}</td>
                <td>{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <template v-if="report.diagrams.system_arch">
          <h3>2.5 系统架构</h3>
          <table class="pr-table">
            <tbody>
              <tr v-for="layer in report.diagrams.system_arch.layers" :key="layer.name">
                <td>
                  <b>{{ layer.name }}</b>
                </td>
                <td>
                  <span v-for="comp in layer.components" :key="comp.title"
                    ><b>{{ comp.title }}</b
                    >：{{ comp.line }}<br
                  /></span>
                  <span v-if="layer.principle" class="pr-muted"
                    >分界原则：{{ layer.principle }}</span
                  >
                </td>
              </tr>
            </tbody>
          </table>
          <table class="pr-table">
            <thead>
              <tr>
                <th>看哪里</th>
                <th>深挖点（面试官会顺着图问）</th>
                <th>出处</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.diagrams.system_arch.deep_dive || []" :key="row.where">
                <td>
                  <b>{{ row.where }}</b>
                </td>
                <td>{{ row.point }}</td>
                <td>{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <template v-if="report.diagrams.sequence">
          <h3>2.6 任务时序</h3>
          <div class="pr-lanes">
            <span v-for="lane in report.diagrams.sequence.lanes" :key="lane" class="pr-lane">{{
              lane
            }}</span>
          </div>
          <table class="pr-table">
            <thead>
              <tr>
                <th>这一步</th>
                <th>带着什么过去</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(msg, i) in report.diagrams.sequence.messages" :key="i">
                <td>{{ msg.from }} → {{ msg.to }}</td>
                <td>{{ msg.text }}</td>
              </tr>
            </tbody>
          </table>
          <p class="pr-note">虚线为失败分支：</p>
          <ul class="pr-ul">
            <li v-for="(branch, i) in report.diagrams.sequence.branches" :key="i">{{ branch }}</li>
          </ul>
          <table class="pr-table">
            <thead>
              <tr>
                <th>看哪里</th>
                <th>深挖点（面试官会顺着图问）</th>
                <th>出处</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.diagrams.sequence.deep_dive || []" :key="row.where">
                <td>
                  <b>{{ row.where }}</b>
                </td>
                <td>{{ row.point }}</td>
                <td>{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <p v-if="report.diagrams.reading_note" class="pr-usage">
          {{ report.diagrams.reading_note }}
        </p>
      </section>

      <section v-if="report.advice" id="p-advice" class="pr-card">
        <h2 class="pr-ct">三、使用建议</h2>
        <h3>3.1 课程教学建议</h3>
        <table class="pr-table">
          <tbody>
            <tr v-for="pair in teachingRows" :key="pair[0]">
              <td>
                <b>{{ pair[0] }}</b>
              </td>
              <td><ProjectTodoText :text="pair[1]" /></td>
            </tr>
          </tbody>
        </table>
        <h3>3.2 简历复用建议</h3>
        <table class="pr-table">
          <tbody>
            <tr v-for="pair in reuseRows" :key="pair[0]">
              <td>
                <b>{{ pair[0] }}</b>
              </td>
              <td><ProjectTodoText :text="pair[1]" /></td>
            </tr>
          </tbody>
        </table>
        <h3>3.3 面试陪练建议</h3>
        <table class="pr-table">
          <tbody>
            <tr v-for="pair in practiceRows" :key="pair[0]">
              <td>
                <b>{{ pair[0] }}</b>
              </td>
              <td><ProjectTodoText :text="pair[1]" /></td>
            </tr>
          </tbody>
        </table>
        <p class="pr-note">{{ practiceNote }}</p>
        <h3>3.4 补强路径</h3>
        <table class="pr-table">
          <thead>
            <tr>
              <th>缺口</th>
              <th>补齐动作</th>
              <th>补齐后预计</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.advice.strengthen" :key="row.gap">
              <td>{{ row.gap }}</td>
              <td><ProjectTodoText :text="row.action" /></td>
              <td>{{ row.expected }}</td>
            </tr>
          </tbody>
        </table>
        <p class="pr-note">
          需实测的数字一律标【待补：按 X 路径跑一遍得到实测值】——不替使用者编数字。
        </p>
        <h3>3.5 引用红线</h3>
        <table class="pr-table">
          <tbody>
            <tr v-for="pair in citationRows" :key="pair[0]">
              <td>
                <b>{{ pair[0] }}</b>
              </td>
              <td><ProjectTodoText :text="pair[1]" /></td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="report.questions_state === 'not_generated'" class="pr-card">
        <h2 class="pr-ct">四、面试准备（二十题）</h2>
        <p class="pr-lead">
          这一节不在刚才那一次里：它要单独花一发模型调用（二十道题的口述稿与两轮追问，是这条链上最长的一发）。
          前三节看着没问题了再点，点完这一页会自己刷新。
        </p>
        <el-button
          type="primary"
          :loading="questionsJob.loading"
          :disabled="!report.job_id"
          @click="startQuestions"
        >
          生成面试准备
        </el-button>
        <span v-if="questionsError" class="pr-loading">{{ questionsError }}</span>
      </section>

      <section v-else id="p-questions" class="pr-card">
        <h2 class="pr-ct">四、面试准备（每题含标准答案与两轮追问）</h2>
        <p v-if="questionsDeferred" class="pr-concl">{{ report.questions?.note }}</p>
        <template v-else>
          <div class="pr-qstat">{{ questionStatText }}</div>
          <div v-for="item in report.questions?.questions || []" :key="item.no" class="pr-q">
            <p class="pr-q-title">
              <span class="pr-no">Q{{ item.no }}</span> {{ item.question }}
              <em class="pr-kind">{{ item.kind }}</em>
            </p>
            <p class="pr-lbl">【标准答案】</p>
            <p>{{ item.answer }}</p>
            <template v-if="item.diagram">
              <p class="pr-lbl">本题配图｜{{ item.diagram.title }}</p>
              <div class="pr-dcards">
                <span v-for="card in item.diagram.cards" :key="card.title" class="pr-dcard"
                  ><b>{{ card.title }}</b
                  ><br /><span v-for="(line, i) in card.lines" :key="i">{{ line }}<br /></span
                ></span>
              </div>
              <p v-if="item.diagram.note" class="pr-concl">{{ item.diagram.note }}</p>
              <p class="pr-how">{{ item.diagram.how_to_draw }}</p>
            </template>
            <p v-for="(fu, i) in item.followups" :key="i">
              <span class="pr-lbl-z">【追问 {{ i + 1 }}｜{{ fu.kind }}】</span>{{ fu.text }}
            </p>
            <ul v-if="item.missing?.length" class="pr-ul">
              <li v-for="(m, i) in item.missing" :key="i"><ProjectTodoText :text="m" /></li>
            </ul>
            <span class="pr-st" :class="statusClass(item.status)">{{
              statusMark(item.status)
            }}</span>
          </div>
          <p class="pr-concl">题型分布：{{ kindText }}</p>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from '@/plugins/element-services'
import { createAgentTaskPoller } from '@/utils/agentTaskPolling'
import { userErrorCopy } from '@/utils/requestTracing'
import {
  createProjectQuestionsJob,
  createProjectReportJob,
  downloadProjectReportHtml,
  getProjectReportJob,
  getResume,
  getResumeList,
} from '@/api/resume'
import { getJDList } from '@/api/jd'
import ProjectTodoText from '../components/ProjectTodoText.vue'

/* 锚点与后端 `project_report_html_lint.SECTIONS` 同一张表：两份交付物必须指向同一批 id。 */
const SECTIONS = [
  { anchor: 'p-profile', label: '一、项目档案' },
  { anchor: 'p-diagrams', label: '二、项目图解' },
  { anchor: 'p-advice', label: '三、使用建议' },
  { anchor: 'p-questions', label: '四、面试准备' },
]

/* 前三节两发模型调用，预算 = 报告那一族的 225 次 × 2 秒 × 2。
   第四节是一发长输出，同一族纪律下不带 per-request 超时。 */
const POLL_INTERVAL_MS = 2000
const POLL_MAX_ATTEMPTS = 450
const QUESTIONS_MAX_ATTEMPTS = 225

const route = useRoute()
const router = useRouter()

const resumes = ref([])
const projects = ref([])
const jdOptions = ref([])
const optionsLoading = ref(false)
const form = reactive({ resumeId: null, projectIndex: null, jdId: null })

const job = reactive({ id: null, status: '', loading: false })
const questionsJob = reactive({ id: null, loading: false })
const report = ref(null)
const pageError = ref('')
const questionsError = ref('')
const activeAnchor = ref(SECTIONS[0].anchor)
const downloading = ref(false)
let alive = true

const poller = createAgentTaskPoller(
  {
    getAgentTask: (jobId) => getProjectReportJob(jobId),
    getAgentSteps: async () => ({ steps: [] }),
  },
  {
    rejectOnStop: true,
    setPollingState(value) {
      job.loading = value
    },
  }
)

const questionsPoller = createAgentTaskPoller(
  {
    getAgentTask: (jobId) => getProjectReportJob(jobId),
    getAgentSteps: async () => ({ steps: [] }),
  },
  { rejectOnStop: true }
)

const reportName = computed(
  () => report.value?.excerpt?.name || `项目${(report.value?.project_index ?? 0) + 1}`
)
const portrait = computed(() => report.value?.portrait || {})

const contributionText = computed(() => {
  const c = report.value?.contribution || {}
  const share =
    c.share === null || c.share === undefined ? '算不出来（同简历其它项目没读全）' : `${c.share}%`
  return `简历第 ${c.rank ?? 1} 个项目 · 系数 ${c.coefficient ?? '—'} · 占这份简历 ${share}`
})

const scoreText = computed(() => {
  const cell = report.value?.score_cell || '未评分'
  return cell === '不作数' || cell === '未评分' ? cell : `${cell}/100`
})

const visibleSections = computed(() => {
  const doc = report.value
  if (!doc) return []
  return SECTIONS.filter((item) => {
    if (item.anchor === 'p-diagrams') return !!doc.diagrams
    if (item.anchor === 'p-advice') return !!doc.advice
    if (item.anchor === 'p-questions') return doc.questions_state !== 'not_generated'
    return true
  })
})

const teachingRows = computed(() => {
  const t = report.value?.advice?.teaching || {}
  const level = report.value?.advice?.level
  return [
    ['难度级别', level ? `${level}——${report.value.advice.level_reason || ''}` : ''],
    ['适合讲什么', t.suitable],
    ['可拆几步', t.steps],
    ['实操切入点', t.entry],
    ['适配环节', t.stage],
  ]
})

const reuseRows = computed(() => {
  const r = report.value?.advice?.reuse || {}
  return [
    ['可借鉴的结构', r.structure],
    ['可迁移的表述', r.expression],
    ['需要替换的内容', r.replace],
    ['反例提示', r.counterexample],
  ]
})

const practiceRows = computed(() => {
  const p = report.value?.advice?.practice || {}
  return [
    ['必练题（按重要性）', p.must_practice],
    ['高危题', p.high_risk],
    ['练习方法', p.method],
    ['追问预演', p.rehearsal],
    ['时间分配', p.timing],
  ]
})

const practiceNote = computed(() =>
  report.value?.advice?.practice?.must_practice
    ? '这两行由第四节生成完回填。'
    : '这两行要等你点了「生成面试准备」之后才填得上。'
)

const citationRows = computed(() => {
  const c = report.value?.advice?.citation || {}
  return [
    ['✅ 可借鉴', c.borrow],
    ['⚠️ 需改造', c.adapt],
    ['🔴 一抄就穿', c.breaks],
  ]
})

const questionsDeferred = computed(() => report.value?.questions_state === 'deferred')

const questionStatText = computed(() => {
  const d = report.value?.questions?.distribution || {}
  return `共 ${d.total ?? 0} 题 · 可答 ${d.answerable ?? 0} · 需补强 ${d.weak ?? 0} · 高危 ${d.high_risk ?? 0} · 就地配图 ${d.diagrammed ?? 0}`
})

const kindText = computed(() => {
  const by = report.value?.questions?.distribution?.by_kind || {}
  return Object.entries(by)
    .map(([name, count]) => `${name} ${count}`)
    .join('、')
})

const canStart = computed(
  () => form.resumeId && form.projectIndex !== null && form.projectIndex !== undefined
)

function resumeLabel(r) {
  return r.name || r.file_name || `简历 #${r.id}`
}

function isLow(row) {
  if (row.score === null || !row.full) return true
  return row.score / row.full <= 0.7
}

function bandOf(row) {
  // 落档那一格是"排第几"，不是这一维的得分：第 1 位拿 5 分，用分数会打成"第 5 位"
  if (row.positional) return `第 ${report.value?.contribution?.rank ?? row.score ?? 0} 位`
  if (row.score === null) return '未读出来'
  const ratio = row.full ? row.score / row.full : 0
  if (ratio >= 0.9) return '优'
  if (ratio >= 0.75) return '良'
  return ratio >= 0.6 ? '中' : '弱'
}

function statusMark(status) {
  return { 可答: '✅ 可答', 需补强: '⚠️ 需补强', 高危: '🔴 高危' }[status] || status
}

function statusClass(status) {
  return status === '可答' ? '' : status === '高危' ? 'danger' : 'warn'
}

function onScroll() {
  const y = window.pageYOffset + 160
  let current = SECTIONS[0].anchor
  for (const item of visibleSections.value) {
    const el = document.getElementById(item.anchor)
    if (el && el.offsetTop <= y) current = item.anchor
  }
  activeAnchor.value = current
}

onUnmounted(() => {
  alive = false
  poller.stopPolling()
  questionsPoller.stopPolling()
  window.removeEventListener('scroll', onScroll)
})

onMounted(async () => {
  window.addEventListener('scroll', onScroll, { passive: true })
  await loadOptions()
  const resumed = await restoreFromQuery()
  if (!resumed) onScroll()
})

async function loadOptions() {
  optionsLoading.value = true
  try {
    const data = await getResumeList({ page: 1, page_size: 50 })
    resumes.value = data?.items || []
  } catch {
    resumes.value = []
    pageError.value = '暂时读不到简历列表，请检查网络后回到这一页重试'
  }
  try {
    const jdData = await getJDList({ page: 1, page_size: 100 })
    jdOptions.value = jdData?.items || []
  } catch {
    // 岗位列表读不出来只是少一个可选项，不影响这一页的主数据
  }
  const fromQuery = Number(route.query.resume_id || 0) || null
  form.resumeId = resumes.value.some((r) => r.id === fromQuery)
    ? fromQuery
    : resumes.value[0]?.id || null
  await loadProjects()
  optionsLoading.value = false
}

/**
 * 项目下拉来自这份简历解析出来的项目条目——位次那一维就是它的顺序。
 * 键名与后端 `project_report_service.project_entries` 同一条：`project_experience` 优先、
 * 退回 `projects`。少这一半退，那种简历在下拉里就是"没有项目"，而后端明明能算。
 */
async function loadProjects() {
  projects.value = []
  form.projectIndex = null
  if (!form.resumeId) return
  try {
    const detail = await getResume(form.resumeId)
    const parsed = detail?.parsed || {}
    const raw = Array.isArray(parsed.project_experience)
      ? parsed.project_experience
      : Array.isArray(parsed.projects)
        ? parsed.projects
        : []
    const rows = raw.filter((row) => row && typeof row === 'object')
    projects.value = rows.map((row, index) => ({
      index,
      name: row.name || `项目经历 ${index + 1}`,
    }))
    const wanted = Number(route.query.project_index || -1)
    form.projectIndex = projects.value.some((p) => p.index === wanted)
      ? wanted
      : (projects.value[0]?.index ?? null)
  } catch {
    pageError.value = '这一份简历的项目读不出来，回简历中心确认它已经解析过再试'
  }
}

async function restoreFromQuery() {
  const jobId = Number(route.query.job_id || 0)
  if (!jobId) return false
  await runJob(jobId)
  return true
}

function rememberJobInQuery(jobId) {
  router.replace({ query: { ...route.query, job_id: String(jobId) } })
}

function startAnalysis() {
  if (job.loading || !canStart.value) return
  pageError.value = ''
  questionsError.value = ''
  runCreate()
}

async function runCreate() {
  job.loading = true
  job.status = 'pending'
  try {
    const created = await createProjectReportJob(form.resumeId, {
      project_index: form.projectIndex,
      jd_id: form.jdId || null,
    })
    job.id = created?.job_id ?? null
    if (job.id) rememberJobInQuery(job.id)
    await runJob(job.id, created?.status)
  } catch (err) {
    if (!alive) return
    job.status = 'failed'
    pageError.value = userErrorCopy(err, '这一份项目分析没能生成，稍后再试')
  } finally {
    if (alive) job.loading = false
  }
}

async function runJob(jobId, knownStatus = '') {
  if (!jobId) return
  job.id = jobId
  job.status = knownStatus || 'pending'
  try {
    const data = await poller.pollTask(jobId, {
      maxPollCount: POLL_MAX_ATTEMPTS,
      intervalMs: POLL_INTERVAL_MS,
      timeoutMessage: '这一份项目分析这次没跑完，稍后再试',
      failedMessage: '这一份项目分析没能生成，稍后再试',
    })
    if (!alive) return
    job.status = data?.status || 'completed'
    report.value = data?.report || null
    pageError.value = ''
  } catch (err) {
    if (!alive || err?.code === 'polling_stopped') return
    job.status = 'failed'
    pageError.value = userErrorCopy(err, '这一份项目分析没能生成，稍后再试')
  } finally {
    if (alive) job.loading = false
  }
}

async function startQuestions() {
  if (!report.value?.job_id || questionsJob.loading) return
  questionsJob.loading = true
  questionsError.value = ''
  try {
    const created = await createProjectQuestionsJob(report.value.job_id)
    questionsJob.id = created?.job_id ?? null
    const data = await questionsPoller.pollTask(questionsJob.id, {
      maxPollCount: QUESTIONS_MAX_ATTEMPTS,
      intervalMs: POLL_INTERVAL_MS,
      timeoutMessage: '这一轮的题目这次没出完，稍后再试',
      failedMessage: '这一轮的题目没能生成，可以再点一次',
    })
    if (data?.status !== 'completed') throw new Error('这一轮的题目没能生成，可以再点一次')
    // 回来之后重新读**父作业**那一份：装配只有一条路，前端不自己拼第二份文档。
    await runJob(report.value.job_id)
    ElMessage.success('面试准备已经接上这一份项目分析')
  } catch (err) {
    questionsError.value = userErrorCopy(err, '这一轮的题目没能生成，可以再点一次')
  } finally {
    if (alive) questionsJob.loading = false
  }
}

async function doDownload() {
  if (!report.value?.job_id || downloading.value) return
  downloading.value = true
  try {
    const blob = await downloadProjectReportHtml(report.value.job_id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `项目分析_${reportName.value}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (err) {
    pageError.value = userErrorCopy(err, '这份文件这次没能下载下来，稍后再试')
  } finally {
    downloading.value = false
  }
}

function backToCenter() {
  router.push('/resume/center')
}
</script>

<style scoped>
.pr-page {
  padding-bottom: 40px;
}
.pr-actions,
.pr-start-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pr-card {
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  padding: 20px 22px;
  margin-bottom: 16px;
  box-shadow: var(--app-shadow-soft);
}
.pr-h3,
.pr-ct {
  margin: 0 0 12px;
  color: var(--app-text);
}
.pr-h3 {
  font-size: 16px;
}
h3 {
  margin: 20px 0 8px;
  font-size: 15.5px;
  color: var(--app-text);
}
.pr-lead {
  color: var(--app-muted);
  font-size: 14px;
  margin: 6px 0 14px;
}
.pr-form {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 14px;
}
.pr-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 220px;
}
.pr-field-label {
  font-size: 13px;
  color: var(--app-muted);
}
.pr-loading {
  color: var(--app-warning);
  font-size: 13.5px;
}
.pr-nav {
  position: sticky;
  top: 0;
  z-index: 30;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  display: flex;
  gap: 4px;
  overflow-x: auto;
  margin-bottom: 14px;
  padding: 0 8px;
}
.pr-nav a {
  padding: 11px 13px;
  font-size: 13.5px;
  color: var(--app-muted);
  text-decoration: none;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
}
.pr-nav a.on {
  color: var(--app-primary);
  border-bottom-color: var(--app-primary);
  font-weight: 600;
}
.pr-redline {
  background: var(--app-accent-soft);
  border: 1px solid var(--app-line-strong);
  border-radius: var(--app-radius-sm);
  padding: 12px 15px;
  margin-bottom: 14px;
  color: var(--app-danger);
  font-size: 14px;
}
.pr-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.pr-pill {
  background: var(--app-score-good-soft);
  border: 1px solid var(--app-line);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--app-text);
}
.pr-pill b {
  color: var(--app-primary);
  margin-right: 6px;
}
.pr-table {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0 12px;
  font-size: 14px;
}
.pr-table th {
  background: var(--app-surface-muted);
  color: var(--app-text);
  text-align: left;
  padding: 8px 10px;
  border: 1px solid var(--app-line);
}
.pr-table td {
  padding: 8px 10px;
  border: 1px solid var(--app-line);
  vertical-align: top;
}
.pr-table tr.hot td {
  background: var(--app-accent-soft);
}
.pr-table tr.total td {
  background: var(--app-surface-muted);
  font-weight: 600;
}
.pr-table td.n,
.pr-table th.n {
  text-align: center;
  width: 64px;
}
.pr-paper {
  border: 1px solid var(--app-line-strong);
  border-radius: var(--app-radius-sm);
  padding: 12px 16px;
  background: var(--app-surface);
}
.pr-sl {
  margin: 12px 0 4px;
  font-size: 14px;
  color: var(--app-text);
}
.pr-vl,
.pr-paper p {
  margin: 4px 0;
}
.pr-muted {
  color: var(--app-muted);
}
.pr-note {
  font-size: 13px;
  color: var(--app-muted);
  margin: 6px 0;
}
.pr-concl {
  background: var(--app-score-good-soft);
  border-left: 3px solid var(--app-primary);
  padding: 9px 13px;
  border-radius: 0 var(--app-radius-sm) var(--app-radius-sm) 0;
  font-size: 14px;
  color: var(--app-text);
  margin: 10px 0;
}
.pr-ul {
  margin: 6px 0 10px;
  padding-left: 22px;
}
.pr-mine {
  color: var(--app-primary);
  font-weight: 700;
  font-size: 12.5px;
  margin-left: 6px;
}
.pr-flow {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}
.pr-node {
  flex: 1 1 180px;
  border: 1px solid var(--app-line-strong);
  border-radius: var(--app-radius-sm);
  padding: 9px 11px;
  background: var(--app-surface);
  font-size: 13.5px;
  color: var(--app-text);
}
.pr-exit {
  background: var(--app-score-good-soft);
  border-color: var(--app-primary);
}
.pr-lanes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}
.pr-lane {
  background: var(--app-score-good-soft);
  border: 1px solid var(--app-line-strong);
  border-radius: var(--app-radius-xs);
  padding: 3px 9px;
  font-size: 13px;
  color: var(--app-text);
}
.pr-usage {
  background: var(--app-surface-muted);
  border: 1px solid var(--app-line-strong);
  border-radius: var(--app-radius-sm);
  padding: 10px 14px;
  font-size: 13.5px;
  color: var(--app-text);
  margin-top: 14px;
}
.pr-qstat {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  background: var(--app-score-good-soft);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  padding: 8px 12px;
  margin-bottom: 12px;
}
.pr-q {
  border-top: 1px dashed var(--app-line-strong);
  padding-top: 14px;
  margin-top: 16px;
}
.pr-q:first-of-type {
  border-top: 0;
  padding-top: 0;
}
.pr-q-title {
  font-weight: 700;
  color: var(--app-text);
}
.pr-no {
  color: var(--app-primary);
}
.pr-kind {
  font-style: normal;
  font-size: 12.5px;
  color: var(--app-muted);
  font-weight: 400;
  margin-left: 6px;
}
.pr-lbl {
  font-weight: 700;
  font-size: 13.5px;
  color: var(--app-text);
  margin: 10px 0 3px;
}
.pr-lbl-z {
  font-weight: 700;
  font-size: 13px;
  color: var(--app-muted);
  margin-right: 6px;
}
.pr-dcards {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 6px 0;
}
.pr-dcard {
  flex: 1 1 150px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  padding: 7px 9px;
  font-size: 13px;
  background: var(--app-surface-strong);
  color: var(--app-text);
}
.pr-how {
  font-size: 13.5px;
  color: var(--app-muted);
}
.pr-st {
  display: inline-block;
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-success);
}
.pr-st.warn {
  color: var(--app-warning);
}
.pr-st.danger {
  color: var(--app-danger);
}
</style>
