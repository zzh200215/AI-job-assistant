import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

import AppLoadError from '@/components/ui/AppLoadError.vue'
import { installElement } from '@/plugins/element'

function render(props) {
  return mount(AppLoadError, { props, global: { plugins: [installElement, createPinia()] } })
}

describe('AppLoadError', () => {
  it('说清是哪一件东西没加载出来，并带上后端原话', () => {
    const wrapper = render({ title: '推荐加载失败', message: '服务暂时不可用' })
    expect(wrapper.attributes('role')).toBe('alert')
    expect(wrapper.find('strong').text()).toBe('推荐加载失败')
    expect(wrapper.find('span').text()).toBe('服务暂时不可用')
  })

  it('重试按钮把决定权交回调用方', async () => {
    const wrapper = render({ title: 'x', retryLabel: '重试' })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('没有可重试动作时不渲染空按钮，没有后端原话时不留空行', () => {
    const wrapper = render({ title: '版本记录加载失败', retryLabel: '' })
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.find('span').exists()).toBe(false)
  })
})
