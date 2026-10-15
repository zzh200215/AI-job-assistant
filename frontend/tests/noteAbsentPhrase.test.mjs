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

/* 2026-10-14 组合分析（第三把尺那张表）是**第五与第六个消费者**。同一条理由：
   这句话在六份文件里各写一遍，迟早一份改了另五份没改。 */
const portfolioHtmlSource = await read('backend/app/services/portfolio_report_html.py')
const portfolioVueSource = await read('frontend/src/features/resume/views/PortfolioReport.vue')

test('the portfolio renderer consumes it instead of retyping it', () => {
  assert.match(
    portfolioHtmlSource,
    /from app\.services\.report_html_lint import[^)\n]*\bNOTE_ABSENT\b/,
    '组合分析的渲染器不再从机检那一份取这句话，而是自己重打了一遍'
  )
  assert.ok(
    !portfolioHtmlSource.includes(absentPhrase),
    '组合分析渲染器里又出现这份句子的字面量：两处权威'
  )
})

test('the portfolio page says exactly the same sentence', () => {
  assert.ok(
    portfolioVueSource.includes(absentPhrase),
    `组合分析那一页的空栏标记与机检不同一句：机检认的是「${absentPhrase}」`
  )
})

test('那一族的"命中红线不出题"也只有一句权威', async () => {
  /* 与 NOTE_ABSENT 同一条毛病：出局那份不许续跑第四节，接口层与人话说明各有出处。
     单项目与组合两族的接口都读各自 schema 里那一个常量，而不是在 api 层重打一遍。 */
  const apiSource = await read('backend/app/api/resume.py')
  const projectSchema = await read('backend/app/services/project_report_schema.py')
  const portfolioSchema = await read('backend/app/services/portfolio_report_schema.py')
  for (const [name, source] of [
    ['project', projectSchema],
    ['portfolio', portfolioSchema],
  ]) {
    const sentence = source.match(/^EXCLUDED_NO_QUESTIONS_MESSAGE = \(?\s*"(.+?)"$/m)?.[1]
    assert.ok(sentence, `${name} 那一侧找不到这一句话的权威`)
    assert.ok(
      !apiSource.includes(sentence),
      `api/resume.py 里重打了一遍「${name}」那句人话：两处权威`
    )
  }
})

/* 2026-10-15：树里有了第三把尺之后，"这把尺与另外几把不是一把"那句话本身漂了——
   两份下载 HTML 与应用内两页 Vue 各写一遍，写的时候都还是"两把尺"的世界。
   同一条毛病第三次现形，所以这条钉子从"一句话"扩到"这一族的四份交付物"。 */
const rubricNote = lintSource.match(/^THREE_RUBRICS_NOTE = "(.+)"$/m)?.[1]

test('那把"几把尺"的自报只有一处权威', () => {
  assert.ok(rubricNote, '没在 report_html_lint.py 里找到 THREE_RUBRICS_NOTE，权威那一侧已经变了')
  assert.equal(
    lintSource.match(/^THREE_RUBRICS_NOTE = /gm).length,
    1,
    '这句话在机检那一份里出现了两份权威'
  )
  for (const [name, source] of [
    ['单项目', projectHtmlSource],
    ['组合', portfolioHtmlSource],
  ]) {
    assert.match(
      source,
      /from app\.services\.report_html_lint import[^)\n]*\bTHREE_RUBRICS_NOTE\b/,
      `${name}的渲染器不再从权威那一份取这句，而是自己重打了一遍`
    )
    assert.ok(!source.includes(rubricNote), `${name}的渲染器里又出现这句的字面量：两处权威`)
  }
})

test('应用内那两页说的是同一句', () => {
  for (const [name, source] of [
    ['单项目那一页', projectVueSource],
    ['组合那一页', portfolioVueSource],
  ]) {
    assert.ok(
      source.includes(rubricNote),
      `${name}的"几把尺"与权威不同一句：权威是「${rubricNote}」。` +
        '这句话漂成"两把尺"的时候没人会报错——它只是少告诉读者一件事。'
    )
  }
})

/* 2026-10-15：那两张随项目数变宽的表，地板宽是**活页量出来的三个数**（96 / 86 / 100），
   后端机检按它们重算一遍再比，前端那一页把它们抄成了 JS 常量。抄的这份没人比对的话，
   改后端那三个数时页面会静默地比下载件宽（或窄），而两边各自的测试都还绿。 */
const rubricSource = await read('backend/app/services/portfolio_report_rubric.py')

test('宽表那三个地板宽，两棵树是同一组数', () => {
  for (const name of ['WIDE_LABEL_PX', 'WIDE_CELL_PX', 'WIDE_TAIL_PX']) {
    const back = Number(rubricSource.match(new RegExp(`^${name} = (\\d+)$`, 'm'))?.[1])
    const front = Number(portfolioVueSource.match(new RegExp(`^const ${name} = (\\d+)$`, 'm'))?.[1])
    assert.ok(Number.isInteger(back), `后端 rubric 里找不到 ${name}，权威那一侧已经变了`)
    assert.ok(Number.isInteger(front), `组合分析那一页里找不到 ${name}，前端这一侧断了`)
    assert.equal(front, back, `${name} 两棵树不一样：后端 ${back}，前端 ${front}`)
  }
  const formula = rubricSource.match(/def wide_table_min_px[\s\S]*?return (.+)$/m)?.[1]
  assert.ok(
    formula?.includes('WIDE_TAIL_PX'),
    '地板宽那个函数不再带尾列那一档，前端抄的算法要一起改'
  )
})
