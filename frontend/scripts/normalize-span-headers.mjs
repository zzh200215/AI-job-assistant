import { readFileSync, writeFileSync } from 'node:fs'

/* §10.14 决定 ②（D99）：把 `CareerPlanPane` 里 7 处 `.panel-header > span` 的标题改成面板规格
   （`.panel-header > .panel-title-row > h3`），之后才能当普通站点迁进 AppPanel。
   实测这一族 span 头上**没有任何** `.panel-header*` scoped 规则，且 `span → h3` 的计算值差别
   只有字重 400 → 700（字号两边都是 16px、margin / line-height / letter-spacing 全同，
   flex 子项的 display 差异被 blockify 掉）——所以这是一次"标题变粗"的可见改动，不是零变化。

   脚本只认"头部里就一个 `<span>`、不含任何嵌套 div"的形状；命中数不是 7 就不写盘。 */

const REL = 'src/features/analysis/components/CareerPlanPane.vue'
const EXPECT = 7

const src = readFileSync(REL, 'utf8')
let hits = 0
const out = src.replace(
  /([ \t]*)<div class="panel-header">((?:(?!<div\b|<\/div>)[\s\S])*?)<\/div>/g,
  (whole, ind, inner) => {
    const t = inner.trim()
    if (!/^<span\b/.test(t)) return whole
    // 取出文本：去掉 `<span ...>` 与 `</span ...>`（prettier 会把 `>` 悬挂到行首）
    const text = t
      .replace(/^<span[^>]*>/, '')
      .replace(/^>/, '')
      .replace(/<\/span\s*>?$/, '')
      .replace(/>\s*$/, '')
      .replace(/\s+/g, ' ')
      .trim()
    if (!text) return whole
    hits += 1
    return [
      `${ind}<div class="panel-header">`,
      `${ind}  <div class="panel-title-row">`,
      `${ind}    <h3>${text}</h3>`,
      `${ind}  </div>`,
      `${ind}</div>`,
    ].join('\n')
  }
)

if (hits !== EXPECT) {
  console.error(`期望归一 ${EXPECT} 处 span 头部，实到 ${hits} —— 不写盘`)
  process.exit(1)
}
writeFileSync(REL, out, 'utf8')
console.log(`已归一 ${hits} 处 span → .panel-title-row > h3`)
