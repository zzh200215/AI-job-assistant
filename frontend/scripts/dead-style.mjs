#!/usr/bin/env node
/* 死样式候选的**静态粗尺**。它只挑页、不判决——删一条规则仍然要 D67/D68 那套浏览器
   "删掉 → 比 44 条计算属性 + rect → 塞回去" 才允许动手。
   为什么要把它写进仓库而不是每次临时搭：D67/D68 的探针与脚本用完即删，于是每一轮都要重搭一次，
   而重搭时最容易丢的就是下面这五条腿（D68 记着丢过一次，把 33 条活规则报成死规则）。

   五条"这个类名其实被用到了"的判据：
     1  模板里静态 class="a b"
     2  模板/脚本里的对象键 { active: … } 或 'active':
     3  模板字面量的静态片段 `node-${…}` → 前缀 node-
     4  :class="someVar" → 回到 script 把该变量可能返回的字符串全收出来
     5  'dot-' + x 这种**加号拼接** → 前缀 dot-，后缀取本文件里出现过的字符串字面量
        （D68 的四条腿里没有这一条；实测它只在未清扫的那些页里出现，见 docs/upgrade-plan.md D75）

   用法：node scripts/dead-style.mjs [--json] [相对 frontend 的路径…]   默认扫 src 下所有 .vue
*/
import fs from 'node:fs'
import path from 'node:path'

const SWEEPED = new Set([
  'JobSearch.vue',
  'PipelineKanban.vue',
  'SmartAnalysis.vue',
  'InterviewRoom.vue',
])

const vueFiles = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return p === 'node_modules' || p === 'dist' ? [] : vueFiles(p)
    return p.endsWith('.vue') ? [p] : []
  })

/** 按深度配对取出根 `<template>` 的内容——SFC 里 `<template #slot>` 是嵌套的，
 *  非贪婪正则会在第一个 `</template>` 就停，实测把模板截掉一半、伪造出 1055 条候选（D75）。 */
function rootTemplate(src) {
  // 闭标签要允许跨行：`CareerPlanning.vue:261` 那个 `</template` 后面直接换行（prettier 折的），
  // 按 `</template>` 死配会让根模板取空，于是整页 136 条规则全被报成死规则——和 D68 那次
  // "只认以 `{` 结尾的选择器行"是同一类缺陷。
  const re = /<template\b[^>]*>|<\/template\s*>/g
  let depth = 0
  let start = -1
  let m
  while ((m = re.exec(src))) {
    if (m[0].startsWith('</')) {
      if (depth === 1) return src.slice(start, m.index)
      depth -= 1
    } else {
      depth += 1
      if (depth === 1) start = m.index + m[0].length
    }
  }
  return ''
}

/** 抓出根 template / 每个 <script> / 每条 <style>。 */
function splitSfc(src) {
  const pick = (tag) => {
    const out = []
    const re = new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, 'g')
    let m
    while ((m = re.exec(src))) out.push(m[1])
    return out
  }
  return { template: rootTemplate(src), script: pick('script').join('\n'), styles: pick('style') }
}

