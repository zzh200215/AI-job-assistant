<template>
  <div class="pf-page">
    <div class="pf-card">
      <h2 class="pf-ct">组合分析｜几个项目放在一起看</h2>
      <p class="pf-lead">
        这一份量的不是单个项目，也不是整份简历：把选中的几个项目叠在一起，
        看它们合起来像不像同一个人来应聘这一个岗位。
      </p>
      <div class="pf-form">
        <label class="pf-field">
          <span class="pf-field-label">简历</span>
          <el-select
            v-model="form.resumeId"
            :loading="optionsLoading"
            placeholder="选一份简历"
            @change="loadProjects"
          >
            <el-option v-for="r in resumes" :key="r.id" :label="resumeLabel(r)" :value="r.id" />
          </el-select>
        </label>
        <label class="pf-field">
          <span class="pf-field-label">目标岗位（可不选）</span>
          <el-select v-model="form.jdId" clearable placeholder="不选就按项目原文识别方向">
            <el-option v-for="jd in jdOptions" :key="jd.id" :label="jd.title" :value="jd.id" />
          </el-select>
        </label>
      </div>
      <div class="pf-pick">
        <span class="pf-field-label">放在一起看的项目（至少两个）</span>
        <el-checkbox-group v-model="form.indices">
          <el-checkbox v-for="p in projects" :key="p.index" :value="p.index">
            项目 {{ p.index + 1 }} · {{ p.name }}
          </el-checkbox>
        </el-checkbox-group>
        <p v-if="projects.length < 2" class="pf-loading">这一份简历里只有一个项目，凑不成组合。</p>
      </div>
      <div class="pf-actions">
        <el-button
          type="primary"
          :loading="job.loading"
          :disabled="!canStart"
          @click="startAnalysis"
        >
          开始分析
        </el-button>
        <el-button :disabled="!report || downloading" :loading="downloading" @click="doDownload">
          下载自包含 HTML
        </el-button>
        <el-button link @click="backToCenter">回简历中心</el-button>
      </div>
      <p v-if="pageError" class="pf-error">{{ pageError }}</p>
    </div>

    <nav v-if="visibleSections.length" class="pf-nav" aria-label="四大节点导航">
      <a
        v-for="item in visibleSections"
        :key="item.anchor"
        :href="`#${item.anchor}`"
        :class="{ on: activeAnchor === item.anchor }"
        >{{ item.label }}</a
      >
    </nav>

    <template v-if="report">
      <p class="pf-pills">
        <span class="pf-pill"><b>项目数</b>{{ report.project_count }} 个</span>
        <span class="pf-pill"><b>组合评分</b>{{ scoreText }}</span>
        <span class="pf-pill"><b>组合难度</b>{{ report.difficulty?.level || '未定级' }}</span>
        <span class="pf-pill"><b>单项目均分</b>{{ report.average_cell }}</span>
      </p>

      <section id="c-profile" class="pf-card">
        <h2 class="pf-ct">一、组合档案</h2>
        <div v-if="report.excluded" class="pf-redline">
          <p>{{ report.excluded_note }}</p>
          <ul>
            <li v-for="row in report.excluded_by" :key="row.key">
              <b>{{ row.label }}</b
              >——{{ row.quote }}
              <ProjectTodoText :text="row.why" />
            </li>
          </ul>
        </div>

        <h3>1.1 组合六维评分卡</h3>
        <table class="pf-tbl">
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
                <b>{{ row.score ?? '—' }}</b>
              </td>
              <td class="n">{{ row.full }}</td>
              <td>{{ bandOf(row) }}</td>
              <td>
                <ProjectTodoText v-if="row.note" :text="row.note" />
                <span v-else class="pf-muted">{{ NOTE_ABSENT }}</span>
              </td>
            </tr>
            <tr class="total">
              <td>合计</td>
              <td class="n">
                <b>{{ report.score_cell }}</b>
              </td>
              <td class="n">100</td>
              <td>{{ report.grade || (report.excluded ? '出局' : '—') }}</td>
              <td>{{ report.grade_desc || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="pf-concl">
          {{
            report.grade_scale
          }}。这一档说的是<b>这一组项目叠在一起</b>；这里的档位区间按组合口径切，
          同名的那一档与单项目报告里的不是同一个分数带。{{ THREE_RUBRICS_NOTE }}
        </p>

        <h3>1.2 项目横向对比</h3>
        <table class="pf-tbl">
          <thead>
            <tr>
              <th>对比项</th>
              <th v-for="p in report.projects" :key="p.project_index">{{ labelOf(p) }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in compareRows" :key="row.key">
              <td>
                <b>{{ row.label }}</b>
              </td>
              <td v-for="p in report.projects" :key="p.project_index">
                <ProjectTodoText :text="row.cells[String(p.project_index)] || '—'" />
              </td>
            </tr>
          </tbody>
        </table>

        <h3>1.3 组合能力覆盖矩阵</h3>
        <!-- 这一张表以前给列头与格子挂了 `.n`（不换行 + 居中），五个项目时它的最小内容宽度
             被五个"项目 N · 一长串项目名"钉死在 897px，容器窄于 900 就压出卡片 280px。
             表头改成可换行，外面再套一层滚动容器兜住更极端的情况。 -->
        <div class="pf-scroll">
          <table class="pf-tbl pf-matrix">
            <thead>
              <tr>
                <th>能力维度</th>
                <th v-for="p in report.projects" :key="p.project_index">
                  {{ labelOf(p) }}
                </th>
                <th>组合覆盖</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.capabilities" :key="row.key">
                <td>
                  <b>{{ row.label }}</b>
                </td>
                <td
                  v-for="p in report.projects"
                  :key="p.project_index"
                  class="cov"
                  :class="cellClass(row, p.project_index)"
                >
                  {{ markOf(row, p.project_index) }}
                </td>
                <td>{{ verdictText(row) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="pf-note">
          <span class="cov full">●</span> 重点覆盖&nbsp;<span class="cov part">○</span>
          部分覆盖&nbsp;空白 未覆盖。 「组合覆盖」那一列不是模型写的：由这一行的格子推出来。
        </p>

        <h3>1.4 整体风险提示</h3>
        <table class="pf-tbl">
          <thead>
            <tr>
              <th>风险点</th>
              <th>说明</th>
              <th>补齐建议</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.risks" :key="row.point">
              <td>
                <b>{{ row.point }}</b>
              </td>
              <td><ProjectTodoText :text="row.detail" /></td>
              <td><ProjectTodoText :text="row.fix" /></td>
            </tr>
          </tbody>
        </table>

        <h3>1.5 选中项目原文（逐字摘录，未作改写）</h3>
        <p class="pf-note">上面每一栏的说法都要能回到这几段字里；这一节一个字都不过模型。</p>
        <div v-for="p in report.projects" :key="p.project_index" class="pf-paper">
          <p class="pf-hd">
            <b>{{ labelOf(p) }}</b
            >（代号 {{ p.code }}）
          </p>
          <template v-for="section in p.sections" :key="section.label">
            <p class="pf-hd">{{ section.label }}</p>
            <p v-for="(line, i) in section.lines" :key="i" class="pf-vl">{{ line }}</p>
          </template>
        </div>
      </section>

      <section v-if="report.diagrams" id="c-diagrams" class="pf-card">
        <h2 class="pf-ct">二、组合图解</h2>

        <h3>2.1 组合能力覆盖矩阵</h3>
        <p class="pf-note">与 1.3 是同一批格子，这里只换一种画法。</p>
        <div class="pf-lanes">
          <div v-for="row in report.capabilities" :key="row.key" class="pf-covrow">
            <span class="pf-covname">{{ row.label }}</span>
            <span
              v-for="p in report.projects"
              :key="p.project_index"
              class="cov"
              :class="cellClass(row, p.project_index)"
              >{{ markOf(row, p.project_index) }}</span
            >
            <span class="pf-covtail">{{ verdictText(row) }}</span>
          </div>
        </div>

        <template v-if="report.diagrams.narrative">
          <h3>2.2 叙事主线</h3>
          <h4 class="pf-sl">{{ report.diagrams.narrative.title }}</h4>
          <div
            v-for="stage in report.diagrams.narrative.stages"
            :key="stage.project_index"
            class="pf-node"
          >
            <p class="pf-hd">
              <b>{{ stage.stage_name }}</b
              >｜{{ stage.label }}<span class="pf-code">{{ stage.code }}</span>
            </p>
            <ul>
              <li v-for="(point, i) in stage.points" :key="i"><ProjectTodoText :text="point" /></li>
            </ul>
            <p>核心问题：{{ stage.core_question }}</p>
            <p class="pf-muted">能力关键词：{{ stage.keywords }}</p>
          </div>
          <p class="pf-concl"><ProjectTodoText :text="report.diagrams.narrative.one_line" /></p>
        </template>

        <h3>2.3 技术栈复用与差异</h3>
        <p class="pf-note">这两栏由技术栈清单求交集算出来，模型只写下面那两段解读。</p>
        <div class="pf-lanes">
          <span class="pf-field-label">共用（出现在两个以上项目里）</span>
          <div v-if="report.diagrams.stack?.shared?.length" class="pf-chips">
            <span v-for="name in report.diagrams.stack.shared" :key="name" class="pf-chip">{{
              name
            }}</span>
          </div>
          <p v-else class="pf-muted">没有一个组件出现在两个以上项目里。</p>
        </div>
        <div
          v-for="(items, index) in report.diagrams.stack?.unique_by_index || {}"
          :key="index"
          class="pf-lanes"
        >
          <span class="pf-field-label">只在 {{ uniqueLabel(Number(index)) }} 里出现</span>
          <div class="pf-chips">
            <span v-for="name in items" :key="name" class="pf-chip grey">{{ name }}</span>
            <span v-if="!items.length" class="pf-muted">—</span>
          </div>
        </div>
        <p v-if="report.diagrams.reuse_read" class="pf-para">
          <b>共用栈说明什么：</b><ProjectTodoText :text="report.diagrams.reuse_read" />
        </p>
        <p v-if="report.diagrams.unique_read" class="pf-para">
          <b>差异栈说明什么：</b><ProjectTodoText :text="report.diagrams.unique_read" />
        </p>
        <p v-if="report.diagrams.sameness_answer" class="pf-concl">
          <b>回答「是不是换皮」：</b><ProjectTodoText :text="report.diagrams.sameness_answer" />
        </p>

        <template v-if="report.diagrams.rounds">
          <h3>2.4 跨项目面试时序</h3>
          <div v-for="row in report.diagrams.rounds" :key="row.key" class="pf-round">
            <p class="pf-hd">
              <b>{{ row.label }}</b
              ><span v-if="row.decisive" class="pf-star">胜负手</span>
            </p>
            <ProjectTodoText :text="row.text" />
          </div>
          <p v-if="report.diagrams.strategy" class="pf-concl">
            <b>准备策略：</b><ProjectTodoText :text="report.diagrams.strategy" />
          </p>
          <p v-if="report.diagrams.usage" class="pf-usage">
            <ProjectTodoText :text="report.diagrams.usage" />
          </p>
        </template>
      </section>

      <section v-if="report.advice" id="c-advice" class="pf-card">
        <h2 class="pf-ct">三、使用建议</h2>
        <h3>3.1 项目排列建议</h3>
        <table class="pf-tbl">
          <thead>
            <tr>
              <th>排列方式</th>
              <th>适用场景</th>
              <th>好处 / 风险</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in report.advice.arrangements" :key="row.rendered">
              <td>
                <b>{{ row.rendered }}</b
                ><span v-if="i === report.advice.default_index">（默认采用）</span>
              </td>
              <td><ProjectTodoText :text="row.scenario" /></td>
              <td>
                <ProjectTodoText :text="row.pros" />
                <span class="pf-muted">｜风险：</span><ProjectTodoText :text="row.cons" />
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="report.advice.default_reason" class="pf-concl">
          <ProjectTodoText :text="report.advice.default_reason" />
        </p>

        <h3>3.2 面试叙事建议</h3>
        <table class="pf-tbl">
          <thead>
            <tr>
              <th>被问</th>
              <th>怎么答</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.advice.asked_before" :key="row.asked">
              <td>
                <b>{{ row.asked }}</b>
              </td>
              <td><ProjectTodoText :text="row.answer" /></td>
            </tr>
          </tbody>
        </table>

        <h3>3.3 补强路径（组合层面）</h3>
        <table class="pf-tbl">
          <thead>
            <tr>
              <th>缺口</th>
              <th>补齐动作</th>
              <th>补齐后预计</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.advice.strengthen" :key="row.gap">
              <td>
                <b>{{ row.gap }}</b>
              </td>
              <td><ProjectTodoText :text="row.action" /></td>
              <td><ProjectTodoText :text="row.expected" /></td>
            </tr>
          </tbody>
        </table>

        <h3>3.4 引用红线（组合层面）</h3>
        <table class="pf-tbl">
          <tbody>
            <tr v-for="row in citationRows" :key="row[0]">
              <td>
                <b>{{ row[0] }}</b>
              </td>
              <td><ProjectTodoText :text="row[1]" /></td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="report.questions_state !== 'not_generated'" id="c-questions" class="pf-card">
        <h2 class="pf-ct">四、跨项目面试</h2>
        <p class="pf-note">只针对组合层面的追问；单个项目的深挖题在它们各自的项目分析里。</p>
        <p v-if="report.questions_state === 'deferred'" class="pf-concl">
          <ProjectTodoText :text="report.questions?.note" />
        </p>
        <template v-else>
          <p class="pf-qstat">{{ questionStatText }}</p>
          <div v-for="item in report.questions.questions" :key="item.no" class="pf-qst">
            <p class="pf-q">
              <span class="no">Q{{ item.no }}</span> · {{ item.question }}
              <em class="pf-kind">{{ item.kind }}</em>
            </p>
            <span class="pf-lbl">标准答案</span>
            <p class="pf-ans"><ProjectTodoText :text="item.answer" /></p>
            <p v-for="(follow, i) in item.followups" :key="i" class="pf-fu">
              <span class="pf-lbl fuk">{{ follow.kind }}</span
              ><ProjectTodoText :text="follow.text" />
            </p>
            <ul v-if="item.missing?.length" class="pf-miss">
              <li v-for="(line, i) in item.missing" :key="i"><ProjectTodoText :text="line" /></li>
            </ul>
            <p v-if="item.risk_ref" class="pf-how">对应 1.4 第 {{ item.risk_ref }} 条风险。</p>
            <span class="pf-st" :class="statusClass(item.status)">{{
              statusMark(item.status)
            }}</span>
          </div>
          <p class="pf-concl">题型分布：{{ kindText }}。</p>
        </template>
      </section>

      <div v-if="report.questions_state === 'not_generated' && !report.excluded" class="pf-card">
        <p class="pf-lead">
          第四节那 12 道跨项目的题要点按钮才跑——它要再花一发模型调用，没点就不花这笔钱。
        </p>
        <div class="pf-actions">
          <el-button type="primary" :loading="questionsJob.loading" @click="startQuestions">
            生成跨项目面试（12 题）
          </el-button>
        </div>
        <p v-if="questionsError" class="pf-error">{{ questionsError }}</p>
      </div>
      <p v-else-if="report.excluded" class="pf-note">
        这一份命中了一条一票否决，按口径不出跨项目的题。
      </p>
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
  createPortfolioQuestionsJob,
  createPortfolioReportJob,
  downloadPortfolioReportHtml,
  getPortfolioReportJob,
  getResume,
  getResumeList,
} from '@/api/resume'
import { getJDList } from '@/api/jd'
import ProjectTodoText from '../components/ProjectTodoText.vue'

/* 锚点与后端 `portfolio_report_html_lint.SECTIONS` 同一张表：两份交付物必须指向同一批 id。 */
const SECTIONS = [
  { anchor: 'c-profile', label: '一、组合档案' },
  { anchor: 'c-diagrams', label: '二、组合图解' },
  { anchor: 'c-advice', label: '三、使用建议' },
  { anchor: 'c-questions', label: '四、跨项目面试' },
]

/* 「这一栏空着」那句话与两份渲染器同一句权威（`report_html_lint.NOTE_ABSENT`）。 */
const NOTE_ABSENT = '本次分析没有为这一维写出待优化点'

/* 这句与两份下载 HTML、单项目那一页同一句权威（`report_html_lint.THREE_RUBRICS_NOTE`）。 */
const THREE_RUBRICS_NOTE =
  '树里有三把尺：整份简历那份七维、单个项目那份六维（含位次）、几个项目叠一起那份组合六维（含位次区间）。三把尺的分数不能直接比。'

/* 格子符号与后端 `portfolio_report_rubric.COVERAGE_MARKS` 同一张表。 */
const MARKS = { 重点覆盖: '●', 部分覆盖: '○', 未覆盖: '' }

/* 前三节三发模型调用：预算 = 报告那一族的 225 次 × 2 秒 × 2。第四节是一发长输出。 */
const POLL_INTERVAL_MS = 2000
const POLL_MAX_ATTEMPTS = 450
const QUESTIONS_MAX_ATTEMPTS = 225

const route = useRoute()
const router = useRouter()

const resumes = ref([])
const projects = ref([])
const jdOptions = ref([])
const optionsLoading = ref(false)
const form = reactive({ resumeId: null, indices: [], jdId: null })

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
    getAgentTask: (jobId) => getPortfolioReportJob(jobId),
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
    getAgentTask: (jobId) => getPortfolioReportJob(jobId),
    getAgentSteps: async () => ({ steps: [] }),
  },
  { rejectOnStop: true }
)

const compareRows = computed(() => report.value?.compare?.rows || [])
const citationRows = computed(() => {
  const c = report.value?.advice?.citation || {}
  return [
    ['✅ 可借鉴', c.borrow],
    ['⚠️ 需改造', c.adapt],
    ['🔴 一抄就穿', c.breaks],
  ]
})

const scoreText = computed(() => {
  const cell = report.value?.score_cell || '未评分'
  return cell === '不作数' || cell === '未评分' ? cell : `${cell}/100`
})

const questionStatText = computed(() => {
  const d = report.value?.questions?.distribution || {}
  return `共 ${d.total ?? 0} 题 · 可答 ${d.answerable ?? 0} · 需补强 ${d.weak ?? 0} · 高危 ${d.high_risk ?? 0}`
})

const kindText = computed(() => {
  const by = report.value?.questions?.distribution?.by_kind || {}
  return Object.entries(by)
    .map(([name, count]) => `${name} ${count}`)
    .join('、')
})

const visibleSections = computed(() => {
  const doc = report.value
  if (!doc) return []
  return SECTIONS.filter((item) => {
    if (item.anchor === 'c-diagrams') return !!doc.diagrams
    if (item.anchor === 'c-advice') return !!doc.advice
    if (item.anchor === 'c-questions') return doc.questions_state !== 'not_generated'
    return true
  })
})

const canStart = computed(
  () => form.resumeId && form.indices.length >= 2 && projects.value.length >= 2
)

function resumeLabel(r) {
  return r.name || r.file_name || `简历 #${r.id}`
}

function labelOf(p) {
  return `项目 ${Number(p.project_index) + 1} · ${p.name || `项目经历 ${Number(p.project_index) + 1}`}`
}

function uniqueLabel(index) {
  const p = (report.value?.projects || []).find((row) => Number(row.project_index) === index)
  return p ? labelOf(p) : `项目 ${index + 1}`
}

function isLow(row) {
  if (row.score === null || !row.full) return true
  return row.score / row.full <= 0.7
}

/* 位次那一格的落档写的是**占了第几位到哪几位**，不是这一维的得分。
   与渲染器同一条：拿分数当位次会打成"第 5 位"（D236 活页量出来的那一处错）。 */
function bandOf(row) {
  if (row.positional) {
    const span = row.span || []
    return span[0] === span[1] ? `第 ${span[0]} 位` : `第 ${span[0]}~${span[1]} 位`
  }
  if (row.score === null) return '未读出来'
  const ratio = row.full ? row.score / row.full : 0
  if (ratio >= 0.9) return '优'
  if (ratio >= 0.75) return '良'
  return ratio >= 0.6 ? '中' : '弱'
}

function cellOf(row, index) {
  return row.cells?.[index] ?? row.cells?.[String(index)] ?? '未覆盖'
}

function markOf(row, index) {
  return MARKS[cellOf(row, index)] || ''
}

function cellClass(row, index) {
  const cell = cellOf(row, index)
  return cell === '重点覆盖' ? 'full' : cell === '部分覆盖' ? 'part' : ''
}

function verdictText(row) {
  const v = row.verdict || {}
  return v.word ? `${v.word}（${v.detail}）` : '—'
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
    : (resumes.value[0]?.id ?? null)
  await loadProjects()
  optionsLoading.value = false
}

/**
 * 勾选表来自这份简历解析出来的项目条目。键名与后端 `project_report_service.project_entries`
 * 同一条：`project_experience` 优先、退回 `projects`——少那一半退路，那种简历在这里就是
 * "没有项目可勾"，而后端明明能算。默认全选：多数人要看的就是全部项目放在一起的样子。
 */
async function loadProjects() {
  projects.value = []
  form.indices = []
  if (!form.resumeId) return
  try {
    const detail = await getResume(form.resumeId)
    const parsed = detail?.parsed || {}
    const raw = Array.isArray(parsed.project_experience)
      ? parsed.project_experience
      : Array.isArray(parsed.projects)
        ? parsed.projects
        : []
    projects.value = raw
      .filter((row) => row && typeof row === 'object')
      .map((row, index) => ({ index, name: row.name || `项目经历 ${index + 1}` }))
    form.indices = projects.value.map((row) => row.index)
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
    const created = await createPortfolioReportJob(form.resumeId, {
      project_indices: [...form.indices].sort((a, b) => a - b),
      jd_id: form.jdId || null,
    })
    job.id = created?.job_id ?? null
    if (job.id) rememberJobInQuery(job.id)
    await runJob(job.id, created?.status)
  } catch (err) {
    if (!alive) return
    job.status = 'failed'
    pageError.value = userErrorCopy(err, '这一份组合分析没能生成，稍后再试')
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
      timeoutMessage: '这一份组合分析这次没跑完，稍后再试',
      failedMessage: '这一份组合分析没能生成，稍后再试',
    })
    if (!alive) return
    job.status = data?.status || 'completed'
    report.value = data?.report || null
    pageError.value = ''
  } catch (err) {
    if (!alive || err?.code === 'polling_stopped') return
    job.status = 'failed'
    pageError.value = userErrorCopy(err, '这一份组合分析没能生成，稍后再试')
  } finally {
    if (alive) job.loading = false
  }
}

