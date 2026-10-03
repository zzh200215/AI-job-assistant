/* 浏览器探针的驱动模块：把共享 axios 实例换成夹具，让页面**不需要真后端**也能带数据画出来，
   然后提供 D67/D68 那套判据：`删掉这条规则 → 比全页计算属性 + rect → 塞回原位`。
   用法（在浏览器里）：
     await __probe.go('/knowledge')
     await __probe.audit({ selector: '.page-shell', scope: 'abcd1234' })
     // D85：规则已经不在源码里时，先注回去再测（正向对照要的就是这条能力）
     const P = __probe.scopeOf('InterviewRoom')
     __probe.injectRule({ selector: '.interview-room-page .stage-card', scope: P, decls: 'border-top: 3px solid var(--app-cyan)' })
     await __probe.audit({ selector: '.interview-room-page .stage-card', scope: P })
     __probe.dropRule('.interview-room-page .stage-card', P)
   scope 是那一页自己的 `__scopeId`（`__probe.scopes()` 列出全部），不靠猜构建哈希。
   判据与限制写在 docs/upgrade-plan.md D76 / D79 / D85。 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '../src/App.vue'
import router from '../src/router'
import { installElement } from '../src/plugins/element'
import request from '../src/api/request'
/* 跨页"上一次选择"的键格式由 utils/lastSelection 持有，探针不自己拼键名：
   它要的是"这一页带着上一次的选择进来"，否则 SmartAnalysis 的 `v-if="result"`（:272）
   不成立，五个标签页面板根本不挂载——D76 那 9 条子组件副本判不了就是卡在这里。 */
import {
  rememberJD,
  rememberRecord,
  rememberResume,
  setSelectionOwner,
} from '../src/utils/lastSelection'
import { clearSession, writeSession } from '../src/utils/session'
import '../src/plugins/element.css'
import '../src/styles/main.css'
import '../src/styles/panels.css'

import JobSearch from '../src/features/jobs/views/JobSearch.vue'
import JobRecommend from '../src/features/jobs/views/JobRecommend.vue'
import TaskCenter from '../src/features/shell/views/TaskCenter.vue'
import RecommendationEval from '../src/features/eval/views/RecommendationEval.vue'
import SmartAnalysis from '../src/features/analysis/views/SmartAnalysis.vue'
import SkillsPane from '../src/features/analysis/components/SkillsPane.vue'
import ReferencesPane from '../src/features/analysis/components/ReferencesPane.vue'
import InterviewQuestionsPane from '../src/features/analysis/components/InterviewQuestionsPane.vue'
import ReportSummaryPane from '../src/features/analysis/components/ReportSummaryPane.vue'
import ResumeOptimizePane from '../src/features/analysis/components/ResumeOptimizePane.vue'
import Home from '../src/features/shell/views/Home.vue'
import KnowledgeBase from '../src/features/knowledge/views/KnowledgeBase.vue'
import DeliveryGuide from '../src/features/shell/views/DeliveryGuide.vue'
import SystemStatus from '../src/features/admin/views/SystemStatus.vue'
import DefaultLayout from '../src/layouts/DefaultLayout.vue'
/* D85：D67/D68 那两轮唯一没回头核的一笔——三条 `matched=1` 的规则（打在子组件根元素上的
   `.interview-room-page .stage-card` / `.question-card` / `.interviewer-avatar` /
   `.structure-box` / `.user-shell`）当时是用一次性 harness 判的，而那台 harness 的属性读法无法确认
   是否瞎（D79 之后才知道"只改颜色"的删除会被报成 0 差异）。要核它得先让这一屏画出来，
   所以这四块面板也进组件表：父 scope 用来注入"当时被删的那份"，子 scope 用来测"现在还在画的那份"。 */
