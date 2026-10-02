import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

import Profile from '@/features/shell/views/Profile.vue'
import { installElement } from '@/plugins/element'

/* §10.25 的那半拍：Profile 的统计格与脚注原先读的是 `GET /dashboard/overview` **不返回**的键
   （`resume_count` / `total_sessions` / `days_active` / `created_at`），所以"简历数"恒 0、
   脚注恒"已使用 1 天 · 0 次模拟面试"。D83 把它们改成读同一份载荷里真存在的
   `summary.total_resumes` / `summary.total_interviews`，天数改从 `/auth/me` 的 user 取。
   钉四件事：
   ① 那三格现在画的是载荷里的真值（同一份夹具下，旧读法算出来是 0 / 0 / 1 —— 三条都会红）；
   ② **两个"面试次数"不许合并**：格子里那个是 funnel 推出来的（interview + offer 阶段的投递数 2+1=3），
      脚注那个是 `summary.total_interviews`（会话数 7），语义不同；
   ③ 「简历初成」这颗成就随 resume_count 一起活过来（它此前永不解锁）；
   ④ 「面试之星」仍锁着——`best_score` 全仓没有生产者（最接近的是面试统计端点的**均值**），
      这一半还没拍，所以这条断言记的是**现状**不是主张。 */

const CREATED_AT = new Date(Date.now() - 61 * 86400000).toISOString()

vi.mock('@/api/request', () => ({
  default: {
    get: async (url) =>
      url === '/auth/me' ? { id: 1, username: 'zzh', created_at: CREATED_AT } : {},
    post: async () => ({}),
    put: async () => ({}),
    delete: async () => ({}),
  },
}))

vi.mock('@/api/dashboard', async (importOriginal) => ({
  ...(await importOriginal()),
  getDashboardOverview: vi.fn(async () => ({
    user: { id: 1, username: 'zzh' },
    summary: {
      total_resumes: 3,
      total_interviews: 7,
      total_applications: 4,
      avg_match_score: 74.5,
    },
    funnel: { todo: 1, applied: 4, written_test: 0, interview: 2, offer: 1 },
    trend: [],
    recent_activities: [],
  })),
}))

async function mounted() {
  const wrapper = mount(Profile, {
    attachTo: document.body,
    global: { plugins: [createPinia(), installElement] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

function statNum(label) {
  const card = [...document.querySelectorAll('.stat-card-v')].find(
    (c) => c.querySelector('.stat-label')?.textContent.trim() === label
  )
  return card ? card.querySelector('.stat-num').textContent.trim() : null
}

function footer() {
  return document.querySelector('.stats-footer')?.textContent.replace(/\s+/g, ' ').trim() ?? null
}

function badge(name) {
  return [...document.querySelectorAll('.achievement-card')].find(
    (b) => b.querySelector('.ach-info strong')?.textContent.trim() === name
  )
}

beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  /* 凭据要从**生产的形状**灌进来：`useAuthStore` 建 store 时读 localStorage 的 `user` 槽
     （setAuth 写就是这个键），而 `fetchMe()` 第一件事是 `if (!token.value) return null`。
     只灌 user 不灌 token 的话，那一发 /auth/me 根本不发，`created_at` 停在 undefined，
     这一条会红在"已使用 1 天"上——红在夹具上，不是红在该红的位置。 */
  localStorage.setItem('token', 'probe-token')
  localStorage.setItem('user', JSON.stringify({ id: 1, username: 'zzh', created_at: CREATED_AT }))
})

describe('个人中心：统计格、脚注与两颗成就', () => {
  it('简历数与脚注用的是载荷里的真值，不再是兜底的 0 与「1 天」', async () => {
    await mounted()

    expect(statNum('简历数')).toBe('3')
    const text = footer()
    expect(text, '脚注整行没画出来（markup 或类名改了）').toBeTruthy()
    expect(text).toContain('7 次模拟面试')
    /* 期望值就是"注册到今天的自然日数"：夹具把 created_at 放在 61 天前，向上取整是 62。
       旧读法在这里恒等于 1（它减的是 `data.created_at`，overview 里没有这个键）。 */
    expect(text).toContain(`已使用 ${Math.ceil((Date.now() - new Date(CREATED_AT)) / 86400000)} 天`)
    expect(text).not.toContain('已使用 1 天')
  })

  it('格子那个「面试次数」是漏斗推的 3，脚注那个是会话数 7，两个不是一回事', async () => {
    await mounted()
    expect(statNum('面试次数')).toBe('3')
    expect(footer()).toContain('7 次模拟面试')
  })

  it('「简历初成」随真值解锁；「面试之星」仍锁着，因为 best_score 没有生产者', async () => {
    await mounted()
    expect(badge('简历初成').classList.contains('unlocked'), '简历数=3 时这颗成就应当已达成').toBe(
      true
    )
    expect(badge('面试之星').classList.contains('locked')).toBe(true)
  })
})
