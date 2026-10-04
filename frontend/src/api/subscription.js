// 订阅与权益 API
import request from './request'

// 获取所有套餐定义
export const getSubscriptionPlans = () => request.get('/subscription/plans')

// 获取当前用户订阅与权益状态
export const getMySubscription = () => request.get('/subscription/my')

// 检查某项资源额度（可选是否消耗）
export const checkQuota = (resource, consume = false) =>
  request.post('/subscription/check-quota', { resource, consume })

// D109：`createOrder` 与 `mockPayOrder` 随订阅页的"模拟支付"入口一起删除——后端那两个端点还在
// （E19 的默认拒绝继续盖着），但前端不再有 wrapper，也不再能从一个候选人页面上把自己的套餐改掉。
// `checkQuota` / `getMyOrders` 在本仓同样是零调用方，它们不是这次删的（删前就该由 §2 的口径判），
// 记在 docs/upgrade-plan.md D109。

// 获取用户订单历史
export const getMyOrders = () => request.get('/subscription/orders')

// 管理员读全量订单：Overview（取前 100 条）与 Orders（翻页）共用这一条端点
export const getAdminOrders = (params = {}, config = {}) =>
  request.get('/subscription/admin/orders', { params, ...config })
