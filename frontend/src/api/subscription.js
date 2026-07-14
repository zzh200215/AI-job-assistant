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