import InterviewRoom from '../src/features/interview/views/InterviewRoom.vue'
import StagePane from '../src/features/interview/components/StagePane.vue'
import QuestionPane from '../src/features/interview/components/QuestionPane.vue'
import TranscriptPane from '../src/features/interview/components/TranscriptPane.vue'

const COMPONENTS = {
  JobSearch,
  JobRecommend,
  TaskCenter,
  RecommendationEval,
  SmartAnalysis,
  SkillsPane,
  ReferencesPane,
  InterviewQuestionsPane,
  ReportSummaryPane,
  ResumeOptimizePane,
  Home,
  KnowledgeBase,
  DeliveryGuide,
  SystemStatus,
  DefaultLayout,
  InterviewRoom,
  StagePane,
  QuestionPane,
  TranscriptPane,
}

/* ---------- 夹具：形状抄自单测，只给"页面要走到那一屏"所需的最小量 ---------- */
const ANALYSIS_RECORD = {
  id: 99,
  record_id: 99,
  match_score: 76,
  matched_skills: ['Go', 'K8s'],
  missing_skills: ['Rust'],
  match_report: {
    recommendation: '可以投递',
    summary: '整体匹配',
    dimension_scores: { skills: 0.72, experience: { score: 0.5 }, education: 3, industry: {} },
    skill_match: { missing_required: ['Rust'], missing_nice: ['Docker'] },
    strengths: [{ item: '后端经验', impact: '高', evidence: '三年' }],
    gaps: [{ item: '云原生', action: '补 K8s 实战', severity: '中' }],
    risk_points: ['样本量小'],
    interview_questions: { basic: [{ q: '为什么', intent: '动机' }], advanced: [] },
  },
  career_planning: {
    summary: '往平台方向走',
    directions: [
      { title: '平台工程师', category: '高度匹配', match_score: 78, gap_skills: ['K8s'] },
    ],
    salary_range: { p25: 25, p50: 30, p75: 40 },
    skill_gaps: [{ name: 'K8s', severity: '高' }],
    learning_resources: [{ title: 'K8s 实战', url: '#', type: 'course' }],
    milestones: [{ name: '三个月内跑通一次部署', type: 'milestone' }],
    visual_roadmap: {
      total_duration_months: 9,
      phases: [
        {
          id: 'p1',
          name: '补基本功',
          order: 1,
          color: 'blue',
          duration_months: 3,
          skills: ['K8s'],
        },
      ],
    },
  },
  created_at: '2026-09-30T02:00:00Z',
}

