// AppPanel 迁移器：把 `div.panel > div.panel-header > div.panel-title-row + div.panel-body`
// 这四层手写标记搬进 components/ui/AppPanel.vue。样式本来就在 styles/panels.css，重复的只是标记。
//
// 用法（在 frontend/ 目录里跑）：
//   node scripts/panel-migration.mjs --all          全量统计：每个视图命中/被拒多少，拒因分布
//   node scripts/panel-migration.mjs --all --verbose 逐处打印拒因
//   node scripts/panel-migration.mjs                按下面 BATCH 里的预期干跑
//   node scripts/panel-migration.mjs --write        写盘（先过逐文件断言 + 标签配平检查）
//   node scripts/panel-migration.mjs --selftest     跑内置的合成用例，证明判定不是空转
//
// 写盘之后要做的三件事：`npx prettier --write` 改过的视图 → `npm run build` → 把预算
// `handRolledPanelHeaders` 降到扫描器报的新值；**并且**逐路由跑一次 getComputedStyle 差分
// （方法记在 docs/upgrade-plan.md 的 D18/D26）。这个脚本只保证标记等价，不保证渲染等价。
//
// 拒因编号：1=本视图自己有 `.panel-header` 规则（scoped CSS 匹配不到子组件内部节点，标记搬走规则
// 就失效）；2=包裹不是单独的 `<div class="panel…">`（可能是 `<section>`，也可能是动态 `:class`）；
// 3=头部的第一个子节点不是 `panel-title-row`；5=标题行内没有"单独一行的 `<h3>…</h3>`"；
// 6/7/8=头部收尾、panel-body 起点、面板收尾对不上。
//
// 它看不见 `<div class="panel-header"><span>…</span></div>` 这种一行式写法（判定 3/5 的锚点是整行），
// 而预算 `handRolledPanelHeaders` 数的是 `class="panel-header"` 出现次数——所以"命中 0"不等于
// "没有可迁的了"，只等于"没有*纯 drop-in* 了"。两处形状差异现在各有 7 处（SmartAnalysis 5 / Privacy 2）。
//
// 判定过严不是 bug：宁可漏迁，也不要把一处需要人决定的改写自动化掉。
import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const sp = (n) => ' '.repeat(n)
const VIF = 'v-if="[^"]*"'
// 包裹层允许 class="panel…" 与 v-if 的任意顺序、任意一个或两个都在：
// 顺序只是书写习惯，把它当成"结构不合格"会漏掉真正的 drop-in（RecommendationConfig:105）。
const WRAP = new RegExp(
  `^(\\s*)<div(?:(?:\\s+${VIF})?\\s+class="panel([^"]*)"(?:\\s+${VIF})?|(?:\\s+class="panel([^"]*)")(?:\\s+${VIF})?\\s+${VIF})>$`
)
const WRAP_VIF = new RegExp(`\\s+(${VIF})`, 'g')
function wrap(L, i) {
  const line = L[i - 1] || ''
  const m = line.match(WRAP)
  if (!m) return null
  const mod = (m[2] !== undefined ? m[2] : m[3]) || ''
  const vifs = [...line.matchAll(WRAP_VIF)].map((x) => x[1].trim())
  return { ind: m[1], mod: mod.trim(), vifs }
}
const ICON = /^ {4}<el-icon :size="18" color="([^"]+)">(.+)<\/el-icon>$/
const H3 = /^ {4}<h3>(.*)<\/h3>$/

