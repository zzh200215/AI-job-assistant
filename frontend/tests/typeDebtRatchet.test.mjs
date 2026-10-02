import test from 'node:test'
import assert from 'node:assert/strict'
import process from 'node:process'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// 全仓类型错的计数棘轮。跑的是 vue-tsc 本身，不是缓存、不是抽样。
// 一次约 24 秒，所以它住在 node --test 这一层（CI 的 `npm test`），不进 vitest 那 71 个文件。
const BUDGET = 65

// 编译器"看到多少个文件"。D40 那次的教训是尺子会跟着搬家安静地少测文件，所以这条不是装饰：
// include 少一根、或某类文件改了扩展名，先在这里红，而不是等到"债清完了"才发现量的是空气。
// 按扩展名各点一个下限，是因为实测过去掉 `src/**/*.vue` 那根只少 1 个文件（其余 .vue 仍被
// import 拖着进程序）——只看总数的话这条腿只剩 1 的余量。
const MIN_PROGRAM_FILES = 128
const MIN_BY_EXTENSION = { vue: 68, js: 59, ts: 1 }
const NAMED_ROOTS = [
  'src/features/jobs/views/JobSearch.vue',
  'src/features/analysis/views/SmartAnalysis.vue',
  'src/features/pipeline/views/PipelineKanban.vue',
  'src/features/interview/views/InterviewRoom.vue',
  'src/api/http-client.d.ts',
]

const FRONTEND = fileURLToPath(new URL('..', import.meta.url))
const VUE_TSC = fileURLToPath(new URL('../node_modules/vue-tsc/bin/vue-tsc.js', import.meta.url))

function runVueTsc(extraArgs) {
  const result = spawnSync(
    process.execPath,
    [VUE_TSC.replace(/\\/g, '/'), '--noEmit', '-p', 'tsconfig.json', ...extraArgs],
    { cwd: FRONTEND, encoding: 'utf8', maxBuffer: 128 * 1024 * 1024 }
  )
  assert.equal(result.error, undefined, `vue-tsc failed to start: ${result.error?.message}`)
  // 0 = 干净，2 = 有类型错。别的退出码是崩了或参数错了——那种情况下"0 条错"是假绿灯。
  assert.ok(
    result.status === 0 || result.status === 2,
    `vue-tsc exited with ${result.status}, which is not a type-error run:\n${(result.stderr || '').slice(0, 2000)}`
  )
  return result.stdout.replace(/\\/g, '/')
}

const output = runVueTsc(['--listFiles'])
const lines = output.split(/\r?\n/)
const errorLines = lines.filter((l) => /error TS\d+/.test(l))
const programFiles = lines.filter(
  (l) =>
    !/error TS\d+/.test(l) &&
    !l.includes('/node_modules/') &&
    /(?:^|\/)src\/.+\.(vue|js|ts)$/.test(l)
)

test('the compiler run is a real run, not a crash that printed no errors', () => {
  const seen = {}
  for (const f of programFiles) {
    const ext = f.split('.').pop()
    seen[ext] = (seen[ext] || 0) + 1
  }
  for (const [ext, floor] of Object.entries(MIN_BY_EXTENSION)) {
    assert.ok(
      (seen[ext] || 0) >= floor,
      `vue-tsc saw ${seen[ext] || 0} .${ext} files under src/ (floor ${floor}) — the "${ext}" include root went missing`
    )
  }
  assert.ok(
    programFiles.length >= MIN_PROGRAM_FILES,
    `vue-tsc only saw ${programFiles.length} files under src/ (floor ${MIN_PROGRAM_FILES}) — an include root went missing`
  )
  for (const root of NAMED_ROOTS) {
    assert.ok(
      programFiles.some((f) => f.endsWith(root)),
      `${root} is not in the compiler's file set — the ruler would silently stop measuring it`
    )
  }
  for (const line of errorLines.slice(0, 5)) {
    assert.match(line, /\S+\(\d+,\d+\): error TS\d+:/, `unparseable error line: ${line}`)
  }
})

test('keeps the whole-repo type error count within the budget', () => {
  assert.ok(
    errorLines.length <= BUDGET,
    `type errors grew: ${errorLines.length} > ${BUDGET}\n${errorLines.slice(0, 10).join('\n')}`
  )
})

test('forces the type budget to be tightened once debt is paid down', () => {
  assert.ok(
    errorLines.length >= BUDGET,
    `type debt went down — lower BUDGET in tests/typeDebtRatchet.test.mjs to ${errorLines.length}`
  )
})