const FIXTURES = [
  [/\/auth\/me$/, 'get', { id: 1, username: 'probe', role: 'candidate', nickname: '探针' }],
  [/\/resume\/?(\?|$)/, 'get', [{ id: 1, title: '探针简历', created_at: '2026-09-01' }]],
  [/\/resume\/\d+$/, 'get', { id: 1, title: '探针简历', parsed_json: { basics: {} } }],
  [/\/jd\/?(\?|$)/, 'get', [{ id: 7, title: '平台工程师', company: '示例' }]],
  /* §10.17 要量的那一张卡（`JobCompareDialog` 的 `.compare-card`）只在对比弹窗里存在，而弹窗要
     先在搜索结果里勾满两个岗位。这一族原先一条夹具都没有，所以 `matched=0` 是**假阴性**（D76 那个坑的
     第三种形态：不是状态没点开，是数据源就没喂）。形状按 `useJobSearch.js:136-141` 读的键给。 */
  [
    /\/jobs\/search-external/,
    'post',
    {
      jobs: [
        {
          id: 501,
          title: '平台后端',
          company: '示例科技',
          location: '上海',
          salary_range: '25-40K',
          skill_tags: ['Python', 'Go'],
          source: 'api',
        },
        {
          id: 502,
          title: '前端架构',
          company: '示例网络',
          location: '上海',
          salary_range: '30-50K',
          skill_tags: ['Vue', 'TypeScript'],
          source: 'api',
        },
      ],
      saved_count: 2,
      is_demo: false,
    },
  ],
  [/\/jobs\/cities/, 'get', { cities: ['上海', '北京'], provinces: [] }],
  [/\/jobs\/pipeline\/list/, 'get', { items: [], total: 0 }],
  [/\/jobs\/bookmarks\/list/, 'get', { items: [], total: 0 }],
  [/\/analysis\/records(\?|$)/, 'get', { items: [ANALYSIS_RECORD], total: 1 }],
  [/\/analysis\/\d+$/, 'get', ANALYSIS_RECORD],
  [/\/analysis\/list(\?|$)/, 'get', { items: [ANALYSIS_RECORD], total: 1 }],
  /* 面板只有在**跑完一轮分析**之后才挂载：`result` 只在 SmartAnalysis.vue:749 置上，
     onMounted 只恢复上一次选择、不读记录。所以这条链要三条夹具（启动 → 轮询 completed → 取记录），
     外加解释与引用那两条，否则标签页根本不存在，matched=0 就又是一次假阴性（D76 的坑第二次）。 */
  [/\/analysis\/full/, 'post', { task_id: 'probe-task' }],
  [/\/agent\/task\/probe-task\/steps/, 'get', { steps: [], items: [] }],
  [
    /\/agent\/task\/probe-task/,
    'get',
    {
      status: 'completed',
      task_status: 'completed',
      analysis_record_id: 99,
    },
  ],
  [
    /\/analysis\/explain-match/,
    'post',
    {
      explain_mode: 'rules',
      recommendation: '可以投递',
      overall_reason: '技能命中两条',
      dimension_explain: [],
    },
  ],
  [
    /* 引用来源：消费者是 useAnalysisReferences.js:37-41，读的是 `data.references` /
       `data.query` / `data.rag_confidence`。第一版给的是 documents + confidence，
       面板会拿到空数组——D76 那条"形状要照消费者写"在这里第二次差点成立。 */
    /\/analysis\/\d+\/references/,
    'get',
    {
      query: 'K8s 怎么落地',
      references: [
        {
          doc_title: '云原生笔记',
          doc_type: 'guide',
          chunks: [{ text: '一次部署的三步', score: 0.71 }],
        },
      ],
      rag_confidence: { level: 'high', score: 0.82 },
    },
  ],
  [
    /\/knowledge\/list/,
    'get',
    { items: [{ id: 3, title: '探针文档', doc_type: 'guide', status: 'ready' }], total: 1 },
  ],
  [/\/knowledge\/\d+\/chunks/, 'get', { items: [{ id: 1, content: '片段', seq: 0 }] }],
  [
    /\/knowledge\/stats|\/knowledge\/.*stats/,
    'get',
    {
      total_calls: 12,
      total_texts: 30,
      cache_hits: 10,
      cache_misses: 2,
      network_batches: 1,
      cache_hit_rate: 0.83,
      provider_totals: { qwen: 12 },
      model_totals: { 'qwen-plus': 12 },
      last_call_at: '2026-10-01T00:00:00Z',
      daily_trend: [{ date: '2026-10-01', calls: 12 }],
    },
  ],
  [
    /\/dashboard\/overview/,
    'get',
    {
      user: {
        id: 1,
        username: 'probe',
        nickname: '探针',
        avatar_url: '',
        job_seeking_status: 'open',
      },
      summary: {
        total_applications: 8,
        active_applications: 5,
        upcoming_interviews: 1,
        pending_offers: 1,
        total_resumes: 2,
        total_interviews: 3,
        bookmarked_jobs: 4,
        unread_notifications: 0,
        avg_match_score: 76,
      },
      weekly_new: 3,
      monthly_new: 9,
      stage_counts: { todo: 2, applied: 3, interview: 1, offer: 1, accepted: 0, rejected: 1 },
      funnel: { todo: 2, applied: 3, written_test: 0, interview: 1, offer: 1 },
      trend: [
        { date: '2026-09-25', count: 1 },
        { date: '2026-09-26', count: 2 },
        { date: '2026-09-27', count: 0 },
        { date: '2026-09-28', count: 3 },
        { date: '2026-09-29', count: 1 },
        { date: '2026-09-30', count: 2 },
        { date: '2026-10-01', count: 4 },
      ],
      recent_activities: [
        { id: 1, type: 'apply', title: '投递 平台工程师', create_time: '2026-10-01' },
      ],
    },
  ],
  [
    /\/dashboard\/today-tasks/,
    'get',
    /* 形状要照消费者写：Home 的循环是 `v-for="task in tasks.tasks"`（Home.vue:124）。
       第一版给的是 `{ items: [...] }`，任务列表整块没画出来，于是 `.dot-high` 的 matched=0
       是夹具骗人而不是规则死了（D76 那次假阴性）。三档优先级各给一条。 */
    {
      tasks: [
        { title: '跟进一处投递', subtitle: '已投 4 天', priority: 'high', link: '/pipeline' },
        { title: '补一份定制简历', subtitle: '差 K8s', priority: 'medium', link: '/resume' },
        { title: '看一次周报', subtitle: '上周', priority: 'low', link: '/weekly-report' },
      ],
    },
  ],
  [
    /\/dashboard\/next-actions/,
    'get',
    { mode: 'rules', items: [{ text: '补一份定制简历', why: '差 K8s' }] },
  ],
  [/\/dashboard\/weekly-report/, 'get', { generated_at: '2026-09-28', sections: [] }],
  [
    /\/tasks(\?|$)/,
    'get',
    { items: [{ id: 4, task_status: 'running', status: 'running', name: '深度分析' }] },
  ],
  [
    /\/agent\/tasks/,
    'get',
    /* 六档状态各一条，让 `dot-<status>` 这一族的每一档都真能被画到 ——
       守卫只保证"域 ↔ 规则"对齐，这条夹具保证"规则 ↔ 屏幕"可测（D77 的教训）。
       status / task_status 两个键名一起给：后端 `to_dict()` 与前端读取过的那份不同名。 */
    {
      items: [
        { id: 1, name: '待跑的深度分析', status: 'pending', task_status: 'pending' },
        { id: 2, name: '在跑的深度分析', status: 'running', task_status: 'running' },
        { id: 3, name: '跑完的深度分析', status: 'completed', task_status: 'completed' },
        { id: 4, name: '部分完成的分析', status: 'partial', task_status: 'partial' },
        { id: 5, name: '失败的解析', status: 'failed', task_status: 'failed' },
        { id: 6, name: '取消的解析', status: 'cancelled', task_status: 'cancelled' },
      ],
      total: 6,
    },
  ],
  [
    /\/system\/status/,
    'get',
    { services: [{ name: 'api', ok: true }], queue: { depth: 0, workers: 2 } },
  ],
  [/\/system\/metrics/, 'get', { counters: {}, queues: [] }],
  /* 面试房间（D85 的正向对照要这一屏）。形状全部照消费者写：
     - `store.hydrateSession(detail)`（stores/interview.js:110-134）读 status / total_questions /
       messages / evaluation / evaluation_status / memory_snapshot / answered_count；
     - `startWS` 第一行是 `Number(session.value?.id) === Number(sessionId)`，**id 与路由参数不一致
       就把刚灌进去的整块状态清掉**，所以这里必须是 12，与 `go('/interview/room/12')` 对齐；
     - `.user-shell` 那一支的条件是 `msg.type === 'answer'`（TranscriptPane.vue:27），不是 'user'；
     - status 不能给 'completed'，否则 onMounted 直接 replace 去报告页（InterviewRoom.vue:266-268）。
     WS 那一发在探针里没有后端，会连不上——它只改 status/按钮禁用，不影响这一族类名的元素是否存在，
     所以测量不依赖它（真要测 WS 态得另说）。 */
  [
    /\/interview\/sessions\/\d+$/,
    'get',
    {
      id: 12,
      status: 'ongoing',
      interview_type: 'tech',
      total_questions: 5,
      answered_count: 1,
      evaluation_status: 'idle',
      memory_snapshot: {},
      questions: [{ id: 1, text: '介绍一下你做过的服务', category: 'project' }],
      messages: [
        {
          id: 1,
          type: 'question',
          content: '介绍一下你做过的服务',
          round: 1,
          metadata: { category: 'project' },
        },
        { id: 2, type: 'answer', content: '我负责过一个招聘分析服务', round: 1, metadata: {} },
      ],
      evaluation: null,
    },
  ],
]

