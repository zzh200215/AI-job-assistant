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

  /* D189：上面那条"服务端 120 < 客户端 150"只算了单次。真量出来的是——上游一直挂着不答时，
     60s 那一档要跑到 184.56s 才失败（3 次尝试 + 退避 1.5s、3s），即同序那一句在服务端最坏
     那里不成立。这条不把它变成"要求"，而是把**那个数从源码推出来**并钉进两条注释：
     谁动了 LLM_TIMEOUT 或重试次数，推导值就变了，注释必须跟着改，否则红。 */
  it('服务端最坏 = 单次 ×(1+重试) + 退避和；两条注释写的就是这个推导值', () => {
    const fromBackend = (path, pattern, label) =>
      Number(only(read(`../../../backend/${path}`), pattern, label))
    const server = fromBackend(
      'app/core/config.py',
      'LLM_TIMEOUT:\\s*int\\s*=\\s*(\\d+)',
      '服务端 LLM_TIMEOUT'
    )
    const retries = fromBackend(
      'app/services/llm_service.py',
      '_LLM_MAX_RETRIES = (\\d+)',
      'LLM 重试次数'
    )
    const backoff = fromBackend(
      'app/utils/retry.py',
      'backoff_factor: float = ([\\d.]+)',
      '退避系数'
    )
    const worst = server * (1 + retries) + backoff * ((retries * (retries + 1)) / 2)

    /* 公式对照实测：D189-A 把单次设成 60（改动前那一档）量到 184.56s，同式给 60×3+4.5=184.5。
       容差取 0.5s（连接建立与 python 的那 0.06s）；不算重试的话是 60，差 124.5s，红。 */
    expect(60 * (1 + retries) + backoff * ((retries * (retries + 1)) / 2)).toBeCloseTo(184.56, 0)
    expect(worst).toBe(364.5)
    /* 最坏那一档比客户端与 nginx 都久——所以客户端那 150s 是兜底，不是配平。 */
    expect(worst).toBeGreaterThan(REWRITE_SUGGESTIONS_TIMEOUT_MS / 1000)

    const apiBlock = only(
      read('../../nginx.conf'),
      'location /api/ \\{([\\s\\S]*?)\\n    \\}',
      'nginx /api 块'
    )
    expect(
      Number(only(apiBlock, 'proxy_read_timeout (\\d+)s', 'nginx proxy_read_timeout'))
    ).toBeLessThan(worst)
    expect(read('../../src/api/resume.js')).toContain(`${worst}s`)
    expect(read('../../nginx.conf')).toContain(`${worst}s`)
  })
})
