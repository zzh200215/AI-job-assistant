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
