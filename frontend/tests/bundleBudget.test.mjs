/**
 * D5：首屏字节数的天花板。
 *
 * 为什么要有这条：D90 把 59 项手写注册表换成 `unplugin-vue-components` 时，量过一笔账并写进了
 * `vite.config.js`——构建总量 1894.58 → 约 2242.63 kB（+18.4%），由产品负责人指令覆盖测量建议。
 * 那次之后**再没有任何东西看着这个数**：包只会变胖，而"变胖"在 CI 里是完全安静的。
 * 这条闸把它变成一个数字：只许降、或者带着理由往上抬一格。
 *
 * 量的是**发出去的那几个字节**，不是构建总量：
 *   · 首屏 = `dist/index.html` 里 `<script src>` 与 `<link rel=modulepreload|stylesheet>` 指到的文件
 *     （Vite 已经把静态依赖的 modulepreload 写进去了，所以这份清单就是"页面画出来之前必须到的"）；
 *   · 单块 = 任何一个 js 分块 gzip 后的大小，用来拦"有人从 barrel 里 import 了一个库"这种事故。
 * gzip 用 level 9、与本机/CI 无关（同样的输入同样的字节数），所以这两条不是环境敏感的门。
 *
 * 它顺带是一道"还编得出来"的门——`npm test` 此前不跑 `npm run build`，CI 里那次构建在
 * 测试之后才跑，构建坏了要等到最后一步才知道。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import process from 'node:process'
import { spawnSync } from 'node:child_process'
import { readFileSync, readdirSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const FRONTEND = fileURLToPath(new URL('..', import.meta.url))
const DIST = path.join(FRONTEND, 'dist')
const VITE = path.join(FRONTEND, 'node_modules', 'vite', 'bin', 'vite.js')

/** 首屏（index.html 直接引用到的 js+css）gzip 总量。2026-11-14 实测 406 kB。 */
const INITIAL_BUDGET_KB = 420
/** 任何单个 js 分块 gzip 后的上限。2026-11-14 最大是 vendor-element 245 kB。 */
const SINGLE_CHUNK_BUDGET_KB = 260

const kb = (bytes) => Math.round(bytes / 1024)

const build = spawnSync(process.execPath, [VITE, 'build', '--logLevel', 'error'], {
  cwd: FRONTEND,
  encoding: 'utf8',
  maxBuffer: 64 * 1024 * 1024,
})
assert.equal(
  build.status,
  0,
  `前端已经编不出来了（这正是这条闸要拦的第一件事）：\n${(build.stderr || build.stdout || '').slice(0, 3000)}`
)

const html = readFileSync(path.join(DIST, 'index.html'), 'utf8')
const initialRefs = [
  ...new Set(
    [...html.matchAll(/(?:src|href)\s*=\s*"\/?(assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1])
  ),
]
const initialBytes = initialRefs.reduce(
  (sum, rel) => sum + gzipSync(readFileSync(path.join(DIST, rel)), { level: 9 }).length,
  0
)

const jsFiles = readdirSync(path.join(DIST, 'assets')).filter((f) => f.endsWith('.js'))
const sizes = jsFiles
  .map((f) => ({
    f,
    gz: gzipSync(readFileSync(path.join(DIST, 'assets', f)), { level: 9 }).length,
  }))
  .sort((a, b) => b.gz - a.gz)

test('首屏 gzip 总量不许超过预算', () => {
  // 防空转：清单必须真的指到东西，且每个文件都不是空的
  assert.ok(initialRefs.length >= 8, `首屏只引用了 ${initialRefs.length} 个文件，取数方式变了`)
  assert.ok(initialBytes > 100 * 1024, `首屏只算出 ${kb(initialBytes)} kB，说明量错了`)
  // 每次跑都把这一行数字打出来（绿的时候也打）：这条闸的价值一半在"看得见"。
  // 用 stdout.write 而不是 console.log —— 全仓 test 里没有一处 console.*，`no-console` 是 warning，
  // 写 console.log 会让 lint 的 warning 预算从 87 变成 88。
  process.stdout.write(
    `首屏 ${kb(initialBytes)} kB gzip（预算 ${INITIAL_BUDGET_KB}）· ${initialRefs.length} 个文件 · 最大单块 ${sizes[0].f} ${kb(sizes[0].gz)} kB\n`
  )
  assert.ok(
    kb(initialBytes) <= INITIAL_BUDGET_KB,
    `首屏涨到 ${kb(initialBytes)} kB gzip（预算 ${INITIAL_BUDGET_KB}）：把新增的重量说清楚，或把预算往下一格抬`
  )
})

test('没有哪个分块大到"整包进来了"的样子', () => {
  const worst = sizes[0]
  assert.ok(jsFiles.length >= 60, `只产出 ${jsFiles.length} 个 js 分块，按路由切分可能被破坏了`)
  assert.ok(
    kb(worst.gz) <= SINGLE_CHUNK_BUDGET_KB,
    `${worst.f} 有 ${kb(worst.gz)} kB gzip（上限 ${SINGLE_CHUNK_BUDGET_KB}）：多半是某个 barrel/全量入口被整包 import 了`
  )
})
