import { describe, expect, it } from 'vitest'
import {
  INTERVIEW_SCORE_BANDS,
  MATCH_SCORE_BANDS,
  scoreTone,
  scoreToneClass,
  scoreToneColor,
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
})
