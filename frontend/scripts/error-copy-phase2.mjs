import { readFileSync, writeFileSync } from 'node:fs'

/* D100：§10.22 那族泄漏的第二半。D92 收掉的是 `x?.userMessage || x?.message || '中文'`（25 处），
   判据要求前面有 `userMessage ||`。但还有 27 处**连 userMessage 都不读**，直接把 catch 绑定对象的
   `.message` 当用户文案（`userErrorCopy` 的注释里写着"技术串留在 err.message 给日志"，正是给这一族看的）。
   这一脚本按逐文件期望计数改，任何一处对不上就不写盘。载荷字段（`data.message`、`overview.message`）
   不在这一族里，判据按 catch 绑定名筛，不靠变量名猜。 */

const FILES = {
  'src/features/analysis/views/ExplainMatch.vue': 1,
  'src/features/analysis/views/AnalysisResult.vue': 2,
  'src/features/analysis/views/SmartAnalysis.vue': 2,
  'src/features/billing/views/Subscription.vue': 2,
  'src/features/interview/views/Interview.vue': 1,
  'src/features/interview/views/InterviewReport.vue': 1,
  'src/features/interview/views/InterviewRoom.vue': 1,
  'src/features/interview/views/InterviewSetup.vue': 1,
  'src/features/jobs/views/JobRecommend.vue': 3,
  'src/features/knowledge/views/KnowledgeBase.vue': 1,
  'src/features/planning/views/CareerPlanning.vue': 1,
  'src/features/resume/views/ResumeCompare.vue': 9,
  'src/features/resume/views/ResumeUpload.vue': 1,
  // `src/stores/interview.js` 只算请求层那一条（"创建面试失败"）；同文件 :162 那条是 **WebSocket**
  // 回调参数，拿到的不是请求层的 Error（没有 userMessage 可读），兜底句也不同，单独手改。
  'src/stores/interview.js': 1,
}
const IMPORT = `import { userErrorCopy } from '@/utils/requestTracing'`
const NETWORK = '网络异常，请稍后重试'

// A: `VAR?.message || '兜底'`（含 `|| VAR` 的尾巴，那会把整个 Error 拼进提示）
const SHAPE_A =
  /([A-Za-z_$][\w$]*)(\??)\.message\s*\|\|\s*(?:'([^']*)'|"([^"]*)"|([A-Za-z_$][\w$]*))/g
// B: 模板串里的 `${VAR?.message}`（没有 || 也要收：那会把 undefined 印给人看）
const SHAPE_B = /\$\{([A-Za-z_$][\w$]*)(\??)\.message\}/g
// C: 运行链返回的结果对象上挂的 Error：`outcome.error?.message || '兜底'`。
//    它不是 catch 绑定（链自己把异常收进返回值），但下游拿到的是同一个 Error 对象。
const SHAPE_C = /([A-Za-z_$][\w$]*)\.error(\??)\.message\s*\|\|\s*'([^']*)'/g

const staged = []
let total = 0
for (const [rel, expected] of Object.entries(FILES)) {
  const original = readFileSync(rel, 'utf8')
  // 绑定名两族：`catch (X)`，以及轮询那套回调参数 `onFailed(error)` / `onCancelled(error)`
  // （它们拿的就是请求层抛出来的同一个对象，所以同样有 userMessage 可读）。
  const binds = new Set([
    ...[...original.matchAll(/\bcatch\s*\(\s*([A-Za-z_$][\w$]*)/g)].map((m) => m[1]),
    ...[
      ...original.matchAll(/\bon(?:Failed|Error|Cancelled|Catch)\s*\(\s*([A-Za-z_$][\w$]*)/g),
    ].map((m) => m[1]),
  ])
  let hits = 0
  let out = original.replace(SHAPE_A, (whole, v, opt, s1, s2, alias) => {
    if (!binds.has(v)) return whole
    if (alias !== undefined) {
      // `x.message || x`：兜底只能是中文一句，原写法会把 Error 对象 stringify 上屏
      hits += 1
      return `userErrorCopy(${v}, '${NETWORK}')`
    }
    const copy = s1 ?? s2
    hits += 1
    return `userErrorCopy(${v}, '${copy}')`
  })
  out = out.replace(SHAPE_B, (whole, v) => {
    if (!binds.has(v)) return whole
    hits += 1
    return `\${userErrorCopy(${v}, '${NETWORK}')}`
  })
  out = out.replace(SHAPE_C, (whole, obj, _opt, copy) => {
    hits += 1
    return `userErrorCopy(${obj}.error, '${copy}')`
  })
  if (hits !== expected) {
    console.error(`${rel}: 期望 ${expected} 处，实到 ${hits} —— 不写盘`)
    process.exit(1)
  }
  if (hits && !out.includes(IMPORT)) {
    const eol = out.includes('\r\n') ? '\r\n' : '\n'
    const m = out.match(/^<script[^\n\r>]*>/m)
    if (m) out = out.replace(m[0], `${m[0]}${eol}${IMPORT}`)
    else {
      const first = out.match(/^import .*\r?\n/m)
      if (!first) {
        console.error(`${rel}: 找不到 import 锚点`)
        process.exit(1)
      }
      out = out.replace(first[0], `${first[0]}${IMPORT}${eol}`)
    }
    const at = out.split('\n').findIndex((l) => l === IMPORT)
    const open = out.split('\n').findIndex((l) => /^<script\b/.test(l))
    const close = out.split('\n').findIndex((l) => /^<\/script>/.test(l))
    if (!rel.endsWith('.vue')) continue
    if (!(at > open && at < close)) {
      console.error(`${rel}: import 落在脚本块之外（行 ${at + 1}）—— 不写盘`)
      process.exit(1)
    }
  }
  total += hits
  staged.push([rel, out, hits])
}
if (total !== 26) {
  console.error(`总数应为 26，实为 ${total} —— 不写盘`)
  process.exit(1)
}
for (const [rel, out] of staged) writeFileSync(rel, out, 'utf8')
for (const [rel, , hits] of staged) console.log(`${hits}\t${rel}`)
console.log(`合计 ${total} 处`)
