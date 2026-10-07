import { describe, expect, it } from 'vitest'
import { createApp } from 'vue'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { installElement } from '@/plugins/element'

/* `src/plugins/element.js`（手写组件注册表）与 `src/plugins/element.css`（手写样式清单）是两份
   要人手工同步的平行列表。§7 阶段 3 想用 unplugin 把它们删掉；在删之前，先让"漂移"这件事
   变成会红的测试，而不是靠人想起来去对表。
   这轮量到的真实漂移：`ElStep`/`ElSteps` 注册了、`el-step.css`/`el-steps.css` 也导入了，
   但全站没有任何一处用 `<el-steps>` —— 白进包。同一次量里出现的两个"用了没注册"
   （`<el-button-group>`、`<el-sub-menu>`）是**假阳性**：EP 的 `withInstall(ElButton, { ButtonGroup })`
   与 `withInstall(ElMenu, { SubMenu, MenuItemGroup })` 会顺带注册子组件。所以这条守卫判"能不能解析"
   用的是 Vue 装完之后的真实注册表，不是 element.js 里的名字列表。 */

function vueFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return vueFiles(full)
    return entry.name.endsWith('.vue') ? [full] : []
  })
}

const sources = vueFiles('src').map((full) => ({
  rel: full.split(path.sep).join('/'),
  src: readFileSync(full, 'utf8'),
}))

const usedTags = new Map()
for (const { rel, src } of sources) {
  for (const m of src.matchAll(/<(el-[a-z0-9-]+)[\s/>]/g)) {
    if (!usedTags.has(m[1])) usedTags.set(m[1], rel)
  }
}

const app = createApp({ render: () => null })
installElement(app)
const installed = new Set(Object.keys(app._context.components))

/* D88 第一步：把"能不能解析"的判据从**单一手写注册表**改成**双源**。
   §7 阶段 3 要删的正是 `plugins/element.js` 那份手写列表；删掉之后组件由 `unplugin-vue-components`
   在每个 `.vue` 编译时按需 import，届时的真相是插件生成的 `components.d.ts`。
   如果不先做这一步，删列表那天这条守卫会因为"两个集合都空"而**静默变绿**（`unresolvable` 恒空）。
   所以现在：可解析 = 装完 app 的真实注册表 ∪ `components.d.ts` 声明的名字；
   并且下面 `hasRegistrySource` 那条钉住"两个来源不许同时消失"。 */
const autoComponentsFile = 'components.d.ts'
const autoComponents = (() => {
  try {
    const text = readFileSync(autoComponentsFile, 'utf8')
    return new Set([...text.matchAll(/\b(El[A-Z]\w+)\b/g)].map((m) => m[1]))
  } catch {
    return new Set()
  }
})()
const resolvable = new Set([...installed, ...autoComponents])

const toPascal = (tag) =>
  'El' +
  tag
    .slice(3)
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')

const registeredNames = (() => {
  let list
  try {
    list = readFileSync('src/plugins/element.js', 'utf8')
  } catch {
    return [] // 手写列表被删掉之后由 components.d.ts 接手，下面两条会用同一套名字
  }
  const block = list.slice(list.indexOf('const components = ['))
  return [...new Set([...block.matchAll(/\b(El[A-Z]\w+)\b/g)].map((m) => m[1]))].filter(
    (n) => n !== 'components'
  )
})()

