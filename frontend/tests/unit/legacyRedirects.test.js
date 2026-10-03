import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'

/* D87 结的是 D74 挂的那笔"等一次路由复核"。
   `src/router/index.js:322` 那条 TS2322 的根因是数组没标类型（`redirect` 被推成可选属性，于是既
   不像 `RouteRecordRedirect` 也不像 `RouteComponentRouteRecord`）。但当时没顺手加标注的理由写在账上：
   **光让类型过，等于默认这五条遗留重定向还对着新位置**。所以这一刀两半——标注（运行时零变化）+ 这张表。

   为什么用 `push()` 不用 `resolve()`：`router.resolve()` **不跟 redirect**（它只做 location→record
   的解析），我第一次写完四条断言全在 '/' 那一条上炸成 `Received: "/ → /"`，那不是我预期的回归，
   是量具选错。`push()` 才走重定向，代价是它同时跑 `beforeEach` 的角色守卫——所以这里要真登录。
   五条 path 从路由表现抄：`:47-49`（`/` → /home）、`:295-296`、`:299`、`:307-308`（带 `?tab=debug`，
   且它是 ADMIN 档）、`:312-313`。 */

const CANDIDATE_LINKS = [
  { from: '/', to: '/home', name: 'home' },
  { from: '/resume', to: '/resume-center', name: 'resume-center' },
  { from: '/jd', to: '/jd/input', name: 'jd-input' },
  { from: '/explain-match', to: '/smart-analysis', name: 'smart-analysis' },
]
const ADMIN_LINKS = [
  { from: '/query-rewrite-test', to: '/knowledge', name: 'knowledge-base', query: 'debug' },
]

function countRedirects(list) {
  return list.reduce(
    (n, r) => n + (r.redirect ? 1 : 0) + (r.children ? countRedirects(r.children) : 0),
    0
  )
}

async function landOn(router, auth, user, links) {
  auth.setAuth('probe-token', user)
  for (const { from, to, name, query } of links) {
    await router.push(from)
    const now = router.currentRoute.value
    expect(now.path, `旧链接 ${from} 落在了 ${now.fullPath}`).toBe(to)
    expect(now.name, `旧链接 ${from} 的命名路由不是 ${name}`).toBe(name)
    if (query) expect(now.query.tab, `旧链接 ${from} 丢了 ?tab`).toBe(query)
  }
}

let router
let auth

beforeEach(() => {
  setActivePinia(createPinia())
  auth = useAuthStore()
  router = createRouter({ history: createMemoryHistory(), routes })
})

describe('遗留链接的重定向（路由表 + 守卫一起走）', () => {
  it('候选人侧四条各归各位', async () => {
    await landOn(router, auth, { id: 1, username: 'probe', role: 'candidate' }, CANDIDATE_LINKS)
  })

  it('管理员侧那条带 ?tab=debug 的也在', async () => {
    await landOn(
      router,
      auth,
      { id: 2, username: 'root', role: 'admin', is_admin: true },
      ADMIN_LINKS
    )
  })

  it('表里的 redirect 记录数与这份清单一致——多一条就得同时说清它指向哪', () => {
    expect(
      countRedirects(routes),
      '路由表里的 redirect 记录数变了：要么新加一条没进断言，要么删了一条而旧链接开始 404'
    ).toBe(CANDIDATE_LINKS.length + ADMIN_LINKS.length)
  })

  it('每个目标都真的有组件（重定向到一条空记录不会报错，只会白屏）', async () => {
    for (const { to, name } of [...CANDIDATE_LINKS, ...ADMIN_LINKS]) {
      const record = router.getRoutes().find((r) => r.name === name)
      expect(record, `目标 ${name}（${to}）不在路由表里`).toBeTruthy()
      expect(record.components?.default, `${name} 没有组件`).toBeTruthy()
    }
  })
})
