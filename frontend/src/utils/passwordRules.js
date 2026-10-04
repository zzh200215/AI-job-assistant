import { isWeakPassword } from '@/constants/weakPasswords'

/**
 * 密码规则的客户端镜像，逐条对齐后端 `app/schemas/auth.py::_validate_password_strength`
 * （含判断顺序——顺序决定候选人先看到哪一句）。
 *
 * 为什么要镜像：后端这些规则跑在 Pydantic 校验里，失败就是 HTTP 422，而
 * `normalizeValidationMessage` 把 `detail` 原样拼成 `"body.<字段>: <msg>"` 上屏（见 D103 的表）。
 * 自定义 `ValueError` 那几句虽然是中文，外面仍套着 `Value error, ` 与字段路径；更糟的是
 * `model_validator` 那类错误的 `loc` 会塌成 `body`，候选人完全看不出是哪一格。表单如果承诺了一条
 * 比服务端弱的规则，用户就会在"点提交"之后才看见那句话——注册页此前正是这样：客户端只要求
 * "字母 + 数字"，服务端对 8–11 位要求大写/小写/数字/特殊字符里的 3 类，实测 `abcd1234`、
 * `zhang1234`、`password123` 表单放行、服务端 422。
 *
 * **两边不许各自漂移**：`backend/tests/test_password_rules_agree_with_frontend.py` 把同一张用例表
 * 打在服务端与这份实现上，并把清单与 `constants/weakPasswords.js` 做集合相等断言。
 */

// 与后端同一组类别定义：小写 / 大写 / 数字 / 常见标点。
const CATEGORY_TESTS = [/[a-z]/, /[A-Z]/, /\d/, /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/]

export function passwordProblem(value, { username = '', email = '' } = {}) {
  if (typeof value !== 'string' || value === '') return '请输入密码'
  if (value !== value.trim()) return '密码首尾不能包含空格'
  if (value.length < 8) return '密码长度至少为 8 位'

  const categories = CATEGORY_TESTS.filter((re) => re.test(value)).length
  if (value.length >= 12) {
    if (categories < 2) return '密码需至少包含字母、数字、特殊字符中的 2 种'
  } else if (categories < 3) {
    return '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种'
  }

  if (isWeakPassword(value)) return '密码过于常见，请更换更复杂的密码'

  const user = String(username || '').trim()
  if (user && value.toLowerCase() === user.toLowerCase()) return '密码不能与用户名相同'

  const local = String(email || '')
    .split('@')[0]
    .trim()
  if (local && value.toLowerCase() === local.toLowerCase()) return '密码不能与邮箱前缀相同'

  return null
}
