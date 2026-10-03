import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { levelTagType } from '@/utils/statusTone'

/* D91：高/中/低 这三档的颜色此前在五个地方各写各的三元式，现在只有一个出处。
   两条判据各管一头：
   ① **等价**：迁移动的是写法不是观感，所以每个档位的返回值必须与原来那串三元式逐字相同；
   ② **不许长回来**：`styleDebtRatchet` 那把尺子按 `键: '颜色'` 计数，**三元式形态它看不见**
      （实测迁完 5 处，`statusTagEntries` 一分未动），所以这条重复是守卫盲区里的，得自己钉。 */

describe('levelTagType：高/中/低 → el-tag 颜色', () => {
  it('三档各归一位，未知值退回 info 而不是失败色', () => {
    expect(levelTagType('高')).toBe('danger')
    expect(levelTagType('中')).toBe('warning')
    expect(levelTagType('低')).toBe('info')
    /* 后端多给一档、或给了空串/英文时不能把东西涂成红：与 tagTypeFor 同一口径。 */
    expect(levelTagType('紧急')).toBe('info')
    expect(levelTagType('')).toBe('info')
    expect(levelTagType(undefined)).toBe('info')
  })

  it('全仓只剩那一处刻意保留的两段式，没有第三处在自己写这张表', () => {
    const walk = (dir, rel = dir) =>
      readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
        e.isDirectory() ? walk(path.join(dir, e.name), `${rel}/${e.name}`) : [`${rel}/${e.name}`]
      )
    const hits = walk('src')
      .filter((f) => f.endsWith('.vue'))
      .filter((rel) => /=== '[高中]' \? '(danger|warning|info)'/.test(readFileSync(rel, 'utf8')))
    /* `CareerPlanning.vue` 的投递策略标签是**两段式**（高→danger，其余→warning，没有 info 档），
       并进这张表会改它的观感，所以留在原地并在 statusTone.js 里点名。 */
    expect(hits, `这些地方不该再自己写 高/中/低 → 颜色：${hits.join(', ')}`).toEqual([
      'src/features/planning/views/CareerPlanning.vue',
    ])
  })
})
