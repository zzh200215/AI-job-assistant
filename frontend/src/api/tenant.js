import request from '@/api/request'

// 当前租户品牌（公开接口，未配置回落默认）
export const getTenantBrand = (config = {}) => request.get('/tenant/brand', config)

// ===== 管理员：租户管理（T4-1） =====
export const listTenants = (params, config = {}) =>
  request.get('/admin/tenants', { params, ...config })
export const createTenant = (data, config = {}) => request.post('/admin/tenants', data, config)
export const updateTenant = (id, data, config = {}) =>
  request.put(`/admin/tenants/${id}`, data, config)
export const assignTenantAdmin = (id, data, config = {}) =>
  request.post(`/admin/tenants/${id}/admin`, data, config)
export const renewTenant = (id, data, config = {}) =>
  request.post(`/admin/tenants/${id}/renew`, data, config)

// ===== 管理员：品牌配置（T2-5） =====
export const updateTenantBrand = (id, data, config = {}) =>
  request.put(`/admin/tenants/${id}/brand`, data, config)

// ===== 管理员：域名绑定（T4-1） =====
export const listTenantDomains = (id, config = {}) =>
  request.get(`/admin/tenants/${id}/domains`, config)
export const bindTenantDomain = (id, data, config = {}) =>
  request.post(`/admin/tenants/${id}/domains`, data, config)
export const unbindTenantDomain = (id, domain, config = {}) =>
  request.delete(`/admin/tenants/${id}/domains/${domain}`, config)
