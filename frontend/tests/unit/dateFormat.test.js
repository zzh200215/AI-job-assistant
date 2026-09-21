import { describe, expect, it } from 'vitest'
import {
  compactDateTime,
  dateTime,
  isoMonthDay,
  monthDay,
  monthDayTime,
  rawStamp,
  utcStamp,
} from '../../src/utils/format/date'

/* 迁移前 18 份副本的真实实现，逐字抄在这里当黄金对照：新函数必须与它们逐输入相等，
   不等就是我在改（下面"故意不同"的两组单独断言，不混在水下）。
   按输出归类后只有 6 种格式——两份"看起来不同"的写法实测逐字节相同。 */
const legacy = {
  // A 组 5 份：OfferCompare / PipelineKanban / ResumeCompare / ResumeUpload / WeeklyReport
  monthDayGuarded: (d) => {
    if (!d) return ''
    try {
      return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
    } catch {
      return d
    }
  },
  monthDayBare: (v) => {
    if (!v) return ''
    return new Date(v).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  },
  // B 组 4 份：Interview 用 toLocaleDateString 带时分，其余用 toLocaleString
  monthDayTimeViaDateString: (d) => {
    if (!d) return ''
    try {
      return new Date(d).toLocaleDateString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return d
    }
  },
  monthDayTimeViaString: (d) => {
    if (!d) return ''
    try {
      return new Date(d).toLocaleString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return d
    }
  },
  // C 组：TaskCenter 不带 hour12，admin 四份带 hour12:false 且占位符是 '-'
  dateTimeLocal: (d) => {
    if (!d) return ''
    try {
      return new Date(d).toLocaleString('zh-CN')
    } catch {
      return d
    }
  },
  dateTime24: (v) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'),
  // 投递漏斗弹层的紧凑排版
  compactPipeline: (value) => {
    if (!value) return '--'
    try {
      return new Date(value).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return value
    }
  },
  // 图表横轴：不构造 Date，直接切 ISO 串
  sliceMonthDay: (dateText) => {
    if (!dateText || typeof dateText !== 'string') return '--'
    return dateText.slice(5)
  },
  // D 组：EvalReport / PromptTrace 不本地化
  utcStamp: (value) => {
    if (!value) return '-'
    return String(value).replace('T', ' ').replace('+00:00', ' UTC').slice(0, 23)
  },
  rawStamp: (value) => {
    if (!value) return '-'
    return String(value).replace('T', ' ').slice(0, 19)
  },
  // Profile 那份：不带 locale，浏览器语言决定输出
  browserLocale: (value) => {
    if (!value) return '--'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
  },
}

const VALID = [
  '2026-09-21T18:05:00',
  '2026-09-21T18:05:00Z',
  '2026-09-21T18:05:00+08:00',
  '2026-09-21',
  '2026-02-28T23:59:59',
  '2025-12-31T12:00:00',
  1760000000000,
]
const EMPTY = [null, undefined, '', 0]
const GARBAGE = ['abc', 'not-a-date', {}]

