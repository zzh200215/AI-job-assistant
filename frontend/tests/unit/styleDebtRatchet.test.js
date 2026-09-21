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
