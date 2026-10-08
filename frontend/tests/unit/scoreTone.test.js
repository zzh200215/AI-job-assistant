import { describe, expect, it } from 'vitest'
import {
  INTERVIEW_SCORE_BANDS,
  MATCH_SCORE_BANDS,
  scoreTone,
  scoreToneClass,
  scoreToneColor,
  scoreToneTextColor,
  interviewScoreTextColor,
  scoreToneFillClass,
} from '../../src/utils/scoreTone'

describe('scoreTone', () => {
  it('match-score bands follow the recommendation thresholds the label uses', () => {
    // 后端 MatchExplainer._recommendation 是 85 / 70 / 50；色带必须与它一致，
    // 否则同一张卡片会一边写"可以投递"一边把分数标成警告色。
    expect(MATCH_SCORE_BANDS.map((b) => b.min)).toEqual([85, 70, 50, -Infinity])
    for (const [value, tone] of [
      [100, 'high'],
      [85, 'high'],
      [84, 'good'],
      [72, 'good'],
      [70, 'good'],
      [69, 'warn'],
      [50, 'warn'],
      [49, 'risk'],
      [0, 'risk'],
    ]) {
      expect(scoreTone(value), `score ${value}`).toBe(tone)
    }
  })

  it('interview performance keeps its own bands but the same tones', () => {
    expect(INTERVIEW_SCORE_BANDS.map((b) => b.min)).toEqual([85, 70, 55, -Infinity])
    expect(scoreTone(52, INTERVIEW_SCORE_BANDS)).toBe('risk')
    expect(scoreTone(52)).toBe('warn') // 同一分数在两种口径下不同，口径必须显式传
  })

  it('never invents a tone for missing or non-numeric scores', () => {
    for (const value of [null, undefined, NaN, '', 'abc']) {
      expect(scoreTone(value)).toBe('unknown')
    }
  })

  it('hands colors to CSS: no hex literal leaves this module', () => {
    expect(scoreToneColor(72)).toBe('var(--app-score-good)')
    expect(scoreToneColor(40)).toBe('var(--app-score-risk)')
    expect(scoreToneColor(null)).toBe('var(--app-score-unknown)')
    expect(scoreToneClass(72)).toBe('score-tone score-tone--good')
    expect(scoreToneClass(72, MATCH_SCORE_BANDS, 'dim-score')).toBe('dim-score dim-score--good')
    expect(scoreToneFillClass(88)).toBe('score-fill--high')
    for (const out of [scoreToneColor(72), scoreToneClass(72), scoreToneFillClass(72)]) {
      expect(out).not.toMatch(/#[0-9a-fA-F]{3,8}/)
    }
  })

  it('lifts only the two tones that fail as text on a dark surface', () => {
    // 五个 tone 各有一条，且只有实测不过线的那两档被抬：good 3.06 → 5.08、risk 4.15 → 5.48；
    // high / warn / unknown 在深色面板上本体就有 5.20 / 5.86 / 5.07，不许顺手也混白。
    const byValue = [
      [90, 'var(--app-score-high)'],
      [72, 'color-mix(in srgb, var(--app-score-good), white 25%)'],
      [55, 'var(--app-score-warn)'],
      [30, 'color-mix(in srgb, var(--app-score-risk), white 20%)'],
      [null, 'var(--app-score-unknown)'],
    ]
    for (const [value, want] of byValue) {
      expect(scoreToneTextColor(value), `tone of ${value}`).toBe(want)
      expect(scoreToneColor(value)).toContain('var(--app-score-')
    }
    // 反证：文字档不许退化成 tone 本体（那正是 3.06 那一档），也不许多出第二份色值。
    expect(scoreToneTextColor(72)).not.toBe(scoreToneColor(72))
    expect(scoreToneTextColor(30)).not.toBe(scoreToneColor(30))
    expect(scoreToneTextColor(90)).toBe(scoreToneColor(90))
    for (const [, out] of byValue) {
      expect(out).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(/)
    }
    // 文字档跟着**自己的分界**：52 在匹配分里是 warn、在面试分里是 risk（55 那道界），
    // 两条不能因为共用一张表就被抹平成同一档。
    expect(interviewScoreTextColor(52)).toBe('color-mix(in srgb, var(--app-score-risk), white 20%)')
    expect(scoreToneTextColor(52)).toBe('var(--app-score-warn)')
  })
})