request.defaults.adapter = async (config) => {
  const method = String(config.method || 'get').toLowerCase()
  const url = String(config.url || '')
  const hit = FIXTURES.find(([re, m]) => re.test(url) && m === method)
  const data = hit ? hit[2] : {}
  return {
    data: { code: 0, message: 'ok', data },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  }
}

/* 上一次的选择：uid 与夹具里的 user.id 一致（1），简历/JD/记录 id 与 FIXTURES 对得上。 */
setSelectionOwner(1)
rememberResume(1)
rememberJD(7)
rememberRecord(99)

/* ---------- 快照与判据 ---------- */
const PROPS = [
  'color',
  'backgroundColor',
  'backgroundImage',
  'opacity',
  'visibility',
  'display',
  'position',
  'top',
  'left',
  'right',
  'bottom',
  'zIndex',
  'width',
  'height',
  'margin',
  'marginTop',
  'marginRight',
  'marginBottom',
  'marginLeft',
  'padding',
  'paddingTop',
  'paddingRight',
  'paddingBottom',
  'paddingLeft',
  'borderTopWidth',
  'borderRightWidth',
  'borderBottomWidth',
  'borderLeftWidth',
  'borderTopColor',
  'borderRightColor',
  'borderBottomColor',
  'borderLeftColor',
  'borderTopLeftRadius',
  'borderBottomRightRadius',
  'fontSize',
  'fontWeight',
  'lineHeight',
  'letterSpacing',
  'textAlign',
  'flexDirection',
  'justifyContent',
  'alignItems',
  'gap',
  'overflow',
  'boxShadow',
  'textDecorationLine',
]

