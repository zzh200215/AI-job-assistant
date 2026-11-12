/**
 * D4：投递阶段的状态机，前端那份镜像必须和后端 `VALID_TRANSITIONS` 逐键相同。
 *
 * 为什么要有这条：D4 给看板卡片加了「移至「X」」菜单——拖拽在触屏上收不到 `dragstart`，
 * 手机上那张卡原先只能往"结束"走、前进不了。菜单要列出"能去哪"，而**能去哪是后端的规则**：
 * `api/job_pipeline.py:517` 拿 `VALID_TRANSITIONS` 判流转，不认的会回 422，原文是
 * `不允许从 'applied' 流转到 'todo'，允许的目标: interview, rejected, withdrawn, written_test [web-…]`
 * ——英文阶段键 + request id，候选人读不懂，还像是页面出了 bug。
 *
 * 那份表没法在测试里跨语言 import（Python 的 set 字面量），所以前端的镜像只能靠**解析比对**
 * 来钉：改一边不改另一边，这里当场红。这不是"复制一份更容易"，是"必须现在就知道"——菜单的
 * 每一项、拖拽的每一放，都要在发请求之前判完。
 *
 * 逃不掉的分叉风险用这条守卫兜住；守卫自己也要防空转（见最后一条），否则正则一失效，
 * 两边都解析成空对象也会绿。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BACKEND = readFileSync(
  join(HERE, '..', '..', 'backend', 'app', 'models', 'job_pipeline.py'),
  'utf-8'
)
const FRONTEND = readFileSync(
  join(HERE, '..', 'src', 'features', 'pipeline', 'lib', 'pipelineBoard.js'),
  'utf-8'
)

/** 从 `head` 处开始找那一对花括号之间的内容（含嵌套的一层 set/array 字面量）。 */
function braceBlock(src, head) {
  const at = src.indexOf(head)
  assert.ok(at >= 0, `找不到 ${head}：锚点变了，这条守卫要重取而不是放行`)
  let depth = 0
  for (let i = at + head.length - 1; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(at + head.length, i)
    }
  }
  throw new Error(`${head} 的花括号没有闭合`)
}

/** 后端：`STAGE_APPLIED = "applied"` 这种常量表 → { STAGE_APPLIED: 'applied' } */
function backendStageConstants() {
  const map = {}
  for (const hit of BACKEND.matchAll(/^(STAGE_[A-Z_]+)\s*=\s*"([a-z_]+)"\s*$/gm)) {
    map[hit[1]] = hit[2]
  }
  return map
}

/** 后端：VALID_TRANSITIONS 的每一条 → { applied: ['written_test', ...] }
 *  终态那三行写的是 `STAGE_ACCEPTED: set(),`——**没有花括号**，所以两种写法都要认，
 *  否则三个终态会安静地从读数里消失（第一次写这条守卫就是这么漏的：读到 5 个键）。 */
function backendTransitions() {
  const consts = backendStageConstants()
  const block = braceBlock(BACKEND, 'VALID_TRANSITIONS = {')
  const out = {}
  for (const line of block.split(/\r?\n/)) {
    const hit = line.match(/^\s*(STAGE_[A-Z_]+)\s*:\s*(\{([^}]*)\}|set\(\))\s*,?\s*$/)
    if (!hit) continue
    const from = consts[hit[1]]
    assert.ok(from, `${hit[1]} 没有对应的字符串常量：解析器的假设变了`)
    const inner = (hit[3] ?? '').trim()
    out[from] = inner
      ? inner.split(',').map((s) => {
          const name = s.trim()
          assert.ok(consts[name], `允许目标里出现未定义的常量 ${name}`)
          return consts[name]
        })
      : []
  }
  return out
}

/** 前端：`export const STAGE_TRANSITIONS = { todo: ['applied', 'withdrawn'], ... }` */
function frontendTransitions() {
  const block = braceBlock(FRONTEND, 'export const STAGE_TRANSITIONS = {')
  const out = {}
  for (const line of block.split(/\r?\n/)) {
    const hit = line.match(/^\s*([a-z_]+)\s*:\s*\[([^\]]*)\]\s*,?\s*$/)
    if (!hit) continue
    out[hit[1]] = hit[2]
      .split(',')
      .map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
      .filter(Boolean)
  }
  return out
}

const sorted = (list) => [...new Set(list)].sort()

test('前端镜像与后端 VALID_TRANSITIONS 逐阶段相同（键、目标、终态都算）', () => {
  assert.deepEqual(frontendTransitions(), backendTransitions())
})

test('镜像与真值都是八个阶段，一个不少', () => {
  const stages = sorted([
    ...Object.keys(backendTransitions()),
    ...Object.keys(frontendTransitions()),
  ])
  assert.deepEqual(stages, [
    'accepted',
    'applied',
    'interview',
    'offer',
    'rejected',
    'todo',
    'withdrawn',
    'written_test',
  ])
})

test('两条读数都不是从空气里来的', () => {
  const backend = backendTransitions()
  const frontend = frontendTransitions()
  // 防空转：解析失败会得到空表，两边都空也算"相同"，所以这里钉住真读到了东西
  assert.equal(Object.keys(backend).length, 8)
  assert.equal(Object.keys(frontend).length, 8)
  assert.ok(backend.applied.includes('written_test'), '后端 applied 的出口解析丢了')
  // 终态在后端是两对花括号（`set()`），在前端是空数组——两边都必须真的解析成"没有出口"
  for (const terminal of ['accepted', 'rejected', 'withdrawn']) {
    assert.deepEqual(backend[terminal], [], `${terminal} 在后端不是终态了`)
    assert.deepEqual(frontend[terminal], [], `${terminal} 在前端不是终态了`)
  }
  // 解析器确实看见了"同一段代码"的两种写法，而不是匹到了注释里的词
  assert.ok(BACKEND.includes('VALID_TRANSITIONS = {'))
  assert.ok(FRONTEND.includes('export const STAGE_TRANSITIONS = {'))
})
