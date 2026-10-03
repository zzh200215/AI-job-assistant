import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  AGENT_TASK_STATUSES,
  CONFIDENCE_LEVELS,
  PRIORITY_LEVELS,
  SEVERITY_LEVELS,
} from '../../src/constants/states.js'

// Ratchet guards. Every ceiling below is a measurement of existing debt, not an
// approval of it. A count may only move DOWN: when you fix some, lower the
// number in this file in the same commit, otherwise `staleBudgets` fails and
// tells you the new value to write.
const BUDGET = {
  hardcodedColorLiterals: {
    /* D67 让这一维第一次**往下走**（此前每次拆页都只往上加）。删的根据不是静态推断：
       先在真浏览器里数每条规则命中几个元素（0 命中才候选），再把候选规则原样塞回同一份 DOM
       比一遍全页计算样式，四个页面各自 0 差异（48/77/80/56 条，2270/505/692/267 个元素实例）；
       再叠一把尺子——被删类名一个都不出现在页面自己的模板里（动态拼出来的 `node-*`/`badge-*`/
       `score-tone` 那几族实测全部留在表里，`el-` 那类库里选择器一律不动）。
       下面这四个数就是量完剩下的"页面自己还在用"的那些。 */
    'src/features/interview/views/InterviewRoom.vue': 43,
    'src/features/shell/views/Home.vue': 71,
    'src/features/jobs/views/JobSearch.vue': 26,
    'src/features/jobs/components/JobCompareDialog.vue': 1,
    'src/features/jobs/components/JobDetailDrawer.vue': 1,
    /* D44 搬两个面板时的**复制成本**，不是新写的色值：scoped 样式不跨组件边界，父页面那 27 条
       `.warehouse-*` / `.pipeline-*` 规则只能原样拷一份进子组件，于是同一份 rgba 同时存在于
       两个文件里，本维度的总数因此**上涨**（父页面仍是 45，一条没删）。
       WarehousePane 的拷贝里没有一个色值（全是 var()），所以它不进这张表——未知的路径预算就是 0。
       这笔债的正确还法是把它们换成主题 token 并逐路由 getComputedStyle 差分，见 §7 阶段 2 的说明。
       **D67 起这段里的「父页面一条没删」不再成立**：0 命中那批已从父页面删掉，JobSearch 45 → 30。 */
    'src/features/jobs/components/PipelinePane.vue': 5,
    /* D45 又搬出两个面板，同一笔复制成本再记一次：这两份是从父页面**复制**的（父页面 45 条一条没删），
       所以这一维的总数随拆页上升：45 → 50 → 67。不是新写的色值，是同一份 rgba 现在住在两个文件里。 */
    'src/features/jobs/components/SearchPane.vue': 8,
    'src/features/jobs/components/RecommendPane.vue': 9,
    'src/layouts/DefaultLayout.vue': 34,
    'src/features/shell/views/Profile.vue': 31,
    'src/features/planning/views/CareerPlanning.vue': 27,
    'src/features/analysis/views/SmartAnalysis.vue': 9,
    /* D51 搬出「职业规划」面板时样式按 D44 的口径**复制**（父页面那 1092 行一行没删，因为静态切分
       看不见动态类名），所以这 3 个是从页面里**重复**出来的，不是新增的债：这一页面上的色值
       15 → 18。css 分块实测 17.01 → 19.42 kB、js 分块 46.36 → 48.30 kB。 */
    'src/features/analysis/components/CareerPlanPane.vue': 3,
    /* D52 同上：引用来源面板复制的是页面里 "RAG Confidence / References / Loading state" 三段，
       这 3 个是从 15 里重复出来的第二个副本；匹配度解释面板复制的两段一个色值都没有，所以不列。 */
    'src/features/analysis/components/ReferencesPane.vue': 3,
    'src/features/jobs/views/JobRecommend.vue': 20,
    'src/features/auth/views/Register.vue': 26,
    'src/features/interview/views/InterviewReport.vue': 22,
    'src/features/resume/views/ResumeCompare.vue': 19,
    'src/features/auth/views/Login.vue': 16,
    'src/features/interview/views/Interview.vue': 13,
    'src/features/pipeline/views/PipelineKanban.vue': 1,
    /* D62 把转化分析与版本表现两块面板搬出 PipelineKanban：样式照 D44 的口径**复制不切**
       （`.funnel-fill` 的配色走 `'fill-' + stage.accent` 这种动态类名，静态切分会把 6 条
       fill-* 整条切没）。这 1 条 `#94a3b8` 是页面那 12 条里重复出来的第二个副本，
       页面一条没删，所以这一维总数 12 → 13，不是新写的色值。 */
    'src/features/pipeline/components/StatsPane.vue': 1,
    /* D63 搬看板列：同一笔复制成本再记一次。这 9 条是 `.dot-*` 与 `.follow-*` 那些
       十六进制值从页面**重复**出来的第二份（页面 12 条仍然一条没删——那些类名有一半是
       拼出来的：`'dot-' + col.accent`、`'card-follow follow-' + followUpLevel(...)`）。
       这一维在 pipeline 这个域里 12 → 13 → 22。 */
    'src/features/pipeline/components/BoardPane.vue': 9,
    /* D64 搬列表视图：同一笔复制成本第三次记在这个域里。这 7 条是 .follow-* 与
       .score-level--* 那些十六进制值从页面**重复**出来的第二份（页面 12 条一条没删；
       这两个类名分别是 'follow-' + followUpLevel(...) 与 scoreToneClass(..., 'score-level')
       拼出来的，静态切分会整条切错）。pipeline 域这一维：12 → 13 → 22 → 29。 */
    'src/features/pipeline/components/ListPane.vue': 7,
    /* D65 把 SmartAnalysis 剩下 5 个标签页面板搬出视图，其中只有这一页带色值：`.cp-score` 的
       白色前景（压在 `score-fill--*` 的分数渐变上，那五条渐变规则住在 src/styles/main.css，
       跨组件边界有效，所以不重复）。这 1 条是从页面那 15 条里**重复**出来的第二份，
       页面一条没删；其余四块面板复制的四段（Query card / Generate area / Dev card / List）
       全是 var()，一个 hex 都没有，所以它们不进这张表。 */
    'src/features/analysis/components/CareerDirectionPane.vue': 1,
    /* D66 把 InterviewRoom 的四块展示面板搬出视图，同一笔复制成本第四次记在这个域里，而且这次最贵：
       这页的样式里有**两层**——基础规则之外还有 20 多条 `.interview-room-page .xxx` 的覆盖层，
       它们的目标元素一搬进子组件就只带子组件的 scope id，页面那份再也命中不了，于是必须连覆盖层
       一起复制。interview 域这一维 69 → 69+29=98（页面那 69 条仍然一条没删，删除属 D67 那场差分）。
       其中 QuestionPane 19 条最多，因为它那块把头像、徽章、结构框三个上色的块都带走了。 */
    'src/features/interview/components/QuestionPane.vue': 19,
    'src/features/interview/components/TranscriptPane.vue': 7,
    'src/features/interview/components/RoomAside.vue': 2,
    'src/features/interview/components/StagePane.vue': 1,
    'src/features/auth/views/ResetPassword.vue': 12,
    'src/features/interview/views/InterviewSetup.vue': 11,
    'src/features/eval/views/RecommendationEval.vue': 11,
    'src/features/analysis/views/ExplainMatch.vue': 9,
    'src/features/auth/views/NotFound.vue': 5,
    'src/features/eval/views/RecommendationConfig.vue': 5,
    'src/features/billing/views/Subscription.vue': 5,
    'src/features/knowledge/views/KnowledgeBase.vue': 4,
    'src/features/shell/views/WeeklyReport.vue': 4,
    'src/features/resume/views/ResumeUpload.vue': 3,
    'src/features/shell/views/TaskCenter.vue': 3,
    'src/features/shell/views/About.vue': 2,
    'src/features/analysis/views/AgentAnalysis.vue': 2,
    'src/features/eval/views/EvalReport.vue': 2,
    'src/features/analysis/views/MultiAgentAnalysis.vue': 2,
    'src/features/jobs/views/OfferCompare.vue': 2,
    'src/features/admin/views/PromptTrace.vue': 2,
    'src/features/jobs/views/SalaryInsight.vue': 2,
    'src/features/shell/views/History.vue': 1,
    'src/features/jobs/views/JobTargets.vue': 1,
  },
  // 分数→颜色的挑选此前藏在 <script> 的字符串里，style 预算数不到它，于是六处实现
  // 各挑一套阈值与 hex。匹配分与面试分已全部交给 utils/scoreTone.js，此处清零：
  // 视图的 <script> 里再出现 hex，这条预算就会红。
  scriptColorLiterals: {},
  /* 模板属性里的色值：上面两个预算都看不见它（一个数 <style>，一个数 <script>）。
     这里的数字是现状记账，不是认可——Login 的 17 处是第三方登录按钮的品牌色
     （Google / GitHub 官方值），本来就该写死；其余 8 处是真债（导航菜单两个蓝、
     风险点/改进建议两个 Element 默认色、两处内联 SVG 描边、一个兜底色），且都与
     主题 token 不同值。本段一条都没换成 var()：`stroke="var(--app-…)"` 这类表现
     属性必须能在浏览器里看结果才敢改，而 browser 工具被会话策略拦着。 */
  /* 模板属性里的色值。三个维度里只有这一维必须逐条在真浏览器里看过才敢动（D1 第三段）。
     D17 动了 5 处，其中 2 处是**删掉**而不是换成 token：`el-menu` 的 `text-color` /
     `active-text-color` 在本文件 `<style>` 里被 `.el-menu-item`、`:hover`、`.is-active`、
     `.el-sub-menu__title` 四条 `color: … !important` 全覆盖，实测把属性值改成 #ff00ff/#00ffff
     后 23 个导航项的计算色一个字节都没动（167,169,181 / 189,164,255）——它们从来不说真话，
     留着只会误导下一个人。剩下 3 处各有各的理由不动：
     - Login 17 处是 Google/GitHub 官方品牌色与雷达图描边，本就该写死；
     - DefaultLayout 这 1 处是品牌标记的白描边，压在 #6d3ce8 的紫色块上，是刻意的对比色，
       不是"忘了用 token"（它等于 --app-surface-strong 也是巧合）；
     - ExplainMatch 2 处：D16 查到这个视图**没有路由可达**（`explain-match` 是 redirect），
       改了没人看见，等 §7 阶段 3 决定删不删。 */
  templateColorLiterals: {
    'src/features/auth/views/Login.vue': 17,
    'src/layouts/DefaultLayout.vue': 1,
    'src/features/analysis/views/ExplainMatch.vue': 2,
  },
  /* 手写的 `class="panel-header"` 标记数——AppPanel（components/ui/AppPanel.vue）的迁移台账。
     样式早就集中在 styles/panels.css（main.js 全局引入），重复的只是那四层 div，所以这条数的是
     "还有多少处标记没搬进组件"。台账从 93 降到 35：D18 建组件并迁 WeeklyReport 5 处（241 元素
     × 20 条计算属性 0 差异）、D19 OfferCompare 5 处（首个带 #actions 的站点，1113 元素 0 差异，
     顺带证明 **slot 内容带着父组件的 scoped 作用域**）、D20–D25 再收 26 处（含 12 处裸 h3 头部）、
     D26 一次性迁 22 处（Profile 4 / InterviewSetup 3 / MultiAgentAnalysis 3 / PromptTrace 3 /
     AgentAnalysis 2 / AnalysisResult 2 / RecommendationConfig 2 / RecommendationEval 2 / History 1）。
     剩下 35 处分四类，每一类都不是"没来得及"，而是**要先决定 AppPanel 的 API**：
     - 11 处在还带自己 `.panel-header` 覆盖的 5 个视图里（JobSearch / KnowledgeBase / Privacy /
       Register / OrganizationWorkspace，见 LOCAL_OVERRIDE_FILES）——覆盖不进 panels.css 就迁不动；
     - 12 处标题包在调用方自己的 div 里（InterviewReport 8 处 `card-header`、InterviewRoom 4 处
       `transcript-header` / `side-title`）——要迁得先给 AppPanel 加 `#heading` 槽，见 §10.12；
     - 10 处在 SmartAnalysis，标题一律是 `<span>` 而不是 h3：3 处 `<section class="panel">` 里
       `<el-icon/> + <span>`、2 处头部只有裸 `<span>`、5 处整个头部就是一行
       `<div class="panel-header"><span>…</span></div>`——搬进 #title 等于把 span 换成 h3（那 3 处
       还会顺手删掉 `<section>` 地标），是**视觉/语义变更**不是等价迁移，要先量；
     - 2 处结构上就不该迁：MultiAgentAnalysis:94 的 agent 卡片头没有 h3（只有 el-tag + span），
       AnalysisResult:54 的进度头把 `is-loading` 图标写在 h3 **内部**——AppPanel 的 #title 会把它
       套进自己的 h3，等于 h3 嵌 h3。
     这四类由 `scripts/panel-migration.mjs --all` 逐处判定（0 命中 = 纯 drop-in 已经迁完）。注意这条
     台账数的是 `class="panel-header"` 出现次数，而扫描器只认"单独一行的 `<div class="panel-header`>"
     那种写法：上面 SmartAnalysis 的 5 处一行式 + Privacy 的 2 处一共 7 处，扫描器看不见、这条数看得见
     ——拿"命中 0"当"没有可迁的了"就错了，那是同一把尺子量两种形状的差别。
     全仓 `:deep(.panel-header)` 为 0 处，所以没有第三种隐藏耦合。 */
  handRolledPanelHeaders: 35,
  /* 状态→el-tag 颜色此前和分数色板同病：17 份手写表、32 个键，其中 `running` 在任务中心
     是蓝、两个 agent 页是橙，`ongoing` 在房间页是绿、设置页是橙。异步任务与面试会话两组
     已收进 utils/statusTone.js；下面数的是**还剩多少条手写映射**，只能往下走。

     口径是 **token**（`键: '颜色'`），不是整行。按行数吃过两次亏：
     `{ a: 'success', b: 'danger' }` 写在一行只算 1，被 prettier 折开又变 2，
     所以同一份代码的计数会随换行漂。2026-09-23 一次性格式化把它戳穿：按行口径只看见 52 条，
     换成 token 口径是 99 条（D70 复算是 **98**：D58 把看板那两处卡片派生合并成一处实现之后
     就没回到 99；本文件的"预算比现实松就失败"全绿，所以 98 是实数），其中 47 条（admin/Tenants 9、JobTargets 4、Privacy 3…）从来没有
     进入过任何预算——就是本文件上面那句"预算看不见"第四次复发。
     已知噪声（不要把它当精确值）：99 条里 17 条是 `ElMessageBox.confirm(..., { type: 'warning' })`
     的对话框图标色。它和 PromptTrace 的 `RESPONSE_SOURCES`（真色表，键也叫 `type`）在 token 层
     无法区分，想区分要看数据流（这个值最终有没有喂给 `:type`），不值得为一把尺子上 AST。
     所以这条预算是**上界**：数得多、漏不掉，只许往下走。 */
  statusTagEntries: {
    'src/features/knowledge/views/KnowledgeBase.vue': 13,
    /* D49 把三张色表（复杂度、匹配建议、以及两个分数三元式）从视图搬进 lib：这 9 条不是新债，
       是搬家搬出来的——视图侧只剩 4 条（任务结果那一支）。合并计数与搬家前一样是 13。 */
    'src/features/analysis/lib/analysisModel.js': 9,
    'src/features/analysis/views/SmartAnalysis.vue': 4,
    'src/features/admin/views/Tenants.vue': 9,
    /* D53 同理：职业规划页的优先级/复杂度两张表搬进 lib，6 条是搬家的账不是新债，
       页面侧只剩任务状态那一支（3 条）。合并计数与搬前一样是 9。 */
    'src/features/planning/lib/planningModel.js': 6,
    'src/features/planning/views/CareerPlanning.vue': 3,
    /* D57 同理：`stageTagType` 那七条阶段色表搬进 pipeline lib，视图侧只剩两处派生。
       合并计数与搬前一样是 9。 */
    'src/features/pipeline/lib/pipelineBoard.js': 7,
    'src/features/pipeline/views/PipelineKanban.vue': 1,
    'src/features/admin/views/PromptTrace.vue': 7,
    'src/features/analysis/views/AnalysisResult.vue': 5,
    'src/features/analysis/views/ExplainMatch.vue': 4,
    'src/features/jobs/views/JobTargets.vue': 4,
    'src/features/billing/views/OrganizationWorkspace.vue': 4,
    'src/features/admin/views/Orders.vue': 3,
    'src/features/admin/views/Overview.vue': 3,
    'src/features/legal/views/Privacy.vue': 3,
    'src/features/resume/views/ResumeCompare.vue': 3,
    'src/features/shell/views/History.vue': 2,
    'src/features/interview/views/InterviewRoom.vue': 2,
    'src/features/resume/views/ResumeUpload.vue': 2,
    'src/features/interview/views/Interview.vue': 1,
    'src/features/shell/views/Profile.vue': 1,
    'src/features/billing/views/Subscription.vue': 1,
    'src/features/shell/views/TaskCenter.vue': 1,
  },
  /* 失败被清成空态的存量（见 silentCatchCounts）。D5 把候选人侧 8 处接到了
     components/ui/AppLoadError；剩下的每一条都是明知故留，理由写在行内：
     - admin/*：企业侧已冻结（见 docs/upgrade-plan.md 的范围决定），不再投入；
     - ResumeUpload 的 loadVersionCount 失败时把 `_versionCount` 设为 null（=不知道），
       卡片因此不显示数字，也不再显示"0 个版本"——它没有作出假断言，只是少了一个按钮。
     - admin/Tenants 的 loadDomains：`notifyError: false` 且 `catch { domains[tid] = [] }`，
       展开某一行的租户域名列表失败会演成"该租户没有域名"。它是 D10 记下的那条盲区自己冒出来的：
       旧尺子往后看 12 行找"有没有提示"，2026-09-23 格式化把 submitCreate 的 ElMessage 折出了
       窗口，它才现形（代码没变，是尺子的视野变了）。企业侧冻结，所以进预算不修。
     - JobSearch 的 explainCurrentJob 是 **POST**：`request.js` 对非 GET 会弹提示，所以它不属于
       "失败演成没有数据"，只是解读块不出来时要用户自己再点一次"投递解读"。判据按形状数、不看
       动词，所以它留在账上；D15 把窗口收到函数作用域后新暴露的三处里，两处 GET 已经修掉了。 */
  silentEmptyCatches: {
    'src/features/admin/views/Overview.vue': 2,
    'src/features/admin/views/Tenants.vue': 1,
    'src/features/jobs/views/JobSearch.vue': 1,
    'src/features/resume/views/ResumeUpload.vue': 1,
  },
  themeCompatWildcards: 27,
  themeImportantOverrides: 56,
  /* 视图侧的色值预算有三条（style/script/template），但把 `#fff` 从视图**上提到 src/styles/ 的
     某个 .css** 就能全部绕过——而视图预算按文件路径记账，上提还会让它看起来"还了债"。
     这条按整个样式层记一笔总量，与视图侧同尺子（`#hex` + `rgba(`）。 */
  themeColorLiterals: 124,
  /* D76 用浏览器探针把三条"视图自己重写 .page-shell"判死并删掉（KnowledgeBase /
     DeliveryGuide / SystemStatus，各自 matched=0、删→比 46 条计算属性+rect=0 差异、塞回=0 差异），
     22 → 19。这一维以前只有上限、没有"还完必须调小"，所以那 3 的下降本来会静悄悄。 */
  pageShellRedeclarations: 19,
  /* `viewsBypassingApiLayer` 这个键在 §10.22 落地后**删掉了**：那一维以前复用 `viewSources`
     （被 `JS_OUT_OF_SCOPE_ROOTS` 豁免了 `src/stores`），所以它的 `0` 只说得出"视图没绕过"。
     现在那条守卫自带文件集、判据是硬零，不需要一个预算数字在旁边。 */
}

