import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Ratchet guards. Every ceiling below is a measurement of existing debt, not an
// approval of it. A count may only move DOWN: when you fix some, lower the
// number in this file in the same commit, otherwise `staleBudgets` fails and
// tells you the new value to write.
const BUDGET = {
  hardcodedColorLiterals: {
    'src/views/InterviewRoom.vue': 69,
    'src/views/Home.vue': 72,
    'src/views/JobSearch.vue': 46,
    'src/layouts/DefaultLayout.vue': 34,
    'src/views/Profile.vue': 31,
    'src/views/CareerPlanning.vue': 27,
    'src/views/SmartAnalysis.vue': 15,
    'src/views/JobRecommend.vue': 20,
    'src/views/Register.vue': 26,
    'src/views/InterviewReport.vue': 22,
    'src/views/ResumeCompare.vue': 19,
    'src/views/Login.vue': 16,
    'src/views/Interview.vue': 13,
    'src/views/PipelineKanban.vue': 12,
    'src/views/ResetPassword.vue': 12,
    'src/views/InterviewSetup.vue': 11,
    'src/views/RecommendationEval.vue': 11,
    'src/views/ExplainMatch.vue': 9,
    'src/views/NotFound.vue': 5,
    'src/views/RecommendationConfig.vue': 5,
    'src/views/Subscription.vue': 5,
    'src/views/KnowledgeBase.vue': 4,
    'src/views/WeeklyReport.vue': 4,
    'src/views/ResumeUpload.vue': 3,
    'src/views/TaskCenter.vue': 3,
    'src/views/About.vue': 2,
    'src/views/AgentAnalysis.vue': 2,
    'src/views/EvalReport.vue': 2,
    'src/views/MultiAgentAnalysis.vue': 2,
    'src/views/OfferCompare.vue': 2,
    'src/views/PromptTrace.vue': 2,
    'src/views/SalaryInsight.vue': 2,
    'src/views/History.vue': 1,
    'src/views/JobTargets.vue': 1,
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
  templateColorLiterals: {
    'src/views/Login.vue': 17,
    'src/layouts/DefaultLayout.vue': 3,
    'src/views/ExplainMatch.vue': 2,
    'src/views/CareerPlanning.vue': 1,
    'src/views/NotFound.vue': 1,
    'src/views/ResumeUpload.vue': 1,
  },
  /* 状态→el-tag 颜色此前和分数色板同病：17 份手写表、32 个键，其中 `running` 在任务中心
     是蓝、两个 agent 页是橙，`ongoing` 在房间页是绿、设置页是橙。异步任务与面试会话两组
     已收进 utils/statusTone.js；下面数的是**还剩多少条手写映射**，只能往下走。

     口径是 **token**（`键: '颜色'`），不是整行。按行数吃过两次亏：
     `{ a: 'success', b: 'danger' }` 写在一行只算 1，被 prettier 折开又变 2，
     所以同一份代码的计数会随换行漂。2026-09-23 一次性格式化把它戳穿：按行口径只看见 52 条，
     换成 token 口径是 99 条，其中 47 条（admin/Tenants 9、JobTargets 4、Privacy 3…）从来没有
     进入过任何预算——就是本文件上面那句"预算看不见"第四次复发。
     已知噪声（不要把它当精确值）：99 条里 17 条是 `ElMessageBox.confirm(..., { type: 'warning' })`
     的对话框图标色。它和 PromptTrace 的 `RESPONSE_SOURCES`（真色表，键也叫 `type`）在 token 层
     无法区分，想区分要看数据流（这个值最终有没有喂给 `:type`），不值得为一把尺子上 AST。
     所以这条预算是**上界**：数得多、漏不掉，只许往下走。 */
  statusTagEntries: {
    'src/views/KnowledgeBase.vue': 13,
    'src/views/SmartAnalysis.vue': 13,
    'src/views/admin/Tenants.vue': 9,
    'src/views/CareerPlanning.vue': 9,
    'src/views/PipelineKanban.vue': 9,
    'src/views/PromptTrace.vue': 7,
    'src/views/AnalysisResult.vue': 5,
    'src/views/ExplainMatch.vue': 4,
    'src/views/JobTargets.vue': 4,
    'src/views/OrganizationWorkspace.vue': 4,
    'src/views/admin/Orders.vue': 3,
    'src/views/admin/Overview.vue': 3,
    'src/views/Privacy.vue': 3,
    'src/views/ResumeCompare.vue': 3,
    'src/views/History.vue': 2,
    'src/views/InterviewRoom.vue': 2,
    'src/views/ResumeUpload.vue': 2,
    'src/views/Interview.vue': 1,
    'src/views/Profile.vue': 1,
    'src/views/Subscription.vue': 1,
    'src/views/TaskCenter.vue': 1,
  },
  /* 失败被清成空态的存量（见 silentCatchCounts）。D5 把候选人侧 8 处接到了
     components/ui/AppLoadError；剩下的每一条都是明知故留，理由写在行内：
     - admin/*：企业侧已冻结（见 docs/upgrade-plan.md 的范围决定），不再投入；
     - ResumeUpload 的 loadVersionCount 失败时把 `_versionCount` 设为 null（=不知道），
       卡片因此不显示数字，也不再显示"0 个版本"——它没有作出假断言，只是少了一个按钮。
     - admin/Tenants 的 loadDomains：`notifyError: false` 且 `catch { domains[tid] = [] }`，
       展开某一行的租户域名列表失败会演成"该租户没有域名"。它是 D10 记下的那条盲区自己冒出来的：
       这条尺子会往后看 12 行找"有没有提示"，2026-09-23 格式化把 submitCreate 的 ElMessage 折出
       了窗口，它才现形（代码没变，是尺子的视野变了）。企业侧冻结，所以进预算不修。 */
  silentEmptyCatches: {
    'src/views/admin/Overview.vue': 2,
    'src/views/admin/Tenants.vue': 1,
    'src/views/ResumeUpload.vue': 1,
  },
  themeCompatWildcards: 27,
  themeImportantOverrides: 56,
  pageShellRedeclarations: 22,
  viewsBypassingApiLayer: 7,
}

function vueFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return vueFiles(full)
    return entry.name.endsWith('.vue') ? [full] : []
  })
}

