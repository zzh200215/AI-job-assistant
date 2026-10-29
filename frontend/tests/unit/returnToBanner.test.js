import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import ReturnToBanner from '@/components/ui/ReturnToBanner.vue'
import { installElement } from '@/plugins/element'
import { readReturnTo, rememberReportReturn } from '@/utils/navigationReturn'

/* 横幅只做两件事：说明来源、能回去；关掉或回去都要把上下文清掉。 */

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/interview/setup', component: { template: '<div />' } },
      { path: '/interview/report/:sessionId', component: { template: '<div />' } },
    ],
  })
}

describe('面试报告来源横幅', () => {
  let router

  beforeEach(async () => {
    sessionStorage.clear()
    router = makeRouter()
    await router.push('/interview/setup')
    await router.isReady()
  })

  async function mounted() {
    const wrapper = mount(ReturnToBanner, {
      global: { plugins: [router, installElement] },
    })
    await flushPromises()
    return wrapper
  }

  it('显示来源并返回报告，返回后清掉上下文', async () => {
    rememberReportReturn(12)
    const wrapper = await mounted()

    expect(wrapper.text()).toContain('从面试报告跳转而来')
    const back = wrapper.findAll('button').find((button) => button.text().includes('返回面试报告'))
    expect(back).toBeTruthy()
    await back.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/interview/report/12')
    expect(readReturnTo()).toBeNull()
  })

  it('知道了只清上下文，不导航', async () => {
    rememberReportReturn(12)
    const wrapper = await mounted()

    const dismiss = wrapper.findAll('button').find((button) => button.text().includes('知道了'))
    await dismiss.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/interview/setup')
    expect(readReturnTo()).toBeNull()
    expect(wrapper.find('.return-banner').exists()).toBe(false)
  })

  it('没有来源上下文时什么都不画', async () => {
    const wrapper = await mounted()

    expect(wrapper.find('.return-banner').exists()).toBe(false)
  })
})
