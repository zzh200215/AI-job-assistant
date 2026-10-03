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

export function normalizeValidationMessage(detail, fallback = 'Request validation failed') {
  if (Array.isArray(detail)) {
    return detail.map((item) => `${item.loc?.join('.') || ''}: ${item.msg}`).join('; ')
  }
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  return fallback
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
