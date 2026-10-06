import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

/* D119：`scripts/dead-style.mjs` 这把尺从 D76 装好那天起**没进过任何门**，全靠人手动跑一次、
   把数字抄进账。实测后果就在眼前：D109 摘掉企业版块时标记走了、`@media` 里那条
   `.enterprise-body` 留下，**全仓没有一条测试会因此红**。现在把"候选必须为 0"变成门。
   门槛数字（文件数、规则数）是防空转的：扫描如果因为路径/解析坏了只看到一小撮文件，
   "候选 0"就是假绿——这一族在这一仓里已经红过五次（D40/D96/D104/D106/D112）。 */

const sweep = () =>
  JSON.parse(
    execFileSync('node', ['scripts/dead-style.mjs', '--json'], {
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    })
  )

test('the dead-style sweep sees the whole tree, not a corner of it', () => {
  const rows = sweep()
  assert.ok(rows.length >= 66, `只扫到 ${rows.length} 个 .vue，这把尺又在看空目录`)
  const rules = rows.reduce((a, r) => a + r.rules, 0)
  assert.ok(rules >= 2000, `规则总数 ${rules}，不像扫到了整仓（解析器又漏形状了）`)
  assert.ok(
    rows.some((r) => /SmartAnalysis\.vue$/.test(r.file)),
    '扫描里不含 SmartAnalysis.vue——文件集或路径变了'
  )
})

test('there is not a single dead-style candidate left in the tree', () => {
  const rows = sweep()
  const candidates = rows.flatMap((r) =>
    r.candidates.map((c) => `${r.file}: [${c.why}] ${String(c.selector).slice(0, 70)}`)
  )
  assert.deepEqual(
    candidates,
    [],
    '新出现的死规则候选。删之前要按 D67/D119 那套办法证它在真浏览器里 0 命中' +
      '（探针 `probe/dead-style.html`，判据写在 D76/D79/D85），不是看到名字没用就删'
  )
  const undecidable = rows.filter((r) => (r.undecidable || []).length)
  assert.deepEqual(
    undecidable.map((r) => `${r.file}: ${(r.undecidable || []).length} 条`),
    [],
    '出现"前缀认得、后缀不在已声明值域里"的规则：要判它先把值域加进 src/constants/states.js，' +
      '而不是把这条腿放宽'
  )
})

test('the counter bites: a rule whose class is nowhere in the file is reported', () => {
  /* 反向证据不能只对着全仓那 2473 条规则说"它们都被保护了"。这里造一条必死的：
     一个只出现在规则里、模板/脚本/动态拼法都没有的类名。
     临时文件写在**系统临时目录**，不写进 `src`——`npm test` 是并行跑多个进程的，
     往 `src` 里放一个带 `color: red` 的文件会串到同批的 `typeDebtRatchet`（它跑 vue-tsc 数错）
     和其它扫 `src` 的守卫上；万一进程被杀，那还会留一个孤儿文件在树里。 */
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'deadstyle-selftest-'))
  const tmp = path.join(dir, 'selftest.vue')
  fs.writeFileSync(
    tmp,
    [
      '<template>',
      '  <div class="selftest-page">',
      '    <p class="selftest-kept">留着</p>',
      '  </div>',
      '</template>',
      '<style scoped>',
      '.selftest-page {',
      '  color: red;',
      '}',
      '.selftest-kept {',
      '  margin: 0;',
      '}',
      '.selftest-orphan {',
      '  padding: 4px;',
      '}',
      '</style>',
      '',
    ].join('\n'),
    'utf8'
  )
  try {
    const rows = JSON.parse(
      execFileSync('node', ['scripts/dead-style.mjs', '--json', tmp], {
        encoding: 'utf8',
        maxBuffer: 8 * 1024 * 1024,
      })
    )
    // 先确认解析器真的读到了三条规则：`rulesOf` 是按行认 `{` 的，写成一行它会数出 0，
    // 那么"候选为空"就是假绿（这一族今天第三次现形）。
    assert.equal(rows[0].rules, 3, `解析器只数到 ${rows[0].rules} 条规则，自测本身在空转`)
    const found = rows.flatMap((r) => r.candidates.map((c) => c.selector))
    assert.deepEqual(found, ['.selftest-orphan'], `这条造出来的死规则没被抓到：${found}`)
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
    assert.ok(!fs.existsSync(dir), '临时目录没删干净')
  }
})
