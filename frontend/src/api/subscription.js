// 订阅与权益 API
import request from './request'

// 获取当前用户订阅与权益状态
export const getMySubscription = () => request.get('/subscription/my')

// D109 删掉了 `createOrder` / `mockPayOrder`（订阅页的"模拟支付"入口，理由见账）。
// D8（2026-11-14）把同源的三条零调用 wrapper 一起清净：`getSubscriptionPlans`（没有任何页面展示
// 套餐表；`/subscription/plans` 仍是公开端点，留着给登录侧未来的定价页）、`checkQuota`（前端从不
// 预检额度，服务端在动作里判）、`getMyOrders`（候选人侧没有订单页，订单只有管理员那个入口）。

// 管理员读全量订单：Overview（取前 100 条）与 Orders（翻页）共用这一条端点
export const getAdminOrders = (params = {}, config = {}) =>
  request.get('/subscription/admin/orders', { params, ...config })
