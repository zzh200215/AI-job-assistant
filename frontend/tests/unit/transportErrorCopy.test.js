import { afterEach, describe, expect, it, vi } from 'vitest'

/* `tests/unit/setup.js` 为了页面测试把 `@/api/request` 整体 mock 掉了；这一文件要量的正是
   那个模块里的**真**响应拦截器，所以先把 mock 撤掉、清空模块图，再动态 import 一次。 */
vi.doUnmock('@/api/request')
vi.resetModules()
const { default: client } = await import('@/api/request')

/* 传输层失败时，`api/request.js` 以前把 axios 自己那句英文（"Network Error" /
   "timeout of 60000ms exceeded"）写进 `err.userMessage`。下游二十几处写的是
   `err.userMessage || err.message || '中文兜底'`，于是那句中文兜底**永远不触发**，
   落到候选人屏幕上的是英文技术串。这里按真实拦截器量，不测纯函数：
   adapter 造出来的就是 axios 那几个形状。 */

const originalAdapter = client.defaults.adapter

afterEach(() => {
  client.defaults.adapter = originalAdapter
})

function rejectWith(build) {
  client.defaults.adapter = async (config) => {
    const err = build(config)
    throw err
  }
}

function httpError(message, extra) {
  return (config) => {
    const err = new Error(message)
    err.config = { ...config, method: 'get' }
    err.isAxiosError = true
    Object.assign(err, extra)
    return err
  }
}

async function failure() {
  try {
    await client.get('/system/status')
    throw new Error('这条请求本该失败')
  } catch (err) {
    return err
  }
}

describe('传输层失败的文案来源', () => {
  it('连不上时 userMessage 是中文，不是 axios 那句英文', async () => {
    rejectWith(httpError('Network Error', { code: 'ERR_NETWORK' }))
    const err = await failure()
    expect(err.userMessage).toBe('网络异常，请稍后重试')
    // 反向证据：这条一旦写错，上面那句就会变成 "Network Error"
    expect(err.userMessage).not.toMatch(/[A-Za-z]/)
    // 技术串没被抹掉，日志与排障还要靠它
    expect(err.message).toBe('Network Error')
  })

  it('超时有自己的一句，而不是 "timeout of 60000ms exceeded"', async () => {
    rejectWith(httpError('timeout of 60000ms exceeded', { code: 'ECONNABORTED' }))
    const err = await failure()
    expect(err.userMessage).toBe('请求超时，请稍后重试')
    expect(err.userMessage).not.toMatch(/timeout|\d{4,}ms/)
  })

  it('有响应但没有服务端文案时，只给状态码，不给 "Request failed with status code 500"', async () => {
    rejectWith(
      httpError('Request failed with status code 500', {
        response: { status: 500, data: '<html>oops</html>', headers: {} },
      })
    )
    const err = await failure()
    expect(err.userMessage).toBe('请求失败（500），请稍后重试')
  })

  it('服务端给了文案就用服务端那句，一个字都不改', async () => {
    rejectWith(
      httpError('Request failed with status code 400', {
        response: { status: 400, data: { message: '简历还没有解析完成' }, headers: {} },
      })
    )
    const err = await failure()
    expect(err.userMessage).toBe('简历还没有解析完成')
  })

  it('正向对照：这里跑的是真拦截器，不是 setup 里那份 mock', async () => {
    /* 没有这条，上面四条的"红"可能只是 mock 没撤销成功。真拦截器会剥掉 `{code:0,data}` 信封，
       而 setup 那份 mock 返回的是整个空列表对象，两者可分辨。 */
    client.defaults.adapter = async () => ({
      data: { code: 0, message: 'ok', data: { marked: 'unwrapped' } },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: { method: 'get' },
    })
    await expect(client.get('/system/status')).resolves.toEqual({ marked: 'unwrapped' })
  })
})
