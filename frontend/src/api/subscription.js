// 订阅与权益 API
import request from './request'

// 获取所有套餐定义
export const getSubscriptionPlans = () => request.get('/subscription/plans')

// 获取当前用户订阅与权益状态
export const getMySubscription = () => request.get('/subscription/my')

// 检查某项资源额度（可选是否消耗）
export const checkQuota = (resource, consume = false) =>
  request.post('/subscription/check-quota', { resource, consume })

// 创建订阅订单
export const createOrder = (planTier, period = 'monthly') =>
  request.post('/subscription/create-order', { plan_tier: planTier, period })

// 获取用户订单历史
export const getMyOrders = () => request.get('/subscription/orders')

// 模拟支付：真实网关接入前的替身（Subscription.vue 就地注释也写着这句话）
export const mockPayOrder = (orderId) =>
  request.post('/subscription/mock-pay', { order_id: orderId })

// 管理员读全量订单：Overview（取前 100 条）与 Orders（翻页）共用这一条端点
export const getAdminOrders = (params = {}, config = {}) =>
  request.get('/subscription/admin/orders', { params, ...config })
