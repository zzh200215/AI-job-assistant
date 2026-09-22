import { beforeEach, describe, expect, it } from 'vitest'

import {
  forgetJD,
  readJDId,
  readRecordId,
  readResumeId,
  rememberJD,
  rememberRecord,
  rememberResume,
  setSelectionOwner,
} from '@/utils/lastSelection'

/**
 * 这三个"上一次选择"以前有两套键名：全局的 `recruit.lastX` 和按用户的 `recruit.lastX.<uid>`。
 * 全局那套跨账号存活，所以换过账号的浏览器会把上一个账号的简历/JD/记录 id 预填进表单，
 * 后端只能回一句"记录不存在，或无权限访问"。现在按登录用户分槽，且登录时清掉全局键与 guest 槽。
 */
describe('lastSelection 按登录用户分槽', () => {
  beforeEach(() => {
    localStorage.clear()
    setSelectionOwner(null)
  })

  it('未登录时写在 guest 槽里，登录后被清掉——上一个人在共享浏览器留下的选择不会嫁过来', () => {
    rememberResume(11)
    rememberJD(22)
    rememberRecord(33)
    expect(readResumeId()).toBe(11)

    setSelectionOwner(7)
    expect(readResumeId()).toBeNull()
    expect(readJDId()).toBeNull()
    expect(readRecordId()).toBeNull()
  })

  it('旧的全局键（迁移前留下的）在登录时一并清掉', () => {
    localStorage.setItem('recruit.lastResumeId', '999')
    localStorage.setItem('recruit.lastJDId', '888')
    localStorage.setItem('recruit.lastRecordId', '777')

    setSelectionOwner(7)
    expect(localStorage.getItem('recruit.lastResumeId')).toBeNull()
    expect(localStorage.getItem('recruit.lastJDId')).toBeNull()
    expect(localStorage.getItem('recruit.lastRecordId')).toBeNull()
  })

  it('A 账号的选择在 B 账号看不见，回到 A 又回来', () => {
    setSelectionOwner(1)
    rememberResume(11)
    rememberJD(22)

    setSelectionOwner(2)
    expect(readResumeId()).toBeNull()
    expect(readJDId()).toBeNull()

    setSelectionOwner(1)
    expect(readResumeId()).toBe(11)
    expect(readJDId()).toBe(22)
  })

  it('写入与读取落在同一个槽里（跨页交接因此只有一种键名）', () => {
    setSelectionOwner(1)
    rememberResume(41) // JobSearch.persistAnalysisContext 写的
    expect(readResumeId()).toBe(41) // CareerPlanning.restoreSelections 读的
  })

  it('forgetJD 只影响当前账号的槽', () => {
    setSelectionOwner(1)
    rememberJD(22)
    setSelectionOwner(2)
    rememberJD(23)
    forgetJD()
    expect(readJDId()).toBeNull()

    setSelectionOwner(1)
    expect(readJDId()).toBe(22)
  })

  it('存进去的东西读回来是数字，坏值不当成 id', () => {
    setSelectionOwner(1)
    rememberResume('not-a-number')
    expect(readResumeId()).toBeNull()

    rememberResume(undefined)
    expect(readResumeId()).toBeNull()
  })
})
