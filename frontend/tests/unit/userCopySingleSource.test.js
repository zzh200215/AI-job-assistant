import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

/* 这一文件管两件事，都是"给人看的那句话只有一个来源"：
   1. D92：错误文案。`api/request.js` 以前把 axios 的英文技术串（"Network Error"）写进
      `err.userMessage`，而下游二十几处写的是 `x?.userMessage || x?.message || '中文兜底'`——
      `userMessage` 非空时后面两项永远取不到，那句中文兜底是死代码，屏幕上就是英文串。
      现在面向用户的错误只有一个出口 `userErrorCopy(x, '…')`，它只认服务端文案。
   2. §10.21：同一个动作在两个视图里不许各写一句提示（原话是"已标记为拒绝"/"已标记拒绝"）。 */

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
/* 每个文件只读一次：这一文件里有三条判据都要看全仓文本，而 `tests/unit` 整体是并行跑的——
   D100 那次全量红过 7 条别的用例（都是墙钟敏感的竞态测试），把重复的磁盘读去掉之后同一台机器上稳定全绿。 */
const CACHE = new Map()
const textOf = (rel) => {
  if (!CACHE.has(rel)) CACHE.set(rel, readFileSync(rel, 'utf8'))
  return CACHE.get(rel)
}

describe('错误文案只有一个出口', () => {
  /**
   * 判据按**绑定**认，不按文本认（D100）。第一版要求行里出现 `userMessage ||`，
   * 于是漏掉一整族"连 userMessage 都不读、直接把 catch 对象的 `.message` 当文案"的站点
   * （26 处，加 1 处 WebSocket 回调）。按绑定认还有个附带好处：`data.message`、
   * `overview.message` 这类**服务端载荷字段**天然不算，不需要维护白名单。
   */
  const errorCopyIn = (source) => {
    const binds = new Set([
      ...[...source.matchAll(/\bcatch\s*\(\s*([A-Za-z_$][\w$]*)/g)].map((m) => m[1]),
      ...[...source.matchAll(/\bon(?:Failed|Error|Cancelled)\s*\(\s*([A-Za-z_$][\w$]*)/g)].map(
        (m) => m[1]
      ),
    ])
    const hits = []
    for (const m of source.matchAll(/([A-Za-z_$][\w$]*)\??\.message/g)) {
      if (binds.has(m[1])) hits.push(m[1])
    }
    // 运行链把异常收进返回值时的那一种：`outcome.error?.message`
    if (/\.error\??\.message/.test(source)) hits.push('result.error')
    return hits
  }

  it('src 里不再有任何一处把 Error 的技术串当作用户可见文案', () => {
    const hits = ALL.filter((rel) => !DOCUMENTS_THE_RULE.includes(rel))
      .map((rel) => [rel, errorCopyIn(textOf(rel))])
      .filter(([, list]) => list.length)
      .map(([rel, list]) => `${rel}（${[...new Set(list)].join(', ')}）`)
    expect(hits, `这些地方还在读 Error 的技术串：${hits.join('; ')}`).toEqual([])
  })

  it('反向证据：判据认得改之前那几种写法，也不误伤服务端载荷', () => {
    // 形态 A：`userMessage || x.message ||`（D92 收的那 25 处）
    expect(
      errorCopyIn("  } catch (e) {\n    x.value = e?.userMessage || e?.message || '兜底'\n  }")
    ).toEqual(['e'])
    // 形态 B：模板串插值（D100 才收的那一族）
    expect(
      errorCopyIn(
        "  } catch (error) {\n    ElMessage.error(`分析失败: ${error.message || '未知错误'}`)\n  }"
      )
    ).toEqual(['error'])
    // 形态 C：WebSocket 回调
    expect(
      errorCopyIn('  } catch (err) {\n  errorMsg.value = `连接错误: ${err.message || err}`\n  }')
    ).toEqual(['err'])
    // 形态 D：运行链返回值上的 error
    expect(
      errorCopyIn("  if (!outcome.ok) ElMessage.error(outcome.error?.message || '生成失败')")
    ).toEqual(['result.error'])
    // 不是 catch/回调绑定的同名变量不算（避免把载荷字段误判成 Error）
    expect(
      errorCopyIn("  const data = await getX()\n  overview.value = data.message || ''")
    ).toEqual([])
    expect(errorCopyIn('  ElMessage.error(e.message || e)')).toEqual([])
    // 落地后的写法
    expect(errorCopyIn("  } catch (e) {\n    x.value = userErrorCopy(e, '兜底')\n  }")).toEqual([])
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