function vueFiles(dir, exts = ['.vue']) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return vueFiles(full, exts)
    return exts.some((e) => entry.name.endsWith(e)) ? [full] : []
  })
}

/* 拆页的落点：§7 阶段 2 把视图的逻辑往 `src/features/<域>/{lib,components,composables}` 和
   `src/composables/` 里搬。所有预算原先只数 .vue，于是"把一段债搬进 .js"既能躲过色值尺子，
   又能让"还完债必须调小预算"那条把少掉的数字当成新基线——同一把尺子的第五种盲区，且这次是
   我们自己即将造成的。把这两个根一起纳入扫描后实测：目前 .js 层的色值 / 静默 catch / 令牌 /
   状态色表 / 日期格式化全部为 0，纳管不需要任何预算数字。
   刻意不扫 src/utils、src/api 等：那里 scoreTone/statusTone 是色表的**法定归宿**、format/date 与
   lastSelection 是被这些尺子指定出去的替代品、api/* 本来就该 import request.js——纳入会把解药当病计数。 */
const toRel = (full) => full.split(path.sep).join('/')

/* 拆页的落点：§7 阶段 2 把视图的逻辑往 `src/features/<域>/{lib,components,composables}` 和
   `src/composables/` 里搬。所有预算原先只数 .vue，于是"把一段债搬进 .js"既能躲过色值尺子，
   又能让"还完债必须调小预算"那条把少掉的数字当成新基线——同一把尺子的第五种盲区，且这次是我们
   自己即将造成的。所以 .js 默认全扫，只列出**法定解药所在的根**：scoreTone/statusTone 是色表被
   指定过去的归宿、format/date 与 lastSelection 是这几把尺子指定出去的替代品、api/* 本来就该
   import request.js——把它们当病计数会把解药算成债。实测纳入后 .js 层的色值 / 静默 catch /
   令牌 / 状态色表 / 日期格式化为 0，纳管不需要新增任何预算数字。 */
