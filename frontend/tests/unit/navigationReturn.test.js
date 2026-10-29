import { beforeEach, describe, expect, it } from 'vitest'

import { clearReturnTo, readReturnTo, rememberReportReturn } from '@/utils/navigationReturn'

/* P5(b) 的落点提示：只认"面试报告"这一种来源，且只活在一次跳转里。 */

describe('面试报告跳转的来源上下文', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('记住报告路径与标签', () => {
    rememberReportReturn(12)

    expect(readReturnTo()).toEqual({ path: '/interview/report/12', label: '面试报告' })
  })

  it('非报告路径一律不认，避免把任意字符串当路由推出去', () => {
    sessionStorage.setItem('returnTo', JSON.stringify({ path: '/admin', label: '后台' }))

    expect(readReturnTo()).toBeNull()
  })

  it('坏 JSON 当成没有提示', () => {
    sessionStorage.setItem('returnTo', '{oops')

    expect(readReturnTo()).toBeNull()
  })

  it('清掉之后不再提示', () => {
    rememberReportReturn(12)
    clearReturnTo()

    expect(readReturnTo()).toBeNull()
  })
})