describe('Element 注册表与真实使用必须互相对得上', () => {
  it('注册来源不许同时消失（手写列表、或插件生成的 components.d.ts）', () => {
    expect(
      installed.size + autoComponents.size,
      '两个注册来源都是空的：`<el-*>` 将无人解析，而"用了却解析不出来"那条会因为集合为空而静默变绿'
    ).toBeGreaterThan(0)
  })

  it('every <el-*> used in a view resolves through the installed registry', () => {
    const unresolvable = [...usedTags.entries()]
      .filter(([tag]) => !resolvable.has(toPascal(tag)) && !resolvable.has(tag))
      .map(([tag, rel]) => `${tag} (${rel})`)
    expect(
      unresolvable,
      `这些标签在视图里用了却解析不出来，会静默渲染成空元素：${unresolvable.join(', ')}`
    ).toEqual([])
  })

  it('every registered component is actually used by some view', () => {
    const declared = [...new Set([...registeredNames, ...autoComponents])].filter(
      // 解析器会把**指令**也写进 components.d.ts（实测多出来的是 `ElLoadingDirective`）。
      // "有没有被用"这条判据是按 `<el-*>` 标签写的，表达不了指令，所以走下面那条专门的判据。
      (name) => !name.endsWith('Directive')
    )
    const dead = declared
      .filter((name) => {
        const kebab = name
          .slice(2)
          .replace(/([A-Z])/g, '-$1')
          .toLowerCase()
          .replace(/^-/, '')
        return !usedTags.has(`el-${kebab}`)
      })
      .sort()
    expect(
      dead,
      `注册表里有没人用的组件（连样式一起白进包），删掉或说明为什么留：${dead.join(', ')}`
    ).toEqual([])
  })

  it('每一条声明出来的**指令**也真的有 v-* 用法在（上面那条按标签判，判不了指令）', () => {
    const directives = [...autoComponents].filter((n) => n.endsWith('Directive'))
    const unused = directives.filter((name) => {
      // `ElLoadingDirective` → `v-loading`
      const kebab = name
        .replace(/Directive$/, '')
        .slice(2)
        .replace(/([A-Z])/g, '-$1')
        .toLowerCase()
        .replace(/^-/, '')
      return !sources.some(({ src }) => new RegExp(`\\sv-${kebab}[\\s=]`).test(src))
    })
    expect(unused, `解析器声明了这些指令却没有 v-* 用法：${unused.join(', ')}`).toEqual([])
  })

  it('every element.css import belongs to a component the app can render', () => {
    const css = readFileSync('src/plugins/element.css', 'utf8')
    const imported = [...css.matchAll(/el-([a-z0-9-]+)\.css/g)].map((m) => `el-${m[1]}`)
    // 这三类没有 <el-*> 标签，但样式必须在：v-loading 指令，以及 ElMessage / ElMessageBox 两个服务
    const NO_TAG_BUT_USED = ['el-loading', 'el-overlay', 'el-message', 'el-message-box']
    const orphan = imported.filter((name) => !usedTags.has(name) && !NO_TAG_BUT_USED.includes(name))
    expect(orphan, `element.css 导入了渲染不出来的组件样式：${orphan.join(', ')}`).toEqual([])
  })

  /* P1-④（2026-10-07，§10 记忆里的第 23 条）：**图标用了没 import，过去任何门都不响**。
     现场是 /history 控制台一条 `Failed to resolve component: Clock` + `Unhandled error during
     execution of render function`，静态核对 `grep -n Clock` 全文件只有用法那一行；按行重扫
     另有 JDInput 的 DataAnalysis / Document / Promotion。上面那条守卫判的是 `<el-*>`，
     而 EP 图标是 PascalCase 的独立组件，既不在这份手写注册表里、也不在 `components.d.ts` 里
     （后者只记解析器解析过的 `El*`），所以它从来不在射程内——这条补上那个洞。
     判据是"模板区出现的 PascalCase 标签，要么本文件脚本区提到过（import 或局部注册），
     要么在全局可解析集合里"。按行切模板/脚本，不按 `<template>…</template>` 切块：
     模板里有嵌套 `<template #slot>`，非贪婪匹配会在第一个 `</template>` 截断，
     我第一把这么写的尺子给了 History.vue **假清洁**。 */
  const VUE_BUILTINS = new Set([
    'RouterView',
    'RouterLink',
    'Component',
    'Transition',
    'TransitionGroup',
    'KeepAlive',
    'Teleport',
    'Suspense',
    'Slot',
  ])

  function unresolvedTags(src) {
    const cut = src.indexOf('<script')
    const tpl = cut < 0 ? '' : src.slice(0, cut)
    const scr = cut < 0 ? '' : src.slice(cut)
    const out = []
    for (const m of tpl.matchAll(/<([A-Z][A-Za-z0-9]*)[\s/>]/g)) {
      const name = m[1]
      if (VUE_BUILTINS.has(name) || resolvable.has(name)) continue
      if (new RegExp(`\\b${name}\\b`).test(scr)) continue
      out.push(name)
    }
    return out
  }

  it('视图模板里用到的 PascalCase 组件必须本文件可见或全局可解析', () => {
    const offenders = sources
      .map(({ rel, src }) => unresolvedTags(src).map((n) => `${rel}: <${n} />`))
      .flat()
    expect(
      offenders,
      `这些标签运行时解析不了（Vue 只会 warn 一条，界面少画一个图标）：${offenders.join(' | ')}`
    ).toEqual([])

    // 反证：把已修好的四处之一退回旧样子（去掉 Clock 的 import），判据必须重新报它。
    const history = sources.find((s) => s.rel.endsWith('shell/views/History.vue'))
    expect(history, 'History.vue 不在扫描范围内，这条反证就是空转').toBeTruthy()
    const reverted = history.src.replace("import { Clock } from '@element-plus/icons-vue'\n", '')
    expect(reverted, '反证前提不成立：原文里找不到那行 import').not.toBe(history.src)
    expect(unresolvedTags(reverted)).toContain('Clock')
  })
})