const JS_OUT_OF_SCOPE_ROOTS = ['src/api', 'src/plugins', 'src/router', 'src/stores', 'src/utils']
const isOutScope = (rel) => JS_OUT_OF_SCOPE_ROOTS.some((root) => rel.startsWith(`${root}/`))

const viewSources = [
  ...vueFiles('src/features'),
  ...vueFiles('src/layouts'),
  ...vueFiles('src', ['.js'])
    .map(toRel)
    .filter((rel) => !isOutScope(rel)),
].map((full) => {
  const source = readFileSync(full, 'utf8')
  // The template block is everything before <script: a lazy `</template>` match would
  // stop at the first slot template (`<template #default>`), under-counting views.
  const scriptAt = source.search(/<script/)
  if (scriptAt < 0) return { rel: toRel(full), style: '', script: source, template: '', source }
  return {
    rel: toRel(full),
    style: (source.match(/<style[\s\S]*?<\/style>/g) || []).join('\n'),
    script: (source.match(/<script[\s\S]*?<\/script>/g) || []).join('\n'),
    template: source.slice(0, scriptAt),
    source,
  }
})

function colorCounts(blockKey) {
  const actual = {}
  for (const block of viewSources) {
    const text = block[blockKey] || ''
    const n =
      (text.match(/#[0-9a-fA-F]{3,8}\b/g) || []).length + (text.match(/\brgba?\(/g) || []).length
    if (n) actual[block.rel] = n
  }
  return actual
}

const themeCss = readFileSync('src/styles/main.css', 'utf8')

/** 整个样式层（src/styles/*.css）里写死的色值，与视图侧用同一把尺子。 */
function themeColorLiteralCount() {
  return readdirSync('src/styles')
    .filter((f) => f.endsWith('.css'))
    .reduce((n, f) => {
      const src = readFileSync(path.join('src/styles', f), 'utf8')
      return (
        n +
        (src.match(/#[0-9a-fA-F]{3,8}\b/g) || []).length +
        (src.match(/\brgba?\(/g) || []).length
      )
    }, 0)
}

/* 视图自己重写 `.page-shell` 的文件数——它本该只由 `styles/panels.css` 给一次。 */
function pageShellCount() {
  return viewSources.filter(({ style }) => /^\s*\.page-shell\s*[,{]/m.test(style)).length
}

/* 失败被清成空态：`request.js` 只对**非 GET** 弹提示（`notifyError !== false && method !== 'get'`），
   所以 `catch { list.value = [] }` 这种写法会把一次 500 渲染成页面自己的"暂无数据"文案。
   数出来的每条都是待收的谎，只能往下走。

   "这一处到底报告了没有"看的是**本函数剩余部分**，不是固定的 12 行。旧口径往后看 12 行，会把邻居函数
   里的 `localError.value =` / `ElMessage` 当成这一处的报告：D10 用实验量到它会漏数（当时 3 → 7），
   D13 那次纯格式化又让它现形一处（admin/Tenants 的 loadDomains）。catch 之后**新开的**嵌套函数体同样
   跳过，否则又会栽在邻居 `seedData()` 的提示上——那正是 D10 记下的假阳性来源。

   已知盲区（不要把这个数字当"全部修完"）：它只看 catch 体里清值的写法，看不见两类同病——
   1) try 之前先清值、catch 里只留注释（SalaryInsight 曾写"保留上一次结果"，其实既没保留也没提示，
      D6 已修并有测试）；2) 值原样留着不删，于是新输入配旧答案。
   所以这条预算是下限，不是全集；改注释型谎用时请连行为一起改。 */
const CATCH_HEAD = /^\s*\}\s*catch/
const CLEARS_VALUE = /=\s*(\[\]|null|''|0)\s*;?\s*$/
/* D92 之后"把失败报出来"的写法换成了单一出口 `userErrorCopy(e, '…')`，它不再在行里留下
   `userMessage` 这个字面——只认字面的判据会把"其实报了失败"的 catch 数成静默（实测红在
   `ResumeUpload.vue` 两处）。判据要认的是**行为**：这一族现在有两种写法，都算报了。
   反向证据在下面那条 selftest 里，两式各测一次。 */
const REPORTS = /userMessage|userErrorCopy\(|loadError|\w*Error\.value\s*=|ElMessage|console\./
const BLOCK_HEAD = /^(?:if|for|while|switch|case|catch|else|try|finally|do|with|return)\b/
const FUNCTION_HEAD = /\bfunction\b|=>|\b[\w$.]+\s*\([^()]*\)\s*\{?\s*$/

/* 花括号配对，给出"函数体"的行区间。模板的 `{{ }}` 与 CSS 块也参与配对，但它们的块头既没有 `=>`
   也没有 `名字(...)`，所以不会冒充函数；`} catch (e) {` 这类要先剥掉行首的括号才判得对。 */
function functionRanges(lines) {
  const stack = []
  const ranges = []
  lines.forEach((line, i) => {
    for (let k = 0; k < line.length; k++) {
      if (line[k] === '{') {
        const head = line
          .slice(0, k)
          .trim()
          .replace(/^[})\]]+\s*/, '')
        stack.push({ fn: !BLOCK_HEAD.test(head) && FUNCTION_HEAD.test(head), start: i })
      } else if (line[k] === '}') {
        const top = stack.pop()
        if (top?.fn) ranges.push({ start: top.start, end: i })
      }
    }
  })
  return ranges
}

/** 一个文件里"失败被清成空态、且本函数内没有任何报告"的 catch 行号（1 起）。 */
function silentCatchesIn(source) {
  const lines = source.split(/\r?\n/)
  const ranges = functionRanges(lines)
  const found = []
  for (let i = 0; i < lines.length; i++) {
    if (!CATCH_HEAD.test(lines[i])) continue
    let depth = 1
    const body = []
    let j = i
    for (j = i + 1; j < lines.length && depth > 0; j++) {
      for (const ch of lines[j]) {
        if (ch === '{') depth++
        else if (ch === '}') depth--
      }
      if (depth > 0) body.push(lines[j])
    }
    const commented = body.length > 0 && body.every((l) => /^\s*(\/\/|\/\*|\*)/.test(l))
    if (!body.some((l) => CLEARS_VALUE.test(l)) || commented) continue
    // 内层函数：包住这个 catch 的那一层（catch 体结束在 j-1）
    const owner = ranges
      .filter((r) => r.start <= i && r.end >= j - 1)
      .sort((a, b) => b.start - a.start || a.end - b.end)[0]
    const upto = owner ? owner.end : lines.length - 1
    const rest = []
    for (let k = j; k <= upto; k++) {
      if (ranges.some((r) => r.start >= j && r.start < k && r.end >= k)) continue
      rest.push(lines[k])
    }
    if (!REPORTS.test(`${body.join('\n')}\n${rest.join('\n')}`)) found.push(i + 1)
  }
  return found
}

function silentCatchCounts() {
  const actual = {}
  for (const { rel, source } of viewSources) {
    const n = silentCatchesIn(source).length
    if (n) actual[rel] = n
  }
  return actual
}

/* 一个令牌实例只管一条链。`useLatestCall()` 里的计数器是**整个实例共享**的，所以两个不同的加载函数
   领同一份令牌时，症状不是"旧的盖掉新的"，而是"两条都不写"：后发起的那条把仍在途的前一条判为过期，
   前一条连 `finally` 里的解 loading 都带着条件，于是列表永久空着。D30 在 JobSearch 量到的即此
   （切到「智能推荐」把在途的岗位仓库响应一起废掉，hero 的"岗位仓库"数字停在 0）。 */
const TOKEN_DECL = /^\s*const\s+(\w+)\s*=\s*useLatestCall\(\)/
const tokenClaim = (name) => new RegExp(`(?<![\\w$.])${name}\\(\\s*\\)`)

/** 按令牌实例名分组，给出它在哪些函数体里被领走。 */
function tokenClaimsByInstance(source) {
  const lines = source.split(/\r?\n/)
  const names = lines.map((line) => TOKEN_DECL.exec(line)?.[1]).filter(Boolean)
  if (!names.length) return {}
  const ranges = functionRanges(lines)
  const ownerOf = (i) => {
    const inner = ranges
      .filter((r) => r.start <= i && r.end >= i)
      .sort((a, b) => b.start - a.start)[0]
    return inner ? `${inner.start}:${inner.end}` : `top:${i}`
  }
  const claims = {}
  lines.forEach((line, i) => {
    if (TOKEN_DECL.test(line) || /^\s*\/\//.test(line)) return
    for (const name of names) {
      if (tokenClaim(name).test(line)) (claims[name] ||= new Set()).add(ownerOf(i))
    }
  })
  return claims
}

/* 手写"状态 → el-tag 颜色"的条目数，见 BUDGET.statusTagEntries 的口径说明。
   键可以是中文（`高: 'danger'`）、可以带引号，颜色后面可以有逗号，但**整条不锚行**。
   旧规则锚了行，于是同一个色表换行就换个数，而且有 47 条从来没被数到。 */
const STATUS_TAG_ENTRY =
  /(?:'[^']+'|"[^"]+"|[\w$一-龥]+)\s*:\s*'(?:primary|success|info|warning|danger)'/g

function statusTagCounts() {
  const actual = {}
  for (const { rel, script } of viewSources) {
    const n = (script.match(STATUS_TAG_ENTRY) || []).length
    if (n) actual[rel] = n
  }
  return actual
}

function staleBudgets(actual, budget) {
  return Object.entries(budget).filter(([file, allowed]) => (actual[file] || 0) < allowed)
}

describe('style debt ratchet', () => {
  /* 色值有三个藏身处：<style>、<script> 里的字符串、以及模板属性。前两处各吃过一次
     "预算看不见"（六套分数色板活了很久；OfferCompare 删了规则却还在发 class），
     模板是第三次。三条预算由同一对测试驱动，再加维度只要多一行。

     成对测试也让"抽取坏了"无法蒙混过关：如果 template 块取空，增长那条会绿，
     但"预算比现实松"那条会把 6 个文件全报出来。 */
  const COLOR_BUDGETS = [
    { block: 'style', key: 'hardcodedColorLiterals', hint: 'use a var(--app-*) token instead' },
    {
      block: 'script',
      key: 'scriptColorLiterals',
      hint: 'score colour belongs in utils/scoreTone',
    },
    {
      block: 'template',
      key: 'templateColorLiterals',
      hint: 'colour hardcoded in a template attribute',
    },
  ]

  for (const { block, key, hint } of COLOR_BUDGETS) {
    it(`keeps ${key} within the per-file budget`, () => {
      const actual = colorCounts(block)
      const grown = Object.entries(actual).filter(([file, n]) => n > (BUDGET[key][file] ?? 0))
      expect(grown, `${hint} — budget exceeded: ${JSON.stringify(grown)}`).toEqual([])
    })

    it(`forces ${key} to be tightened once debt is paid down`, () => {
      const actual = colorCounts(block)
      const stale = staleBudgets(actual, BUDGET[key]).map(
        ([file, allowed]) => `${file}: ${allowed} -> ${actual[file] || 0}`
      )
      expect(
        stale,
        `budget is looser than reality, lower these in BUDGET: ${stale.join(', ')}`
      ).toEqual([])
    })
  }

  it('keeps hand-written status -> tag colour maps within budget', () => {
    const actual = statusTagCounts()
    const grown = Object.entries(actual).filter(
      ([file, n]) => n > (BUDGET.statusTagEntries[file] ?? 0)
    )
    expect(
      grown,
      `new status colour map — shared states belong in utils/statusTone: ${JSON.stringify(grown)}`
    ).toEqual([])
  })

  it('forces the status colour budget to be tightened once paid down', () => {
    const actual = statusTagCounts()
    const stale = staleBudgets(actual, BUDGET.statusTagEntries).map(
      ([file, allowed]) => `${file}: ${allowed} -> ${actual[file] || 0}`
    )
    expect(
      stale,
      `status budget is looser than reality, lower these in BUDGET: ${stale.join(', ')}`
    ).toEqual([])
  })

  /* 日期格式化：迁移前 18 份副本散在 16 个文件里，其中一份还漏掉了 locale（同一条时间戳
     在英文浏览器上会变成美式排版）。现在视图与布局里不许再出现 Intl/toLocale*。 */
  it('keeps date formatting out of views', () => {
    const offenders = viewSources
      .filter(({ script, template }) =>
        /toLocaleDateString|toLocaleTimeString|toLocaleString|Intl\.DateTimeFormat/.test(
          `${script}${template}`
        )
      )
      .map(({ rel }) => rel)
    expect(
      offenders,
      `use utils/format/date (monthDay / monthDayTime / dateTime / compactDateTime / utcStamp / rawStamp / isoMonthDay): ${offenders.join(
        ', '
      )}`
    ).toEqual([])
  })

  it('never hands a JD id to the analysis-detail route', () => {
    // `/analysis/:id` 打开的是 `getAnalysis(id)` → 后端按 AnalysisRecord.id 取记录。
    // 简历中心的诊断弹窗以前有个按钮往这条路由里塞 jd_id：诊断接口从不返回 jd_id，
    // 所以它永远渲染不出来；而一旦返回，候选人看到的就是 id 恰好撞上的**另一条**分析记录。
    const offenders = viewSources
      .filter(({ script, template }) =>
        /\/analysis\/\$\{[^}]*jd[^}]*\}/i.test(`${script}${template}`)
      )
      .map(({ rel }) => rel)
    expect(
      offenders,
      `/analysis/:id wants an AnalysisRecord id, never a JD id — link to the record the action produced, or do not offer the jump: ${offenders.join(
        ', '
      )}`
    ).toEqual([])
  })

  it('ships no GBK-mis-decoded (mojibake) UI strings', () => {
    // 判据不靠手写坏字清单，也不要求能复原（有的坏串已经吞掉字节，复原不出来）：只要有一段 3 字
    // 的 CJK 连续窗口里连一个高频字（本仓出现 >=5 次）都没有，就不可能是人写的。
    // 为什么不扩到 .md：散文里生僻字连排是合法的（实测本仓 2 处误报），而文档乱码到不了候选人眼前。
    // 为什么后端守卫只看字符串字面量：整行口径的误报全在注释里（"撞车干扰""回落默认租户"）。
    // 第二条腿是结构性的：串里出现私用区码位（U+E000-U+F8FF）或 U+FFFD 即判红。正常中文文案不可能
    // 用到私用码位，而 GBK 的用户自定义行（0xAA-0xF7）在 CP936 解码下正好落到那里——`JobSearch.vue:972`
    // 的 `建议` 坏成了 U+5BE4 U+9E3F U+E185，第三个字把 CJK 游程截断成 2 字，3 字滑窗从此看不见它。
    // 为什么不能把窗口降到 2 字：实测本仓有 14 个正常的 2 字游程两字都不在高频表里（硕士/博士/北京/
    // 封装/剩余/左右…），降窗口就是把守卫改成误报器。私用区这条没有误报面：`git grep -InP
    // "[\x{e000}-\x{f8ff}\x{fffd}]"` 打到 551 个跟踪文件只命中一处，而那一处正是滑窗漏掉的（修复后 0 命中）。
    const walk = (dir, out = []) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name)
        if (entry.isDirectory()) walk(full, out)
        else if (/\.(vue|js)$/.test(entry.name))
          out.push({ rel: full.split(path.sep).join('/'), text: readFileSync(full, 'utf8') })
      }
      return out
    }
    // index.html 也算：它是浏览器标签与首屏文案，候选人第一眼看的就是它
    const files = [...walk('src'), { rel: 'index.html', text: readFileSync('index.html', 'utf8') }]
    const freq = new Map()
    for (const { text } of files) {
      for (const ch of text) if (ch >= '一' && ch <= '鿿') freq.set(ch, (freq.get(ch) || 0) + 1)
    }
    // 私用区码位（U+E000-U+F8FF）与替换符不可能出现在人写的中文文案里，它们只来自一次误读；
    // 这条腿不看频率、不要求能复原，专治"游程被私用字截短到 3 字以下"的那一类。
    const PRIVATE_USE = /[\uE000-\uF8FF\uFFFD]/
    // 第三条腿：短游程的"可复原"判据。1-2 字的坏串频率法看不见——U+8DEF 这个字是全仓高频字，
    // 而它正是 `·`（UTF-8 的 C2 B7）被按 GBK 读回的结果，游程又只有 1 字。做法：把每个字反查回
    // GBK 字节，再严格按 UTF-8 解一次；解出来**不含任何字母或组合符号**（即只剩标点/符号/ASCII）才算误读。
    // 为什么必须带"不含字母"这一条：同一批 1155 个 1-2 字游程里，只看"能复原"命中 53 处，其中 46 处
    // 是正常词（状态/未知/专业/每页/硕士/平台… 它们的 GBK 字节恰好也是合法 UTF-8）；加上这一条之后
    // 命中 7 处、误报 0，而那 7 处全是同一个分隔符。3 字以上仍交给频率那条腿。
    const LETTER_OR_MARK = /\p{L}|\p{M}/u
    const MAXIMAL_CJK_RUN = new RegExp(
      `[${String.fromCharCode(0x3400)}-${String.fromCharCode(0x9fff)}]+`,
      'g'
    )
    const GBK_BYTES = new Map()
    {
      const dec = new TextDecoder('gbk', { fatal: false })
      const pair = new Uint8Array(2)
      for (let lead = 0x81; lead <= 0xfe; lead++) {
        for (let second = 0x40; second <= 0xfe; second++) {
          if (second === 0x7f) continue
          pair[0] = lead
          pair[1] = second
          const s = dec.decode(pair)
          if (s.length === 1 && s.codePointAt(0) !== 0xfffd && !GBK_BYTES.has(s))
            GBK_BYTES.set(s, [lead, second])
        }
      }
    }
    const UTF8_STRICT = new TextDecoder('utf-8', { fatal: true })
    // 复原出来的字符必须是"这个仓库真写得出来的字符"：`说` 的 GBK 字节 CBB5 也是合法 UTF-8，
    // 解出来是 U+02F5——它不是字母也不是组合符号（类别 Sk），光靠上一条会漏进来。而 U+02F5 在本仓
    // 出现 0 次，`·` 出现 85 次，用"有没有人这么写过"分得开，且不需要列任何清单。
    const WRITTEN = new Map()
    for (const { text } of files) for (const ch of text) WRITTEN.set(ch, (WRITTEN.get(ch) || 0) + 1)

    function shortRunMisDecoded(line) {
      for (const run of line.match(MAXIMAL_CJK_RUN) || []) {
        if (run.length > 2) continue
        const bytes = []
        let known = true
        for (const ch of run) {
          const b = GBK_BYTES.get(ch)
          if (!b) {
            known = false
            break
          }
          bytes.push(b[0], b[1])
        }
        if (!known) continue
        let back
        try {
          back = UTF8_STRICT.decode(new Uint8Array(bytes))
        } catch {
          continue // 解不出合法 UTF-8，就不是误读
        }
        if (back === run || LETTER_OR_MARK.test(back)) continue
        if (![...back].every((c) => (WRITTEN.get(c) || 0) >= 1)) continue
        return true
      }
      return false
    }
    const suspicious = (line) => {
      if (PRIVATE_USE.test(line)) return true
      if (shortRunMisDecoded(line)) return true
      if (line.includes('€')) return true
      // 用 3 字**滑窗**而不是整串：乱码嵌在正常句子里时，整串会被周围的高频字（"的"这类）掩护过去
      // ——这条是我把坏串种进 index.html 的 <title> 才发现的，整串口径当时放过了它。
      // 已知漏报：乱码串里任意 3 字窗口都混进了高频字；想靠"罕见字比例"收紧会误伤"熟练掌握"，放弃。
      for (const run of line.match(/[㐀-鿿]{3,}/g) || []) {
        const chars = [...run]
        for (let i = 0; i + 3 <= chars.length; i++) {
          if (!chars.slice(i, i + 3).some((ch) => (freq.get(ch) || 0) >= 5)) return true
        }
      }
      return false
    }
    const isComment = (line) => /^\s*(\/\/|\*|\/\*|<!--)/.test(line)
    const offenders = files
      .map(({ rel, text }) => {
        // 注释里的生僻词（如"咖啡馆"）不是会到用户眼前的文案，跳过后误报面更小
        const i = text.split(/\r?\n/).findIndex((l) => !isComment(l) && suspicious(l))
        return i < 0 ? null : `${rel}:${i + 1}`
      })
      .filter(Boolean)
    expect(
      offenders,
      `这些行的中文是被按 GBK 读回后另存的乱码，候选人看到的就是这串生僻字：${offenders.join(', ')}`
    ).toEqual([])
    // 判据自身的非空性：嵌在正常句子里的乱码必须抓得到，正常文案必须放过
    expect(suspicious('<title>AI 驱动的涓汉姹傛暀缁</title>')).toBe(true)
    expect(suspicious('<title>AI 驱动的个人求职教练</title>')).toBe(false)
    expect(suspicious('TIP = "熟练掌握"')).toBe(false)
    // 私用区这条腿的两方向自证。正例就是 JobSearch.vue:972 当年的实际码位序列：三个字里最后那个
    // 落在私用区，于是 CJK 游程只剩 2 字，滑窗这条腿从一开始就看不见它（频率窗口降到 2 字又会误伤
    // 14 个正常词，所以补的不是窗口，是这条结构判据）。码位用 fromCodePoint 拼，避免把坏字符写进源码。
    const GARBLED = String.fromCodePoint(0x5be4, 0x9e3f, 0xe185)
    const RESTORED = String.fromCodePoint(0x5efa, 0x8bae)
    expect(suspicious(`<span>${GARBLED}</span>`)).toBe(true)
    expect(suspicious(`<span>${RESTORED}</span>`)).toBe(false)
    expect(suspicious(`msg = "对接上游${String.fromCodePoint(0xfffd)}服务"`)).toBe(true)
    // 第三条腿的两方向自证：分隔符被误读成高频字必须抓到；"能复原、但复原出来是字母"的正常词必须放过
    const SEP = String.fromCharCode(0x8def) // 路 <- GBK 读回的 C2 B7，也就是 `·`
    expect(suspicious(`<span>优先投递 ${SEP} 83</span>`)).toBe(true)
    expect(suspicious('<span>优先投递 · 83</span>')).toBe(false)
    expect(suspicious('<el-table-column label="状态" />')).toBe(false) // 能复原成字母串，放过
    expect(suspicious('<span>每页 20 条</span>')).toBe(false) // 同上
    // 这条是"复用"条件存在的理由：`说` 复原成 U+02F5，既不是字母也不是组合符号，但本仓从不写它
    expect(suspicious(`TAG = "说 JD 要求全缺"`)).toBe(false)
  })

  const panelHeaderCount = () =>
    viewSources.reduce(
      (sum, { template, script }) =>
        sum + (`${template}${script}`.match(/class="panel-header"/g) || []).length,
      0
    )

  it('keeps hand-rolled panel markup from growing past the AppPanel ledger', () => {
    const n = panelHeaderCount()
    expect(
      n,
      `a new hand-written .panel-header appeared — use components/ui/AppPanel.vue, or lower this budget only with a reason: ${n} > ${BUDGET.handRolledPanelHeaders}`
    ).toBeLessThanOrEqual(BUDGET.handRolledPanelHeaders)
  })

  it('forces the panel-markup ledger down as sites migrate', () => {
    const n = panelHeaderCount()
    expect(
      n < BUDGET.handRolledPanelHeaders,
      `panel markup was paid down — lower BUDGET.handRolledPanelHeaders to ${n}`
    ).toBe(false)
  })

  it('never lets a view style .panel-header locally without saying so in the ledger', () => {
    // 这条是 AppPanel 的真正约束：视图自己的 scoped `.panel-header` 规则匹配不到搬进子组件的节点，
    // 所以这些文件必须先解决覆盖才能迁移。清单只准缩短，且必须与实际一致。
    /* §10.14 决定 ③（D96）：候选人侧那三页（JobSearch 1 + Register 1 + Privacy 2 处）的本地覆盖
       搬进了 `panels.css` 的页根作用域，所以这里只剩 §2 冻结侧的两个文件。
       **清单变短不是"债变少了"的凭证**——那 4 处头部标记还在原地，只是它们不再挡住迁移判定。 */
    const LOCAL_OVERRIDE_FILES = [
      'src/features/knowledge/views/KnowledgeBase.vue',
      'src/features/billing/views/OrganizationWorkspace.vue',
    ]
    const overriding = viewSources
      // 先剥掉 CSS 注释：一条"这条规则已搬走"的说明不该被当成还在覆盖（与后端乱码守卫
      // 只看 ast 字面量、不看注释是同一个口径）
      .filter(({ style }) => /\.panel-header\b/.test(style.replace(/\/\*[\s\S]*?\*\//g, '')))
      .map(({ rel }) => rel)
      .sort()
    expect(overriding, `视图里 .panel-header 的本地覆盖变了，台账要一起改：${overriding}`).toEqual(
      [...LOCAL_OVERRIDE_FILES].sort()
    )
  })

  it('keeps the cross-page "last selection" handoff inside utils/lastSelection', () => {
    // 匹配字段名而不是完整键名：`storageKey('lastResumeId')` 这种自己拼前缀的写法要一起抓到。
    const offenders = viewSources
      .filter(({ script, template }) => /last(ResumeId|JDId|RecordId)/.test(`${script}${template}`))
      .map(({ rel }) => rel)
    expect(
      offenders,
      `read/write the last resume / JD / record id through @/utils/lastSelection — it slots these per logged-in user, which a raw localStorage key cannot, and a stale foreign id gets prefilled into a form: ${offenders.join(
        ', '
      )}`
    ).toEqual([])
  })

  it('never lets one race-token instance serve two loading functions', () => {
    const offenders = viewSources
      .flatMap(({ rel, source }) =>
        Object.entries(tokenClaimsByInstance(source))
          .filter(([, owners]) => owners.size > 1)
          .map(([name, owners]) => `${rel}: ${name} (${owners.size} 条链)`)
      )
      .sort()
    expect(
      offenders,
      `一个 useLatestCall() 实例被多条链共用，后发起的那条会把前一条仍在途的响应整个废掉 —— 每条链各建一个实例：${offenders.join(', ')}`
    ).toEqual([])
  })

  it('keeps "failure cleared into an empty state" within budget', () => {
    const actual = silentCatchCounts()
    const grown = Object.entries(actual).filter(
      ([file, n]) => n > (BUDGET.silentEmptyCatches[file] ?? 0)
    )
    expect(
      grown,
      `a failed load now reads as "no data" — GET failures are never toasted, render AppLoadError instead: ${JSON.stringify(grown)}`
    ).toEqual([])
  })

  it('forces the silent-empty budget to be tightened once paid down', () => {
    const actual = silentCatchCounts()
    const stale = staleBudgets(actual, BUDGET.silentEmptyCatches).map(
      ([file, allowed]) => `${file}: ${allowed} -> ${actual[file] || 0}`
    )
    expect(
      stale,
      `silent-empty budget is looser than reality, lower these in BUDGET: ${stale.join(', ')}`
    ).toEqual([])
  })

  /* 把"往后看 12 行"换成"看到本函数结束"这件事，两个方向都要有对照组，否则收窄窗口可以悄悄
     变成"什么都看不见"。用合成源码，不依赖任何视图。 */
  it('counts a report anywhere later in the same function as a report', () => {
    const src = [
      'async function loadThings() {',
      '  try {',
      '    things.value = await api.get()',
      '  } catch (e) {',
      '    things.value = []',
      '  }',
      // 报告落在第 21 行：远超旧口径的 12 行窗口，但它就在同一个函数里
      ...Array.from({ length: 14 }, (_, k) => `  const pad${k} = ${k}`),
      '  loadError.value = e?.userMessage',
      '}',
    ].join('\n')
    expect(silentCatchesIn(src)).toEqual([])
  })

  it('recognises the single-source copy call as a report (D92)', () => {
    /* 两式各测一次，谁也不许被当成静默；第三份是"两种都没有"的对照组，
       否则这条判据可以靠"什么都算报告"变绿。 */
    const both = (reportLine) =>
      silentCatchesIn(
        [
          'async function loadThings() {',
          '  try {',
          '    things.value = await api.get()',
          '  } catch (e) {',
          '    things.value = []',
          '  }',
          reportLine,
          '}',
        ].join('\n')
      )
    expect(both("  rewrite.error = userErrorCopy(e, '改写建议生成失败')")).toEqual([])
    expect(both('  loadError.value = e?.userMessage')).toEqual([])
    expect(both('  const note = `读不到`')).toEqual([4])
  })

  it('does not borrow a report from the next function', () => {
    const src = [
      'async function loadThings() {',
      '  try {',
      '    things.value = await api.get()',
      '  } catch (e) {',
      '    things.value = []',
      '  }',
      '}',
      'function seedData() {',
      "  ElMessage.success('已补充')",
      '}',
    ].join('\n')
    // 这正是 JobSearch.vue 当年被放过的方式：邻居函数里的 searchError.value = 被当成了报告
    expect(silentCatchesIn(src)).toEqual([4])
  })

  it('does not borrow a report from a nested function opened after the catch', () => {
    const src = [
      'async function loadThings() {',
      '  try {',
      '    things.value = await api.get()',
      '  } catch (e) {',
      '    things.value = []',
      '  }',
      '  const paint = () => {',
      "    ElMessage.success('画好了')",
      '  }',
      '  paint()',
      '}',
    ].join('\n')
    expect(silentCatchesIn(src)).toEqual([4])
  })

  it('does not let the theme layer grow its class-name wildcards', () => {
    const n = (themeCss.match(/\[class\*=/g) || []).length
    expect(n).toBeLessThanOrEqual(BUDGET.themeCompatWildcards)
  })

  it('does not let the theme layer grow its !important overrides', () => {
    const n = (themeCss.match(/!important/g) || []).length
    expect(n).toBeLessThanOrEqual(BUDGET.themeImportantOverrides)
  })

  it('does not let hardcoded colours escape into the theme layer', () => {
    const n = themeColorLiteralCount()
    expect(
      n,
      `src/styles/ 里的写死色值变多了（${n} > ${BUDGET.themeColorLiterals}）——视图侧那三条预算挡不住"把颜色上提到全局 css"，所以这里封顶：新增语义色请做成 var(--app-*) token`
    ).toBeLessThanOrEqual(BUDGET.themeColorLiterals)
  })

  it('forces the theme colour budget to be tightened once paid down', () => {
    const n = themeColorLiteralCount()
    expect(
      n < BUDGET.themeColorLiterals,
      `样式层的色值少了——把 BUDGET.themeColorLiterals 降到 ${n}`
    ).toBe(false)
  })

  it('does not let views re-declare the shared .page-shell chrome', () => {
    expect(pageShellCount()).toBeLessThanOrEqual(BUDGET.pageShellRedeclarations)
  })

  /* D76 之前这一维只有上限、没有"还完必须调小"的同伴断言，所以删掉三条重复声明之后
     全套测试照样绿——天花板只是安静地松了 3。补上这一条，形状与其它四把尺子一致。 */
  it('forces the page-shell budget to be tightened once paid down', () => {
    const n = pageShellCount()
    expect(
      n < BUDGET.pageShellRedeclarations,
      `视图里 .page-shell 的重复声明少了——把 BUDGET.pageShellRedeclarations 降到 ${n}`
    ).toBe(false)
  })

  /* 上面每一条预算都只扫 src/features 与 src/layouts。§7 阶段 2 这轮已经把视图按 feature 搬进 src/features/，
     搬完忘了改这两个根的话，预算不是报错而是安静地少测一批文件——"还完债必须把预算调小"那条
     还会把少掉的数字固化成新基线。这条把"根之外还有哪些 .vue"钉死：多出一个不进预算的 .vue，
     必须先在这里说清它为什么不进。 */
  it('scans every .vue under src except the listed shell and ui components', () => {
    const UNSCANNED = [
      'src/App.vue',
      'src/components/ui/AppLoadError.vue',
      'src/components/ui/AppPanel.vue',
    ]
    const scanned = viewSources.map(({ rel }) => rel)
    const missing = vueFiles('src')
      .map((full) => full.split(path.sep).join('/'))
      .filter((rel) => !scanned.includes(rel))
      .sort()
    expect(
      missing,
      `这些 .vue 不在任何预算的扫描范围里：把它们纳入 viewSources，或在这里写明为什么不进预算：${missing.join(', ')}`
    ).toEqual(UNSCANNED)
  })

  /* 上一条只管 .vue。拆页搬出去的是 .js，所以"新根没人管"这条路要单独钉：
     src 下任何 .js 默认被扫，除非它在 JS_OUT_OF_SCOPE_ROOTS 列出的法定解药根里。
     新开一个放逻辑的根却没在这里出现，这条会红。 */
  it('scans every .js outside the listed helper roots', () => {
    const scanned = viewSources.map(({ rel }) => rel)
    const unswept = vueFiles('src', ['.js'])
      .map(toRel)
      .filter((rel) => !scanned.includes(rel) && !isOutScope(rel))
      .sort()
    expect(
      unswept,
      `这些 .js 既没进预算扫描，也不在 JS_OUT_OF_SCOPE_ROOTS 里：${unswept.join(', ')}`
    ).toEqual([])
  })

  it('does not let anything outside the api layer import the shared request instance', () => {
    /* §10.22 拍的那条 ②：这一维**不再复用** `viewSources`。`viewSources` 为了让色值/日期那几把尺子
       不去数法定解药（`src/api`、`src/plugins`、`src/router`、`src/stores`、`src/utils`），把
       `src/stores` 整根豁免了，于是那 5 处裸 `request` 顺手也被豁免——报出来的 `0` 只说得出"视图没绕过"，
       说不出"只有 api 层出网"。现在换成自带文件集：扫 `src` 下全部 `.vue` 与 `.js`，
       只豁免 `src/api` 与 `src/plugins` 两根。豁免面从 5 个根缩到 2 个，是有意的收紧。 */
    const EXEMPT = ['src/api/', 'src/plugins/']
    const offenders = [...vueFiles('src', ['.vue', '.js'])]
      .map(toRel)
      .filter((rel) => !EXEMPT.some((root) => rel.startsWith(root)))
      .filter((rel) =>
        /from '@\/api\/request'|from '\.\/request'|from '\.\.\/request'/.test(
          readFileSync(rel, 'utf8')
        )
      )
      .sort()
    expect(
      offenders,
      `只有 src/api 与 src/plugins 可以 import 那个共享 axios 实例，这些地方还在绕过 api 层：${offenders.join(
        ', '
      )}`
    ).toEqual([])
  })

  it('keeps pure-white surfaces tokenized', () => {
    const offenders = viewSources
      .filter(({ style }) => /background(?:-color)?:\s*(?:#fff|#ffffff|white)\s*;/.test(style))
      .map(({ rel }) => rel)
    expect(offenders, `use var(--app-surface-strong): ${offenders.join(', ')}`).toEqual([])
  })

  /* 上一版改动删掉了 .score-high/.score-mid/.score-low 的规则，却留下一个函数继续发
     这些 class，于是"加权综合评分"就此失去颜色。hex 预算数不到这种事——它数的是色值，
     不是"发了没人接的类名"。这里把视图实际发出的 tone 前缀和五个档位绑成契约。 */
  const TONES = ['high', 'good', 'warn', 'risk', 'unknown']
  const styleOf = (rel) => viewSources.find((v) => v.rel === rel)?.style ?? ''
  const sourceOf = (rel) => viewSources.find((v) => v.rel === rel)?.source ?? ''
  /* 前两个前缀的规矩住在主题层；后两个住在**发出这个 class 的那个文件自己**的 <style> 里。
     D64/D66 把看板列与实录那块搬进组件之后，`.score-level--*` 与 `.score-chip--*` 的规则跟着
     markup 一起走了（页面里那份成了 0 命中，D67 已删），所以这里改成指向真正的主人，
     并且额外钉一条"这个文件确实发出这个前缀"——否则下次搬家又会把指针留在一个不再发 class
     的文件上，这条守卫就悄悄变成永远为真的空检查。 */
  const TONE_CLASS_SITES = [
    { prefix: 'score-tone', css: themeCss, where: 'src/styles/main.css' },
    { prefix: 'score-fill', css: themeCss, where: 'src/styles/main.css' },
    {
      prefix: 'score-chip',
      css: styleOf('src/features/interview/components/TranscriptPane.vue'),
      where: 'TranscriptPane.vue',
      emitsIn: 'src/features/interview/components/TranscriptPane.vue',
    },
    {
      prefix: 'score-level',
      css: styleOf('src/features/pipeline/components/ListPane.vue'),
      where: 'ListPane.vue',
      emitsIn: 'src/features/pipeline/components/ListPane.vue',
    },
  ]

  it('gives every tone a rule for each class prefix a view emits', () => {
    const missing = []
    for (const { prefix, css, where, emitsIn } of TONE_CLASS_SITES) {
      for (const tone of TONES) {
        if (!new RegExp(`\\.${prefix}--${tone}\\b`).test(css)) {
          missing.push(`${prefix}--${tone} (no rule in ${where})`)
        }
      }
      if (emitsIn && !sourceOf(emitsIn).includes(`'${prefix}'`)) {
        missing.push(`${prefix} (发出方已经不是 ${where}，指针该跟着搬)`)
      }
    }
    expect(missing, `emitted tone class with no rule: ${missing.join(', ')}`).toEqual([])
  })

  it('defines the full token set the tone classes and helpers reference', () => {
    const missing = []
    for (const tone of TONES) {
      for (const suffix of ['', '-fill', '-soft', '-soft-line']) {
        if (!themeCss.includes(`--app-score-${tone}${suffix}:`)) {
          missing.push(`--app-score-${tone}${suffix}`)
        }
      }
    }
    expect(missing, `main.css is missing score tokens: ${missing.join(', ')}`).toEqual([])
  })

  /* 拼出来的类名（`'dot-' + task.priority`、`` `severity-${item.severity}` ``）这一族，
     D76/D77 用静态尺子和浏览器快照都判不了：静态看不见后端的值域，单屏快照只证明"这一屏没渲染到"。
     所以域写在 `src/constants/states.js`（每个值标了后端出处），这里正反两个方向各钉一遍：
       正向 域里有的值，该文件必须有一条规则（或明写在 unstyled 里并给出理由）；
       反向 该文件里有的 `prefix-*` 规则，值必须在域内（或明写在 siblings 里 = 它不是状态类）。
     任何一侧多出来或删除，都会把另一侧的豁免条目要求同步删掉，所以豁免不会过期。 */
  const STATE_CLASS_SITES = [
    {
      prefix: 'dot',
      values: PRIORITY_LEVELS,
      file: 'src/features/shell/views/Home.vue',
      unstyled: [],
      siblings: [],
    },
    {
      // `partial` 后端会发（`strategies.py:459,602`、`langgraph_flow.py:438,500`）。
      // D78 咬出这一档没有点色时，它挂在 unstyled 里等拍；D79 已补规则，豁免同步撤掉——
      // 这条守卫的设计就是"补了规则不删豁免会红"，所以这里必须是空数组。
      prefix: 'dot',
      values: AGENT_TASK_STATUSES,
      file: 'src/features/shell/views/TaskCenter.vue',
      unstyled: [],
      siblings: [],
    },
    {
      prefix: 'confidence',
      values: CONFIDENCE_LEVELS,
      file: 'src/features/knowledge/views/KnowledgeBase.vue',
      unstyled: [],
      // 这四个是布局类，不是状态类
      siblings: ['grid', 'main', 'score', 'signals'],
    },
    {
      prefix: 'severity',
      values: SEVERITY_LEVELS,
      file: 'src/features/eval/views/RecommendationEval.vue',
      unstyled: [],
      siblings: [],
    },
    {
      prefix: 'action',
      values: SEVERITY_LEVELS,
      file: 'src/features/jobs/views/JobRecommend.vue',
      unstyled: [],
      siblings: ['list', 'item', 'detail', 'title'],
    },
  ]

  it('keeps concatenated state classes aligned with their backend value domain', () => {
    const problems = []
    for (const site of STATE_CLASS_SITES) {
      const css = styleOf(site.file)
      const source = sourceOf(site.file)
      if (!css) {
        problems.push(`${site.file}: 尺子看不见这个文件了（搬家没改根）`)
        continue
      }
      if (!source.includes(`'${site.prefix}-'`) && !source.includes('`' + site.prefix + '-${')) {
        problems.push(
          `${site.file}: 这里已经不再发 .${site.prefix}-* 了，指针该跟着搬（否则这条守卫会退化成空检查）`
        )
      }
      for (const value of site.values) {
        const has = new RegExp(`\\.${site.prefix}-${value}\\b`).test(css)
        const waived = site.unstyled.includes(value)
        if (has && waived) {
          problems.push(
            `${site.file}: .${site.prefix}-${value} 已经有规则了，把 unstyled 里那条删掉`
          )
        }
        if (!has && !waived) {
          problems.push(`${site.file}: 值域里有 ${value}，但没有 .${site.prefix}-${value} 规则`)
        }
      }
      for (const sibling of site.siblings) {
        if (!new RegExp(`\\.${site.prefix}-${sibling}\\b`).test(css)) {
          problems.push(
            `${site.file}: siblings 里的 .${site.prefix}-${sibling} 已经不在这个文件里，删掉这个豁免`
          )
        }
      }
      const extra = [...css.matchAll(new RegExp(`^\\.${site.prefix}-([a-z]+)\\b`, 'gm'))]
        .map((m) => m[1])
        .filter((v) => !site.values.includes(v) && !site.siblings.includes(v))
      for (const v of extra) {
        problems.push(
          `${site.file}: .${site.prefix}-${v} 不在值域里 = 死样式（要么删它，要么说明后端会发它并加进域里）`
        )
      }
    }
    expect(problems, problems.join('\n')).toEqual([])
  })

  it('keeps the auth session keys inside utils/session', () => {
    /* D87 之前这两个键散在三个文件 12 处：`api/request.js`（每次请求读 + 401 直接 removeItem 两个键）、
       `api/interview.js`（拼 WS 地址又读一次）、`stores/auth.js`（建 store 读、setAuth/clearAuth/fetchMe 写）。
       今天没出事是因为 401 那条路还会 dispatch `auth:expired` 把 store 一起清掉——两个机制靠一个事件对齐，
       而不是因为有单一出处。现在键名/序列化只住 `utils/session.js`。
       判据只认这两个字面量键名，别的 localStorage 键（`organization.active_id`、`recruit.last*`、
       每日任务那两把）不归它管——那一族由 lastSelection 的守卫与各自页面负责。 */
    const offenders = []
    for (const full of vueFiles('src', ['.js', '.vue'])) {
      const rel = toRel(full)
      if (rel === 'src/utils/session.js') continue
      const source = readFileSync(full, 'utf8')
      const hits = source.match(
        /localStorage\.(?:getItem|setItem|removeItem)\(\s*['"](token|user)['"]/g
      )
      if (hits) offenders.push(`${rel}×${hits.length}`)
    }
    expect(
      offenders,
      `auth keys must be read/written through utils/session.js, not by naming the key again: ${offenders.join(', ')}`
    ).toEqual([])
  })

  it('never lets a rubric entry fall through to printing the whole object', () => {
    /* `{{ x.item || x }}` 是"两代写法各吃一种"那句话：条目可能是裸字符串，也可能是
       `normalizeLocalizedObjectList` 写回的对象。生产端对对象**一定**补 `item`（五个名字键
       都挑不到时给空串），于是 `'' || 对象` 走到右边，Vue 的插值把整个对象序列化成 JSON 印给
       候选人——D81 拿旧表达式的编译形态量过那一串输出，D82 把剩下两处屏幕一起收掉。
       现在三处（SkillsPane / AnalysisResult / History）都过 utils 的 `rubricRow` 收成一帧。
       判据只数 `<template>` 段（注释里允许出现这句话），且要求后面跟着 `}}`，
       所以钉的是"整颗对象被插值出去"，不是"读了 .item"。 */
    const offenders = viewSources
      .filter(({ template }) => /\.item\s*\|\|\s*[\w.]+\s*\}\}/.test(template))
      .map(({ rel }) => rel)
    expect(
      offenders,
      `rubric entries must be collapsed once by rubricRow (src/utils/analysisLocalization.js), ` +
        `not per template expression — the || branch prints the whole object to the candidate: ${offenders.join(
          ', '
        )}`
    ).toEqual([])
  })
})
