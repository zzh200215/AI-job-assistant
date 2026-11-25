/**
 * 应用内「工程口径」那一页与 `docs/交付摘要.md` 必须说的是同一组数（D12）。
 *
 * 为什么需要这条：这一页存在的意义是"只有浏览器、没有仓库的人也能读到工程口径"，
 * 所以它天然是**第二处写法**。第二处就会漂：文档改了读数、页面没跟，屏幕上那句就成了假话，
 * 而没有任何东西会红——这正是 D5 那条"守卫只看一个方向"的同类。
 *
 * 判据刻意做得笨：只比**关键读数的字面量是否两边都在**。它不保证两处措辞一致
 * （那本来就该不一致：文档给仓库读者，页面给浏览器读者），只保证数字不会各说各的。
 */

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import assert from 'node:assert/strict'

const FRONTEND = process.cwd()
const DOC = path.join(FRONTEND, '..', 'docs', '交付摘要.md')
const PAGE = path.join(
  FRONTEND,
  'src',
  'features',
  'shell',
  'views',
  'DeliveryGuideEngineering.vue'
)

/* 必须两边都在的读数：后端用例数、前端用例数、前端文件数、静态守卫条数、首屏与天花板、ruff 文件数。 */
const SHARED_NUMBERS = ['1631', '825', '129', '57', '406', '420', '498']

const doc = fs.readFileSync(DOC, 'utf8')
const page = fs.readFileSync(PAGE, 'utf8')

test('两处都写着的那组读数，任一处缺了就红', () => {
  /* 非空断言：文件挪了/编码坏了会让下面的比对变成"两边都空"的假绿。 */
  assert.ok(doc.length > 2000, `交付摘要.md 读出来只有 ${doc.length} 字符，路径或编码不对`)
  assert.ok(doc.includes('D1–D18'), '交付摘要.md 里找不到标题里的 D1–D18，读的可能是别的文件')
  assert.ok(page.includes('D1') && page.includes('D11'), '工程口径组件里找不到 D 系列轮次')

  for (const value of SHARED_NUMBERS) {
    assert.ok(doc.includes(value), `交付摘要.md 里没有读数 ${value}——文档更新了？`)
    assert.ok(page.includes(value), `工程口径页面里没有读数 ${value}——页面没跟上文档`)
  }
})

test('十八轮一条都不许缺：页面与文档的轮次集合必须相同', () => {
  const rounds = Array.from({ length: 18 }, (_, index) => `D${index + 1}`)

  for (const id of rounds) {
    /* 2026-11-16 修的一个洞：原来查的是 `\bD16\b`，而页面开头那句「D1–D18 分两半」正好命中——
       于是"第十四轮那一项没写"照样绿。现在两边各查**结构**而不是字符串：
       页面要有一条 `id: 'D16'` 的轮次项，文档要有一行 `| **D16** |` 的表行。 */
    assert.match(
      page,
      new RegExp(`id: '${id}'`),
      `工程口径页面缺了 ${id} 的轮次项（不是提到名字就算，要有一条 id: '${id}'）`
    )
    assert.match(doc, new RegExp(`\\| \\*\\*${id}\\*\\* \\|`), `交付摘要.md 缺了 ${id} 的表行`)
  }
})
