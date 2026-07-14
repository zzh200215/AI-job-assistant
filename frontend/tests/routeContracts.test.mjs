import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import { USER_ROLES } from '../src/constants/roles.js'
import { getRouteRedirect } from '../src/router/guard.js'

const routerSource = await readFile(new URL('../src/router/index.js', import.meta.url), 'utf8')

function routeBlock(name) {
  const match = routerSource.match(
    new RegExp(String.raw`\{\s*path:\s*'[^']*',\s*name:\s*'${name}'[\s\S]*?meta:\s*\{([^}]*)\}`)
  )

  assert.ok(match, `Expected route "${name}" to be declared`)
  return match[0]
}

test('candidate workflow routes remain available and role-protected', () => {
  const contracts = [
    ['resume-compare', "path: 'resume/compare/:id'"],
    ['task-center', "path: 'tasks'"],
    ['pipeline-kanban', "path: 'jobs/pipeline/kanban'"],
  ]

  for (const [name, path] of contracts) {
    const block = routeBlock(name)
    assert.match(block, new RegExp(path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
    assert.match(block, /roles:\s*CANDIDATE/)
  }
})

test('administrator pages remain inaccessible to candidate navigation', () => {
  const adminRoute = routeBlock('admin-overview')

  assert.match(adminRoute, /roles:\s*ADMIN/)
  assert.match(routerSource, /getRouteRedirect\(/)
})

test('route guard redirects unauthenticated and unauthorized users', () => {
  assert.equal(
    getRouteRedirect({
      to: { name: 'resume-compare', meta: { roles: [USER_ROLES.candidate] } },
      loggedIn: false,
      role: USER_ROLES.candidate,
      homeRoute: '/home',
    }),
    '/login'
  )

  assert.equal(
    getRouteRedirect({
      to: { name: 'admin-overview', meta: { roles: [USER_ROLES.admin] } },
      loggedIn: true,
      role: USER_ROLES.candidate,
      homeRoute: '/home',
    }),
    '/home'
  )
})

test('route guard keeps authorized routes and redirects signed-in users from auth pages', () => {
  assert.equal(
    getRouteRedirect({
      to: { name: 'admin-overview', meta: { roles: [USER_ROLES.admin] } },
      loggedIn: true,
      role: USER_ROLES.admin,
      homeRoute: '/home',
    }),
    null
  )

  assert.equal(
    getRouteRedirect({
      to: { name: 'login', meta: { public: true } },
      loggedIn: true,
      role: USER_ROLES.candidate,
      homeRoute: '/home',
    }),
    '/home'
  )
})
