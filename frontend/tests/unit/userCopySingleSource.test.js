import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

/* 这一文件管两件事，都是"给人看的那句话只有一个来源"：
   1. D92：错误文案。`api/request.js` 以前把 axios 的英文技术串（"Network Error"）写进
      `err.userMessage`，而下游二十几处写的是 `x?.userMessage || x?.message || '中文兜底'`——
      `userMessage` 非空时后面两项永远取不到，那句中文兜底是死代码，屏幕上就是英文串。
      现在面向用户的错误只有一个出口 `userErrorCopy(x, '…')`，它只认服务端文案。
   2. §10.21：同一个动作在两个视图里不许各写一句提示（原话是"已标记为拒绝"/"已标记拒绝"）。 */

const RAW_COPY_FALLBACK = /\w+\??\.userMessage\s*\|\|\s*\w+\??\.message/

/* 这两个文件是**规则本身**的家，注释里必须逐字写出被禁的那串，否则守卫把自己钉死了。
   白名单只放"解释这条规则的文件"，不放任何调用点。 */
const DOCUMENTS_THE_RULE = ['src/api/request.js', 'src/utils/requestTracing.js']

function sources(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return sources(full)
    return /\.(vue|js)$/.test(e.name) ? [full.split(path.sep).join('/')] : []
  })
}

const ALL = sources('src')
const textOf = (rel) => readFileSync(rel, 'utf8')

describe('错误文案只有一个出口', () => {
  it('src 里不再有任何一处把 err.message 当作用户可见文案', () => {
    const hits = ALL.filter(
      (rel) => !DOCUMENTS_THE_RULE.includes(rel) && RAW_COPY_FALLBACK.test(textOf(rel))
    )
    expect(hits, `这些地方还在读原始技术串：${hits.join(', ')}`).toEqual([])
  })

  it('反向证据：判据认得改之前那两种写法', () => {
    // 形态 A：赋值式（原先 21 处）
    expect(
      RAW_COPY_FALLBACK.test(`  weakError.value = e?.userMessage || e?.message || '稍后再试'`)
    ).toBe(true)
    // 形态 B：拼串弹提示式（JobRecommend 那 4 处）
    expect(
      RAW_COPY_FALLBACK.test(`  ElMessage.error('恢复失败: ' + (e.userMessage || e.message || e))`)
    ).toBe(true)
    // 现在的出口不会被误判
    expect(RAW_COPY_FALLBACK.test(`  weakError.value = userErrorCopy(e, '稍后再试')`)).toBe(false)
  })
})

describe('同一个动作只有一句提示', () => {
  const KANBAN = 'src/features/pipeline/views/PipelineKanban.vue'

  it('标记拒绝在全仓只有一句', () => {
    const hits = ALL.filter((rel) => textOf(rel).includes('已标记拒绝'))
    expect(hits, `这句短写法是 §10.21 淘汰的那一支：${hits.join(', ')}`).toEqual([])
  })

  it('看板与列表共用一份标签，值就是「已标记为拒绝」', () => {
    /* 判据认的是"标签表里 rejected 这一键的定义次数"——两处各写一张表正是当初漂起来的原因。
       反向证据：把这两句合成一句之前，这条正则量到 2。 */
    const defs = [...textOf(KANBAN).matchAll(/rejected:\s*'([^']*)'/g)].map((m) => m[1])
    expect(
      defs,
      `rejected 的文案定义应只有一处，实到 ${defs.length} 处：${defs.join(' / ')}`
    ).toEqual(['已标记为拒绝'])
  })
})