// 内置合成用例：判定器两侧都要能给出答案——合格的必须出方案、不合格的必须报对拒因。
// 这条是 D25/D26 那三个"尺子错在同一处：数的是文本不是东西"的教训留下的自动化版本。
function selftest() {
  const fails = []
  const chk = (label, got, want) => {
    const g = JSON.stringify(got),
      w = JSON.stringify(want)
    console.log(g === w ? `  ok   ${label}` : `  FAIL ${label}\n       得到 ${g}\n       期望 ${w}`)
    if (g !== w) fails.push(label)
  }
  // 包裹层：四种合法书写 + 三种必须拒绝的
  chk('wrap 只 class', wrap(['      <div class="panel">'], 1), { ind: '      ', mod: '', vifs: [] })
  chk('wrap class+vif', wrap(['      <div class="panel" v-if="x">'], 1), {
    ind: '      ',
    mod: '',
    vifs: ['v-if="x"'],
  })
  chk('wrap vif+class', wrap(['      <div v-if="c" class="panel">'], 1), {
    ind: '      ',
    mod: '',
    vifs: ['v-if="c"'],
  })
  chk('wrap 带修饰类', wrap(['    <div class="panel today-panel">'], 1), {
    ind: '    ',
    mod: 'today-panel',
    vifs: [],
  })
  chk('wrap 拒动态 :class', wrap(["      <div :class=\"['a','panel']\">"], 1), null)
  chk('wrap 拒 section', wrap(['    <section class="panel">'], 1), null)
  chk('wrap 拒多余属性', wrap(['      <div class="panel" v-if="x" :style="s">'], 1), null)

  const GOOD = [
    '    <div class="panel">',
    '      <div class="panel-header">',
    '        <div class="panel-title-row">',
    '          <el-icon :size="18" color="var(--app-primary)"><Star /></el-icon>',
    '          <h3>标题</h3>',
    '          <el-tag>角标</el-tag>',
    '        </div>',
    '        <el-button>操作</el-button>',
    '      </div>',
    '      <div class="panel-body">',
    '        <p>正文</p>',
    '      </div>',
    '    </div>',
  ]
  const w = { r: '' }
  const pl = plan(GOOD, 1, w)
  chk('plan 合格站点', pl && { from: pl.from, to: pl.to, block: pl.block }, {
    from: 0,
    to: 13,
    block: [
      '    <AppPanel icon-color="var(--app-primary)">',
      '      <template #icon><Star /></template>',
      '      <template #title>标题</template>',
      '      <template #badge>',
      '        <el-tag>角标</el-tag>',
      '      </template>',
      '      <template #actions>',
      '        <el-button>操作</el-button>',
      '      </template>',
      '      <p>正文</p>',
      '    </AppPanel>',
    ],
  })
  chk(
    'plan 拒无 h3',
    plan(
      GOOD.filter((l) => !/^ +<h3>/.test(l)),
      1,
      w
    ),
    null
  )
  chk('拒无 h3 的拒因', w.r.startsWith('5'), true)
  // 没有图标时不能凭空冒出 icon-color 属性
  chk(
    'plan 无图标站点',
    plan(
      GOOD.filter((l) => !/^ +<el-icon/.test(l)),
      1,
      w
    ).block[0],
    '    <AppPanel>'
  )
  chk(
    'plan 拒坏包裹',
    plan(
      GOOD.map((l, i) => (i === 0 ? '    <div class="other">' : l)),
      1,
      w
    ),
    null
  )
  chk('拒坏包裹的拒因', w.r.startsWith('2'), true)
  console.log(fails.length ? `selftest: ${fails.length} 条不符` : 'selftest: 全部通过')
  process.exit(fails.length ? 1 : 0)
}

// 上一批（D26，2026-09-24 已执行完）的账。留在这里是给"改判定逻辑会不会反过来动旧账"当回归基线：
// 对当前 HEAD 跑一遍批处理模式，命中数必须还是 0（因为那 22 处已经迁走了）。
const BATCH = {
  Profile: 0,
  InterviewSetup: 0,
  MultiAgentAnalysis: 0,
  PromptTrace: 0,
  AgentAnalysis: 0,
  AnalysisResult: 0,
  History: 0,
  RecommendationConfig: 0,
  RecommendationEval: 0,
}
const WRITE = process.argv.includes('--write')
const VIEWS = fileURLToPath(new URL('../src/views/', import.meta.url))
if (process.argv.includes('--selftest')) selftest()

/** 返回该 panel-header 的迁移方案，或 null（不合格）。 */
function plan(L, i, why) {
  const bail = (r) => {
    if (why) why.r = r
    return null
  }
  const headInd = L[i].match(/^ */)[0].length
  const w = wrap(L, i)
  if (!w) return bail('2 包裹')
  if (L[i + 1] !== `${sp(headInd + 2)}<div class="panel-title-row">`) return bail('3 title-row 行')

  let k = i + 2
  let icon = null
  let title = null
  const badge = []
  while (k < L.length && L[k] !== `${sp(headInd + 2)}</div>`) {
    const rel = sp(4) + L[k].slice(headInd + 4)
    if (!title && H3.test(rel)) title = rel.match(H3)[1]
    else if (!icon && ICON.test(rel)) {
      const mi = rel.match(ICON)
      icon = { color: mi[1], node: mi[2] }
    } else badge.push(L[k])
    k++
  }
  if (process.argv.includes('--dbg'))
    console.log(
      '   [dbg] i=',
      i,
      'headInd=',
      headInd,
      'k=',
      k,
      'title=',
      JSON.stringify(title),
      'icon=',
      !!icon,
      'L[i+1]=',
      JSON.stringify(L[i + 1]),
      'close-wanted=',
      JSON.stringify(sp(headInd + 2) + '</div>'),
      'L[k]=',
      JSON.stringify(L[k])
    )
  if (k >= L.length || !title) return bail('5 无 h3 或未收尾')

  let j = k + 1
  const actions = []
  while (j < L.length && L[j] !== `${sp(headInd)}</div>`) {
    actions.push(L[j])
    j++
  }
  if (j >= L.length) return bail('6 header 未收尾')
  if (L[j + 1] !== `${sp(headInd)}<div class="panel-body">`)
    return bail('7 后面不是 panel-body: ' + JSON.stringify((L[j + 1] || '').trim().slice(0, 30)))

  const wInd = w.ind
  let e = -1
  for (let q = j + 2; q < L.length - 1; q++) {
    if (L[q] === `${sp(headInd)}</div>` && L[q + 1] === `${wInd}</div>`) {
      e = q
      break
    }
  }
  if (e < 0) return bail('8 面板收尾不配对')

  // headInd 是原 panel-header 的缩进，wInd 是包裹 div 的缩进；AppPanel 顶替包裹层，
  // 所以新结构里所有层级都相对 wInd 计，原来相对 headInd 的行要整体平移。
  const wi = wInd.length
  const d = wi - headInd
  const reind = (lines, delta) =>
    lines.map((l) =>
      !l.trim() ? l : sp(Math.max(0, l.match(/^ */)[0].length + delta)) + l.trimStart()
    )

  const attrs = `${w.vifs.map((v) => ` ${v}`).join('')}${w.mod ? ` class="${w.mod}"` : ''}`
  const block = [`${wInd}<AppPanel${attrs}${icon ? ` icon-color="${icon.color}"` : ''}>`]
  if (icon) block.push(`${sp(wi + 2)}<template #icon>${icon.node}</template>`)
  block.push(`${sp(wi + 2)}<template #title>${title}</template>`)
  if (badge.length)
    block.push(`${sp(wi + 2)}<template #badge>`, ...reind(badge, d), `${sp(wi + 2)}</template>`)
  if (actions.length)
    block.push(
      `${sp(wi + 2)}<template #actions>`,
      ...reind(actions, d + 2),
      `${sp(wi + 2)}</template>`
    )
  block.push(...reind(L.slice(j + 2, e), d), `${wInd}</AppPanel>`)

  // e 是 panel-body 的收尾、e+1 是包裹 div 的收尾，两层都被 </AppPanel> 取代，
  // 所以替换区间是 [i-1, e+2)——早先写成 e+1 会留下一个多余的 </div>。
  return { from: i - 1, to: e + 2, block }
}

