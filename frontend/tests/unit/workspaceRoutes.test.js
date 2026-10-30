import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent, h } from 'vue'
import { RouterView } from 'vue-router'

import { routes } from '@/router'
import { installElement } from '@/plugins/element'

const Root = defineComponent({ render: () => h(RouterView) })

async function renderWorkspace(path) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()

  const wrapper = mount(Root, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  /* 路由组件是懒加载的，页面自身还要在 `onMounted` 里发请求，所以"挂载完了"不是一瞬间的事。
     这里最多等 2s，等到了仍然按下面那些原条件判。 */
  const deadline = Date.now() + 2000
  while (Date.now() < deadline) {
    const main = wrapper.find('.main-shell')
    if (main.exists() && main.element.children.length > 0) break
    await new Promise((resolve) => setTimeout(resolve, 25))
  }
  return wrapper
}

const WORKSPACE_ROUTES = [
  ['/home', '首页'],
  ['/jobs/search', '岗位搜索'],
  ['/smart-analysis', '求职分析'],
  ['/career-planning', '职业规划'],
  ['/jobs/pipeline/kanban', '投递看板'],
  ['/jobs/recommend', '岗位推荐'],
  ['/resume-center', '简历中心'],
  ['/interview/setup', 'AI 模拟面试'],
  ['/profile', '个人中心'],
  ['/tasks', '任务中心'],
  ['/history', '历史记录'],
]

/* 管理后台仍走深色作用域；候选端在浅色外壳里。两条腿都要在真实路由上验，
   否则"切主题"只会在登录页那四条公共路由上成立。 */
const ADMIN_ROUTES = [
  ['/prompt-traces', 'Prompt 追踪'],
  ['/knowledge', '知识库'],
]

describe('workspace routes render inside the shell', () => {
  for (const [path, title] of WORKSPACE_ROUTES) {
    it(`${path} mounts in the light shell`, async () => {
      const wrapper = await renderWorkspace(path)
      try {
        expect(wrapper.find('.layout-shell').classes(), `${path} 不该再套深色作用域`).not.toContain(
          'workspace-theme'
        )
        expect(wrapper.find('.main-shell').exists()).toBe(true)
        expect(wrapper.find('.topbar').exists()).toBe(true)
        // 页面标题只由页面自己那一个 H1 承担，顶栏不再重复一份。
        expect(wrapper.find('.topbar').text(), `${path} 顶栏还在重复页面标题`).not.toContain(title)
        expect(wrapper.find('.main-shell').element.children.length).toBeGreaterThan(0)
      } finally {
        wrapper.unmount()
      }
    })
  }

  for (const [path, title] of ADMIN_ROUTES) {
    it(`${path} keeps the dark admin scope`, async () => {
      const wrapper = await renderWorkspace(path)
      try {
        expect(wrapper.find('.layout-shell').classes(), `${path} 丢了深色作用域`).toContain(
          'workspace-theme'
        )
        expect(wrapper.find('.topbar').text()).not.toContain(title)
        expect(wrapper.find('.main-shell').element.children.length).toBeGreaterThan(0)
      } finally {
        wrapper.unmount()
      }
    })
  }
})
