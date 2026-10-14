import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

/* 某一维没写出待优化点时，屏上那句"这一栏空着"的标记必须与交付前机检认的那句**逐字相同**。

为什么要有这条：机检（`report_html_lint._check_dimension_notes`）判"给了分却没写待优化点"，
看的是那一栏正文为空、或等于 `NOTE_ABSENT` 这句话。这句话本来在三处各写了一遍
（机检、HTML 渲染器、Vue 那一页）——两份渲染形态迟早一份改了另一份没改，
那时同一份报告在应用里显示"没写"、下载那一份却照样过机检，两边各自都看起来正常。
现在 HTML 渲染器与机检共用同一个常量，Vue 那一页是另一棵树，所以用这条钉子比对。 */

const repoRoot = new URL('../../', import.meta.url)
const read = (rel) => readFile(new URL(rel, repoRoot), 'utf8')

const lintSource = await read('backend/app/services/report_html_lint.py')
const vueSource = await read('frontend/src/features/resume/views/ResumeReport.vue')
const htmlSource = await read('backend/app/services/resume_report_html.py')

const absentPhrase = lintSource.match(/^NOTE_ABSENT = "(.+)"$/m)?.[1]

test('the delivery lint owns the empty-note sentence', () => {
  assert.ok(absentPhrase, '没在 report_html_lint.py 里找到 NOTE_ABSENT，判据那一侧已经变了')
  assert.equal(lintSource.match(/^NOTE_ABSENT = /gm).length, 1, '这句话在机检里出现了两份权威')
})

test('the standalone renderer consumes it instead of retyping it', () => {
  assert.match(
    htmlSource,
    /from app\.services\.report_html_lint import[^)]*\bNOTE_ABSENT\b/,
    'HTML 渲染器不再从机检那一份取这句话，而是自己重打了一遍'
  )
  assert.ok(!htmlSource.includes(absentPhrase), '渲染器里又出现这份句子的字面量：两处权威')
})

test('the in-app page says exactly the same sentence', () => {
  assert.ok(
    vueSource.includes(absentPhrase),
    `应用内那一页的空栏标记与机检不同一句：机检认的是「${absentPhrase}」`
  )
})

/* 2026-10-14 单项目分析（六维那张表）是**第三与第四个消费者**：同一句"这一栏空着"
   在四份文件里各写一遍，迟早一份改了另三份没改——那时下载的那份过机检、应用里那句 yet 不一样。
   这里把新两棵树也纳入同一条比对。 */
const projectHtmlSource = await read('backend/app/services/project_report_html.py')
const projectVueSource = await read('frontend/src/features/resume/views/ProjectReport.vue')

test('the project-report renderer consumes it too instead of retyping it', () => {
  assert.match(
    projectHtmlSource,
    /from app\.services\.report_html_lint import[^)\n]*\bNOTE_ABSENT\b/,
    '单项目分析的渲染器不再从机检那一份取这句话，而是自己重打了一遍'
  )
  assert.ok(
    !projectHtmlSource.includes(absentPhrase),
    '单项目分析渲染器里又出现这份句子的字面量：两处权威'
  )
})

test('the project-analysis page says exactly the same sentence', () => {
  assert.ok(
    projectVueSource.includes(absentPhrase),
    `单项目分析那一页的空栏标记与机检不同一句：机检认的是「${absentPhrase}」`
  )
})
