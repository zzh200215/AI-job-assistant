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
  // 状态→el-tag 颜色此前和分数色板同病：17 份手写表、32 个键，其中 `running` 在任务中心
  // 是蓝、两个 agent 页是橙，`ongoing` 在房间页是绿、设置页是橙。异步任务与面试会话两组
  // 已收进 utils/statusTone.js；下面数的是**还剩多少条手写映射**，只能往下走。
  statusTagEntries: {
    'src/views/KnowledgeBase.vue': 12,
    'src/views/CareerPlanning.vue': 9,
    'src/views/SmartAnalysis.vue': 8,
    'src/views/PipelineKanban.vue': 7,
    'src/views/AnalysisResult.vue': 5,
    'src/views/ExplainMatch.vue': 4,
    'src/views/InterviewRoom.vue': 2,
    'src/views/History.vue': 1,
    'src/views/OrganizationWorkspace.vue': 1,
    'src/views/Profile.vue': 1,
    'src/views/Subscription.vue': 1,
  },
  /* 失败被清成空态的存量（见 silentCatchCounts）。D5 把候选人侧 8 处接到了
     components/ui/AppLoadError；剩下的每一条都是明知故留，理由写在行内：
     - admin/*：企业侧已冻结（见 docs/upgrade-plan.md 的范围决定），不再投入；
     - ResumeUpload 的 loadVersionCount 失败时把 `_versionCount` 设为 null（=不知道），
       卡片因此不显示数字，也不再显示"0 个版本"——它没有作出假断言，只是少了一个按钮。 */
  silentEmptyCatches: {
    'src/views/admin/Overview.vue': 2,
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

/* 手写"状态 → el-tag 颜色"的条目数。只认 `<script>` 里 `键: 'success'` 这种形状，
   不数 ElMessageBox 的 { type: 'warning' } 之类——那不是状态色表。 */
const STATUS_TAG_ENTRY =
  /^\s*['"]?[\w一-龥]+['"]?:\s*'(primary|success|info|warning|danger)'\s*,?\s*$/gm

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
    // 判据不靠手写坏字清单：这类损坏产出的是一串正文里几乎不重复的生僻字，
    // 所以"一行里出现 >=3 个全仓只出现一次的 CJK 字"就是它自己的指纹。
    // 若哪天因正当生僻字（人名/地名）误报，把那个字加进 allowlist，别调低阈值。
    const walk = (dir, out = []) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name)
        if (entry.isDirectory()) walk(full, out)
        else if (/\.(vue|js)$/.test(entry.name))
          out.push({ rel: full.split(path.sep).join('/'), text: readFileSync(full, 'utf8') })
      }
      return out
    }
    const files = walk('src')
    const freq = new Map()
    for (const { text } of files) {
      for (const ch of text) if (ch >= '一' && ch <= '鿿') freq.set(ch, (freq.get(ch) || 0) + 1)
    }
    const suspicious = (line) => {
      if (line.includes('€')) return true
      // 乱码的指纹是一整段"正文里几乎不出现的字"连着出现：一段 CJK 连续串里连一个高频字
      // （出现 >=5 次）都没有，就不可能是人写的句子。
      // 已知漏报：乱码串里恰好混进一个高频字时看不见（`鐩镐技搴` 的"技"就是这样，本仓曾有一条
      // 这样的损坏并已修）；想靠"罕见字比例"补这个洞会误伤"熟练掌握"这种正常词，已试过并放弃。
      for (const run of line.match(/[㐀-鿿]{3,}/g) || []) {
        if (![...run].some((ch) => (freq.get(ch) || 0) >= 5)) return true
      }
      return false
    }
    const offenders = files
      .map(({ rel, text }) => {
        const i = text.split(/\r?\n/).findIndex(suspicious)
        return i < 0 ? null : `${rel}:${i + 1}`
      })
      .filter(Boolean)
    expect(
      offenders,
      `这些行的中文是被按 GBK 读回后另存的乱码，候选人看到的就是这串生僻字：${offenders.join(', ')}`
    ).toEqual([])
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
