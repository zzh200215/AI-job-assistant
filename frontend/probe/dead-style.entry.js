/* 浏览器探针的驱动模块：把共享 axios 实例换成夹具，让页面**不需要真后端**也能带数据画出来，
   然后提供 D67/D68 那套判据：`删掉这条规则 → 比全页计算属性 + rect → 塞回原位`。
   用法（在浏览器里）：
     await __probe.go('/knowledge')
     await __probe.audit({ selector: '.page-shell', scope: 'abcd1234' })
   scope 是那一页自己的 `__scopeId`（`__probe.scopes()` 列出全部），不靠猜构建哈希。
   判据与限制写在 docs/upgrade-plan.md D76。 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '../src/App.vue'
import router from '../src/router'
import { installElement } from '../src/plugins/element'
import request from '../src/api/request'
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
  [/\/analysis\/records(\?|$)/, 'get', { items: [ANALYSIS_RECORD], total: 1 }],
  [/\/analysis\/\d+$/, 'get', ANALYSIS_RECORD],
  [/\/analysis\/list(\?|$)/, 'get', { items: [ANALYSIS_RECORD], total: 1 }],
  [
    /\/analysis\/references/,
    'get',
    {
      query: 'K8s',
      confidence: { level: 'high', score: 0.82 },
      documents: [
        {
          doc_title: '云原生笔记',
          doc_type: 'guide',
          chunks: [{ text: '一次部署的三步', score: 0.71 }],
        },
      ],
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
    { items: [{ id: 4, task_status: 'running', name: '深度分析' }], total: 1 },
  ],
  [
    /\/system\/status/,
    'get',
    { services: [{ name: 'api', ok: true }], queue: { depth: 0, workers: 2 } },
  ],
  [/\/system\/metrics/, 'get', { counters: {}, queues: [] }],
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
    for (const p of PROPS) row.push(cs.getPropertyValue(p))
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
  const mark = `[data-v-${scopeId}]`
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

const probe = {
  props: PROPS.length,
  scopes() {
    return Object.fromEntries(
      Object.entries(COMPONENTS).map(([k, v]) => [k, v && v.__scopeId ? v.__scopeId : null])
    )
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
      matched = document.querySelectorAll(norm(`${selector}[data-v-${scope}]`)).length
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
}

window.__probe = probe

const app = createApp(App)
app.use(createPinia())
app.use(router)
installElement(app)
app.mount('#app')
