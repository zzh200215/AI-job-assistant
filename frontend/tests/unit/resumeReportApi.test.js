import { beforeEach, describe, expect, it, vi } from 'vitest'

/* 简历评估报告那一族四个接口的**形状**：URL 段、请求体键名、blob 那一条。
   与 `rewriteSuggestionJobFlow.test.js` 同一族判据——作业化之后每一发都必须是毫秒级返回的，
   所以这里钉的第一件事就是"没有第三个实参"（那条 150 秒的 per-request 超时不能跟着搬过来）。 */

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

const { applyReportRedline, createReportJob, downloadReportHtml, getReportJob } =
  await import('@/api/resume')

beforeEach(() => {
  sent.length = 0
})

describe('评估报告的四个接口', () => {
  it('建作业打的是简历那一段，体里带 jd_id 与 target_position，不带超时配置', async () => {
    await createReportJob(7, { jd_id: 3, target_position: 'RAG 应用开发' })
    expect(sent).toEqual([
      {
        method: 'post',
        url: '/resume/7/report-jobs',
        second: { jd_id: 3, target_position: 'RAG 应用开发' },
        third: undefined,
      },
    ])
  })

  it('没选目标岗位时给的是 null 与空串，而不是把键漏掉', async () => {
    await createReportJob(7)
    expect(sent[0].second).toEqual({ jd_id: null, target_position: '' })
  })

  it('轮询那一发是 `/resume/report-jobs/{job_id}`，同样不带第三个实参', async () => {
    await getReportJob(77)
    expect(sent).toEqual([
      { method: 'get', url: '/resume/report-jobs/77', second: undefined, third: undefined },
    ])
  })

  it('采纳带的是全局编号列表', async () => {
    await applyReportRedline(77, [1, 3])
    expect(sent).toEqual([
      {
        method: 'post',
        url: '/resume/report-jobs/77/apply-redline',
        second: { marks: [1, 3] },
        third: undefined,
      },
    ])
  })

  it('独立 HTML 走 blob——下载与页面上那一份同源，前端不拼第二套 HTML', async () => {
    await downloadReportHtml(77)
    expect(sent).toEqual([
      {
        method: 'get',
        url: '/resume/report-jobs/77/report.html',
        second: { responseType: 'blob' },
        third: undefined,
      },
    ])
  })
})
