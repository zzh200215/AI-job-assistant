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

const toPascal = (tag) =>
  'El' +
  tag
    .slice(3)
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')

const registeredNames = (() => {
  const list = readFileSync('src/plugins/element.js', 'utf8')
  const block = list.slice(list.indexOf('const components = ['))
  return [...new Set([...block.matchAll(/\b(El[A-Z]\w+)\b/g)].map((m) => m[1]))].filter(
    (n) => n !== 'components'
  )
})()

describe('Element 注册表与真实使用必须互相对得上', () => {
  it('every <el-*> used in a view resolves through the installed registry', () => {
    const unresolvable = [...usedTags.entries()]
      .filter(([tag]) => !installed.has(toPascal(tag)) && !installed.has(tag))
      .map(([tag, rel]) => `${tag} (${rel})`)
    expect(
      unresolvable,
      `这些标签在视图里用了却解析不出来，会静默渲染成空元素：${unresolvable.join(', ')}`
    ).toEqual([])
  })

  it('every registered component is actually used by some view', () => {
    const dead = registeredNames
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

  it('every element.css import belongs to a component the app can render', () => {
    const css = readFileSync('src/plugins/element.css', 'utf8')
    const imported = [...css.matchAll(/el-([a-z0-9-]+)\.css/g)].map((m) => `el-${m[1]}`)
    // 这三类没有 <el-*> 标签，但样式必须在：v-loading 指令，以及 ElMessage / ElMessageBox 两个服务
    const NO_TAG_BUT_USED = ['el-loading', 'el-overlay', 'el-message', 'el-message-box']
    const orphan = imported.filter((name) => !usedTags.has(name) && !NO_TAG_BUT_USED.includes(name))
    expect(orphan, `element.css 导入了渲染不出来的组件样式：${orphan.join(', ')}`).toEqual([])
  })
})