const FREEZE = '*,*::before,*::after{animation:none!important;transition:none!important}'

/** scope 有两种写法：`__scopeId` 给的是 `data-v-xxxx`（`scopes()` 原样返回），手写调用时常只给 `xxxx`。
 *  拼两次前缀会得到 `[data-v-data-v-xxxx]`，匹配 0 个元素、0 条规则，而**任何一条判据都会安静地
 *  把它当成"这条规则没在画"**——与 D79 那条瞎快照同一类仪器错，所以在源头归一，不在调用方绕。 */
const bare = (scope) => String(scope || '').replace(/^data-v-/, '')
const markOf = (scope) => `[data-v-${bare(scope)}]`

function norm(text) {
  return String(text).replace(/\s+/g, ' ').trim()
}

function elements() {
  return Array.from(document.querySelectorAll('#app *'))
}

function snapshot() {
  const out = []
  for (const el of elements()) {
    const cs = getComputedStyle(el)
    const r = el.getBoundingClientRect()
    const row = [r.x.toFixed(1), r.y.toFixed(1), r.width.toFixed(1), r.height.toFixed(1)]
    // 必须用 camel 索引：getPropertyValue() 要 kebab-case，而 PROPS 是 camelCase，
    // 于是 backgroundColor / borderTopWidth 那一整批在快照里一直是空串 ——
    // "只改颜色"的删除会被报成 0 差异。D79 撞见的正是这个。
    for (const p of PROPS) row.push(String(cs[p] ?? ''))
    out.push(row.join('|'))
  }
  return out
}

