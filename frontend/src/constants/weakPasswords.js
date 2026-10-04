import WEAK_LIST from './weakPasswords.json'

/**
 * 常见弱密码清单，唯一出处是 `weakPasswords.json`，它与后端 `app/core/password_blacklist.py` 的
 * `_WEAK_PASSWORDS` 同一份内容。
 *
 * 为什么前端也要有一份：注册与重置密码的客户端校验必须说同一句"密码过于常见"，否则表单放行、
 * 服务端 422，候选人看到的是一副英文骨架（docs/upgrade-plan.md D103 量过那一族）。
 * 为什么是 `.json` 而不是把清单写在这个 JS 里：守卫的第一版是用正则读 JS 里的字符串字面量，
 * prettier 把双引号改成单引号那天，它读到 0 条并据此宣布"两边一致"——同一族第十五次复发
 * （尺子数的是文本/格式，不是东西）。JSON 由 `json.loads` 与 Vite 各自解析，谁也不用猜写法。
 *
 * **两边不许各自漂移**：`backend/tests/test_password_rules_agree_with_frontend.py` 读那个 JSON 做
 * 集合相等断言，并把同一张用例表同时打在服务端规则与前端镜像上。
 */
export const WEAK_PASSWORDS = new Set(WEAK_LIST)

/** 后端判成员前做的是 `password.strip().lower()`，这里逐字对齐。 */
export function isWeakPassword(value) {
  return WEAK_PASSWORDS.has(String(value).trim().toLowerCase())
}