async function startQuestions() {
  if (!report.value?.job_id || questionsJob.loading) return
  questionsJob.loading = true
  questionsError.value = ''
  try {
    const created = await createPortfolioQuestionsJob(report.value.job_id)
    questionsJob.id = created?.job_id ?? null
    const data = await questionsPoller.pollTask(questionsJob.id, {
      maxPollCount: QUESTIONS_MAX_ATTEMPTS,
      intervalMs: POLL_INTERVAL_MS,
      timeoutMessage: '这一轮的跨项目题这次没出完，稍后再试',
      failedMessage: '这一轮的跨项目题没能生成，可以再点一次',
    })
    if (data?.status !== 'completed') throw new Error('这一轮的跨项目题没能生成，可以再点一次')
    // 回来之后重新读**父作业**那一份：装配只有一条路，前端不自己拼第二份文档。
    await runJob(report.value.job_id)
    ElMessage.success('跨项目面试已经接上这一份组合分析')
  } catch (err) {
    questionsError.value = userErrorCopy(err, '这一轮的跨项目题没能生成，可以再点一次')
  } finally {
    if (alive) questionsJob.loading = false
  }
}

async function doDownload() {
  if (!report.value?.job_id || downloading.value) return
  downloading.value = true
  try {
    const blob = await downloadPortfolioReportHtml(report.value.job_id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `组合分析_${report.value.project_count}个项目.html`
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
.pf-page {
  padding-bottom: 40px;
}
.pf-card {
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  padding: 20px 22px;
  margin-bottom: 16px;
  box-shadow: var(--app-shadow-soft);
}
.pf-ct {
  margin: 0 0 12px;
  color: var(--app-text);
  font-size: 18px;
}
h3 {
  margin: 20px 0 8px;
  font-size: 15.5px;
  color: var(--app-text);
}
.pf-sl {
  margin: 12px 0 4px;
  font-size: 14px;
  color: var(--app-text);
}
.pf-lead {
  color: var(--app-muted);
  font-size: 14px;
  margin: 6px 0 14px;
}
.pf-form,
.pf-actions,
.pf-pick {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}
.pf-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 220px;
}
.pf-field-label {
  font-size: 13px;
  color: var(--app-muted);
}
.pf-loading,
.pf-error {
  color: var(--app-danger);
  font-size: 13.5px;
  margin: 6px 0;
}
.pf-nav {
  position: sticky;
  top: 0;
  z-index: 30;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  display: flex;
  gap: 4px;
  overflow-x: auto;
  padding: 0 8px;
  margin-bottom: 14px;
}
.pf-nav a {
  padding: 11px 13px;
  font-size: 13.5px;
  color: var(--app-muted);
  text-decoration: none;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
}
.pf-nav a.on {
  color: var(--app-accent);
  border-bottom-color: var(--app-accent);
  font-weight: 600;
}
.pf-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 14px;
}
.pf-pill {
  background: var(--app-surface-soft);
  border: 1px solid var(--app-line);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--app-muted);
}
.pf-pill b {
  color: var(--app-text);
  margin-right: 6px;
}
.pf-tbl {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0 12px;
  font-size: 14px;
}
.pf-tbl th {
  background: var(--app-surface-soft);
  color: var(--app-text);
  text-align: left;
  font-weight: 600;
  padding: 8px 10px;
  border: 1px solid var(--app-line);
}
.pf-tbl td {
  padding: 8px 10px;
  border: 1px solid var(--app-line);
  vertical-align: top;
}
.pf-tbl tr.hot td {
  background: var(--app-danger-soft);
}
.pf-tbl tr.total td {
  background: var(--app-surface-soft);
  font-weight: 600;
}
.pf-tbl td.n,
.pf-tbl th.n {
  text-align: center;
  white-space: nowrap;
}
.cov {
  font-weight: 700;
  /* 居中以前是 `.n` 顺手给的，撤掉那个类就得自己说——格子还是不能左对齐。 */
  text-align: center;
}
.pf-scroll {
  /* 表格压不下去时宁可让它在这层里横向滚，别把卡片撑破、把整页顶出滚动条。 */
  overflow-x: auto;
}
.cov.full {
  color: var(--app-accent);
}
.cov.part {
  color: var(--app-muted);
}
.pf-covrow {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  padding: 6px 10px;
  margin-bottom: 6px;
  background: var(--app-surface-soft);
}
.pf-covname {
  flex: 1 1 180px;
  font-weight: 600;
  color: var(--app-text);
}
.pf-covtail {
  color: var(--app-muted);
  font-size: 13.5px;
}
.pf-redline {
  background: var(--app-danger-soft);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  padding: 12px 15px;
  margin: 10px 0 14px;
  font-size: 14px;
  color: var(--app-danger);
}
.pf-paper {
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  padding: 12px 16px;
  background: var(--app-surface-soft);
  margin: 6px 0 14px;
}
.pf-hd {
  margin: 6px 0 2px;
  font-size: 13px;
  color: var(--app-text);
}
.pf-vl {
  margin: 4px 0;
  color: var(--app-muted);
  font-size: 13.5px;
}
.pf-note {
  font-size: 13px;
  color: var(--app-muted);
  margin: 6px 0;
}
.pf-concl {
  background: var(--app-surface-soft);
  border-left: 3px solid var(--app-accent);
  padding: 9px 13px;
  border-radius: 0 var(--app-radius-sm) var(--app-radius-sm) 0;
  font-size: 14px;
  color: var(--app-text);
  margin: 10px 0;
}
.pf-para {
  margin: 6px 0 10px;
  font-size: 14px;
}
.pf-usage {
  background: var(--app-warning-soft);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  padding: 10px 14px;
  font-size: 13.5px;
  color: var(--app-text);
  margin-top: 14px;
}
.pf-muted {
  color: var(--app-muted);
}
.pf-node {
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  padding: 9px 11px;
  background: var(--app-surface-soft);
  font-size: 13.5px;
  color: var(--app-text);
  margin-bottom: 8px;
}
.pf-node ul {
  margin: 4px 0 6px;
  padding-left: 20px;
}
.pf-code {
  float: right;
  font-size: 12px;
  color: var(--app-muted);
}
.pf-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pf-chip {
  background: var(--app-surface-soft);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  padding: 3px 9px;
  font-size: 13px;
  color: var(--app-text);
}
.pf-chip.grey {
  color: var(--app-muted);
}
.pf-lanes {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 8px 0;
}
.pf-round {
  border-top: 1px dashed var(--app-line);
  padding-top: 8px;
  margin-top: 8px;
}
.pf-star {
  display: inline-block;
  margin-left: 8px;
  font-size: 12px;
  color: var(--app-danger);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  padding: 0 6px;
}
.pf-qstat {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  background: var(--app-surface-soft);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  padding: 8px 12px;
  margin-bottom: 12px;
}
.pf-qst {
  border-top: 1px dashed var(--app-line);
  padding-top: 14px;
  margin-top: 14px;
}
.pf-q {
  font-weight: 700;
  color: var(--app-text);
}
.pf-q .no {
  color: var(--app-accent);
}
.pf-kind {
  font-style: normal;
  font-size: 12.5px;
  color: var(--app-muted);
  font-weight: 400;
  margin-left: 6px;
}
.pf-lbl {
  display: block;
  font-weight: 700;
  font-size: 13.5px;
  color: var(--app-text);
  margin: 10px 0 3px;
}
.pf-lbl.fuk {
  color: var(--app-accent);
}
.pf-ans,
.pf-fu {
  margin: 4px 0;
  font-size: 14px;
}
.pf-miss {
  margin: 6px 0;
  padding-left: 22px;
}
.pf-st {
  display: inline-block;
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-success);
}
.pf-st.warn {
  color: var(--app-warning);
}
.pf-st.danger {
  color: var(--app-danger);
}
.pf-how {
  font-size: 13.5px;
  color: var(--app-muted);
  margin-top: 6px;
}
</style>