let grand = 0
const BAILS = {}
// --all：只统计所有视图的可迁/被拒分布，不断言、不写盘（下一批开工前先跑这个）。
const ALL = process.argv.includes('--all')
if (ALL && WRITE) {
  console.error('--all 是统计模式，不能同时 --write')
  process.exit(1)
}
const TARGETS = ALL
  ? Object.fromEntries(
      readdirSync(VIEWS)
        .filter((f) => f.endsWith('.vue'))
        .map((f) => [f.slice(0, -4), null])
    )
  : BATCH
for (const [name, expect] of Object.entries(TARGETS)) {
  const p = VIEWS + `${name}.vue`
  let L = readFileSync(p, 'utf8').split('\n')
  // 前提：该视图自己没有 `.panel-header` 的 scoped 规则——标记搬进 AppPanel 后父组件的规则就匹配
  // 不到它了（scoped CSS 只作用于本组件模板节点 + 子组件根）。注释里的类名不算，所以先剥注释。
  const noComment = L.join('\n')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*(\/\/).*$/gm, '$1')
  const overrides = /\.panel-header\b/.test(noComment)
  let done = 0
  let skipped = 0
  for (let i = L.length - 1; i >= 0; i--) {
    if (!/^(\s*)<div class="panel-header">$/.test(L[i])) continue
    const wr = {}
    const pl = overrides ? null : plan(L, i, wr)
    if (!pl) {
      const r = overrides ? '1 本视图覆盖 .panel-header' : wr.r || '?'
      skipped++
      const key = r.split(' ')[0]
      BAILS[key] = (BAILS[key] || 0) + 1
      if (process.argv.includes('--verbose')) console.log(`  MISS ${name} 行${i + 1}: ${r}`)
      continue
    }
    if (WRITE) {
      L = [...L.slice(0, pl.from), ...pl.block, ...L.slice(pl.to)]
      const open = L.filter((l) => /<AppPanel[\s>]/.test(l)).length
      const close = L.filter((l) => /<\/AppPanel>/.test(l)).length
      if (open !== close) {
        console.error(
          `${name}: 写盘后 <AppPanel 共 ${open} 个、</AppPanel> 共 ${close} 个，不平衡 —— 中止`
        )
        process.exit(1)
      }
    }
    done++
    if (!ALL) console.log(`  ${name} 行${i + 1} -> AppPanel ${WRITE ? '(已改)' : '(计划)'}`)
  }
  if (!ALL || done || skipped)
    console.log(`  ${name}: 命中 ${done} / 拒绝 ${skipped}${ALL ? '' : `（预期命中 ${expect}）`}`)
  if (process.env.EXPECT_OFF) {
    grand += done
    continue
  }
  if (ALL) {
    grand += done
    continue
  }
  if (done !== expect) {
    console.error(`${name}: 计划 ${done} 处，预期 ${expect} —— 中止，不写盘`)
    process.exit(1)
  }
  if (WRITE) {
    const importLine = "import AppPanel from '@/components/ui/AppPanel.vue'"
    if (!L.includes(importLine))
      L.splice(
        L.findIndex((l) => /^import /.test(l)),
        0,
        importLine
      )
    writeFileSync(p, L.join('\n'))
  }
  grand += done
}
console.log(
  '拒绝原因分布（1=本视图覆盖 .panel-header，2=包裹不是静态 div.panel，5=标题行内没有单行 h3）:',
  BAILS
)
console.log(WRITE ? `已迁移 ${grand} 处` : `干跑：可迁 ${grand} 处`)
