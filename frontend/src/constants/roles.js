export const USER_ROLES = {
  candidate: 'candidate',
  recruiter: 'recruiter',
}

export function normalizeRole(role) {
  return role === USER_ROLES.recruiter ? USER_ROLES.recruiter : USER_ROLES.candidate
}

export function getRoleLabel(role) {
  return normalizeRole(role) === USER_ROLES.recruiter ? '招聘者端' : '求职者端'
}

export function getHomeRouteByRole(_role) {
  return '/home'
}

export function isRoleAllowed(role, allowedRoles) {
  if (!Array.isArray(allowedRoles) || allowedRoles.length === 0) return true
  return allowedRoles.includes(normalizeRole(role))
}
