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
    } = await import('@/api/auth')

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
    const { exportMyData } = await import('@/api/auth')
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
    // 传的是后端今天真收的那个参数（days）。原先这里写 `{ tenant_id: 3 }`，而 D136 把那四个
    // `?tenant_id=` 从后端摘掉了——这条测试钉的是"包装层把 params 原样转发"，换一个仍被接受的
    // 参数才是它本来想说的事；留着 tenant_id 会让下一次读账的人以为后端还认它。
    const params = { days: 30 }

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
    const { getAdminUsers } = await import('@/api/auth')
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

  /* D109：这里原本还有一条腿钉 `mockPayOrder` 的请求形状。订阅页的"模拟支付"入口按 §10.1
     摘掉之后，那条函数没有任何调用方了——连同 `api/subscription.js` 里的定义一起删。
     留着一个零调用方 wrapper 加一条测它的测试，就是账上 E21 那种"链修好了但调用方是 0"的形状。 */
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

/* D95（§10.22 那条 ②）把凭据四条端点从 `stores/auth.js` 搬进 `api/auth.js`，同时把
   `normalizeText` / `normalizeEmail` 也搬了过来——**搬的是请求体的形状**，那是与后端的契约。
   下面钉的是"搬之前 store 发出去的那一份 body"，逐字对照：账号只去空白（不转小写），
   邮箱去空白并转小写，`login` 固定带 `notifyError: false`（401/密码错都不弹 toast，原因写在表单上方）。 */
describe('auth.js：凭据端点与它自带的请求体形状', () => {
  it('四条端点的 URL、方法、body 形状与 config 照抄 store 里那一份', async () => {
    const { login, register, resetPassword, getCurrentUser } = await import('@/api/auth')

    await login('  Zzh@Example.COM  ', 'pw')
    await register('  Tom ', '  TOM@X.COM ', 'pw')
    await resetPassword(' acct ', ' A@B.COM ', 'n', 'n')
    await getCurrentUser()

    expect(sent[0]).toEqual({
      method: 'post',
      url: '/auth/login',
      second: { account: 'Zzh@Example.COM', password: 'pw' },
      third: { notifyError: false },
    })
    expect(sent[1].second).toEqual({ username: 'Tom', email: 'tom@x.com', password: 'pw' })
    expect(sent[2].second).toEqual({
      account: 'acct',
      email: 'a@b.com',
      new_password: 'n',
      confirm_password: 'n',
    })
    expect(sent[3]).toEqual(plain('get', '/auth/me'))
    // 4 个函数正好发 4 条，不多发
    expect(sent).toHaveLength(4)
  })

  it('反向证据：账号不做小写折叠，邮箱做', async () => {
    const { login, register } = await import('@/api/auth')
    await login('MiXeD', 'pw')
    await register('MiXeD', 'MiXeD@X.COM', 'pw')
    expect(sent[0].second.account).toBe('MiXeD')
    expect(sent[1].second.email).toBe('mixed@x.com')
  })
})
