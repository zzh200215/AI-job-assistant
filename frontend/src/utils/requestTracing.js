export function createRequestId(prefix = 'web', cryptoLike = globalThis.crypto) {
  const generator = cryptoLike?.randomUUID
  if (typeof generator === 'function') {
    return `${prefix}-${generator.call(cryptoLike)}`
  }

  const fallback = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  return `${prefix}-${fallback}`
}

export function formatApiErrorMessage(message, requestId, fallback = 'Request failed') {
  const text = message || fallback
  return requestId ? `${text} [${requestId}]` : text
}

/* §10.29（D116）：422 上屏那一句的唯一出处。
   D103 量到的是**一副英文骨架**，不是"整段英文"：Pydantic 的内置约束全是英文模板且带随字段变的数字
   （`String should have at most {N} characters` 实测 N=50/100/200/255/30 五种），我们自己的
   `@field_validator` 是"中文句子外面套 `Value error, `"，而 `model_validator(mode="after")` 会把
   `loc` 塌成 `body`（连"哪一格错了"都不给）。所以这里**按 `type` + `ctx` 组句子**，不翻译英文 `msg`——
   翻译英文串等于把第二份真相抄进前端，而 Pydantic 一改措辞就悄悄漂。
   这张表覆盖的是**实测可达的那 12 种 type**（24 个请求体模型、821 条可达形状）；
   表里没有的 type 一律退 `VALIDATION_FALLBACK`，绝不上英文：宁可少说一句，不要把正则和枚举码甩给候选人。
   原文始终留在 `rawValidationText` 里，进 `error.validationRaw` 供内部排查——降级对候选人静默、对内可查
   （同 §5 那条口径）。 */
export const VALIDATION_FALLBACK = '请求参数有误，请检查后重试'

export const VALIDATION_COPY = {
  missing: () => '请填写这一项',
  string_type: () => '这一项要填文字',
  int_parsing: () => '这一项要填整数',
  bool_parsing: () => '这一项要选「是」或「否」',
  list_type: () => '这一项要填一个列表',
  dict_type: () => '这一项要填键值对',
  string_too_short: (ctx) => `至少要 ${ctx.min_length} 个字`,
  string_too_long: (ctx) => `最多只能 ${ctx.max_length} 个字`,
  string_pattern_mismatch: () => '格式不对，请按页面提示填写',
  greater_than_equal: (ctx) => `不能小于 ${ctx.ge}`,
  less_than_equal: (ctx) => `不能大于 ${ctx.le}`,
  // 这一族是"中文句子套英文框"：框要摘掉，句子是后端 validators 自己写的
  value_error: (ctx, message) => customValidationCopy(message),
}

/* 字段名→中文标签。只收**视图里已经在用这个词**的那些（逐条对着 `el-form label="…"` 抄的），
   没收录的字段就走"不带主语"的句子——宁可少一句主语，也不要造出第三个名字。
   `loc` 尾段就是模型里的字段名，`model_validator(mode="after")` 那种塌成 `body` 的自然落进无标签分支。 */
export const VALIDATION_FIELD_LABELS = {
  account: '邮箱或用户名',
  username: '用户名',
  email: '邮箱',
  password: '密码',
  new_password: '新密码',
  confirm_password: '确认新密码',
  name: '姓名',
  nickname: '昵称',
  phone: '电话',
  title: '名称',
  company: '公司',
  position: '职位',
  location: '城市',
  industry: '行业',
  expected_city: '期望城市',
  expected_position: '期望职位',
  expected_industry: '期望行业',
  expected_salary_min: '期望最低月薪',
  expected_salary_max: '期望最高月薪',
  salary_min: '最低月薪',
  salary_max: '最高月薪',
  work_years: '工作年限',
  education: '学历',
  job_seeking_status: '求职状态',
  current_employer: '当前公司',
  current_position: '当前职位',
  skills: '技能',
  skill_tags: '技能标签',
  resume_id: '简历',
  jd_id: '岗位',
  raw_text: '正文',
  content: '内容',
  query: '查询内容',
  original_query: '查询内容',
  stage: '阶段',
  target_stage: '目标阶段',
  priority: '优先级',
  rating: '评分',
  mood: '心情',
  note: '备注',
  notes: '备注',
  remark: '备注',
  interview_round: '面试轮次',
  interview_type: '面试类型',
  top_k: '返回条数',
}

