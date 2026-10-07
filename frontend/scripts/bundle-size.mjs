/* 包体积尺（账上 D113 定的算法，落进仓库是为了不再每轮重搭）。
 *
 * 算法：`npm run build` 的 stdout → 剥 ANSI → 取 `dist/assets/<name>-<hash>.{js,css}` 那些行的 kB
 * 列 → 按**剥掉哈希名的键**相加。整目录字节、含 index.html 的总量都是另一口径，不可比。
 *
 * 三条自检腿，都是这两轮真踩过的坑，不是装饰：
 *   1. ANSI 必须剥干净 —— vite 把转义码打在**路径中间**（ESC[2mdist/ESC[22m…），
 *      用错正则（漏掉终止字节那一类）会一个都剥不掉，于是全场匹配 0 行、总量报 0.00；
 *   2. 哈希是**定长 8** —— 写成 8 以上会漏掉一批行，D135 那次因此把 −0.9 kB 报成 −7.1 kB；
 *   3. 含 `dist/assets` 却没被解析的行数必须为 **0** —— 这条抓到上面两种情况，两边都跑过才叫可比。
 *
 * 用法：
 *   node scripts/bundle-size.mjs                # 构建 + 打印总量与各键
 *   node scripts/bundle-size.mjs --selftest     # 拿真 stdout 样本证明三条腿会咬（不构建）
 *   node scripts/bundle-size.mjs --from FILE    # 解析已有的构建输出（比对两次运行用）
 */
import { execSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const ESC = String.fromCharCode(27)
const ANSI = new RegExp(ESC + '\\[[0-9;]*[A-Za-z]', 'g')
const ASSET_LINE = /^dist[/\\]assets[/\\](\S+)\s+([\d.]+)\s+kB/
const HASH_SEGMENT = new RegExp('-[A-Za-z0-9_-]{8}(\\.(?:js|css))$')

/** vite 真实输出样张（转义码打在路径中间），selftest 用它。 */
function sampleOutput({ ansi = true, odd = false } = {}) {
  const wrap = (s) => (ansi ? `${ESC}[2m${s}${ESC}[22m` : s)
  const rows = [
    [wrap('dist/'), `${ESC}[35massets/AppLoadError-BslmmcQ4.css` + `${ESC}[39m  0.50 kB`],
    [
      wrap('dist/'),
      `${ESC}[35massets/Login-DONSwarL.js` + `${ESC}[39m  8.01 kB${ESC}[2m │ gzip: 3 kB${ESC}[22m`,
    ],
    [wrap('dist/'), `${ESC}[35massets/index-Ab12Cd34.js` + `${ESC}[39m  12.00 kB`],
  ]
  if (odd) {
    // 一条哈希不是 8 位的行：正则必须**不**匹配它，从而被"未解析行数"那条腿抓住
    rows.push([wrap('dist/'), `${ESC}[35massets/Weird-Ab1.js` + `${ESC}[39m  1.00 kB`])
  }
  return rows.map(([a, b]) => a + b).join('\n')
}

function parse(text) {
  const stripped = text.replace(ANSI, '')
  const rows = []
  const skipped = []
  for (const raw of stripped.split('\n')) {
    const line = raw.trim()
    if (!line.includes('dist/assets') && !line.includes('dist\\assets')) continue
    const m = line.match(ASSET_LINE)
    if (m) rows.push({ file: m[1], kb: Number(m[2]) })
    else skipped.push(line)
  }
  const keep = rows.filter((r) => r.file.endsWith('.js') || r.file.endsWith('.css'))
  const per = new Map()
  for (const r of keep) {
    const k = r.file.replace(HASH_SEGMENT, '$1')
    per.set(k, (per.get(k) || 0) + r.kb)
  }
  return {
    total: [...per.values()].reduce((a, b) => a + b, 0),
    keys: per,
    parsed: rows.length,
    jsCss: keep.length,
    unparsed: skipped.length,
    ansiLeft: stripped.includes(ESC),
    noHash: keep.filter((r) => r.file.replace(HASH_SEGMENT, '$1') === r.file).map((r) => r.file),
  }
}

function report(r) {
  return [
    `parsed ${r.parsed} asset lines (js/css ${r.jsCss})`,
    `unparsed lines mentioning dist/assets: ${r.unparsed}`,
    `ANSI still present: ${r.ansiLeft}`,
    `names without an 8-char hash segment: ${r.noHash.length} ${JSON.stringify(r.noHash.slice(0, 3))}`,
    `distinct keys: ${r.keys.size}`,
    `TOTAL kB: ${r.total.toFixed(2)}`,
  ].join('\n')
}

function selftest() {
  const problems = []
  const good = parse(sampleOutput())
  if (good.parsed !== 3 || good.unparsed !== 0)
    problems.push(`样张应解析 3 行、0 行未解析，实得 ${good.parsed}/${good.unparsed}`)
  if (Math.abs(good.total - 20.51) > 0.01)
    problems.push(`样张总量应为 20.51 kB，实得 ${good.total.toFixed(2)}`)
  if (good.ansiLeft) problems.push('样张剥 ANSI 后仍留转义码')

  const brokenRuler = sampleOutput().replace(new RegExp(ESC + '\\[', 'g'), '@@')
  const noAnsi = parse(brokenRuler)
  if (noAnsi.parsed !== 0) problems.push('ANSI 坏掉时这把尺居然还匹配到行：自检腿 1 不咬')

  const loose = parse(sampleOutput({ odd: true }))
  const strict = parse(sampleOutput())
  // 两条腿各抓一种坏法，不能混成一条：
  //   · unparsed 抓"这行不是资源行的形状"（路径或列对不上）；
  //   · noHash 抓"这行是资源行，但文件名尾部不是一段定长 8 的哈希"——它会作为一个剥不掉
  //     哈希的**独立键**混进总量，跨两次运行时同一模块可能因哈希长度不同被算成两个键。
  // 主流程对两种情况都拒绝出数（exit 2），所以这里断言"腿会报出来"，不是"总量自动正确"。
  if (loose.unparsed !== 0)
    problems.push(`怪哈希行仍是合法资源行形状，unparsed 应为 0，实得 ${loose.unparsed}`)
  if (loose.noHash.length !== 1)
    problems.push(
      `怪哈希行必须被 noHash 那条腿抓到，实得 ${loose.noHash.length}：这条腿一软，A/B 就不可比`
    )
  if (strict.noHash.length !== 0 || strict.unparsed !== 0)
    problems.push('正常样张上两条腿都不该报东西')

  console.log(
    problems.length ? 'SELFTEST FAILED:\n' + problems.join('\n') : 'selftest ok：三条腿都会咬'
  )
  return problems.length ? 1 : 0
}

const args = process.argv.slice(2)
if (args.includes('--selftest')) process.exit(selftest())

const text = args.includes('--from')
  ? readFileSync(args[args.indexOf('--from') + 1], 'utf8')
  : execSync('npm run build', { cwd: FRONTEND, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })

const r = parse(text)
if (r.unparsed !== 0 || r.ansiLeft || r.noHash.length) {
  console.error('尺子不可信，先修它再引用数字：\n' + report(r))
  process.exit(2)
}
const out =
  report(r) +
  '\n' +
  [...r.keys.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${v.toFixed(2).padStart(8)} ${k}`)
    .join('\n') +
  '\n'
console.log(out)
const target = args.includes('--out') ? args[args.indexOf('--out') + 1] : null
if (target) writeFileSync(target, out, 'utf8')
