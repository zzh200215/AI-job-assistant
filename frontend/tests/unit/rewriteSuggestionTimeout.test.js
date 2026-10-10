import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'

/* D188：`POST /resume/{id}/rewrite-suggestions` 是同步等 LLM 的那一发，而它外面套着**三道 60 秒墙**：
   axios 全局 `timeout: 60000`（`src/api/request.js:15`）、nginx `/api/` 没写 `proxy_read_timeout`
   （nginx 默认就是 60s）、服务端 `LLM_TIMEOUT` 当时也是 60。D182 在真库上量到它撞满 60s 被客户端
   掐断、重试才成功。本条把"只抬一层"变成会红的东西——**三层顺序**，不是三个孤立的数。 */

const sent = []

vi.mock('@/api/request', () => {
  const record = (method) => (url, second, third) => {
    sent.push({ method, url, second, third })
    return Promise.resolve({})
  }
  return {
    default: {
      get: record('get'),
      post: record('post'),
      delete: record('delete'),
      put: record('put'),
    },
  }
})

const { getRewriteSuggestions, REWRITE_SUGGESTIONS_TIMEOUT_MS } = await import('@/api/resume')

const read = (relative) => readFileSync(new URL(relative, import.meta.url), 'utf-8')

/** 从一段文本里取**唯一**一处匹配；取不到或取到多处都直接红——那是"守卫在数空气"的形状。 */
function only(text, pattern, label) {
  const hits = [...text.matchAll(new RegExp(pattern, 'gm'))].map((m) => m[1])
  expect(hits.length, `${label} 命中 ${hits.length} 次（应为 1 次）：${pattern}`).toBe(1)
  return hits[0]
}

beforeEach(() => {
  sent.length = 0
})

describe('那一发同步 LLM 请求的三层超时', () => {
  it('请求带上了 per-request 超时，且它是第三参（axios post 的 config 槽位）', async () => {
    await getRewriteSuggestions(7, 3)
    expect(sent).toEqual([
      {
        method: 'post',
        url: '/resume/7/rewrite-suggestions',
        second: { jd_id: 3 },
        third: { timeout: 150000 },
      },
    ])
    expect(REWRITE_SUGGESTIONS_TIMEOUT_MS).toBe(150000)
  })

  it('不带 jd_id 时也只有这一条，config 照样在第三槽', async () => {
    await getRewriteSuggestions(7)
    expect(sent.length).toBe(1)
    expect(sent[0].second).toEqual({})
    expect(sent[0].third).toEqual({ timeout: REWRITE_SUGGESTIONS_TIMEOUT_MS })
  })

  it('全局 axios 超时仍是 60s——不许用"全局抬一下"糊掉这一发的问题', () => {
    const text = read('../../src/api/request.js')
    expect(Number(only(text, 'timeout:\\s*(\\d+)', 'axios 全局 timeout'))).toBe(60000)
  })

  it('三层顺序：服务端单次 < 客户端 < nginx /api/，谁单独动都会红', () => {
    const clientSeconds = REWRITE_SUGGESTIONS_TIMEOUT_MS / 1000

    const server = Number(
      only(
        read('../../../backend/app/core/config.py'),
        'LLM_TIMEOUT:\\s*int\\s*=\\s*(\\d+)',
        '服务端 LLM_TIMEOUT'
      )
    )
    expect(server).toBeLessThan(clientSeconds)

    const apiBlock = only(
      read('../../nginx.conf'),
      'location /api/ \\{([\\s\\S]*?)\\n    \\}',
      'nginx /api 块'
    )
    const nginxSeconds = Number(
      only(apiBlock, 'proxy_read_timeout (\\d+)s', 'nginx proxy_read_timeout')
    )
    expect(nginxSeconds).toBeGreaterThan(clientSeconds)
  })

  it('nginx 那个块里如果只有 ws 的 300s 而没有 /api/ 的，判据必须找不到', () => {
    // 反向证据：把 /api/ 块里的两行超时删掉，上面的解析方式必须拿不到值（而不是拿到 /ws/ 的 300）。
    const text = read('../../nginx.conf')
    const apiBlock = only(text, 'location /api/ \\{([\\s\\S]*?)\\n    \\}', 'nginx /api 块')
    const stripped = apiBlock
      .replace(/proxy_read_timeout \d+s;/, '')
      .replace(/proxy_send_timeout \d+s;/, '')
    expect(stripped).not.toMatch(/proxy_read_timeout/)
    expect(stripped).not.toContain('300')
  })
})
