import { beforeEach, vi } from 'vitest'

// Element Plus touches these on mount; jsdom does not implement them.
class FakeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}

globalThis.ResizeObserver ??= FakeObserver
globalThis.IntersectionObserver ??= FakeObserver
globalThis.MutationObserver ??= FakeObserver

window.matchMedia ??= (query) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener() {},
  removeListener() {},
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() {
    return false
  },
})

Range.prototype.getBoundingClientRect ??= () => ({
  width: 0,
  height: 0,
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
})
Element.prototype.scrollTo ??= () => {}

// The response interceptor in src/api/request.js unwraps `{ code: 0, data }`,
// so views receive the payload directly. Backend list endpoints are not uniform
// (`/interview/sessions` returns a bare array, `/resume/list` returns
// `{ items, total }`), so the fixture is an array that also carries the
// paginated keys.
const EMPTY_LIST = Object.assign([], {
  items: [],
  list: [],
  results: [],
  records: [],
  total: 0,
  page: 1,
  page_size: 20,
})

function emptyPayload(url) {
  if (/\/me$|\/profile|\/current/.test(url)) return { id: 1, username: 'smoke', role: 'candidate' }
  return EMPTY_LIST
}

const requestMock = Object.assign(
  vi.fn(async (config) => ({ data: emptyPayload(config?.url) })),
  {
    get: vi.fn(async (url) => emptyPayload(url)),
    post: vi.fn(async (url) => emptyPayload(url)),
    put: vi.fn(async (url) => emptyPayload(url)),
    patch: vi.fn(async (url) => emptyPayload(url)),
    delete: vi.fn(async (url) => emptyPayload(url)),
    interceptors: { request: { use() {} }, response: { use() {} } },
  }
)

vi.mock('@/api/request', () => ({ default: requestMock }))

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('token', 'smoke-test-token')
  localStorage.setItem('user', JSON.stringify({ id: 1, username: 'smoke', role: 'candidate' }))
})
