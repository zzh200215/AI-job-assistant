/**
 * 前端 API 层不许有"写完没人用"的导出（D8）。
 *
 * 为什么要有这条：`src/api/analysis.js` 里的 `runMatch` 从写下到删掉（2026-11-14）从来没人调过，
 * 而它指向的那个接口恰恰是**唯一一个**"一步失败、整发 500、前两步白跑"的公开面（见
 * `docs/真provider实测.md` §7）。同一批清出来的一共 **16 条**死导出（清单见
 * `docs/engineering-quality.md` 的 "Frontend API layer has no dead exports"）。
 *
 * 判据只看**引用**，不看名字出现在哪段文字里：
 *   · 具名 import：`import { x } from '@/api/jobs'`
 *   · 默认 import：`import x from '@/api/jobs'`
 *   · 命名空间成员：`import * as authApi from '@/api/auth'` 之后的 `authApi.login(...)`
 * 注释里提到一个导出名不算"用过"——这正是这条守卫要防的形状：一条注释就能让判据闭嘴。
 *
 * 扫的面是 `src/**`（产品代码）。只在测试里被调用的导出算死：测试替死代码背书，不算用户。
 */

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { describe, expect, it } from 'vitest'

// 用 `process.cwd()`：vitest 从 `frontend/` 起跑（仓里其他读文件的用例也是按
// `src/...` 这种相对路径取的），而 `import.meta.url` 在 jsdom 环境下是 http URL，
// `fileURLToPath` 会直接抛 "The URL must be of scheme file"。
const ROOT = process.cwd()
const SRC = path.join(ROOT, 'src')
const API_DIR = path.join(SRC, 'api')

/** 一个 api 模块里 `export const/function` 导出的名字。 */
function exportedNames(text) {
  const found = []
  const decl = /export\s+(?:const|function|async\s+function)\s+([A-Za-z_$][\w$]*)/g
  let match
  while ((match = decl.exec(text))) found.push(match[1])
  return found
}

/** 目录下所有会被打包的源码文件（`.js` / `.vue` / `.ts`），跳过 node_modules。 */
function sourceFiles(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules') continue
      sourceFiles(full, acc)
    } else if (/\.(js|vue|ts)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      acc.push(full)
    }
  }
  return acc
}

/** 一条 import 语句里的三种引用形式，统一成 {named: Set, defaultNames: Set, namespaces: Map<ns, specifier>}。 */
function referencesIn(text) {
  const named = new Set()
  const defaults = new Set()
  const namespaces = new Map()
  const importRe = /import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"]/g
  let match
  while ((match = importRe.exec(text))) {
    const [, clause, specifier] = match
    const ns = clause.match(/^\s*\*\s+as\s+([A-Za-z_$][\w$]*)/)
    if (ns) {
      namespaces.set(ns[1], specifier)
      continue
    }
    const braces = clause.match(/\{([\s\S]*)\}/)
    if (braces) {
      for (const part of braces[1].split(',')) {
        const name = part
          .trim()
          .split(/\s+as\s+/)[0]
          .trim()
        if (/^[A-Za-z_$][\w$]*$/.test(name)) named.add(name)
      }
    }
    const def = clause.match(/^\s*([A-Za-z_$][\w$]*)\s*(?:,|$)/)
    if (def) defaults.add(def[1])
  }
  return { named, defaults, namespaces }
}

/** `@/x/y` → 绝对路径（不含扩展名）；相对路径按给定文件解析。 */
function resolveSpecifier(specifier, fromFile) {
  if (specifier.startsWith('@/')) return path.join(SRC, specifier.slice(2))
  if (specifier.startsWith('.')) return path.resolve(path.dirname(fromFile), specifier)
  return null
}

/**
 * 判据本体：给出 api 模块的导出表与全树的引用，返回"没人引用"的那些。
 *
 * 拆成纯函数是为了能拿合成输入反证它真的会红——真实工作树上零死导出时，
 * 没有这一步就只是"跑了一遍什么都没发现"。
 */
export function findDeadExports(apiModules, files, resolve = resolveSpecifier) {
  const used = new Set()
  const namespaceUses = []
  for (const file of files) {
    const refs = referencesIn(file.text)
    refs.named.forEach((name) => used.add(name))
    refs.defaults.forEach((name) => used.add(name))
    for (const [ns, specifier] of refs.namespaces) {
      const target = resolve(specifier, file.path)
      if (target) namespaceUses.push({ text: file.text, alias: ns, target })
    }
  }

  const dead = []
  for (const mod of apiModules) {
    for (const name of mod.names) {
      if (used.has(name)) continue
      const viaNamespace = namespaceUses.some(
        (use) =>
          use.target === mod.resolvedPath &&
          new RegExp(`\\b${use.alias}\\s*\\.\\s*${name}\\b`).test(use.text)
      )
      if (!viaNamespace) dead.push(`${mod.file}::${name}`)
    }
  }
  return dead
}

function loadApiModules() {
  return fs
    .readdirSync(API_DIR)
    .filter((name) => name.endsWith('.js'))
    .sort()
    .map((name) => {
      const full = path.join(API_DIR, name)
      return {
        file: name,
        resolvedPath: full.replace(/\.js$/, ''),
        names: exportedNames(fs.readFileSync(full, 'utf8')),
      }
    })
    .filter((mod) => mod.names.length > 0)
}

function loadSourceFiles() {
  return sourceFiles(SRC).map((full) => ({ path: full, text: fs.readFileSync(full, 'utf8') }))
}

describe('前端 API 层没有死导出', () => {
  it('全树没有一个"导出后没人 import"的 api 函数', () => {
    const modules = loadApiModules()
    const files = loadSourceFiles()

    // 非空断言：目录挪了/正则断了会让下面的 assert 变成假绿。
    const total = modules.reduce((sum, mod) => sum + mod.names.length, 0)
    expect(total).toBeGreaterThan(120)

    expect(findDeadExports(modules, files)).toEqual([])
  })

  it('判据自己会红：合成输入里，没人 import 的导出必须被点名', () => {
    const modules = [
      {
        file: 'a.js',
        resolvedPath: '/src/api/a',
        names: ['usedByName', 'usedByNamespace', 'nobody'],
      },
    ]
    const files = [
      { path: '/src/api/a.js', text: 'export const usedByName = 1' },
      { path: '/src/views/Page.vue', text: "import { usedByName } from '@/api/a'\nusedByName()" },
      // 命名空间成员也算用：auth 那一族就是这么用的。
      {
        path: '/src/views/Other.vue',
        text: "import * as api from '@/api/a'\napi.usedByNamespace()",
      },
    ]
    const fakeResolve = (specifier) =>
      specifier.startsWith('@/') ? specifier.replace('@/', '/src/') : null

    expect(findDeadExports(modules, files, fakeResolve)).toEqual(['a.js::nobody'])
  })

  it('注释里提到不算用过——否则一段文字就能让判据闭嘴', () => {
    const modules = [{ file: 'a.js', resolvedPath: '/src/api/a', names: ['ghost'] }]
    const files = [
      { path: '/src/api/a.js', text: 'export const ghost = 1' },
      { path: '/src/views/Page.vue', text: '// 这里提了一句 ghost，但它没被 import' },
      { path: '/src/views/B.vue', text: '/* ghost */' },
    ]
    const fakeResolve = (specifier) =>
      specifier.startsWith('@/') ? specifier.replace('@/', '/src/') : null

    expect(findDeadExports(modules, files, fakeResolve)).toEqual(['a.js::ghost'])
  })
})
