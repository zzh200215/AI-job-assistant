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

/* §10.29（D116）：422 这一支以前不走上面那套收口——`normalizeValidationMessage` 把 Pydantic 的
   `detail` **逐字**拼成 `"body.<字段>: <英文 msg>"`，而非 GET 又自动弹 toast，所以候选人看到的是
   "Field required"、"String should have at most 50 characters"。现在上屏那句由 `VALIDATION_COPY`
   按 type + ctx 组出来，英文原文只留在 `err.validationRaw`。这几条量的还是**真拦截器**。 */
describe('422 校验消息上屏的那一句是中文', () => {
  afterEach(() => {
    document.querySelectorAll('.el-message').forEach((node) => node.remove())
  })

  function rejectWith422(detail, method = 'post') {
    client.defaults.adapter = async (config) => {
      const err = new Error('Request failed with status code 422')
      err.config = { ...config, method }
      err.isAxiosError = true
      err.response = { status: 422, data: { detail }, headers: {} }
      throw err
    }
  }

  async function attempt() {
    try {
      await client.post('/auth/register', { username: 'a' })
      throw new Error('这条请求本该失败')
    } catch (err) {
      return err
    }
  }

  it('缺字段：屏上是中文一句，英文原文只在 validationRaw 里', async () => {
    rejectWith422([{ loc: ['body', 'resume_id'], type: 'missing', ctx: {}, msg: 'Field required' }])
    const err = await attempt()

    expect(err.userMessage).toBe('简历：请填写这一项')
    expect(err.userMessage).not.toMatch(/Field required|Input should|String should/)
    expect(err.validationRaw).toBe('body.resume_id: Field required')
    // toast 里那句也是同一个来源，不是另一套拼装
    expect(document.querySelector('.el-message')?.textContent).toContain('简历：请填写这一项')
  })

  it('带数字的约束把数字从 ctx 取，而不是抄英文模板', async () => {
    rejectWith422([
      {
        loc: ['body', 'title'],
        type: 'string_too_long',
        ctx: { max_length: 50 },
        msg: 'String should have at most 50 characters',
      },
    ])
    const err = await attempt()
    expect(err.userMessage).toBe('名称：最多只能 50 个字')
  })

  it('未知 type 退通用中文，不把英文原文吐回屏幕', async () => {
    rejectWith422([
      {
        loc: ['body', 'title'],
        type: 'some_future_pydantic_type',
        ctx: {},
        msg: 'Something nobody has seen',
      },
    ])
    const err = await attempt()
    expect(err.userMessage).toBe('请求参数有误，请检查后重试')
    expect(err.userMessage).not.toMatch(/[A-Za-z]/)
  })

  it('GET 的 422 照旧不弹 toast，但 userMessage 仍是中文', async () => {
    rejectWith422(
      [
        {
          loc: ['query', 'top_k'],
          type: 'int_parsing',
          ctx: {},
          msg: 'Input should be a valid integer, unable to parse string as an integer',
        },
      ],
      'get'
    )
    try {
      await client.get('/knowledge/search')
    } catch (err) {
      expect(err.userMessage).toBe('返回条数：这一项要填整数')
    }
    expect(document.querySelector('.el-message')).toBeNull()
  })
})