/** 一条 CSS 规则里的类名（D68 修过的形状：选择器可能跨行成列表，要整段收）。 */
function rulesOf(css) {
  const lines = css.split(/\r?\n/)
  const rules = []
  let pending = []
  for (const line of lines) {
    const t = line.trim()
    if (!t || t.startsWith('/*') || t.startsWith('*') || t.startsWith('//')) continue
    if (t.endsWith('{') || t.endsWith(',')) {
      pending.push(t.replace(/\{$/, '').replace(/,$/, '').trim())
      if (t.endsWith('{')) {
        const selector = pending.join(' ')
        pending = []
        const classes = [...selector.matchAll(/\.([A-Za-z_][\w-]*)/g)].map((m) => m[1])
        if (classes.length) rules.push({ selector, classes })
      }
    } else {
      pending = []
    }
  }
  return rules
}

/** 判据 1/2：模板与脚本里出现过的静态类名 token。 */
function staticTokens(template, script) {
  const tokens = new Set()
  const add = (s) =>
    s
      .split(/\s+/)
      .filter(Boolean)
      .forEach((c) => tokens.add(c))
  for (const m of template.matchAll(/\s(?:class|:class)="([^"]*)"/g)) {
    const raw = m[1]
    if (/^\s*[\w-]+\s*$/.test(raw)) {
      add(raw)
      continue
    }
    for (const q of raw.matchAll(/['"`]([^'"`{]*)['"`]/g)) add(q[1])
    for (const k of raw.matchAll(/([{,]\s*)([A-Za-z_][\w-]*)\s*:/g)) tokens.add(k[2])
  }
  for (const m of template.matchAll(/\sclass="([^"]*)"/g)) add(m[1])
  for (const m of script.matchAll(/['"`]([A-Za-z_][\w-]*(?: [A-Za-z_][\w-]*)*)['"`]/g)) {
    if (/\s/.test(m[1])) add(m[1])
    else tokens.add(m[1])
  }
  for (const m of script.matchAll(/([{,]\s*)([A-Za-z_][\w-]*)\s*:/g)) tokens.add(m[2])
  return tokens
}

/** 判据 3/5：动态类名的前缀（`node-${…}` 与 'dot-' + x）。 */
function prefixes(...texts) {
  const out = []
  const keep = (s) => {
    for (const tok of s.split(/\s+/)) if (/^[A-Za-z_][\w-]*-$/.test(tok)) out.push(tok)
  }
  for (const text of texts) {
    // 拼接的左操作数：'dot-' + x，也包括串里带空格的 'card-follow follow-' + f(card)
    for (const m of text.matchAll(/['"`]([^'"`\n]*)['"`]\s*\+/g)) keep(m[1])
    // 模板字面量的静态头部：`node-${status}`、`dot-${tone} mt`
    for (const m of text.matchAll(/`([^'`\n]*)\$\{/g)) keep(m[1])
  }
  return [...new Set(out)]
}

/** 判据 5 的后缀集合：本文件里出现过的字符串字面量（保守——宁可少报死规则）。 */
function stringLiterals(text) {
  const out = new Set()
  for (const m of text.matchAll(/['"`]([A-Za-z_][\w-]*)['"`]/g)) out.add(m[1])
  return out
}

/** 判据 4：`:class="变量"` 在 script 里可能返回的字符串。 */
function returnedClassStrings(script) {
  const out = new Set()
  for (const m of script.matchAll(/return\s+(['"`])([^'"`]*)\1/g)) {
    m[2]
      .split(/\s+/)
      .filter(Boolean)
      .forEach((c) => out.add(c))
  }
  for (const m of script.matchAll(/\?\s*(['"`])([^'"`]*)\1\s*:\s*(['"`])([^'"`]*)\3/g)) {
    ;[m[2], m[4]].forEach((s) =>
      s
        .split(/\s+/)
        .filter(Boolean)
        .forEach((c) => out.add(c))
    )
  }
  return out
}

const LIBRARY = /^(el-|is-|has-|deep\b)/

/**
 * 判据 4 的延伸：把这一页**本地 import** 的模块（lib/ 与 composables/）也收进"类名可能从哪来"的宇宙。
 * A2 拆页把发类名的函数搬出了 .vue（`signalClass` 现在住在 `lib/jobModel.js`），只看单文件就会把
 * "其实被子组件用着"的父页面规则误报成死规则——这是本尺第一版自检红掉 61 条的原因（见 D75）。
 */
function localImportUniverse(file, depth = 3, seen = new Set()) {
  const texts = []
  if (depth < 0) return texts
  const src = fs.readFileSync(file, 'utf8')
  for (const m of src.matchAll(/from\s+['"](\.[^'"]+|@\/[^'"]+)['"]/g)) {
    const spec = m[1]
    const base = spec.startsWith('@/')
      ? path.resolve('src', spec.slice(2))
      : path.resolve(path.dirname(file), spec)
    for (const cand of [base + '.js', base, path.join(base, 'index.js')]) {
      if (!fs.existsSync(cand) || !fs.statSync(cand).isFile() || seen.has(cand)) continue
      seen.add(cand)
      texts.push(fs.readFileSync(cand, 'utf8'))
      texts.push(...localImportUniverse(cand, depth - 1, seen))
      break
    }
  }
  return texts
}

function measure(file) {
  const src = fs.readFileSync(file, 'utf8')
  const { template, script, styles } = splitSfc(src)
  const universe = [script, ...localImportUniverse(file)].join('\n')
  const tokens = staticTokens(template, universe)
  const dyn = {
    list: prefixes(template, universe),
    literals: stringLiterals(template + '\n' + universe),
  }
  const returned = returnedClassStrings(universe)
  const rules = styles.flatMap(rulesOf)

  const candidates = []
  let protectedStatic = 0
  let protectedDynamic = 0
  for (const rule of rules) {
    const own = rule.classes.filter((c) => !LIBRARY.test(c))
    if (!own.length) continue
    const used = own.some((c) => tokens.has(c) || returned.has(c))
    if (used) {
      protectedStatic++
      continue
    }
    const isDyn = dyn.list.some((p) => own.some((c) => c.startsWith(p)))
    if (isDyn) {
      const suffixKnown = own.some((c) =>
        dyn.list.some((p) => c.startsWith(p) && dyn.literals.has(c.slice(p.length)))
      )
      if (suffixKnown) {
        protectedDynamic++
        continue
      }
      candidates.push({ selector: rule.selector, why: '拼接前缀命中、后缀找不到字面量' })
      continue
    }
    // 判据 6：`block--modifier` 的两半都作为字面量出现过。加这一条是因为类名可能是**函数参数**
    // 拼出来的——`scoreToneClass(score, bands, 'score-level')` 会产出 `score-level--high`
    // （`utils/scoreTone.js:37`），前缀既不是静态片段也不是拼接左值，五条腿全都看不见。
    const joined = own.some((c) => {
      const at = c.indexOf('--')
      return at > 0 && dyn.literals.has(c.slice(0, at)) && dyn.literals.has(c.slice(at + 2))
    })
    if (joined) {
      protectedDynamic++
      continue
    }
    candidates.push({ selector: rule.selector, why: '五条腿都不认' })
  }
  return {
    file,
    rules: rules.length,
    styleLines: styles.reduce((a, s) => a + s.split(/\r?\n/).length, 0),
    protectedStatic,
    protectedDynamic,
    candidates,
  }
}

const args = process.argv.slice(2)
const json = args.includes('--json')
const roots = args.filter((a) => !a.startsWith('--'))
const files = roots.length ? roots : vueFiles('src')
const rows = files.map(measure)

const sum = (key) => rows.reduce((a, r) => a + r[key], 0)
const swept = rows.filter((r) => SWEEPED.has(path.basename(r.file)))
const rest = rows.filter((r) => !SWEEPED.has(path.basename(r.file)))

const whys = () => rows.flatMap((r) => r.candidates.map((c) => c.why))
const totalCandidates = whys().length

/**
 * `--selftest`：尺子的校准。D67/D68 用浏览器 A/B 把四页清到"两把尺子都归 0 候选"，
 * 所以这四页就是本尺的已知答案——报非 0 就说明尺子又坏了（这次修的过程中它红了三次，
 * 每一次都是一个解析缺陷，见 docs/upgrade-plan.md D75）。
 */
if (args.includes('--selftest')) {
  const bad = swept.filter((r) => r.candidates.length)
  const n = bad.reduce((a, r) => a + r.candidates.length, 0)
  for (const r of bad) {
    console.error(`${r.file}：${r.candidates.length} 条候选`)
    r.candidates
      .slice(0, 5)
      .forEach((c) => console.error(`    [${c.why}] ${c.selector.slice(0, 60)}`))
  }
  console.log(`自检：已清扫四页的候选合计 ${n}（要求 0），全仓候选 ${totalCandidates}`)
  process.exit(n ? 1 : 0)
}

if (json) {
  process.stdout.write(JSON.stringify(rows, null, 1))
} else {
  console.log(`扫了 ${rows.length} 个 .vue：规则 ${sum('rules')} 条，样式 ${sum('styleLines')} 行`)
  console.log(`  静态判据保护 ${sum('protectedStatic')}，动态判据保护 ${sum('protectedDynamic')}`)
  console.log(`  候选死规则合计 ${totalCandidates} 条`)
  console.log(
    `  候选里"五条腿都不认" ${whys().filter((w) => w === '五条腿都不认').length}，` +
      `"拼接前缀命中、后缀找不到" ${whys().filter((w) => w.startsWith('拼接')).length}`
  )
  console.log(`\n自检（D67/D68 已清扫的四页，应当接近 0）：`)
  for (const r of swept) {
    console.log(`  ${path.basename(r.file)}：规则 ${r.rules}，候选 ${r.candidates.length}`)
    r.candidates
      .slice(0, 3)
      .forEach((c) => console.log(`      ${c.why} → ${c.selector.slice(0, 70)}`))
  }
  console.log(`\n未清扫的 ${rest.length} 个文件里，候选最多的 12 个：`)
  for (const r of [...rest]
    .sort((a, b) => b.candidates.length - a.candidates.length)
    .slice(0, 12)) {
    console.log(
      `  候选 ${String(r.candidates.length).padStart(3)} / 规则 ${String(r.rules).padStart(3)} / 样式 ${String(
        r.styleLines
      ).padStart(4)} 行  ${r.file}`
    )
  }
}
