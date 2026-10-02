import { beforeEach, describe, expect, it, vi } from 'vitest'

/* D69 把 7 个视图里的 19 处裸 `request.*` 搬进 api 层。搬家不该改变任何一条请求，
   而"没改变"不能靠眼睛看：现有测试只路过其中 7 处（`taskCenterRace` 的 4 处 +
   `privacySummaryRace` 的概览与两个删除），而且它们 mock 的是 request.get/delete 本身、
   按 URL 认路、**不看 config**——连被路过的这 7 处也没人钉参数。
   下面把**搬走之前逐字写在各视图里的那份参数**钉成期望表——URL、params、responseType、
   notifyError 都是与后端的契约，不是实现细节。
   逐张表整体 `toEqual` 而不是逐条挑：这样同时钉住了"每个函数只发这一条、不多发一条"。

   记录器按 axios 的槽位记：get/delete 的第二参就是 config；post 的第二参是 body、
   第三参才是 config（system.js:5 那条 `request.post(url, {}, config)` 是同一个形状）。

   变异自证（每次只改一处，看谁红）见 D69 那条账。 */

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
      put: record('put'),
      delete: record('delete'),
    },
  }
})

beforeEach(() => {
  sent.length = 0
})

const plain = (method, url) => ({ method, url, second: undefined, third: undefined })

describe('account.js：隐私页与个人中心共用的那批 /auth/* 自助端点', () => {
  it('概览、三类删除、重发验证邮件、注销——URL 与方法照抄', async () => {
    const {
      getDataSummary,
      deleteMyResumes,
      deleteMyAnalyses,
      deleteMyInterviews,
      sendVerificationEmail,
      deleteMyAccount,
    } = await import('@/api/account')

    await getDataSummary()
    await deleteMyResumes()
    await deleteMyAnalyses()
    await deleteMyInterviews()
    await sendVerificationEmail()
    await deleteMyAccount()

    expect(sent).toEqual([
      plain('get', '/auth/data-summary'),
      plain('delete', '/auth/data/resumes'),
      plain('delete', '/auth/data/analyses'),
      plain('delete', '/auth/data/interviews'),
      plain('post', '/auth/send-verification-email'),
      plain('delete', '/auth/account'),
    ])
  })

  it('导出那条带 responseType: blob——丢掉它页面会把坏东西喂给 createObjectURL', async () => {
    const { exportMyData } = await import('@/api/account')
    await exportMyData()
    expect(sent).toEqual([
      {
        method: 'get',
        url: '/auth/export-data',
        second: { responseType: 'blob' },
        third: undefined,
      },
    ])
  })
})

describe('analytics.js / admin.js / subscription.js：后台面那五条', () => {
  it('三条分析读把 params 与 notifyError 一起带上，且 revenue 走 /admin 前缀', async () => {
    const { getAnalyticsSummary, getAdminRevenue, getAnalyticsFunnel } =
      await import('@/api/analytics')
    const params = { tenant_id: 3 }

    await getAnalyticsSummary(params, { notifyError: false })
    await getAdminRevenue(params, { notifyError: false })
    await getAnalyticsFunnel(params, { notifyError: false })

    const withParams = (url) => ({
      method: 'get',
      url,
      second: { params, notifyError: false },
      third: undefined,
    })
    expect(sent).toEqual([
      withParams('/analytics/summary'),
      // 后端把这条挂在独立的 admin_router 上（backend/app/api/analytics.py:72），前缀与另两条不同
      withParams('/admin/analytics/revenue'),
      withParams('/analytics/funnel'),
    ])
  })

  it('admin 用户列表与 admin 订单列表：分页进 params，notifyError 不被挤掉', async () => {
    const { getAdminUsers } = await import('@/api/admin')
    const { getAdminOrders } = await import('@/api/subscription')
    const paged = { page: 2, page_size: 20 }
    const firstHundred = { page: 1, page_size: 100 }

    await getAdminUsers(paged, { notifyError: false })
    await getAdminOrders(firstHundred, { notifyError: false })

    expect(sent).toEqual([
      {
        method: 'get',
        url: '/auth/admin/users',
        second: { params: paged, notifyError: false },
        third: undefined,
      },
      {
        method: 'get',
        url: '/subscription/admin/orders',
        second: { params: firstHundred, notifyError: false },
        third: undefined,
      },
    ])
  })

  it('模拟支付发的是 body 里的 order_id（第二槽），不是 query', async () => {
    const { mockPayOrder } = await import('@/api/subscription')
    await mockPayOrder('ORD-9')
    expect(sent).toEqual([
      {
        method: 'post',
        url: '/subscription/mock-pay',
        second: { order_id: 'ORD-9' },
        third: undefined,
      },
    ])
  })
})

describe('agent.js：任务中心那四条是纯 drop-in（api 层早就有，页面一直在绕过去）', () => {
  it('列表带 params、概览不带、retry/cancel 把 id 拼进路径', async () => {
    const { getAgentTasks, getAgentTaskSummary, retryAgentTask, cancelAgentTask } =
      await import('@/api/agent')
    const params = { limit: 50, status: 'running' }

    await getAgentTasks(params)
    await getAgentTaskSummary()
    await retryAgentTask(12)
    await cancelAgentTask(12)

    expect(sent).toEqual([
      { method: 'get', url: '/agent/tasks', second: { params }, third: undefined },
      plain('get', '/agent/tasks/summary'),
      plain('post', '/agent/task/12/retry'),
      plain('post', '/agent/task/12/cancel'),
    ])
  })
})
