import { describe, expect, it } from 'vitest'
import { useLatestCall } from '@/composables/useLatestCall'

describe('useLatestCall', () => {
  it('只有最后一次 begin() 的令牌仍然有效', () => {
    const latestCall = useLatestCall()
    const first = latestCall()
    const second = latestCall()
    expect(first()).toBe(false)
    expect(second()).toBe(true)
    const third = latestCall()
    expect(second()).toBe(false)
    expect(third()).toBe(true)
  })

  it('每个组件实例各自计数，不共享全局序号', () => {
    const a = useLatestCall()
    const b = useLatestCall()
    const tokenA = a()
    const tokenB = b()
    expect(tokenA()).toBe(true)
    expect(tokenB()).toBe(true)
  })

  it('失败的请求不会把新一次的令牌作废', () => {
    const latestCall = useLatestCall()
    const stale = latestCall()
    const current = latestCall()
    expect(stale()).toBe(false)
    // 过期请求的 finally 之后，新一次仍然有效
    expect(current()).toBe(true)
  })
})