const VALUE_ERROR_FRAME = /^Value error,\s*/
const CHINESE = /[一-鿿]/

function customValidationCopy(message) {
  const text = String(message || '')
    .replace(VALUE_ERROR_FRAME, '')
    .trim()
  // EmailStr 那一族：Pydantic 把英文原因拼在 msg 与 ctx.reason 里（"An email address must have an @-sign."），
  // 那句候选人读不懂，而"哪一格错了"标签里已经说了
  if (/valid email address/i.test(text)) return '邮箱格式不对，请检查后重试'
  // 未来的 validators 若写英文，退通用中文：这条判据要保证的是"屏幕上不出现英文校验句"
  if (!CHINESE.test(text)) return '填写的内容不符合要求，请检查后重试'
  return text
}

/** 给人看的那一句：只说第一条违规 + 还有几条，不拼一长串。 */
export function validationUserCopy(detail, fallback = VALIDATION_FALLBACK) {
  if (!Array.isArray(detail) || !detail.length) {
    const text = typeof detail === 'string' && detail.trim() ? detail.trim() : fallback
    return text
  }
  const [first, ...rest] = detail
  const builder = VALIDATION_COPY[first?.type]
  if (!builder) return fallback
  const sentence = builder(first?.ctx || {}, first?.msg)
  const field = Array.isArray(first?.loc) ? String(first.loc[first.loc.length - 1]) : ''
  const label = VALIDATION_FIELD_LABELS[field]
  // 后端那句 validators 的中文常常已经带上了主语（"密码需至少包含…"），再加一次就成了"密码：密码需…"。
  const head = label && !sentence.includes(label) ? `${label}：${sentence}` : sentence
  return rest.length ? `${head}（另有 ${rest.length} 处需要修改）` : head
}

/** 内部可读的那一串：只进 `error.validationRaw` 与日志，不再上屏。 */
export function rawValidationText(detail) {
  if (Array.isArray(detail)) {
    return detail.map((item) => `${item.loc?.join('.') || ''}: ${item.msg}`).join('; ')
  }
  if (typeof detail === 'string' && detail.trim()) return detail
  return ''
}

/** 保留旧名字，语义换了：这里返回的是**给人看的那一句**，原文请取 `rawValidationText`。 */
export function normalizeValidationMessage(detail, fallback = VALIDATION_FALLBACK) {
  return validationUserCopy(detail, fallback)
}

/* 传输层失败（连不上、超时、有响应但没带文案）时，axios 自己那句 `err.message` 是英文技术串
   （"Network Error" / "timeout of 60000ms exceeded" / "Request failed with status code 500"）。
   这句只能进日志，不能当 `userMessage` 往下发——下游二十几处写的是
   `err.userMessage || err.message || '中文兜底'`，只要 userMessage 非空，那句中文就永远不触发，
   于是候选人屏幕上出现的就是这句英文。原始技术串始终留在 `err.message` 里，没被抹掉。 */
export function networkFailureCopy(err) {
  const status = err?.response?.status
  if (status) return `请求失败（${status}），请稍后重试`
  if (err?.code === 'ECONNABORTED' || /timeout/i.test(String(err?.message || ''))) {
    return '请求超时，请稍后重试'
  }
  return '网络异常，请稍后重试'
}

/** 面向用户的错误文案只认这一个来源；不要再回落到 `err.message`。 */
export function userErrorCopy(err, fallback) {
  const copy = err?.userMessage
  return typeof copy === 'string' && copy.trim() ? copy : fallback
}
