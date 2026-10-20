import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ConnectionBanner from '@/features/interview/components/ConnectionBanner.vue'
import { installElement } from '@/plugins/element'

function mounted(props) {
  return mount(ConnectionBanner, {
    props,
    global: { plugins: [installElement] },
  })
}

describe('面试房间：断线重连提示', () => {
  it('重连中显示第几次与几秒后', () => {
    const wrapper = mounted({ state: 'reconnecting', attempt: 1, max: 3, delaySeconds: 3 })
    const text = wrapper.text()

    expect(text).toContain('网络断开，正在重连（第 1/3 次）')
    expect(text).toContain('3 秒后自动重试')
    expect(text).toContain('无需刷新')
  })

  it('恢复后提示同步进度，失败后给出刷新指引', () => {
    const recovered = mounted({ state: 'recovered' })
    expect(recovered.text()).toContain('已重新连接')
    expect(recovered.text()).toContain('正在同步面试进度')

    const failed = mounted({ state: 'failed', attempt: 3, max: 3 })
    expect(failed.text()).toContain('重连失败')
    expect(failed.text()).toContain('请刷新页面重试')
  })

  it('正常状态下不渲染任何提示', () => {
    expect(mounted({ state: 'idle' }).text()).toBe('')
    expect(mounted({ state: 'connected' }).text()).toBe('')
  })
})
