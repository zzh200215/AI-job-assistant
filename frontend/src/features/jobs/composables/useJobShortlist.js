import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

/* 投递清单与搜索历史是纯浏览器状态：按登录用户分 key，没有请求、没有在途覆盖，所以这条链不需要
   useLatestCall 令牌，也没有 loading / error 三态。读失败当成"清单本来就是空的"——本地存储里
   一段坏 JSON 只能这么处理；写失败（配额满）则照旧抛出，与搬走之前一致。 */

function loadLocalArray(key) {
  try {
    const raw = localStorage.getItem(key)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveLocalArray(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function useJobShortlist() {
  const authStore = useAuthStore()
  const marketStorageKey = (key) => `recruit.market.${key}.${authStore.user?.id || 'guest'}`

  const shortlist = ref(loadLocalArray(marketStorageKey('shortlist')))
  const recentSearches = ref(loadLocalArray(marketStorageKey('history')))

  function toggleShortlist(job) {
    const existing = shortlist.value.findIndex(
      (item) => item.uid === job.uid || (job.id && item.id === job.id)
    )
    if (existing >= 0) {
      shortlist.value.splice(existing, 1)
    } else {
      shortlist.value.unshift({
        uid: job.uid,
        id: job.id || null,
        title: job.title,
        company: job.company,
        location: job.location,
        salary: job.salary,
        summary: job.summary,
        rawText: job.rawText,
        source: job.source,
        sourceUrl: job.sourceUrl,
        skillTags: job.skillTags || [],
        experience: job.experience || '',
        education: job.education || '',
        local: job.local,
      })
    }
    shortlist.value = shortlist.value.slice(0, 20)
    saveLocalArray(marketStorageKey('shortlist'), shortlist.value)
  }

  function isShortlisted(job) {
    return shortlist.value.some((item) => item.uid === job.uid || (job.id && item.id === job.id))
  }

  function clearShortlist() {
    shortlist.value = []
    saveLocalArray(marketStorageKey('shortlist'), shortlist.value)
  }

  function pushRecentSearch(value) {
    const next = [value, ...recentSearches.value.filter((item) => item !== value)].slice(0, 8)
    recentSearches.value = next
    saveLocalArray(marketStorageKey('history'), next)
  }

  return {
    shortlist,
    recentSearches,
    toggleShortlist,
    isShortlisted,
    clearShortlist,
    pushRecentSearch,
  }
}
