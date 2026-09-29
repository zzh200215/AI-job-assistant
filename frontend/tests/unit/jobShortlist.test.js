import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useJobShortlist } from '@/features/jobs/composables/useJobShortlist'
import { useAuthStore } from '@/stores/auth'

/* 投递清单与搜索历史只存在浏览器里，D40 把它们从 JobSearch.vue 搬进 composable，
   搬之前这块没有任何测试。这里钉的是搬走的四条语义：按 uid 或 id 去重、新的在前、
   清单上限 20 / 历史上限 8、key 跟着登录用户走（换账号不能看见上一个人的清单），
   以及 localStorage 里一段坏 JSON 只会读成空清单。 */

const job = (uid, id = null) => ({
  uid,
  id,
  title: `${uid} 岗位`,
  company: '某公司',
  location: '北京',
  salary: '20K-30K',
  skillTags: ['Python'],
  local: true,
})

function stored(key) {
  const raw = localStorage.getItem(`recruit.market.${key}.7`)
  return raw ? JSON.parse(raw) : null
}

let market

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  useAuthStore().user = { id: 7 }
  market = useJobShortlist()
})

describe('投递清单', () => {
  it('同一个岗位按 uid 或 id 去重，且新的排在最前', () => {
    market.toggleShortlist(job('a'))
    market.toggleShortlist(job('b'))
    market.toggleShortlist(job('a'))

    expect(market.shortlist.value.map((item) => item.uid)).toEqual(['b'])
    expect(stored('shortlist').map((item) => item.uid)).toEqual(['b'])

    // id 相同就算同一个岗位，即使 uid 不同（搜索页与仓库页给同一个岗位造的 uid 前缀不一样）。
    // 于是第二个来源看到的是「移出清单」，点它是删而不是替换——这是原语义，不是笔误。
    market.toggleShortlist(job('search-9', 9))
    expect(market.shortlist.value.map((item) => item.uid)).toEqual(['search-9', 'b'])
    expect(market.isShortlisted(job('local-9', 9))).toBe(true)

    market.toggleShortlist(job('local-9', 9))
    expect(market.shortlist.value.map((item) => item.uid)).toEqual(['b'])
    expect(market.isShortlisted(job('local-9', 9))).toBe(false)
  })

  it('再往前加就把最旧的挤出屏幕，上限 20', () => {
    for (let i = 0; i < 22; i++) market.toggleShortlist(job(`job-${i}`))

    expect(market.shortlist.value.length).toBe(20)
    expect(market.shortlist.value[0].uid).toBe('job-21')
    expect(market.shortlist.value[19].uid).toBe('job-2')
    expect(stored('shortlist').length).toBe(20)
  })

  it('移出清单后写回的也是同一份，清空则是空数组而不是删 key', () => {
    market.toggleShortlist(job('a'))
    market.toggleShortlist(job('a'))
    expect(stored('shortlist')).toEqual([])

    market.toggleShortlist(job('b'))
    market.clearShortlist()
    expect(market.shortlist.value).toEqual([])
    expect(localStorage.getItem('recruit.market.shortlist.7')).toBe('[]')
  })

  it('坏 JSON 只会读成空清单，不会把页面炸掉', () => {
    localStorage.setItem('recruit.market.shortlist.7', '{不是 JSON')

    const again = useJobShortlist()
    expect(again.shortlist.value).toEqual([])
    expect(again.recentSearches.value).toEqual([])
  })
})

describe('搜索历史', () => {
  it('同一个词只留最近一次，上限 8', () => {
    for (const word of ['Python', 'Go', 'Python']) market.pushRecentSearch(word)
    expect(market.recentSearches.value).toEqual(['Python', 'Go'])

    for (let i = 0; i < 9; i++) market.pushRecentSearch(`词${i}`)
    expect(market.recentSearches.value.length).toBe(8)
    expect(market.recentSearches.value[0]).toBe('词8')
    expect(market.recentSearches.value).not.toContain('Go')
    expect(stored('history')).toEqual(market.recentSearches.value)
  })

  it('未登录时落在 guest 的 key 上，换账号不会读到上一个用户的清单', () => {
    market.toggleShortlist(job('a'))
    market.pushRecentSearch('Python')

    useAuthStore().user = { id: 8 }
    const other = useJobShortlist()
    expect(other.shortlist.value).toEqual([])
    expect(other.recentSearches.value).toEqual([])

    useAuthStore().user = null
    expect(useJobShortlist().shortlist.value).toEqual([])
    expect(localStorage.getItem('recruit.market.shortlist.guest')).toBeNull()
  })
})