function diffCount(a, b) {
  if (a.length !== b.length) return Math.abs(a.length - b.length) + 1e6
  let n = 0
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) n++
  return n
}

/** 找到"属于某个 scopeId 的那条规则"。传 selector（不含 scope 属性），
 *  编译后会变成 `<selector>[data-v-xxx]`；按**精确相等**比，避免 `.rag-metric` 误命中 `.rag-metric span`。 */
function locate(selector, scopeId) {
  const mark = markOf(scopeId)
  const want = norm(`${selector}${mark}`)
  for (const sheet of Array.from(document.styleSheets)) {
    let rules
    try {
      rules = sheet.cssRules
    } catch {
      continue
    }
    for (let i = 0; i < rules.length; i++) {
      const rule = rules[i]
      if (!rule || !rule.selectorText) continue
      if (norm(rule.selectorText) === want) return { sheet, index: i, text: rule.cssText }
    }
  }
  return null
}

/** 同一条规则在文档里出现几张表 —— vite dev 的 HMR 会把改过的样式块**再注一份**而不撤旧的，
 *  这时"删掉一处、看不出变化"是重复造成的，不是规则死的证据。D79 量 `.dot-partial` 就是这么撞出来的。 */
function copies(selector, scopeId) {
  const want = norm(`${selector}${markOf(scopeId)}`)
  let n = 0
  let first = null
  for (const sheet of Array.from(document.styleSheets)) {
    let rules
    try {
      rules = sheet.cssRules
    } catch {
      continue
    }
    for (let i = 0; i < rules.length; i++) {
      const rule = rules[i]
      if (rule && rule.selectorText && norm(rule.selectorText) === want) {
        n++
        if (!first) first = { sheet, index: i, text: rule.cssText }
      }
    }
  }
  return { n, first }
}

