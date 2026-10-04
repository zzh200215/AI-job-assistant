import { describe, expect, it } from 'vitest'

import { passwordProblem } from '@/utils/passwordRules'
import { WEAK_PASSWORDS } from '@/constants/weakPasswords'

/* D107：客户端与 `backend/app/schemas/auth.py` 的密码规则曾经不一致——表单只要求"字母 + 数字"，
   服务端对 8–11 位要求 4 类里 3 类。后果不是风格问题：表单放行、服务端 422，而 `model_validator`
   那类错误的 `loc` 塌成 `body`，候选人屏幕上是一副英文骨架包着一句中文（D103 的表）。
   下面这张表**不是手写的**：它是把同样的输入打在服务端 `RegisterReq` 上采集回来的
   （`backend/tests/test_password_rules_agree_with_frontend.py` 用同一张表反向钉这两侧）。 */
const CASES = [
  { p: 'Abc12345!', u: 'zhang', e: 'zhang@example.com', accept: true },
  {
    p: 'abcdefgh',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种',
  },
  {
    p: 'abcd1234',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种',
  },
  {
    p: 'password123',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种',
  },
  { p: 'Summer2024', u: 'zhang', e: 'zhang@example.com', accept: true },
  {
    p: 'summer2024',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种',
  },
  {
    p: 'Abcd1234',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码过于常见，请更换更复杂的密码',
  },
  {
    p: 'abcdefg12',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种',
  },
  { p: 'abcdefg12345', u: 'zhang', e: 'zhang@example.com', accept: true },
  {
    p: 'abcdefghijkl',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码需至少包含字母、数字、特殊字符中的 2 种',
  },
  {
    p: 'abcdefgh12 ',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码首尾不能包含空格',
  },
  {
    p: ' abcd12345',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码首尾不能包含空格',
  },
  {
    p: 'zhangzhang',
    u: 'zhangzhang',
    e: 'zhang@example.com',
    accept: false,
    // 服务端先判类别（全小写只 1 类），所以这里报的不是"与用户名相同"——顺序也要对齐
    message: '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种',
  },
  { p: 'zhang', u: 'zhang', e: 'zhang@example.com', accept: false },
  { p: 'abcd1234', u: 'zhang', e: 'abcd1234@example.com', accept: false },
  { p: 'Passw0rd!', u: 'zhang', e: 'zhang@example.com', accept: true },
  { p: 'qwe123', u: 'zhang', e: 'zhang@example.com', accept: false },
  {
    p: '12345678',
    u: 'zhang',
    e: 'zhang@example.com',
    accept: false,
    message: '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种',
  },
  { p: '  ', u: 'zhang', e: 'zhang@example.com', accept: false },
  { p: 'A1b2C3d4e5', u: 'Zhang', e: 'Zhang@Example.COM', accept: true },
]

describe('注册与重置密码的客户端规则等于服务端', () => {
  for (const c of CASES) {
    const label = `${JSON.stringify(c.p)}（用户名 ${c.u}）→ ${c.accept ? '放行' : '拦下'}`
    it(label, () => {
      const problem = passwordProblem(c.p, { username: c.u, email: c.e })
      expect(!!problem, `服务端${c.accept ? '接受' : '拒绝'}，客户端必须一样`).toBe(!c.accept)
      if (c.message) expect(problem).toBe(c.message)
    })
  }

  it('空密码与纯空格也拦得住（服务端那侧报的是英文长度约束，客户端说人话）', () => {
    expect(passwordProblem('', { username: 'zhang' })).toBe('请输入密码')
    expect(passwordProblem('   ', { username: 'zhang' })).toBe('密码首尾不能包含空格')
  })

  it('清单大小写不敏感，与后端的 strip().lower() 一致', () => {
    // 'P@ssW0rd' 落在清单里（存的是小写 'p@ssw0rd'），四类占满、长度够，所以只剩黑名单这一关
    expect(passwordProblem('P@ssW0rd', { username: 'zhang' })).toBe(
      '密码过于常见，请更换更复杂的密码'
    )
    expect(WEAK_PASSWORDS.has('password123')).toBe(true)
  })

  it('首尾带空格的常见密码先被"首尾不能包含空格"拦下（顺序与后端一致）', () => {
    expect(passwordProblem('password123 ', { username: 'zhang' })).toBe('密码首尾不能包含空格')
  })
})
