import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createRequestId,
  formatApiErrorMessage,
  normalizeValidationMessage,
  rawValidationText,
} from '../src/utils/requestTracing.js'

test('formatApiErrorMessage appends request id when present', () => {
  assert.equal(formatApiErrorMessage('Upload failed', 'req-123'), 'Upload failed [req-123]')
})

test('formatApiErrorMessage falls back when message missing', () => {
  assert.equal(formatApiErrorMessage('', '', 'Request failed'), 'Request failed')
})

test('422 上屏的是中文那一句，英文原文只在 raw 里', () => {
  const detail = [
    { loc: ['body', 'resume_id'], type: 'missing', ctx: {}, msg: 'Field required' },
    { loc: ['body', 'jd_id'], type: 'missing', ctx: {}, msg: 'Field required' },
  ]
  // D103 之前这条钉的是 `'body.resume_id: Field required; body.jd_id: Field required'`——
  // 那正是候选人看到的英文骨架。语义换了，所以函数名也换了去处（§10.29 / D116）。
  assert.equal(normalizeValidationMessage(detail), '简历：请填写这一项（另有 1 处需要修改）')
  assert.equal(
    rawValidationText(detail),
    'body.resume_id: Field required; body.jd_id: Field required'
  )
})

test('createRequestId uses fallback format when crypto.randomUUID is unavailable', () => {
  const requestId = createRequestId('ui', null)

  assert.match(requestId, /^ui-[a-z0-9]+-[a-z0-9]+$/)
})
