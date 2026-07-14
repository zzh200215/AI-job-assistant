import request from './request'

export const listOrganizations = () => request.get('/organizations')

export const createOrganization = (data) => request.post('/organizations', data)

export const switchOrganization = (organizationId) =>
  request.put('/organizations/current', { organization_id: organizationId })

export const listOrganizationMembers = (organizationId) =>
  request.get(`/organizations/${organizationId}/members`)

export const addOrganizationMember = (organizationId, data) =>
  request.post(`/organizations/${organizationId}/members`, data)

export const updateOrganizationMemberRole = (organizationId, userId, role) =>
  request.put(`/organizations/${organizationId}/members/${userId}`, { role })

export const removeOrganizationMember = (organizationId, userId) =>
  request.delete(`/organizations/${organizationId}/members/${userId}`)

export const configureOrganizationSso = (organizationId, provider) =>
  request.put(`/organizations/${organizationId}/sso`, { provider })