const probe = {
  props: PROPS.length,
  copiesOf: (selector, scope) => copies(selector, scope).n,
  scopes() {
    return Object.fromEntries(
      Object.entries(COMPONENTS).map(([k, v]) => [k, v && v.__scopeId ? v.__scopeId : null])
    )
  },
  scopeOf(name) {
    const id = COMPONENTS[name] && COMPONENTS[name].__scopeId
    if (!id) throw new Error(`${name} 不在组件表里，或它没有 scoped 样式块`)
    return id
  },
  routes: () => router.getRoutes().map((r) => ({ path: r.path, name: r.name || null })),
  async go(target) {
    const to =
      typeof target === 'string' && target.startsWith('name:') ? { name: target.slice(5) } : target
    if (!document.getElementById('probe-frozen')) {
      const s = document.createElement('style')
      s.id = 'probe-frozen'
      s.textContent = FREEZE
      document.head.appendChild(s)
    }
    await router.replace(to)
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
    await new Promise((r) => setTimeout(r, 250))
    return { path: router.currentRoute.value.fullPath, elements: elements().length }
  },
  /** 铺开这一屏里所有"要点一下才出现"的状态：面板标签页与展开项。 */
  async clickTexts(texts) {
    const out = []
    for (const text of texts) {
      const el = elements().find((e) => (e.textContent || '').trim() === text)
      if (!el) {
        out.push(`${text}: 找不到`)
        continue
      }
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }))
      await new Promise((r) => setTimeout(r, 180))
      out.push(`${text}: ok`)
    }
    return out
  },
  /** 只数不删：这条"带 scope 的选择器"在屏幕上有没有元素（D85 要先确认父侧那份副本确实没了）。 */
  matchedCount(selector, scope) {
    return document.querySelectorAll(norm(`${selector}${markOf(scope)}`)).length
  },
  /** 注回一条"当时被删掉的副本"。D68 那三条 `matched=1` 判完之后规则就不在源码里了，
   *  要做正向对照只能往**活样式表**里造一条同选择器、同 scope 属性的。
   *  落点选"拥有该 scope 的那张表"的表尾：同特异性时后写的赢，而父页的样式表在子面板之后
   *  （视图 import 面板，面板的 style 先注），所以变异那一条真能改到屏幕，而不是被后写的对手压掉。 */
  injectRule({ selector, scope, decls }) {
    const mark = markOf(scope)
    const text = norm(`${selector}${mark} { ${decls} }`)
    for (const sheet of Array.from(document.styleSheets)) {
      let rules
      try {
        rules = sheet.cssRules
      } catch {
        continue
      }
      const owns = Array.from(rules).some(
        (r) => r && r.selectorText && r.selectorText.includes(mark)
      )
      if (owns) {
        sheet.insertRule(text, rules.length)
        return text
      }
    }
    throw new Error(`没有一张表带 ${mark}，injectRule 不知道该注到哪`)
  },
  /** 按**精确选择器**删掉注入过的那条（可重复调用，返回删了几条）。 */
  dropRule(selector, scope) {
    const want = norm(`${selector}${markOf(scope)}`)
    let n = 0
    for (const sheet of Array.from(document.styleSheets)) {
      let rules
      try {
        rules = sheet.cssRules
      } catch {
        continue
      }
      for (let i = rules.length - 1; i >= 0; i--) {
        const rule = rules[i]
        if (rule && rule.selectorText && norm(rule.selectorText) === want) {
          sheet.deleteRule(i)
          n++
        }
      }
    }
    return n
  },
  async audit({ selector, scope, label }) {
    const found = locate(selector, scope)
    if (!found)
      return {
        label,
        selector,
        matched: -1,
        error: '样式表里找不到这条规则（scope 不对或选择器不逐字相同）',
      }
    let matched = -1
    try {
      matched = document.querySelectorAll(norm(`${selector}${markOf(scope)}`)).length
    } catch {
      matched = -2
    }
    const before = snapshot()
    found.sheet.deleteRule(found.index)
    const after = snapshot()
    found.sheet.insertRule(found.text, found.index)
    const restored = snapshot()
    return {
      label,
      selector,
      matched,
      sheets: copies(selector, scope).n,
      elements: before.length,
      diffs: diffCount(before, after),
      restored: diffCount(before, restored),
    }
  },
  async batch(items) {
    const out = []
    for (const it of items) out.push(await probe.audit(it))
    return out
  },
  /**
   * 整页计算样式截屏，按**元素身份**（tag|class|前 40 字文本 + 同身份的出现序号）索引，不按序号——
   * 按序号比会在一刀加进 N 个包裹节点之后把整页都报成"变了"（D18 那轮的假阳性）。
   * 46 个属性 + rect，字典编码后存 localStorage（一条路由约 100 KB，配额 5 MB 装得下十几份）。
   * 装在探针里而不是每次现贴，是因为这件事在 D23/D26/D67/D68/D94 各重贴过一遍。
   */
  capture(label) {
    const nodes = elements()
    const seen = new Map()
    const ids = []
    const props = []
    for (const el of nodes) {
      const cs = getComputedStyle(el)
      const key = `${el.tagName}|${el.getAttribute('class') || ''}|${(el.textContent || '').trim().slice(0, 40)}`
      const occ = seen.get(key) || 0
      seen.set(key, occ + 1)
      ids.push(`${key}#${occ}`)
      const r = el.getBoundingClientRect()
      props.push(
        PROPS.map((p) => cs[p]).concat([
          Math.round(r.width * 100) / 100,
          Math.round(r.height * 100) / 100,
          Math.round(r.top),
          Math.round(r.left),
        ])
      )
    }
    const payload = JSON.stringify({
      ids,
      props,
      n: nodes.length,
      vw: window.innerWidth,
      vh: window.innerHeight,
      dpr: window.devicePixelRatio,
    })
    localStorage.setItem(`cap:${label}`, payload)
    return { label, n: nodes.length, kb: Math.round(payload.length / 1024) }
  },
  /** 同一次运行里比两份截屏；`missingFromB` 是身份消失数（删节点要单独解释），`diffs` 是属性差异数。 */
  diff(a, b) {
    const A = JSON.parse(localStorage.getItem(`cap:${a}`) || 'null')
    const B = JSON.parse(localStorage.getItem(`cap:${b}`) || 'null')
    if (!A || !B) return { error: `缺一帧：${a} ${B ? '' : '或 ' + b}` }
    // 视口不同就别比了：`vh` 结算出来的值一定不同，而那种"差异"和改动无关（D67 就栽过一次）
    if (A.vw !== B.vw || A.vh !== B.vh) {
      return {
        error: `视口不一致：${A.vw}×${A.vh} vs ${B.vw}×${B.vh} —— 差分无效，同一次运行里重取`,
      }
    }
    const bi = new Map(B.ids.map((k, i) => [k, i]))
    let missing = 0
    let diffs = 0
    const samples = []
    A.ids.forEach((k, i) => {
      const j = bi.get(k)
      if (j === undefined) {
        missing += 1
        return
      }
      for (let p = 0; p < A.props[i].length; p++) {
        if (String(A.props[i][p]) === String(B.props[j][p])) continue
        diffs += 1
        if (samples.length < 8) {
          const name = p < PROPS.length ? PROPS[p] : 'rect'
          samples.push(`${k.slice(0, 44)} [${name}] ${A.props[i][p]} -> ${B.props[j][p]}`)
        }
      }
    })
    return { a: A.n, b: B.n, missingFromB: missing, diffs, samples }
  },
}