describe('format/date 与迁移前的 18 份副本对照', () => {
  it('monthDay 与 A 组两份实现逐输入相等', () => {
    for (const v of VALID) {
      expect(monthDay(v), v).toBe(legacy.monthDayGuarded(v))
      expect(monthDay(v), v).toBe(legacy.monthDayBare(v))
    }
    for (const v of EMPTY) {
      expect(monthDay(v), String(v)).toBe('')
      expect(monthDay(v, '-'), String(v)).toBe('-')
    }
  })

  it('monthDayTime 与 B 组两种写法相等——它们本来就是同一个格式', () => {
    for (const v of VALID) {
      expect(monthDayTime(v), v).toBe(legacy.monthDayTimeViaDateString(v))
      expect(monthDayTime(v), v).toBe(legacy.monthDayTimeViaString(v))
      expect(legacy.monthDayTimeViaDateString(v), `两份旧写法自身 ${v}`).toBe(
        legacy.monthDayTimeViaString(v)
      )
    }
  })

  it('dateTime 与 TaskCenter 及 admin 那组一致，中文与 24 小时制不再随浏览器语言', () => {
    for (const v of VALID) {
      expect(dateTime(v), v).toBe(legacy.dateTimeLocal(v))
      expect(dateTime(v, '-'), v).toBe(legacy.dateTime24(v))
      expect(legacy.dateTimeLocal(v), `旧的两写法自身 ${v}`).toBe(legacy.dateTime24(v))
    }
  })

  it('compactDateTime 与漏斗弹层那份逐输入相等，且确实是另一种排版', () => {
    for (const v of VALID) {
      expect(compactDateTime(v, '--'), v).toBe(legacy.compactPipeline(v))
    }
    expect(compactDateTime('2026-09-21T18:05:00')).toBe('09/21 18:05')
    expect(monthDayTime('2026-09-21T18:05:00')).toBe('9月21日 18:05')
  })

  it('isoMonthDay 与图表轴那份切片实现相等（不经过 Date，所以不做时区换算）', () => {
    for (const v of ['2026-09-21', '2026-01-05', '2026-12-31']) {
      expect(isoMonthDay(v), v).toBe(legacy.sliceMonthDay(v))
    }
    for (const v of EMPTY) {
      expect(isoMonthDay(v), String(v)).toBe('--')
      expect(legacy.sliceMonthDay(v), String(v)).toBe('--')
    }
    // 非字符串（含数字时间戳）仍旧返回占位符——旧实现就是这个行为
    expect(isoMonthDay(1760000000000)).toBe('--')
    expect(isoMonthDay('2026-09-21', '?')).toBe('09-21')
  })

  it('两个不本地化的时间戳出口与 EvalReport / PromptTrace 的切法完全一致', () => {
    const cases = [
      '2026-09-21T18:05:00.123456+00:00',
      '2026-09-21T18:05:00.123456',
      '2026-09-21 18:05:00',
      'abc',
    ]
    for (const v of cases) {
      expect(utcStamp(v), v).toBe(legacy.utcStamp(v))
      expect(rawStamp(v), v).toBe(legacy.rawStamp(v))
    }
    for (const v of EMPTY) {
      expect(utcStamp(v), String(v)).toBe('-')
      expect(rawStamp(v), String(v)).toBe('-')
      expect(utcStamp(v, '?'), String(v)).toBe('?')
    }
  })

  /* 以下是故意不同的地方，写成断言而不是悄悄改掉。 */

  it('坏值不再显示成 Invalid Date，而是保留后端原文', () => {
    for (const v of GARBAGE) {
      expect(legacy.monthDayGuarded(v), `旧实现 ${v}`).toBe('Invalid Date')
      expect(legacy.compactPipeline(v), `旧实现 ${v}`).toBe('Invalid Date')
      expect(monthDay(v), `新实现 ${v}`).toBe(String(v))
      expect(monthDayTime(v), v).toBe(String(v))
      expect(dateTime(v), v).toBe(String(v))
      expect(compactDateTime(v), v).toBe(String(v))
    }
  })

  it('Profile 的时间戳从此与全站同一个格式（旧实现随浏览器语言变）', () => {
    const v = '2026-09-21T18:05:00'
    const runtimeLocale = Intl.DateTimeFormat().resolvedOptions().locale
    // 旧写法不带 locale：中文浏览器上恰好与全站相同，英文浏览器上变成 9/21/2026, 6:30:05 PM。
    // 新实现永远输出 zh-CN 的 `2026/9/21 18:05:00`，与运行环境无关。
    expect(dateTime(v)).toMatch(/^\d{4}\/\d{1,2}\/\d{1,2}\s\d{2}:\d{2}:\d{2}$/)
    if (runtimeLocale.toLowerCase().startsWith('zh')) {
      expect(legacy.browserLocale(v), `zh 运行环境下 ${runtimeLocale}`).toBe(dateTime(v))
    } else {
      expect(legacy.browserLocale(v), `非 zh 运行环境下 ${runtimeLocale}`).not.toBe(dateTime(v))
    }
    expect(legacy.browserLocale('')).toBe('--')
    expect(dateTime('', '--')).toBe('--')
  })

  it('那些 catch { return d } 从来没机会执行——toLocaleXxx 不抛异常', () => {
    for (const v of GARBAGE) {
      expect(() => new Date(v).toLocaleString('zh-CN')).not.toThrow()
      expect(() => new Date(v).toLocaleDateString('zh-CN')).not.toThrow()
    }
  })
})
