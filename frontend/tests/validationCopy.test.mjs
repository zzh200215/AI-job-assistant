import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  VALIDATION_COPY,
  VALIDATION_FIELD_LABELS,
  normalizeValidationMessage,
  rawValidationText,
  validationUserCopy,
} from '../src/utils/requestTracing.js'

/* §10.29 落地（D116）。D103 把这一族量成了一张表，结论是"上屏的是一副英文骨架"：
   内置约束纯英文且模板带随字段变的数字，自定义 `ValueError` 是中文句子外面套 `Value error, `，
   `model_validator(mode="after")` 还把 `loc` 塌成 `body`。这一文件钉的是新合同：
   **按 `type` + `ctx` 组中文句子，不翻译英文 `msg`**——翻译等于把第二份真相抄进前端，
   Pydantic 一改措辞就悄悄漂。
   夹具 `tests/fixtures/validationShapes.json` 由 `backend/scripts/collect_validation_shapes.py`
   从真路由的请求体模型导出（24 个模型、12 种可达 type、31 条英文模板），
   所以下面这几条腿比对的是**后端实际发得出来的东西**，不是我想象的样例。 */

const FIXTURE = JSON.parse(
  readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'validationShapes.json'),
    'utf8'
  )
)

const shapeByType = new Map(FIXTURE.shapes.map((s) => [s.type, s]))

test('夹具自己不是空的：type 数、模型数、英文模板数都点得出名', () => {
  assert.ok(FIXTURE.shapes.length >= 10, '夹具在数空气')
  assert.equal(FIXTURE.model_total, 24)
  assert.ok(FIXTURE.english_msgs.length >= 20)
  // 反向证据：这张表里必须真有"随字段变的数字"那一族，否则插值那几条腿是白写的
  assert.ok(FIXTURE.english_msgs.some((m) => /at most \d+ characters/.test(m)))
})

test('可达 type 与映射表**双向相等**：少一条会漏，多一条是死码', () => {
  const mapped = Object.keys(VALIDATION_COPY).sort()
  const reachable = [...shapeByType.keys()].sort()
  assert.deepEqual(mapped, reachable, 'VALIDATION_COPY 与后端可达的 type 不再是同一批')
})

test('每一条可达形状出来的都是中文句子，且不含任何英文框', () => {
  for (const shape of FIXTURE.shapes) {
    const ctx = {}
    for (const key of shape.ctx_keys) ctx[key] = 7
    const copy = validationUserCopy([
      { loc: ['body', 'field'], type: shape.type, ctx, msg: shape.sample_msg },
    ])
    assert.match(copy, /[一-鿿]/, `${shape.type} 出来的句子没有中文：${copy}`)
    for (const english of FIXTURE.english_msgs) {
      assert.ok(!copy.includes(english), `${shape.type} 把英文原文留在屏上了：${copy} ← ${english}`)
    }
    assert.ok(!copy.startsWith('Value error,'), `${shape.type} 的英文框没摘掉：${copy}`)
  }
})

test('数字来自 ctx，不是抄在表里的常量', () => {
  const copy = (max) =>
    validationUserCopy([
      {
        loc: ['body', 'title'],
        type: 'string_too_long',
        ctx: { max_length: max },
        msg: 'String should have at most 50 characters',
      },
    ])
  assert.equal(copy(50), '名称：最多只能 50 个字')
  assert.equal(copy(200), '名称：最多只能 200 个字')
  assert.equal(
    validationUserCopy([
      {
        loc: ['body', 'rating'],
        type: 'less_than_equal',
        ctx: { le: 5 },
        msg: 'Input should be less than or equal to 5',
      },
    ]),
    '评分：不能大于 5'
  )
})

test('自定义 validators 那句中文原样上屏，只摘掉英文框', () => {
  const detail = [
    {
      loc: ['body', 'password'],
      type: 'value_error',
      ctx: { error: 'Value error, 密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 类' },
      msg: 'Value error, 密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 类',
    },
  ]
  // 句子自己已经带了主语，就不再叠一层"密码：密码需…"
  assert.equal(
    validationUserCopy(detail),
    '密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 类'
  )
})

test('EmailStr 的英文原因被换成中文', () => {
  const copy = validationUserCopy([
    {
      loc: ['body', 'email'],
      type: 'value_error',
      ctx: { reason: 'An email address must have an @-sign.' },
      msg: 'value is not a valid email address: An email address must have an @-sign.',
    },
  ])
  assert.equal(copy, '邮箱格式不对，请检查后重试')
})

test('未来的英文 validator 不会把英文甩到屏上', () => {
  const copy = validationUserCopy([
    {
      loc: ['body', 'note'],
      type: 'value_error',
      ctx: {},
      msg: 'Value error, must be shorter than a haiku',
    },
  ])
  assert.doesNotMatch(copy, /[A-Za-z]{4,}/)
})

test('表里没有的 type 退通用中文，且不回吐原文', () => {
  const copy = validationUserCopy([
    {
      loc: ['body', 'title'],
      type: 'string_regex_mismatch',
      ctx: {},
      msg: 'String should match a thing nobody has seen',
    },
  ])
  assert.equal(copy, '请求参数有误，请检查后重试')
})

test('多条违规只说第一条，并如实报还有几条', () => {
  const copy = validationUserCopy([
    { loc: ['body', 'resume_id'], type: 'missing', ctx: {}, msg: 'Field required' },
    { loc: ['body', 'jd_id'], type: 'missing', ctx: {}, msg: 'Field required' },
    {
      loc: ['body', 'title'],
      type: 'string_too_long',
      ctx: { max_length: 100 },
      msg: 'String should have at most 100 characters',
    },
  ])
  assert.equal(copy, '简历：请填写这一项（另有 2 处需要修改）')
})

test('loc 塌成 body 时不硬造主语', () => {
  const copy = validationUserCopy([
    { loc: ['body'], type: 'value_error', ctx: {}, msg: 'Value error, 两次输入的密码不一致' },
  ])
  assert.equal(copy, '两次输入的密码不一致')
})

test('字段标签表没有死条目：每个键都真在后端的 loc 里出现', () => {
  for (const field of Object.keys(VALIDATION_FIELD_LABELS)) {
    assert.ok(
      FIXTURE.loc_tails.includes(field),
      `标签表里的 ${field} 在后端可达的 loc 尾段里找不到`
    )
  }
})

test('原文仍然取得到——收口不等于丢掉排查线索', () => {
  const detail = [{ loc: ['body', 'resume_id'], type: 'missing', ctx: {}, msg: 'Field required' }]
  assert.equal(rawValidationText(detail), 'body.resume_id: Field required')
  // normalizeValidationMessage 的名字留着，语义换了：它给人看，不再给日志看
  assert.equal(normalizeValidationMessage(detail), '简历：请填写这一项')
})

test('空 detail / 字符串 detail / 缺参数三种入口都不崩', () => {
  assert.equal(validationUserCopy([]), '请求参数有误，请检查后重试')
  assert.equal(validationUserCopy(undefined), '请求参数有误，请检查后重试')
  assert.equal(validationUserCopy('参数不对'), '参数不对')
})
