import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  readDefaultResumeId,
  readJDId,
  readRecordId,
  readResumeId,
  setSelectionOwner,
} from '@/utils/lastSelection'
import { useSelectionStore } from '@/stores/selection'

/**
 * §10.9 决定 ①（D124）把 11 个文件、27 个调用点收成这一个 store。分槽规则本身还住在
 * `utils/lastSelection`，那边的测试（lastSelection.test.js）一条没动；这里只钉**这层薄壳**的
 * 三件事，而它们恰好是薄壳最容易静悄悄做错的事：
 * - 接错线（`jdId: () => readResumeId()` 这种一行 typo，全仓现有测试一个都发现不了）；
 * - 把"每次调用都落到存储"顺手写成 computed（缓存之后，第二个标签页写过的值这一页永远读不到）；
 * - `setOwner` 漏接（身份不通知，槽就退回 guest，跨账号那条老路复活）。
 */
function store() {
  setActivePinia(createPinia())
  return useSelectionStore()
}

describe('selection store 只是转发，不改变任何一口径', () => {
  beforeEach(() => {
    localStorage.clear()
    setSelectionOwner(null)
  })

  it('四个写各自落在自己那一格，没有串线', () => {
    const s = store()
    s.setOwner(5)
    s.rememberResume(11)
    s.rememberJD(22)
    s.rememberRecord(33)
    s.rememberDefaultResume(44)

    expect(localStorage.getItem('recruit.lastResumeId.5')).toBe('11')
    expect(localStorage.getItem('recruit.lastJDId.5')).toBe('22')
    expect(localStorage.getItem('recruit.lastRecordId.5')).toBe('33')
    expect(localStorage.getItem('recruit.defaultResumeId.5')).toBe('44')
  })

  it('四个读各自取自己那一格，没有串线', () => {
    setSelectionOwner(5)
    localStorage.setItem('recruit.lastResumeId.5', '11')
    localStorage.setItem('recruit.lastJDId.5', '22')
    localStorage.setItem('recruit.lastRecordId.5', '33')
    localStorage.setItem('recruit.defaultResumeId.5', '44')

    const s = store()
    expect(s.resumeId()).toBe(11)
    expect(s.jdId()).toBe(22)
    expect(s.recordId()).toBe(33)
    expect(s.defaultResumeId()).toBe(44)
    // 与 utils 侧逐字相等：这层壳不许有第二套真相
    expect([s.resumeId(), s.jdId(), s.recordId(), s.defaultResumeId()]).toEqual([
      readResumeId(),
      readJDId(),
      readRecordId(),
      readDefaultResumeId(),
    ])
  })

  it('forgetJD 清的是当前账号那一格', () => {
    const s = store()
    s.setOwner(5)
    s.rememberJD(22)
    expect(s.jdId()).toBe(22)
    s.forgetJD()
    expect(s.jdId()).toBeNull()
    expect(localStorage.getItem('recruit.lastJDId.5')).toBeNull()
  })

  it('读取不是 computed：别的标签页写过，下一次调用就看见新值', () => {
    const s = store()
    s.setOwner(5)
    s.rememberResume(11)
    expect(s.resumeId()).toBe(11)
    // 另开一个标签页写同一格（同一个 uid），这一页什么都没做
    localStorage.setItem('recruit.lastResumeId.5', '12')
    expect(
      s.resumeId(),
      `收成 store 不该顺手把"这一页此刻读到什么"换成"本会话第一次读到什么"`
    ).toBe(12)
  })

  it('setOwner 真的通到 utils：登录这一步会清掉 guest 槽与旧全局键', () => {
    localStorage.setItem('recruit.lastResumeId', '999') // 迁移前的全局键
    localStorage.setItem('recruit.lastJDId.guest', '888') // 登录前留下的
    const s = store()
    s.setOwner(5)
    expect(localStorage.getItem('recruit.lastResumeId')).toBeNull()
    expect(localStorage.getItem('recruit.lastJDId.guest')).toBeNull()
    expect(s.resumeId()).toBeNull()
    expect(s.jdId()).toBeNull()
  })

  it('未登录（setOwner 拿到空身份）落 guest 槽，且不清任何东西', () => {
    const s = store()
    s.setOwner({ id: 5 })
    s.rememberResume(11)
    s.setOwner(null)
    s.rememberResume(12)
    expect(s.resumeId()).toBe(12)
    expect(localStorage.getItem('recruit.lastResumeId.guest')).toBe('12')
    // 5 号那一格没有被这次退出动过：清 guest/全局键只在拿到真实 uid 时发生
    expect(localStorage.getItem('recruit.lastResumeId.5')).toBe('11')
  })
})
