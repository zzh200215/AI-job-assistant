import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'

/* D200：改写建议那一发从"同步等模型"改成"建作业 + 轮询"之后，D188 那条三层超时守卫的
   **前提消失了**——它钉的是"一个挂 150 秒的请求要穿过三层墙"，而现在没有任何一个请求会挂那么久。
   所以这里钉的是新形状该成立的三件事，不是把旧判据放宽：
   ① 请求不带 per-request 超时了（那个 150000 必须整个出树，留着它就是"异步只改了 URL"）；
   ② 轮询有上限、并且卸载时会被停掉（否则关掉面板还在后台转，是第二条泄漏）；
   ③ 服务端那句失败原因**不许**出现在前端读的任何一个键里（它可能带模型返回的原文）。 */

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

const resumeApi = await import('@/api/resume')
const { createRewriteSuggestionJob, getRewriteSuggestionJob } = resumeApi

const read = (relative) => readFileSync(new URL(relative, import.meta.url), 'utf-8')
const view = read('../../src/features/resume/views/ResumeUpload.vue')

/** 取**唯一**一处匹配；取不到或取到多处都直接红——那是"守卫在数空气"的形状。 */
function only(text, pattern, label) {
  const hits = [...text.matchAll(new RegExp(pattern, 'gm'))].map((m) => m[1])
  expect(hits.length, `${label} 命中 ${hits.length} 次（应为 1 次）：${pattern}`).toBe(1)
  return hits[0]
}

beforeEach(() => {
  sent.length = 0
})

describe('改写建议的作业化形状', () => {
  it('建作业那一发不带第三个实参——150 秒那把 per-request 超时整个出树', async () => {
    await createRewriteSuggestionJob(7, 3)
    expect(sent).toEqual([
      {
        method: 'post',
        url: '/resume/7/rewrite-suggestion-jobs',
        second: { jd_id: 3 },
        third: undefined,
      },
    ])
    // 反向证据：那个常量不能再被 import 到（留着它就是异步只改了 URL）。
    expect(resumeApi.REWRITE_SUGGESTIONS_TIMEOUT_MS).toBeUndefined()
    expect(read('../../src/api/resume.js')).not.toMatch(/REWRITE_SUGGESTIONS_TIMEOUT_MS|\b150000\b/)
  })

  it('不带 jd_id 时体是空对象，而不是 { jd_id: null }', async () => {
    await createRewriteSuggestionJob(7)
    expect(sent[0].second).toEqual({})
  })

  it('轮询打的是那条带 job_id 的 GET，同样不带超时', async () => {
    await getRewriteSuggestionJob(77)
    expect(sent).toEqual([
      {
        method: 'get',
        url: '/resume/rewrite-suggestion-jobs/77',
        second: undefined,
        third: undefined,
      },
    ])
  })

  it('全局 axios 超时仍是 60s——这一族不需要它，但别顺手把它抬走', () => {
    const text = read('../../src/api/request.js')
    expect(Number(only(text, 'timeout:\\s*(\\d+)', 'axios 全局 timeout'))).toBe(60000)
  })

  it('轮询预算是一个**有上限**的数，且落在旧那一发 150 秒之内', () => {
    const attempts = Number(
      only(view, 'const REWRITE_JOB_POLL_MAX_ATTEMPTS = (\\d+)', '轮询次数上限')
    )
    const interval = Number(only(view, 'const REWRITE_JOB_POLL_INTERVAL_MS = (\\d+)', '轮询间隔'))
    const budget = attempts * interval
    expect(budget).toBeGreaterThan(0)
    // 上限存在的意义：作业卡在 running 时不许永远转下去。150s 是它替掉的那条 per-request 超时。
    expect(budget).toBeLessThanOrEqual(150000)
    expect(view).toMatch(/timeoutMessage:/)
    expect(view).toMatch(/failedMessage:/)
  })

  it('卸载时停表——否则关了面板还在后台打接口', () => {
    expect(view).toMatch(/onUnmounted\(\(\) => rewritePoller\.stopPolling\(\)\)/)
  })

  it('前端一处都不读 error_msg：那句里可能有模型返回的原文', () => {
    expect(view).not.toMatch(/error_msg/)
    expect(read('../../src/api/resume.js')).not.toMatch(/error_msg/)
  })

  it('这一族复用既有的轮询实现，不另建第二个轮询器', () => {
    expect(view).toMatch(/import \{ createAgentTaskPoller \} from '@\/utils\/agentTaskPolling'/)
    // 反向：视图里不许出现自写的 setTimeout 轮询（两份实现迟早分叉，见 D44 那条记账）。
    expect(view).not.toMatch(/setTimeout\([^)]*poll/i)
  })

  it('nginx /api/ 的超时行还在（它现在保护的是其余同步等模型的路由）', () => {
    const apiBlock = only(
      read('../../nginx.conf'),
      'location /api/ \\{([\\s\\S]*?)\\n    \\}',
      'nginx /api 块'
    )
    const nginxSeconds = Number(
      only(apiBlock, 'proxy_read_timeout (\\d+)s', 'nginx proxy_read_timeout')
    )
    expect(nginxSeconds).toBe(180)
    // 服务端最坏那一档仍然是 `单次 ×(1+重试) + 退避和`（D189 实测 3×60+4.5=184.5s 对上公式）。
    // 这条与改写那一发无关了，但它对树里其余同步等模型的路由还成立，所以注释里的数还得在。
    expect(read('../../nginx.conf')).toContain('364.5s')
  })
})
