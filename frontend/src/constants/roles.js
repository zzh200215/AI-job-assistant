export const USER_ROLES = {
  candidate: 'candidate',
  admin: 'admin',
}

export function normalizeRole(role) {
  if (role === USER_ROLES.admin) return USER_ROLES.admin
  return USER_ROLES.candidate
}

export function getRoleLabel(role) {
  if (role === USER_ROLES.admin) return '管理员'
  return '求职者端'
}

export function getHomeRouteByRole(role) {
  return '/home'
}

export function isRoleAllowed(role, allowedRoles) {
  if (!Array.isArray(allowedRoles) || allowedRoles.length === 0) return true
  // admin 可以访问所有页面
  if (normalizeRole(role) === USER_ROLES.admin) return true
  return allowedRoles.includes(normalizeRole(role))
}
