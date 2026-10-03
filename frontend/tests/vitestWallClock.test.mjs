import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/* D104：`vite.config.js` 的 `test` 段以前从没设过 `testTimeout`，于是 82 个文件里每一条
   时序敏感断言共用 vitest 的隐式 5s 墙——实测空闲全量最慢的一条就是 3.88s（只剩 1.28 倍余量），
   故意把机器压成两倍负载时红 8–9 个文件、全是 `Test timed out in 5000ms`。
   这条门钉的是"上限必须存在、且不许有第二处比它更高"：
   墙钟上限散落在各个测试文件里，就没人知道整把尺子的量程是多少（`jobPipelinePane` 那处手工抬高
   就是这件事的样本——它救过那条测试，同时让"全局上限是多少"这个问题变得没人答得上）。 */

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const configSource = readFileSync(path.join(root, 'vite.config.js'), 'utf8')

// 只认 `test: { … testTimeout: N … }` 里的那个 N，不认注释里提到的数。
function globalTestTimeout(source) {
  const block = source.match(/test:\s*\{([\s\S]*?)\n\s{2}\}/)
  if (!block) return null
  const stripped = block[1].replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
  const hit = stripped.match(/testTimeout:\s*(\d+)/)
  return hit ? Number(hit[1]) : null
}

function perTestTimeouts(dir) {
  /* 第一版把扩展名过滤放在目录判断之前，于是 `tests/unit` 整个被 `continue` 掉——
     这条腿在**空集合**上跑，永远绿（D96 那把在空目录上跑的判定器，同一族第十三次复发）。
     现在先分叉：目录无条件递归，文件只认 `.test.js`；并打印扫到的文件数，为 0 直接红。 */
  const hits = []
  let scanned = 0
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      const nested = perTestTimeouts(full)
      hits.push(...nested.hits)
      scanned += nested.scanned
      continue
    }
    if (!entry.name.endsWith('.test.js')) continue
    scanned += 1
    const source = readFileSync(full, 'utf8')
    for (const match of source.matchAll(/\n\s*\},\s*(\d{4,})\)/g)) {
      hits.push({
        rel: path.relative(root, full).split(path.sep).join('/'),
        value: Number(match[1]),
      })
    }
  }
  return { hits, scanned }
}

const GLOBAL = globalTestTimeout(configSource)

test('the vitest wall-clock ceiling is set, not implicit', () => {
  assert.ok(
    GLOBAL !== null,
    'vite.config.js 的 test 段没有 testTimeout——那意味着 82 个文件共用 vitest 的隐式 5s 墙（D104）'
  )
  assert.ok(
    GLOBAL >= 20000,
    `testTimeout 现在是 ${GLOBAL}ms；空闲最慢的一条已经 3.88s，低于 20000 就等于把 5s 墙换个数字继续撞`
  )
})

test('no test carries a per-test ceiling above the global one', () => {
  const { hits, scanned } = perTestTimeouts(path.join(root, 'tests'))
  assert.ok(scanned > 50, `只扫到 ${scanned} 个测试文件——这把尺子又在看空目录了（判据本身要能红）`)
  const offenders = hits.filter((h) => h.value > GLOBAL)
  assert.deepEqual(
    offenders,
    [],
    `这些测试自己抬了更高的墙钟上限，全局那个数就不再是量程：${JSON.stringify(offenders)}`
  )
})

test('the reader itself is not blind', () => {
  // 反向证据：把配置改成"没设"与"设小了"，读出来的数必须分别是 null 与 5000，否则上面两条是空的。
  // 夹具按 prettier 的真实形状缩进（`test: {` 换行、闭合在 2 格），因为解析器认的就是那个形状。
  const unset = 'export default {\n  test: {\n    environment: "jsdom",\n  },\n}\n'
  assert.equal(globalTestTimeout(unset), null)
  const fiveSeconds =
    'export default {\n  test: {\n    /* testTimeout: 99999 */\n    testTimeout: 5000,\n  },\n}\n'
  assert.equal(globalTestTimeout(fiveSeconds), 5000, '注释里的数字不能被当成配置')
})
