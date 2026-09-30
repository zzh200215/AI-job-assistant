import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeUpload from '@/features/resume/views/ResumeUpload.vue'
import { installElement } from '@/plugins/element'

/* 行下拉里的「解析」调 handleCmd('parse', r)，它 `await parseResume(r.id)` 之后直接写
   currentParsed / showParsed——而 `handleCmd` 里那 11 个分支共用一个函数体，谁都没有令牌。
   下拉菜单是每行一个入口、点完就关，所以"连点两行"完全是正常操作：先点甲的解析、再点乙的解析，
   甲那一发晚回来时，抽屉里显示的就是**甲的解析结果**，而用户最后点的是乙。
   同一支函数里还有一处相反的形状：`r.parsed = parsed.parsed` 写的是这一行自己的事实，
   它不因为"用户后来点了别的行"就变成假的，所以这一条**不该**被令牌作废（D29 分的正是这一类）。 */

const api = vi.hoisted(() => ({
  uploadResume: vi.fn(),
  parseResume: vi.fn(),
  getResumeList: vi.fn(),
  getResumeVersions: vi.fn(),
  getResumeQuickScore: vi.fn(),
  diagnoseResume: vi.fn(),
  getRewriteSuggestions: vi.fn(),
  applyResumeRewrites: vi.fn(),
  deleteResume: vi.fn(),
  generateOptimized: vi.fn(),
  exportResume: vi.fn(),
  downloadResumeExport: vi.fn(),
}))

vi.mock('@/api/resume', () => api)

function deferred() {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { resolve, promise }
}

const inflight = []

function hangParse() {
  const record = deferred()
  inflight.push(record)
  return record.promise
}

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const row = (id, name) => ({
  id,
  file_name: name,
  name,
  status: 'ready',
  create_time: '2026-09-01T00:00:00Z',
  parsed: null,
})

const parsed = (who) => ({
  name: who,
  years_exp: 5,
  phone: '13800000000',
  email: `${who}@example.com`,
  education: '本科',
  current_title: '后端工程师',
  skills: ['Python'],
  work_experience: [],
})

let router

async function renderUpload(rows) {
  api.getResumeList.mockResolvedValue({ items: rows, total: rows.length })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/resume/upload', name: 'resume-upload', component: { template: '<div />' } }],
  })
  router.push('/resume/upload')
  await router.isReady()
  const wrapper = mount(ResumeUpload, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  inflight.length = 0
  api.getResumeList.mockResolvedValue({ items: [], total: 0 })
  api.getResumeVersions.mockResolvedValue({ versions: [] })
  api.getResumeQuickScore.mockResolvedValue({ score: 60 })
  api.diagnoseResume.mockResolvedValue({})
  api.getRewriteSuggestions.mockResolvedValue({})
  api.applyResumeRewrites.mockResolvedValue({})
  api.deleteResume.mockResolvedValue({})
  api.generateOptimized.mockResolvedValue({})
  api.exportResume.mockResolvedValue({})
  api.downloadResumeExport.mockResolvedValue(new Blob(['x']))
  api.parseResume.mockImplementation(hangParse)
})

describe('解析抽屉：抽屉里必须是刚点的那一行', () => {
  it('甲的解析晚回来，不能顶掉乙的抽屉内容', async () => {
    const wrapper = await renderUpload([row(1, '简历甲'), row(2, '简历乙')])

    const 甲 = wrapper.vm.resumes.find((r) => r.id === 1)
    const 乙 = wrapper.vm.resumes.find((r) => r.id === 2)

    wrapper.vm.handleCmd('parse', 甲)
    await flushPromises()
    expect(api.parseResume).toHaveBeenCalledTimes(1)

    wrapper.vm.handleCmd('parse', 乙)
    await flushPromises()
    expect(api.parseResume).toHaveBeenCalledTimes(2)
    expect(api.parseResume.mock.calls[1][0]).toBe(2)

    await settle(inflight[1], { parsed: parsed('乙') })
    expect(wrapper.vm.currentParsed.name).toBe('乙')
    expect(wrapper.vm.showParsed).toBe(true)

    await settle(inflight[0], { parsed: parsed('甲') })
    expect(wrapper.vm.currentParsed.name, '抽屉被甲那一份晚回来的结果换掉了').toBe('乙')
    // 但甲那一行自己的解析结果是真的，不该跟着作废
    expect(甲.parsed?.name).toBe('甲')
    wrapper.unmount()
  })

  it('对照组：只点一行时解析照常开抽屉', async () => {
    const wrapper = await renderUpload([row(1, '简历甲')])
    const 甲 = wrapper.vm.resumes[0]

    wrapper.vm.handleCmd('parse', 甲)
    await flushPromises()
    await settle(inflight[0], { parsed: parsed('甲') })

    expect(wrapper.vm.currentParsed.name).toBe('甲')
    expect(wrapper.vm.showParsed).toBe(true)
    expect(甲.parsed.name).toBe('甲')
    wrapper.unmount()
  })
})
