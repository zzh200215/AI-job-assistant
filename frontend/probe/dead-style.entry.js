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

/* ---------- §10.20（D113）欠的那一帧：职业规划页的四种雷达形状 ----------
   这一屏读的是 `career_planning.skill_radar.dimensions`，而它到 2026-10-06 之前**根本没有夹具**，
   所以 `.radar-card` 在探针里从来没画出来过——D113 那句"只在 jsdom 断过坐标"就是这么来的。
   四种形状：full 四条全读得懂 / partial 四条里一条读不懂（行还在、不进雷达）/ three 少一条行 /
   empty 四条全读不懂（左格换成 el-empty）。读不懂的取值挑模型真写出来的那一族：中文串、缺字段、
   布尔、空串——`Number(true)` 会被旧实现读成 1 分，所以布尔单独占一条。
   夹具用 getter 现取，所以 `__probe.radarShape('empty')` 之后**重新跑一次规划**就换形状，不用重启 dev。 */
let radarShapeMode = 'full'
const RADAR_NAMES = ['技术深度', '工程化', '业务理解', '表达力']
/* 键名抄消费者：`CareerPlanning.vue:870-877` 读的是 `name` / `gap` / `current_score` / `target_score`。
   第一版我写成 `current` / `target`，四条全被判成读不懂——那次意外量到的正是 empty 那一支，
   也正是 D113 欠的那一帧，所以两种都留着：`empty` 走的就是这一族读不懂的取值。 */