window.__probe = probe

/* 探针要的从来不是"登录流程"，而是"页面带着上一次的选择进来"。原先这里不种凭据，
   所以 `/jobs/search` 这类受守卫的路由会被弹回 `/login`——`go()` 里那个 `await router.replace()`
   照样 resolve，但屏幕上是登录页：`.workspace-theme` 数量 0、目标元素 0，量出来的一切都是假的。
   键名与序列化走 `utils/session.js`（那是唯一出处，§10.22 之前它散在三个文件 12 处），探针不自己拼。

   反过来也成立：`/register`、`/login` 这类**访客页**在登录态下会被守卫弹回 `/home`，
   所以加了 `?anon=1` 这一档——量的对象决定了要不要凭据，不是探针该猜的事。
   （清 `localStorage` 解不了这一层：store 的 `token` 是建 store 那一刻读进 ref 的。） */
if (!new URL(location.href).searchParams.has('anon')) {
  writeSession('probe-token', {
    id: 1,
    username: 'probe',
    role: 'candidate',
    is_admin: false,
    created_at: '2026-01-01T00:00:00Z',
  })
} else {
  // 只"不种"不够：localStorage 里上一次种的会话还在，`/register` 这类访客页会被守卫弹回 `/home`
  // （store 的 token 是建 store 那一刻从存储读进 ref 的，所以必须在挂载前把它清掉）。
  clearSession()
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
installElement(app)

/* `?to=/privacy` 在**挂载之前**把路由摆好。这不是 convenience：探针自带的 FREEZE 把
   `transition` 关了，而隐藏标签里 rAF 不触发，Vue 的 `<transition>` 于是永远等不到收尾——
   `go()` 之后屏幕上是"旧页卡在 fade-leave-from + 新页还没挂"的混合体，截到的每一帧都不是那条路由
   （D96 连着两次拿这种帧当基线，差分里全是转场噪声）。首屏导航不走出场动画，所以挂载前定位是干净的。
   注意视口：D67 记过"跨运行的快照会骗人"，所以 capture 把视口一起存进去，diff 在视口不一致时直接拒。 */
const START_TO = new URL(location.href).searchParams.get('to')
const boot = START_TO ? router.replace(START_TO) : Promise.resolve()
boot.finally(() => app.mount('#app'))