const viewSources = [...vueFiles('src/views'), ...vueFiles('src/layouts')].map((full) => {
  const source = readFileSync(full, 'utf8')
  // The template block is everything before <script: a lazy `</template>` match would
  // stop at the first slot template (`<template #default>`), under-counting views.
  const scriptAt = source.search(/<script/)
  return {
    rel: full.split(path.sep).join('/'),
    style: (source.match(/<style[\s\S]*?<\/style>/g) || []).join('\n'),
    script: (source.match(/<script[\s\S]*?<\/script>/g) || []).join('\n'),
    template: scriptAt < 0 ? source : source.slice(0, scriptAt),
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

/* 失败被清成空态：`request.js` 只对**非 GET** 弹提示（`notifyError !== false && method !== 'get'`），
   所以 `catch { list.value = [] }` 这种写法会把一次 500 渲染成页面自己的"暂无数据"文案。
   数出来的每条都是待收的谎，只能往下走。

   已知盲区（不要把这个数字当"全部修完"）：它只看 catch 体里清值的写法，看不见两类同病——
   1) try 之前先清值、catch 里只留注释（SalaryInsight 曾写"保留上一次结果"，其实既没保留也没提示，
      D6 已修并有测试）；2) 值原样留着不删，于是新输入配旧答案。
   所以这条预算是下限，不是全集；改注释型谎用时请连行为一起改。 */
const CATCH_HEAD = /^\s*\}\s*catch/
const CLEARS_VALUE = /=\s*(\[\]|null|''|0)\s*;?\s*$/
const REPORTS = /userMessage|loadError|\w*Error\.value\s*=|ElMessage|console\./

function silentCatchCounts() {
  const actual = {}
  for (const { rel, source } of viewSources) {
    const lines = source.split(/\r?\n/)
    let n = 0
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
      const cleared = body.some((l) => CLEARS_VALUE.test(l))
      // 报告可能写在 catch 之后（批量诊断就是那样），所以往后多看 12 行
      const window = body.join('\n') + '\n' + lines.slice(j, j + 12).join('\n')
      const reported = REPORTS.test(window)
      const commented = body.length > 0 && body.every((l) => /^\s*(\/\/|\/\*|\*)/.test(l))
      if (cleared && !reported && !commented) n++
    }
    if (n) actual[rel] = n
  }
  return actual
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
    const suspicious = (line) => {
      if (PRIVATE_USE.test(line)) return true
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

  it('does not let the theme layer grow its class-name wildcards', () => {
    const n = (themeCss.match(/\[class\*=/g) || []).length
    expect(n).toBeLessThanOrEqual(BUDGET.themeCompatWildcards)
  })

  it('does not let the theme layer grow its !important overrides', () => {
    const n = (themeCss.match(/!important/g) || []).length
    expect(n).toBeLessThanOrEqual(BUDGET.themeImportantOverrides)
  })

  it('does not let views re-declare the shared .page-shell chrome', () => {
    const n = viewSources.filter(({ style }) => /^\s*\.page-shell\s*[,{]/m.test(style)).length
    expect(n).toBeLessThanOrEqual(BUDGET.pageShellRedeclarations)
  })

  it('does not let views bypass the api layer', () => {
    const offenders = viewSources
      .filter(({ source }) => /from '@\/api\/request'/.test(source))
      .map(({ rel }) => rel)
    expect(offenders.length).toBeLessThanOrEqual(BUDGET.viewsBypassingApiLayer)
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
  const TONE_CLASS_SITES = [
    { prefix: 'score-tone', css: themeCss, where: 'src/styles/main.css' },
    { prefix: 'score-fill', css: themeCss, where: 'src/styles/main.css' },
    {
      prefix: 'score-chip',
      css: styleOf('src/views/InterviewRoom.vue'),
      where: 'InterviewRoom.vue',
    },
    {
      prefix: 'score-level',
      css: styleOf('src/views/PipelineKanban.vue'),
      where: 'PipelineKanban.vue',
    },
  ]

  it('gives every tone a rule for each class prefix a view emits', () => {
    const missing = []
    for (const { prefix, css, where } of TONE_CLASS_SITES) {
      for (const tone of TONES) {
        if (!new RegExp(`\\.${prefix}--${tone}\\b`).test(css)) {
          missing.push(`${prefix}--${tone} (no rule in ${where})`)
        }
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
})
