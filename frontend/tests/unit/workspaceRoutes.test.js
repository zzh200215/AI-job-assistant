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
     原来这里只等一个 `setTimeout(0)`：`/jobs/search` 在全量并行跑里红过两次（单跑 13 条全绿），
     满载时这个 0ms 定时器先于那些微任务/网络桩触发。按 D68 的口径处理——**抬高等待上限、
     不放宽断言**：最多等 2s，等到了仍然按下面那些原条件判。 */
  const deadline = Date.now() + 2000
  while (Date.now() < deadline) {
    const main = wrapper.find('.main-shell')
    if (main.exists() && main.element.children.length > 0) break
    await new Promise((resolve) => setTimeout(resolve, 25))
  }
  return wrapper
}

// Routes picked because they own the largest scoped-style blocks in src/features,
// i.e. the ones the global theme compatibility layer currently depends on.
const WORKSPACE_ROUTES = [
  ['/home', '首页'],
  ['/jobs/search', '岗位搜索'],
  ['/smart-analysis', '智能分析'],
  ['/career-planning', '职业规划'],
  ['/jobs/pipeline/kanban', '投递看板'],
  ['/jobs/recommend', '岗位推荐'],
  ['/resume-center', '简历中心'],
  ['/knowledge', '知识库'],
  ['/interview/setup', 'AI 模拟面试'],
  ['/profile', '个人中心'],
  ['/tasks', '任务中心'],
  ['/history', '历史记录'],
  // Admin-owned page, but the test router carries no guard so it mounts for any
  // role; it is here because A2 changed its template and script.
  ['/prompt-traces', 'Prompt 追踪'],
]

describe('workspace routes render inside the themed shell', () => {
  for (const [path, title] of WORKSPACE_ROUTES) {
    it(`${path} mounts with a themed page surface`, async () => {
      const wrapper = await renderWorkspace(path)
      try {
        expect(wrapper.find('.workspace-theme').exists()).toBe(true)
        expect(wrapper.find('.main-shell').exists()).toBe(true)
        expect(wrapper.find('.topbar').text()).toContain(title)
        // A mounted view always contributes at least one element under main.
        expect(wrapper.find('.main-shell').element.children.length).toBeGreaterThan(0)
      } finally {
        wrapper.unmount()
      }
    })
  }
})
