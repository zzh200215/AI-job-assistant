import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  forgetJD,
  readDefaultResumeId,
  readJDId,
  readRecordId,
  readResumeId,
  rememberDefaultResume,
  rememberJD,
  rememberPendingAnalysis,
  rememberRecord,
  rememberResume,
  setSelectionOwner,
  takePendingAnalysis,
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

/* D102：`recruit.defaultResumeId` 以前是**全局键**，由 ResumeUpload 自己读写。
   后果不是风格问题：共享浏览器里换过账号，上一个人的默认版本会嫁到下一个人头上——
   列表里那一行标成"投递中"、`activeResume` 也跟着选错。现在它和另外三个键共用同一套分槽。 */
describe('默认简历也按登录用户分槽', () => {
  it('两个账号各记各的，互不嫁人', () => {
    setSelectionOwner(1)
    rememberDefaultResume(11)
    expect(readDefaultResumeId()).toBe(11)

    setSelectionOwner(2)
    expect(readDefaultResumeId()).toBeNull() // 不是 11
    rememberDefaultResume(12)

    setSelectionOwner(1)
    expect(readDefaultResumeId()).toBe(11)
  })

  it('登录时把旧的全局键一起清掉（迁移期留下的那份）', () => {
    localStorage.setItem('recruit.defaultResumeId', '11')
    setSelectionOwner(7)
    expect(localStorage.getItem('recruit.defaultResumeId')).toBeNull()
    expect(readDefaultResumeId()).toBeNull()
  })
})

/* §10.9 决定 ② 走"只统一槽位、不统一形状"那一支（D125，他点的 ①）。`recruit.pendingAnalysis`
   以前是**全局键**：A 点了"一键智能分析"但没走到目的地，B 在同一台浏览器登录进来，就会看见 A 的
   岗位名与 JD 原文被预填进自己的表单。窗口比那四把 id 小得多，但形状是同一个，所以处置也一样。
   这三条钉的是**这次改动唯一改变的行为**（跨账号看不见），其余（取一次就删、坏 JSON 的 warn）
   是从 `SmartAnalysis.vue` 原样搬过来的口径，不许顺手变。 */
describe('一次性分析载荷也按登录用户分槽', () => {
  const CTX = { jdId: 12, title: '平台后端', company: '示例', jd_text: '三年 Go' }

  beforeEach(() => {
    localStorage.clear()
    setSelectionOwner(null)
  })

  it('写在谁的槽里就只有谁取得到，别的账号拿到 null', () => {
    setSelectionOwner(1)
    rememberPendingAnalysis(CTX)

    setSelectionOwner(2)
    expect(takePendingAnalysis()).toBeNull()

    setSelectionOwner(1)
    expect(takePendingAnalysis()).toEqual(CTX)
  })

  it('取走就是删：第二次拿不到（原来那句 `finally` 的语义，一字没改）', () => {
    setSelectionOwner(1)
    rememberPendingAnalysis(CTX)
    expect(takePendingAnalysis()).toEqual(CTX)
    expect(takePendingAnalysis()).toBeNull()
    expect(localStorage.getItem('recruit.pendingAnalysis.1')).toBeNull()
  })

  it('登录把 guest 槽里那一坨和迁移前的全局键一起清掉', () => {
    rememberPendingAnalysis(CTX) // 登录前点的那一发
    localStorage.setItem('recruit.pendingAnalysis', JSON.stringify(CTX)) // 迁移前留下的全局键
    setSelectionOwner(7)
    expect(localStorage.getItem('recruit.pendingAnalysis')).toBeNull()
    expect(localStorage.getItem('recruit.pendingAnalysis.guest')).toBeNull()
    expect(takePendingAnalysis()).toBeNull()
  })

  it('坏 JSON 也算取走：不抛、给 null、键被删、留原来那句 warn', () => {
    setSelectionOwner(1)
    localStorage.setItem('recruit.pendingAnalysis.1', '{不是 JSON')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(takePendingAnalysis()).toBeNull()
    expect(warn).toHaveBeenCalledWith('解析 pendingAnalysis 失败', expect.any(Error))
    expect(localStorage.getItem('recruit.pendingAnalysis.1')).toBeNull()
    warn.mockRestore()
  })
})
