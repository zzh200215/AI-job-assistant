import { readFileSync, writeFileSync } from 'node:fs'

const EXPECT = {
  'src/features/pipeline/views/PipelineKanban.vue': 1,
  'src/features/legal/views/Privacy.vue': 1,
  'src/features/planning/composables/useSalaryMarket.js': 1,
  'src/features/planning/composables/useCareerDirections.js': 1,
  'src/features/resume/views/ResumeCompare.vue': 1,
  'src/features/shell/views/History.vue': 1,
  'src/features/jobs/views/SalaryInsight.vue': 2,
  'src/features/resume/views/ResumeUpload.vue': 2,
  'src/features/auth/views/Login.vue': 1,
  'src/features/jobs/views/JobRecommend.vue': 6,
  'src/features/jobs/composables/useJobRecommend.js': 1,
  'src/features/jobs/composables/useJobPipeline.js': 1,
  'src/features/jobs/views/JobSearch.vue': 2,
  'src/features/jobs/composables/useJobWarehouse.js': 1,
  'src/features/interview/views/Interview.vue': 3,
}

const IMPORT = `import { userErrorCopy } from '@/utils/requestTracing'`

/** 形态 A：`VAR?.userMessage || VAR?.message || '兜底'` —— 整个三元回落收进一个出口。 */
const SHAPE_A =
  /([A-Za-z_$][\w$]*)(\??)\.userMessage\s*\|\|\s*\1(\??)\.message\s*\|\|\s*(['"`])((?:\\.|[^\\'"`])*)\4/g

/** 形态 B：`'前缀: ' + (VAR.userMessage || VAR.message || VAR)` —— 拼串那四处，前缀逐字保留。 */
const SHAPE_B =
  /(['"`])((?:(?!\1)[^\\]|\\.)*?)\1\s*\+\s*\(([A-Za-z_$][\w$]*)(\??)\.userMessage\s*\|\|\s*\3(\??)\.message\s*\|\|\s*\3\)/g

const staged = []
let total = 0
for (const [rel, expected] of Object.entries(EXPECT)) {
  const original = readFileSync(rel, 'utf8')
  let hits = 0
  let out = original.replace(SHAPE_A, (_m, v, _o1, _o2, q, copy) => {
    hits += 1
    return `userErrorCopy(${v}, ${q}${copy}${q})`
  })
  out = out.replace(SHAPE_B, (_m, _q, prefix, v) => {
    hits += 1
    // 前缀串本身就带 `: `，不要再补一个冒号（第一版就是这么把四处写成 `xx: : ` 的）。
    return `\`${prefix}\${userErrorCopy(${v}, '网络异常，请稍后重试')}\``
  })
  if (hits !== expected) {
    throw new Error(`${rel}: 期望 ${expected} 处，实到 ${hits} —— 不写盘`)
  }
  if (!out.includes(IMPORT)) {
    const eol = out.includes('\r\n') ? '\r\n' : '\n'
    if (rel.endsWith('.vue')) {
      const m = out.match(/^<script[^\n\r>]*>/m)
      if (!m) throw new Error(`${rel}: 找不到 <script> 开标签`)
      out = out.replace(m[0], `${m[0]}${eol}${IMPORT}`)
    } else {
      const first = out.match(/^import .*\r?\n/m)
      if (!first) throw new Error(`${rel}: 找不到首行 import`)
      out = out.replace(first[0], `${first[0]}${IMPORT}${eol}`)
    }
  }
  total += hits
  staged.push([rel, original, out, hits])
}
if (total !== 25) throw new Error(`总数应为 25，实为 ${total} —— 不写盘`)

for (const [rel, , out] of staged) writeFileSync(rel, out, 'utf8')
for (const [rel, , , hits] of staged) console.log(`${hits}\t${rel}`)
console.log(`合计 ${total} 处`)
