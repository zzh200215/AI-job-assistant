import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { SCORE_UNREADABLE_TEXT, readScore, scoreGap, scorePairReadable } from '@/utils/aiScore'

/* §10.20（D113）拍定的那一步：AI 写坏了的分数**不再被讲成 0 分**。
   这里钉三件事：
   1. 读法本身——0 是合法分数、读不懂是 null，两者不许混；
   2. 提升空间的"任一端不知道 = 不知道"；
   3. **两屏都不许再碰裸字段**：`current_score` / `target_score` 只能出现在 aiScore 那三个函数的
      调用参数里。这一条是源扫描，因为这次的缺陷形态正是"有一屏自己算了减法"——职业规划页
      D53 起就夹过一道，而分析页的 CareerPlanPane 从来没人夹，模板里直接写减法，模型把分数写成
      "约80"时那一行的目标条整段消失。 */

describe('readScore：读不懂就是 null，不是 0', () => {
  it('能读的分数照旧夹到 0-100 并四舍五入', () => {
    expect([readScore(0), readScore(100), readScore(-15), readScore(130)]).toEqual([0, 100, 0, 100])
    expect([readScore(62.5), readScore(62.4), readScore('42'), readScore(' 78 ')]).toEqual([
      63, 62, 42, 78,
    ])
  })

  it('读不懂的五种形状全是 null', () => {
    expect([
      readScore(null),
      readScore(undefined),
      readScore(''),
      readScore('约80'),
      readScore(NaN),
    ]).toEqual([null, null, null, null, null])
  })

  /* 布尔是这里唯一一条"看起来能读其实不能读"的形状：`Number(true)` 是 1，模型把分数写成 true
     时会变成一个 1 分的合法分数。旧实现没挡（`Number(true || 0)` 同样是 1）。 */
  it('true / false 不算分数，但 0 算', () => {
    expect([readScore(true), readScore(false)]).toEqual([null, null])
    expect([readScore(0), readScore('0')]).toEqual([0, 0])
  })

  it('旧实现把这些一律讲成"有分数"——那正是要取消的谎', () => {
    const oldSafeScore = (value) => {
      const number = Number(value || 0)
      return Math.max(0, Math.min(100, Math.round(number)))
    }
    /* 反向证据要按形状分开记，不能一句"以前都归零"糊过去（D53 当时量的就是这两族不同）：
       - null / undefined / '' / NaN 是**假值**，`value || 0` 先把它换成 0，所以旧实现归零；
       - '约80' / 'abc' 是真字符串，`Number(...)` 得到 NaN，`Math.min/max(NaN)` 还是 NaN，
         于是旧实现把 NaN 一路传进文案和 `width: NaN%`。
       两族现在都是 null。 */
    for (const value of [null, undefined, '', NaN]) {
      expect(oldSafeScore(value)).toBe(0)
      expect(readScore(value)).toBeNull()
    }
    for (const value of ['约80', 'abc']) {
      expect(oldSafeScore(value)).toBeNaN()
      expect(readScore(value)).toBeNull()
    }
  })
})

describe('scoreGap：一端不知道，整体就是不知道', () => {
  it('两端都可读才算得出提升空间', () => {
    expect(scoreGap(80, 95)).toBe(15)
    expect(scoreGap('80', 95)).toBe(15)
    // 目标低于当前：这是一个**真实**的负数，不是"读不懂"
    expect([scoreGap(90, 70), scoreGap(70, 70)]).toEqual([-20, 0])
  })

  it('任一端读不懂就返回 null，而不是 95 那种假差距', () => {
    // 旧行为：safeScore('约80')=0 ⇒ 屏幕上"95 分提升空间"，把"没读懂"吹成了 95 分的成长空间
    expect(scoreGap('约80', 95)).toBeNull()
    expect(scoreGap(20, '未知')).toBeNull()
    expect(scoreGap(null, null)).toBeNull()
    expect(scorePairReadable('约80', 95)).toBe(false)
    expect(scorePairReadable(20, 95)).toBe(true)
    expect(scorePairReadable(0, 100)).toBe(true)
  })
})

describe('裸分数字段的源扫描', () => {
  const FIELDS = /current_score|target_score/
  const READERS = ['readScore(', 'scoreGap(', 'scorePairReadable(']

  /* 注释里的引用不算引用：这一族的判据是"代码有没有拿它算东西"，而这几条规则的说明里
     必须逐字写出被禁的那串，否则守卫把自己钉死（同 userCopySingleSource 的那份白名单）。
     剥掉注释时按行数补空行，报出来的 file:line 才对得上。 */
  const blank = (match) => '\n'.repeat(match.split('\n').length - 1)
  const stripComments = (text) =>
    text
      .replace(/\/\*[\s\S]*?\*\//g, blank)
      .replace(/<!--[\s\S]*?-->/g, blank)
      .split(/\r?\n/)
      .map((line) => (line.trimStart().startsWith('//') ? '' : line))

  function sources(dir) {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) return sources(full)
      return /\.(vue|js)$/.test(entry.name) ? [full.split(path.sep).join('/')] : []
    })
  }

  const readers = []
  const offenders = []
  let scanned = 0
  for (const file of sources('src')) {
    scanned += 1
    stripComments(readFileSync(file, 'utf8')).forEach((line, index) => {
      if (!FIELDS.test(line)) return
      readers.push(file)
      if (READERS.some((reader) => line.includes(reader))) return
      offenders.push(`${file}:${index + 1} ${line.trim()}`)
    })
  }

  it('这一族字段在 src 里只有那两屏读', () => {
    // 尺子不能建在"我以为有人用"上：先确认扫描真的落在了文件上
    expect(scanned).toBeGreaterThan(100)
    expect([...new Set(readers)].sort()).toEqual([
      'src/features/analysis/components/CareerPlanPane.vue',
      'src/features/planning/views/CareerPlanning.vue',
    ])
  })

  it('每一处引用都套在 readScore / scoreGap / scorePairReadable 里', () => {
    expect(offenders).toEqual([])
  })

  it('这条判据不是摆设：把搬家前的裸算式塞回去就会红', () => {
    const oldTemplateLines = [
      '<div class="radar-bar current" :style="{ width: dim.current_score + \'%\' }">',
      "width: dim.target_score - dim.current_score + '%',",
      '<span>{{ safeScore(dim.current_score) }}</span>',
    ]
    for (const line of oldTemplateLines) {
      expect(FIELDS.test(line), line).toBe(true)
      expect(
        READERS.some((reader) => line.includes(reader)),
        line
      ).toBe(false)
    }
  })

  it('"暂无数据"在两屏都是同一个出处', () => {
    expect(SCORE_UNREADABLE_TEXT).toBe('暂无数据')
    for (const file of [
      'src/features/planning/views/CareerPlanning.vue',
      'src/features/analysis/components/CareerPlanPane.vue',
    ]) {
      const text = stripComments(readFileSync(file, 'utf8')).join('\n')
      expect(text, `${file} 没有引用那个常量`).toContain('SCORE_UNREADABLE_TEXT')
      // §10.21 的教训：同一个说法不许在两处各写一遍
      expect(text.match(/暂无数据/g), `${file} 里自己写死的次数`).toBeNull()
    }
  })
})