const RADAR_READABLE = [
  { current_score: 72, target_score: 88, gap: '补一次线上值班' },
  { current_score: 65, target_score: 85, gap: '把一个服务从零带到上线' },
  { current_score: 58, target_score: 80 },
  { current_score: 61, target_score: 78 },
]
const RADAR_UNREADABLE = [
  { current_score: '约80', target_score: 90 },
  { target_score: 88 },
  { current_score: true, target_score: false },
  { current_score: '', target_score: null },
]
const RADAR_SHAPES = ['full', 'partial', 'three', 'empty']
function radarDimensionsFixture() {
  const readable = (i) => ({ name: RADAR_NAMES[i], ...RADAR_READABLE[i] })
  const unreadable = (i) => ({ name: RADAR_NAMES[i], ...RADAR_UNREADABLE[i] })
  if (radarShapeMode === 'empty') return RADAR_NAMES.map((_, i) => unreadable(i))
  if (radarShapeMode === 'partial') return [readable(0), readable(1), readable(2), unreadable(3)]
  if (radarShapeMode === 'three') return [readable(0), readable(1), readable(2)]
  return RADAR_NAMES.map((_, i) => readable(i))
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
    get skill_radar() {
      return { dimensions: radarDimensionsFixture() }
    },
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

/* 相对"今天"的时间戳：`followUpLevel` 的两个阈值（>=7 / >=3 天）只有用相对天数才能长期各就各位。 */
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString()

/* ―― D183：面试列表上那条"不需要 WebSocket 的收口"（D172 加的按钮）第一次要有活页读数。
   列表夹具是**有状态**的：点过结束的那一行在重拉时必须已经是已完成，否则"点了之后行落到哪一档"
   这一条就只能靠 jsdom 说。岗位名一律中性（甲/乙/丙）——D172 那次教训是夹具名"从未开始的岗位"
   里含着"未开始"三个字，把状态标签的断言变成了空话。 ―― */
const probeEndedSessions = new Set()
const INTERVIEW_LIST_ROWS = [
  { id: 91, jd_title: '岗位甲', created_at: daysAgo(1), overall_score: 0 },
  { id: 92, jd_title: '岗位乙', created_at: daysAgo(2), overall_score: 0 },
  { id: 93, jd_title: '岗位丙', created_at: daysAgo(3), overall_score: 82 },
]
const INTERVIEW_LIST_STATUS = { 91: 'ongoing', 92: 'created', 93: 'completed' }

const FIXTURES = [
  [/\/auth\/me$/, 'get', { id: 1, username: 'probe', role: 'candidate', nickname: '探针' }],
  [/\/resume\/?(\?|$)/, 'get', [{ id: 1, title: '探针简历', created_at: '2026-09-01' }]],
  /* D105：`getResumeList` 打的是 `/resume/list`（`api/resume.js:83`），上面那条正则匹配不到它，
     所以 `JobSearch.loadResumes` 拿到 `{}` → 简历列表空 → `selectedResumeId` 一直是 null →
     智能推荐标签页永远停在"先选择一份简历"（`JobSearch.vue:785-788`）。补这一条之前，
     `RecommendPane` 的卡片在探针里根本画不出来。 */
  [
    /\/resume\/list/,
    'get',
    {
      items: [
        {
          id: 1,
          title: '探针简历',
          file_name: '探针简历.pdf',
          created_at: '2026-09-01',
          /* §10.20 那一帧要的是职业规划页：`usePlanningOptions.js:50-51` 只把 `parsed` 非空的简历
             放进选择列表，原来这份夹具没有 `parsed`，那一页的简历下拉是**空的**——按钮点了只是
             "请先选择简历"，雷达那一屏永远不挂载。键名用 `parsed` 而不是 `parsed_json`，消费者读的是前者。 */
          parsed: { current_title: '平台后端工程师' },
        },
      ],
      total: 1,
    },
  ],
  [/\/resume\/\d+$/, 'get', { id: 1, title: '探针简历', parsed_json: { basics: {} } }],
  /* ―― D158：B1 行级改写那一条链（诊断 → 建议 → 应用 → **撤销**）。
     这四条在夹具里原本**一条都没有**，所以"撤销这次应用"那颗按钮（`ResumeUpload.vue:377-385`，
     B1.4 加的）到今天为止在真浏览器里从没被点过——它是不是把 apply 返回的那个
     `snapshot_version_id` 发回去、点完之后按钮文案与匹配分那行怎么变，全都没有过一次屏幕证据。
     形状逐条抄后端：`app/api/resume.py:1020/1039/1068` 与
     `app/services/resume_rewrite_service.py:165（suggestions）/391（apply）/322（revert）`。
     撤销那一条写成**函数夹具**：它把前端真的发过来的 `snapshot_version_id` 原样回显成
     `restored_from_version_id`，并把 `undo_version_id` 派生成它 +1——前端一旦漏发或发错，
     屏幕上那个"撤销这次撤销"与分数那行就会露出来，而不是"看起来成功了"。―――――――――― */
  [
    /\/resume\/\d+\/diagnose$/,
    'post',
    {
      total_score: 62,
      structure_score: 70,
      expression_score: 58,
      keyword_score: 55,
      highlight_score: 66,
      ats_score: 61,
      structure_issues: ['项目段落只有职责、没有结果口径'],
      expression_issues: ['动词偏弱（"负责"、"参与"）'],
      missing_keywords: ['Kubernetes', '成本治理'],
      highlights: ['后端三年且同一团队'],
      match_analysis: '与目标岗位重合一半，缺口在编排与可观测',
      completeness_issues: [],
      completeness_score: 72,
      module_check: {},
      improvement_roadmap: [],
      /* 后端这句是实心的：`/diagnose` 打的是岗位名字符串，响应里没有 jd_id（:1082 的注释）。
         给 null 就是让改写那两条链走"无目标 JD"的入参形状，与生产一致。 */
      jd_id: null,
    },
  ],
  /* D200：改写建议改成后台作业之后，屏幕上那一条链变成"POST 建作业 → GET 轮询取结果"。
     轮询夹具直接给 `completed`：探针所在的 hidden 标签页不发 rAF、定时器也不可靠（D150 那条机制），
     把 pending→completed 那一跳放在这里等 2 秒去读，量到的是仪器而不是产品。
     "作业还在跑时按钮是 spinner、跑完才出卡片"这一跳由 jsdom 的单测钉（时间可控）。 */
  [/\/resume\/\d+\/rewrite-suggestion-jobs$/, 'post', { job_id: 77, status: 'pending' }],
  [
    /\/resume\/rewrite-suggestion-jobs\/\d+$/,
    'get',
    {
      job_id: 77,
      resume_id: 1,
      jd_id: null,
      status: 'completed',
      block_total: 3,
      suggestions: [
        {
          block_id: 'work[0].desc',
          kind: 'work',
          label: '工作经历 1',
          original: '负责后端服务与接口开发',
          proposed_text: '负责后端服务与接口开发，日均 2k QPS，可用性 99.9%',
          reason: '补一个可核验的结果口径',
        },
        {
          block_id: 'project[0].desc',
          kind: 'project',
          label: '项目经历 1',
          original: '参与召回模块',
          proposed_text: '把 BM25 与向量召回融合，命中率 +12%',
          reason: '动词改具体、给出增量',
        },
      ],
      rejected: [],
      note: null,
    },
  ],
  [
    /\/resume\/\d+\/apply-rewrites$/,
    'post',
    {
      resume_id: 1,
      changed: true,
      applied: [
        { block_id: 'work[0].desc', kind: 'work', label: '工作经历 1' },
        { block_id: 'project[0].desc', kind: 'project', label: '项目经历 1' },
      ],
      rejected: [],
      snapshot_version_id: 9001,
      resume_version: 2,
      block_total: 3,
      score: {
        before: { score: 62, raw_score: 62, method: 'canonical' },
        after: { score: 71, raw_score: 71, method: 'canonical' },
        delta: 9,
      },
    },
  ],
  [
    /\/resume\/\d+\/revert-rewrite$/,
    'post',
    (body) => {
      const from = body && body.snapshot_version_id
      /* `window.__revertStale = true` 切到**被拒那一支**（`changed:false` + `stale_blocks`，
         后端 `resume.py:1075` 那句"撤销与 expected_original 共用一条判据"）。默认不开：
         候选人应用之后自己又改过那几块时整单不动，这是这一族唯一"不能吃掉后写文字"的路径，
         界面上的说法与状态位都要单独量一次。 */
      if (typeof window !== 'undefined' && window.__revertStale) {
        return {
          resume_id: 1,
          reverted: false,
          changed: false,
          stale_blocks: [
            { block_id: 'work[0].desc', kind: 'work' },
            { block_id: 'project[0].desc', kind: 'project' },
          ],
          resume_version: 4,
          score: { before: null, after: null, delta: null },
        }
      }
      return {
        resume_id: 1,
        reverted: true,
        changed: true,
        restored_blocks: ['work[0].desc', 'project[0].desc'],
        restored_from_version_id: from ?? '前端没有发 snapshot_version_id',
        undo_version_id: typeof from === 'number' ? from + 1 : null,
        resume_version: 3,
        block_total: 3,
        /* 撤销那一发也带 score：`rewrite.result` 会被它整体替换（ResumeUpload.vue:752），
           不给的话按钮旁那行会退成"未指定目标岗位…"，看着像 bug 其实是夹具缺键。 */
        score: {
          before: { score: 71, raw_score: 71, method: 'canonical' },
          after: { score: 62, raw_score: 62, method: 'canonical' },
          delta: -9,
        },
        score_note: '',
      }
    },
  ],
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
  /* §10.20 那一帧缺的四条（2026-10-06 现取，`__probe.fixtureMisses()` 报出来的）：
     职业规划页拿的是 `/jd/list`（`api/jd.js:6`，上面那条 `/jd/?` 正则匹配不到它）、
     POST `/career-path/recommend`、GET `/salary/overview`，以及点"开始职业规划"时
     `createGoalJD()` 要发的 POST `/jd`——少最后一条就是"职业规划生成失败"那句 toast，
     而屏幕上完全看不出是数据缺失。形状各自抄消费者：`usePlanningOptions.js:53`（items）、
     `useCareerDirections.js:39-43`（career_paths/summary/corpus/message）、
     `useSalaryMarket.js:23-35` + 单测夹具（has_data/filters/statistics）、`createJD` 的 id。
     `/tenant/brand` 故意**不补**：今天它落到 `{}`，布局走 `|| 'Career Signal'` 那支，
     补上名字会让探针里每一页的首屏都变，历史帧就没法比了。 */
  [
    /\/jd\/list(\?|$)/,
    'get',
    { items: [{ id: 7, title: '平台工程师', company: '示例' }], total: 1 },
  ],
  [
    /\/career-path\/recommend/,
    'post',
    {
      career_paths: [
        {
          direction_key: 'platform',
          label: '平台工程师',
          coverage: 0.62,
          gap_skills: ['K8s', 'Rust'],
        },
        { direction_key: 'backend', label: '后端专家', coverage: 0.55, gap_skills: ['Rust'] },
      ],
      summary: '两条方向都有可讲的缺口',
      corpus: { visible_jds: 18, directions_found: 2 },
      message: '',
    },
  ],
  [
    /\/salary\/overview/,
    'get',
    {
      has_data: true,
      sample_size: 42,
      filters: { position: '平台后端工程师', city: null },
      statistics: { p25: 22, p50: 28, p75: 36, p90: 44 },
    },
  ],
  [
    /\/jd$/,
    'post',
    {
      id: 707,
      title: '平台后端工程师',
      company: '职业规划目标',
      raw_text: '目标岗位：平台后端工程师',
    },
  ],
  /* D108：订阅页此前在探针里是**空白**的——`loadPlans` 请求 `/subscription/plans`，没有夹具就落到
     `catch {}`，而那句注释写着"fallback 到静态数据"其实什么也没做（plans 保持 []）。
     features 逐条抄自后端 `subscription_service.TIER_FEATURES`，价格为分。 */
  [
    /\/subscription\/plans/,
    'get',
    {
      items: [
        {
          tier: 'free',
          name: '免费版',
          price_monthly: 0,
          features: {
            resume_limit: 1,
            daily_analysis_limit: 3,
            daily_interview_limit: 5,
            daily_recommendation_limit: 10,
            can_export_full_report: false,
            can_use_deep_analysis: false,
            can_use_ats_check: false,
            can_use_offer_decision: false,
            can_use_salary_negotiation: false,
          },
        },
        {
          tier: 'pro',
          name: 'Pro 版',
          price_monthly: 9900,
          features: {
            resume_limit: -1,
            daily_analysis_limit: 50,
            daily_interview_limit: 100,
            daily_recommendation_limit: 200,
            can_export_full_report: true,
            can_use_deep_analysis: true,
            can_use_ats_check: true,
            can_use_offer_decision: true,
            can_use_salary_negotiation: true,
          },
        },
        {
          tier: 'enterprise',
          name: '企业版',
          price_monthly: 0,
          features: {
            resume_limit: -1,
            daily_analysis_limit: -1,
            daily_interview_limit: -1,
            daily_recommendation_limit: -1,
            can_export_full_report: true,
            can_use_deep_analysis: true,
            can_use_ats_check: true,
            can_use_offer_decision: true,
            can_use_salary_negotiation: true,
          },
        },
      ],
    },
  ],
  [/\/subscription\/my/, 'get', { tier: 'free', quota_usage: {}, expires_at: null }],
  /* 投递看板与列表（D147）。两条都是**从空到有**的补法，代价要写在账上：
     `/jobs/pipeline/list` 原来是 `{items: [], total: 0}`、`/jobs/pipeline/kanban` 原来**没有夹具**
     （落空成 `{}`），所以那两页一直是空态——§10.26 里 `.batch-bar` / `.offer-row.selected` /
     `.card-interview` 三处只能记"推导"，根因就在这一格。**以前在那两页取过的"0 命中 / 无元素"
     读数从此作废。**
     形状各按自己的消费者写：看板走 `PipelineKanban.vue:386` 的 `data.stages`，而 BoardPane 的
     卡片字段是 snake_case（`card.interview_at` / `match_score` / `salary_range` /
     `resume_version_label` / `create_time`），**与 `jobModel.normalizePipelineEntry` 那套
     camelCase 不是同一个形状**——照后者写只会得到一个空看板。
     面试档那条必须带 `interview_at` 且落在 `interview` 列，`.card-interview` 才会出现
     （`BoardPane.vue:144` 的条件是 `card.interview_at && col.key === 'interview'`）。
     列表那三条卡在 2–4 之间，是为了让 `OfferCompare.vue:592` 那句
     `if (items.length <= 4 && items.length >= 2)` 自动全选，`.offer-row.selected` 才有元素。
     **D149 补的跟进三档**：看板那两张 applied 与一张 written_test 各带一个 `update_time`
     （9 / 1 / 4 天前，相对天数所以不会过几天就跳档），`followUpLevel` 的 danger / ok / warn
     才在同一屏各出一个元素。这一份数据同时喂两块面板——`ListPane` 的 `:rows` 是
     `PipelineKanban.vue:339` 的 `flattenCards(kanban)`，不是那个 list 端点，所以一份夹具量齐两个副本。 */
  /* 面试房间的实录面板（D150）：`TranscriptPane` 的 `.score-chip--*` 由 `hydrateSession(detail.messages)`
     驱动，而 `<TranscriptPane>` 在 `InterviewRoom.vue:37` 是**无条件渲染**的——所以房间不需要真的连上
     WS 就能上屏：`getInterviewDetail` 有数据、`detail.id` 与路由参数同号（`startWS` 里
     `isSameSession` 不同就会把 messages 清空），WS 连不上只会把 status 打成 error 并留下一句提示。
     五条 evaluation 各占一个分数档（INTERVIEW_SCORE_BANDS 是 85 / 70 / 55），加上 `score` 缺失那条走
     unknown，五档一次量齐。字段名照 `TranscriptPane.vue:38-52` 的取法写，不是照后端模型猜。 */
  /* D183：列表与收口那两条（`api/interview.js:11` 的 GET `/interview/sessions` 与
     `:29-30` 的 POST `/interview/sessions/{id}/end`）。正则用 `$` 收口，所以不会与下面
     那条房间详情 `/\/interview\/sessions\/\d+$/` 抢；顺序上列表这条在前，先命中先得。 */
  [
    /\/interview\/sessions(\?|$)/,
    'get',
    () => ({
      items: INTERVIEW_LIST_ROWS.map((row) => ({
        ...row,
        status: probeEndedSessions.has(row.id) ? 'completed' : INTERVIEW_LIST_STATUS[row.id],
      })),
      total: INTERVIEW_LIST_ROWS.length,
    }),
  ],
  [
    /\/interview\/sessions\/\d+\/end$/,
    'post',
    (body, url) => {
      const id = Number((url || '').match(/sessions\/(\d+)\/end/)?.[1] ?? -1)
      probeEndedSessions.add(id)
      return {
        session_id: id,
        status: 'completed',
        overall_score: 0,
        message: '面试已结束，评分按已作答的题生成。',
      }
    },
  ],
  [
    /\/interview\/sessions\/\d+$/,
    'get',
    {
      id: 88,
      status: 'in_progress',
      total_questions: 5,
      answered_count: 5,
      evaluation_status: 'idle',
      memory_snapshot: {},
      messages: [
        {
          id: 1,
          type: 'question',
          round: 1,
          content: '讲一次你把一个卡住的问题推动到底的经历。',
          metadata: { category: '行为面试' },
        },
        { id: 2, type: 'answer', round: 1, content: '我把依赖链拆开，逐段加了可观测点。' },
        {
          id: 3,
          type: 'evaluation',
          round: 1,
          content: 'STAR 结构完整，行动部分具体。',
          metadata: {
            score: 92,
            completeness: 9,
            accuracy: 9,
            depth: 8,
            expression: 9,
            improvement: '补一句结果的可量化影响。',
          },
        },
        {
          id: 4,
          type: 'evaluation',
          round: 2,
          content: '任务描述清楚，行动与结果的因果还差一环。',
          metadata: { score: 78, completeness: 8, accuracy: 7, depth: 7, expression: 8 },
        },
        {
          id: 5,
          type: 'evaluation',
          round: 3,
          content: '回答偏结论，缺少可核对的过程。',
          metadata: { score: 62, completeness: 6, accuracy: 6, depth: 5, expression: 7 },
        },
        {
          id: 6,
          type: 'evaluation',
          round: 4,
          content: '这一条没有覆盖到追问点。',
          metadata: { score: 40, completeness: 4, accuracy: 4, depth: 3, expression: 5 },
        },
        {
          // score 缺失 ⇒ `interviewScoreToneClass(undefined)` 走 unknown 那一档
          id: 7,
          type: 'evaluation',
          round: 5,
          content: '这条回答还没评上分。',
          metadata: { completeness: null, accuracy: null, depth: null, expression: null },
        },
      ],
    },
  ],
  [
    /\/jobs\/pipeline\/list/,
    'get',
    () => ({
      total: 3,
      page: 1,
      page_size: 20,
      items: [
        {
          id: 41,
          jd_id: 7,
          stage: 'offer',
          title: '平台后端工程师',
          company: '示例公司',
          location: '上海',
          salary_range: '30-40K',
          match_score: 88,
          source: '本地',
          resume_version_label: 'v3',
          interview_at: '2026-09-28T10:00:00',
          create_time: '2026-09-20T09:00:00',
        },
        {
          id: 42,
          jd_id: 7,
          stage: 'offer',
          title: '算法工程师',
          company: '示例公司二',
          location: '北京',
          salary_range: '28-38K',
          match_score: 72,
          source: '外部',
          create_time: '2026-09-18T09:00:00',
        },
        {
          id: 43,
          jd_id: 7,
          stage: 'interview',
          title: '数据平台工程师',
          company: '示例公司三',
          location: '杭州',
          salary_range: '26-36K',
          match_score: 65,
          source: '本地',
          interview_at: '2026-10-02T14:00:00',
          create_time: '2026-09-25T09:00:00',
        },
      ],
    }),
  ],
  [
    /\/jobs\/pipeline\/kanban/,
    'get',
    () => ({
      stages: {
        todo: [],
        applied: [
          {
            id: 44,
            jd_id: 7,
            stage: 'applied',
            title: '后端开发工程师',
            company: '示例公司四',
            location: '深圳',
            salary_range: '25-35K',
            match_score: 79,
            source: '本地',
            create_time: '2026-09-26T09:00:00',
            /* 9 天前 → `followUpLevel` 走 danger 那一档（>=7）。 */
            update_time: daysAgo(9),
          },
          {
            id: 46,
            jd_id: 7,
            stage: 'applied',
            title: '服务端开发工程师',
            company: '示例公司六',
            location: '南京',
            salary_range: '22-32K',
            match_score: 58,
            source: '外部',
            create_time: '2026-10-06T09:00:00',
            /* 1 天前 → ok 档（<3）。 */
            update_time: daysAgo(1),
          },
        ],
        written_test: [
          {
            id: 45,
            jd_id: 7,
            stage: 'written_test',
            title: '数据开发工程师',
            company: '示例公司五',
            location: '广州',
            salary_range: '24-34K',
            match_score: 71,
            source: '本地',
            create_time: '2026-10-04T09:00:00',
            /* 4 天前 → warn 档（>=3 且 <7）。三档各有一张卡，正向那条腿才有元素可量。 */
            update_time: daysAgo(4),
          },
        ],
        interview: [
          {
            id: 43,
            jd_id: 7,
            stage: 'interview',
            title: '数据平台工程师',
            company: '示例公司三',
            location: '杭州',
            salary_range: '26-36K',
            match_score: 65,
            source: '本地',
            resume_version_label: 'v2',
            interview_at: '2026-10-02T14:00:00',
            create_time: '2026-09-25T09:00:00',
          },
        ],
        offer: [
          {
            id: 41,
            jd_id: 7,
            stage: 'offer',
            title: '平台后端工程师',
            company: '示例公司',
            location: '上海',
            salary_range: '30-40K',
            match_score: 88,
            source: '本地',
            resume_version_label: 'v3',
            create_time: '2026-09-20T09:00:00',
          },
        ],
        accepted: [],
        rejected: [],
        withdrawn: [],
      },
    }),
  ],
  [/\/jobs\/bookmarks\/list/, 'get', { items: [], total: 0 }],
  /* 智能推荐那条链（D105）：消费者是 `useJobRecommend.js:23-52`，读 `data.recommendations`，
     每条按 `jd_id / job_title / company / location / salary_range / match_score / recommendation_type /
     match_reason / skill_overlap / skill_gap / salary_match / location_match / experience_match` 取。
     没有这条夹具时 `RecommendPane` 永远画不出卡片，它那 23 条被 `null {…}` 判死的规则就没法上屏验证——
     D76 那句话第三次成立：形状要照消费者写，不然 `matched=0` 是假阴性。
     两条卡片、重合与缺口都非空，好让 `.tag-group` / `.tag-label.ok|.gap` / `.recommend-signals` 全出现。 */
  [
    /\/jobs\/recommend$/,
    'get',
    {
      recommendations: [
        {
          jd_id: 701,
          job_title: '推荐后端岗',
          company: '示例科技',
          location: '上海',
          salary_range: '25-40K',
          industry: '互联网',
          match_score: 88,
          recommendation_type: '强烈推荐',
          match_reason: '命中两项必需技能，缺口集中在编排',
          skill_overlap: ['Python', 'SQL'],
          skill_gap: ['Kubernetes'],
          salary_match: true,
          location_match: true,
          experience_match: false,
          /* D157：这两条 `source` 是为了让 `JobRecommend.vue:394` 那颗 `.source-tag` 真上屏——
             它挂在 `v-if="job.source"` 上，而这份夹具原来没有这个键，所以那颗座（plain/primary 通道、
             组件不再自改字色）在探针里永远画不出来。`sourceText`（:986）认 `api` / `imported`。 */
          source: 'api',
        },
        {
          jd_id: 702,
          job_title: '推荐数据岗',
          company: '示例网络',
          location: '北京',
          salary_range: '30-45K',
          industry: '数据服务',
          match_score: 62,
          recommendation_type: '值得一试',
          match_reason: '技能重合一半，薪资与地点都贴合',
          skill_overlap: ['ETL'],
          skill_gap: ['Airflow', 'dbt'],
          salary_match: true,
          location_match: false,
          experience_match: true,
          source: 'imported',
        },
      ],
    },
  ],
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
      /* D157：这份夹具原来只有四个键，而 `ExplainPane.vue:28-36` 是**直接读嵌套字段**的
         （`explainResult.weights_used.skill` 等六次，没有 `?.`），`:11` 还读 `overall_score`。
         缺键的后果不是报错而是"渲染中断"：面板停在上一帧（那条 `v-if="loading"` 的骨架），
         屏幕上永远显示"正在生成匹配度解释…"——`.mb` 这颗座就是这么长期量不到的。
         补齐按消费者来：`weights_used` 六键（后端 `schemas/analysis.py:23` 声明成必填 dict）、
         `dimensions[].{name,weight,score,reason,details}`、`skill_match.{matched,missing_required,missing_nice}`。
         `recommendation` 取「不建议投递」：`explainRecommendationTag`（analysisModel.js:151）把它映成
         `danger`，也就是守卫给这颗座记的那个**最坏档**（dark/danger 4.76）——live 与静态要撞在同一个数上。 */
      recommendation: '不建议投递',
      overall_score: 41,
      overall_reason: '技能命中两条，编排与数据编排缺口拉低总分',
      weights_used: {
        skill: 0.34,
        project: 0.2,
        experience: 0.16,
        education: 0.1,
        keyword: 0.1,
        bonus: 0.1,
      },
      dimensions: [
        {
          name: '技能',
          weight: 0.34,
          score: 72,
          reason: '命中两项必需技能，缺口集中在编排',
          details: ['缺少 Kubernetes 经验'],
        },
        { name: '经验', weight: 0.16, score: 50, reason: '年限相近但领域不同', details: [] },
      ],
      skill_match: {
        matched: ['Python', 'SQL'],
        missing_required: ['Kubernetes'],
        missing_nice: ['Terraform'],
      },
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
  /* 历史记录页（§10.27 那一双 warn 的根因）。`api/history.js:3` 打 `/history`，此前**一条夹具都没有**，
     适配器落空返回 `{}` → `loadList` 裸写 `list.value = data.items` → 模板 `v-if="list.length"`
     在渲染期抛 `Cannot read properties of undefined`，于是这一屏的每一帧都拍在半坏的组件上，
     而且没有任何门会红（console 里两条 warn 是唯一的痕迹）。
     字段名照 `backend/app/api/history.py:69-83` 的返回逐字抄；分数覆盖 scoreTone 的四档加一个 null。 */
  [
    /\/history(\?|$)/,
    'get',
    {
      total: 5,
      page: 1,
      page_size: 10,
      items: [
        {
          id: 99,
          resume_id: 1,
          jd_id: 7,
          resume_name: '探针简历',
          resume_file: '探针简历.pdf',
          jd_title: '平台后端工程师',
          jd_company: '示例公司',
          match_score: 92,
          // D167：这一行是"被回算过"的样子（`displayed_before_backfill` 由
          // `backend/app/api/history.py:76-91` 从 match_report 原样带出）。其余几行没有这个键，
          // 于是活页上同时有"该画一句"和"一个字都不许多"两种现场。
          displayed_before_backfill: 85,
          remark: '高匹配',
          create_time: '2026-10-01T09:00:00',
        },
        {
          id: 98,
          resume_id: 1,
          jd_id: 7,
          resume_name: '探针简历',
          resume_file: '探针简历.pdf',
          jd_title: '算法工程师',
          jd_company: '示例公司二',
          match_score: 76,
          remark: '',
          create_time: '2026-09-28T09:00:00',
        },
        {
          id: 97,
          resume_id: 1,
          jd_id: 7,
          resume_name: '探针简历',
          resume_file: '探针简历.pdf',
          jd_title: '数据工程师',
          jd_company: '示例公司三',
          match_score: 55,
          remark: '',
          create_time: '2026-09-20T09:00:00',
        },
        {
          id: 96,
          resume_id: 1,
          jd_id: 7,
          resume_name: '探针简历',
          resume_file: '探针简历.pdf',
          jd_title: '前端工程师',
          jd_company: '示例公司四',
          match_score: 30,
          remark: '',
          create_time: '2026-09-12T09:00:00',
        },
        {
          id: 95,
          resume_id: 1,
          jd_id: 7,
          resume_name: '探针简历',
          resume_file: '探针简历.pdf',
          jd_title: '未评分岗位',
          jd_company: '示例公司五',
          match_score: null,
          remark: '',
          create_time: '2026-09-05T09:00:00',
        },
      ],
    },
  ],
  /* D168：详情那条路的夹具。列表用的是 `/\/history(\?|$)/`，它**匹配不到** `/history/99`，
     所以点「查看」在探针里一直落空返回 `{}` —— D167 因此只能把"详情那一句"记成未验。
     字段照 `backend/app/api/history.py:112-127` 逐字抄。 */
  [
    /\/history\/\d+$/,
    'get',
    {
      id: 99,
      resume_id: 1,
      jd_id: 7,
      resume: {
        id: 1,
        name: '探针简历',
        file_name: '探针简历.pdf',
        parsed: { current_title: '后端工程师' },
      },
      jd: {
        id: 7,
        title: '平台后端工程师',
        company: '示例公司',
        parsed: { title: '平台后端工程师' },
      },
      match_score: 92,
      match_report: {
        summary: '模型写的那段话',
        recommendation: '谨慎投递',
        displayed_before_backfill: 85,
        score_method: 'rubric_6dim_v2',
      },
      optimize_suggestions: { items: [] },
      interview_questions: [],
      remark: '回算样例',
      create_time: '2026-10-01T09:00:00',
    },
  ],
]

/* 夹具命中账：这一屏到底发过哪些请求、哪一条没夹具可落（落空就是 `{}`，
   于是"点了没反应/生成失败"而屏幕上看不出是数据缺失）。§10.20 那一帧就是靠它定位的。
   D158 起还记**请求体**（`body`）：写操作那几条（应用 / 撤销改写）光看"请求发出去了"不够，
   要看得出发出去的那个 id 是不是上一响应里带回来的那一个——"按钮点了但接错线"正是这一族
   最容易漏的事故（见 [[frontend-extraction-wiring-needs-screen-assertions]]）。
   函数夹具现在会收到这个已解析的请求体，所以撤销那条能把前端真的发出去的 id 原样回显，
   前端一旦漏发，屏幕上立刻看出不对而不是"看起来成功了"。 */
const fixtureLog = []

request.defaults.adapter = async (config) => {
  const method = String(config.method || 'get').toLowerCase()
  const url = String(config.url || '')
  const hit = FIXTURES.find(([re, m]) => re.test(url) && m === method)
  let body = null
  if (typeof config.data === 'string') {
    try {
      body = JSON.parse(config.data)
    } catch {
      body = config.data
    }
  } else if (config.data && typeof config.data === 'object') {
    body = config.data
  }
  /* 夹具可以是函数：跟进档位那一条按 `Date.now()` 算相对天数，写死日期的话过几天整条档就跳了，
     读数会静默变成另一档（和 [[eval-gates-must-beat-chance]] 里"旧基线作废"同一类坑）。 */
  const raw = hit ? hit[2] : {}
  // D183：函数夹具多收一个 `url`——有状态的收口那条要从 URL 里取 session id。
  const data = typeof raw === 'function' ? raw(body, url) : raw
  fixtureLog.push({ url, method, hit: !!hit, body })
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

/* 隐藏标签页里 rAF 一拍都不来（内嵌浏览器 `visibilityState=hidden` 时实测：`go()` 卡在等两帧上，
   URL 已经变了、视图却停在 `fade-leave-from` 永远不换）。D147 那次"0 组不达标"的假数就是这么来的——
   我以为在看板那一屏扫过，其实整页还停在上一张视图上。探针要的是**计算值**，不是像素，所以这里把
   rAF 换成计时器垫片：布局与 getComputedStyle 照常准确，transition 也能走完自己的收尾。
   只在 hidden 时生效，可见标签页照旧走真 rAF。 */
if (document.visibilityState === 'hidden') {
  window.requestAnimationFrame = (cb) => setTimeout(() => cb(performance.now()), 16)
  window.cancelAnimationFrame = (id) => clearTimeout(id)
}

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
  /** 这一屏发过的请求与哪些落到空夹具（`{}`）——"点了没反应"先查这里，别猜页面逻辑。 */
  fixtureLog: () => fixtureLog.slice(),
  fixtureMisses: () => fixtureLog.filter((l) => !l.hit),
  /** §10.20 那一帧的开关：换雷达形状后要重新点一次"开始职业规划"，夹具才现取。 */
  radarShape(mode) {
    if (!RADAR_SHAPES.includes(mode)) {
      throw new Error(`未知雷达形状：${mode}，可选 ${RADAR_SHAPES.join(' / ')}`)
    }
    radarShapeMode = mode
    return { shape: mode, dimensions: radarDimensionsFixture() }
  },
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
   *  （视图 import 面板，面板的 style 先注），所以变异那一条真能改到屏幕，而不是被后写的对手压掉。
   *  D152：注入的那条带一个哨兵声明 `--probe-injected: 1`（自定义属性，不参与渲染），
   *  `dropRule` 只撤**带哨兵的**——之前它按选择器精确删，而我注的就是同一个选择器，
   *  于是把页面自己的那条源规则一起删了（量 `.funnel-track` 时踩过：之后整屏的轨道底色变透明，
   *  我差一点把"注入撤掉后仍是透明"当成真缺陷）。撤完顺手回报源规则还在不在。 */
  injectRule({ selector, scope, decls }) {
    const mark = markOf(scope)
    const withSentinel = `${decls.replace(/;\s*$/, '')}; --probe-injected: 1`
    const text = norm(`${selector}${mark} { ${withSentinel} }`)
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
  /** 撤掉**探针注过的那条**（按哨兵声明认，绝不碰源规则）。返回撤了几条 + 源规则还在不在。 */
  dropRule(selector, scope) {
    const want = norm(`${selector}${markOf(scope)}`)
    let removed = 0
    let sourceLeft = 0
    for (const sheet of Array.from(document.styleSheets)) {
      let rules
      try {
        rules = sheet.cssRules
      } catch {
        continue
      }
      for (let i = rules.length - 1; i >= 0; i--) {
        const rule = rules[i]
        if (!rule || !rule.selectorText || norm(rule.selectorText) !== want) continue
        if (rule.style && rule.style.getPropertyValue('--probe-injected')) {
          sheet.deleteRule(i)
          removed++
        } else {
          sourceLeft++
        }
      }
    }
    return { removed, sourceLeft }
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
      /* D105：深色作用域 `.workspace-theme` 是 `DefaultLayout.vue:2` 上静态写的类，所以在页面里
         `classList.remove('workspace-theme')` 试级联，会把**之后每一帧**都悄悄换成浅色主题——
         实测这样拍出来的两帧差 1820 条属性，全是侧栏文字色，与被测改动无关。
         视口之外还要比主题：主题不同就拒比。 */
      tw: !!document.querySelector('.workspace-theme'),
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
    // D105：主题作用域也要一致，否则整页文字色都会算成"改动带来的差异"。
    if (A.tw !== B.tw) {
      return {
        error: `主题作用域不一致：.workspace-theme 在 A 是 ${A.tw}、在 B 是 ${B.tw} —— 差分无效（比视口更阴，因为它可以是被上一次实验摘掉的）`,
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
