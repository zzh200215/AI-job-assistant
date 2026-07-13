import { isRoleAllowed } from '../constants/roles.js'

const AUTH_ROUTE_NAMES = new Set(['login', 'register'])

export function getRouteRedirect({ to, loggedIn, role, homeRoute }) {
  if (loggedIn && AUTH_ROUTE_NAMES.has(to.name)) {
    return homeRoute
  }

  if (!to.meta?.public && !loggedIn) {
    return '/login'
  }

  if (loggedIn && !isRoleAllowed(role, to.meta?.roles)) {
    return homeRoute
  }

  return null
}
