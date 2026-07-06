import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createRequestId,
  formatApiErrorMessage,
  normalizeValidationMessage,
} from '../src/utils/requestTracing.js'

test('formatApiErrorMessage appends request id when present', () => {
  assert.equal(
    formatApiErrorMessage('Upload failed', 'req-123'),
    'Upload failed [req-123]',
  )
})

test('formatApiErrorMessage falls back when message missing', () => {
  assert.equal(
    formatApiErrorMessage('', '', 'Request failed'),
    'Request failed',
  )
})

test('normalizeValidationMessage joins validation details', () => {
  const message = normalizeValidationMessage([
    { loc: ['body', 'resume_id'], msg: 'Field required' },
    { loc: ['body', 'jd_id'], msg: 'Field required' },
  ])

  assert.equal(
    message,
    'body.resume_id: Field required; body.jd_id: Field required',
  )
})

test('createRequestId uses fallback format when crypto.randomUUID is unavailable', () => {
  const requestId = createRequestId('ui', null)

  assert.match(requestId, /^ui-[a-z0-9]+-[a-z0-9]+$/)
})
