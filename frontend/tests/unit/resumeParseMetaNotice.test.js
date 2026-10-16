import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeUpload from '@/features/resume/views/ResumeUpload.vue'
import { installElement } from '@/plugins/element'

/* `简历与面试优化.md` §4 P1.1 修法表里那两行候选人可见提示。他 2026-10-16 特批这两条**可以**上屏，
   理由是那说的是"用户自己上传的文件超了预算"，不是"AI 这次降级了"——与 A2 那条对候选人静默的决策不同族，
   特批只到这一处。
   这一族最容易静默失效的地方在**接线**：后端 `_meta` 落库了、前端取数路径写错一个键名，页面只是少画一行字，
   既不报错也不红。所以下面三条都断**屏上出现的句子**，不是断 vm 上的判据函数。 */

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

const baseParsed = {
  name: '测试用户',
  years_exp: 5,
  phone: '13800000000',
  email: 'guard@example.com',
  education: '硕士',
  current_title: '高级后端工程师',
  skills: ['Python'],
  work_experience: [],
}

const row = (id, parsed) => ({
  id,
  name: `简历${id}`,
  file_name: `resume-${id}.pdf`,
  file_type: 'pdf',
  file_size: 4096,
  status: 'ready',
  create_time: '2026-10-16T00:00:00Z',
  parsed,
})

async function renderUpload(rows) {
  api.getResumeList.mockResolvedValue({ items: rows, total: rows.length })
  const router = createRouter({
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
  api.getResumeVersions.mockResolvedValue({ versions: [] })
  api.getResumeQuickScore.mockResolvedValue({ score: 60 })
  api.diagnoseResume.mockResolvedValue({})
  api.getRewriteSuggestions.mockResolvedValue({})
  api.applyResumeRewrites.mockResolvedValue({})
  api.deleteResume.mockResolvedValue({})
  api.generateOptimized.mockResolvedValue({})
  api.exportResume.mockResolvedValue({})
  api.downloadResumeExport.mockResolvedValue({})
  api.parseResume.mockResolvedValue({ parsed: baseParsed })
})

describe('解析丢弃段落那一行', () => {
  it('后端说丢了，卡片就报出丢了几段、丢的是哪几段', async () => {
    const wrapper = await renderUpload([
      row(1, {
        ...baseParsed,
        _meta: {
          truncation: {
            truncated: true,
            dropped_chars: 4120,
            dropped_sections: ['技能', '教育'],
          },
        },
      }),
    ])

    expect(wrapper.text()).toContain('解析丢弃了 2 个低优先级段落')
    expect(wrapper.text()).toContain('技能、教育')
  })

  it('truncated 为假时不画这一行', async () => {
    const wrapper = await renderUpload([
      row(2, {
        ...baseParsed,
        _meta: { truncation: { truncated: false, dropped_chars: 0, dropped_sections: [] } },
      }),
    ])

    expect(wrapper.text()).not.toContain('解析丢弃')
  })
})

describe('解析不完整那条黄条', () => {
  it('落库带 parse_degraded 时，卡片上出现那句人话', async () => {
    const wrapper = await renderUpload([
      row(3, {
        ...baseParsed,
        _meta: {
          parse_degraded: true,
          validation_errors: ['skills: Missing data for required field'],
        },
      }),
    ])

    expect(wrapper.text()).toContain('解析不完整，建议检查原文格式')
    expect(wrapper.find('.el-alert').exists()).toBe(true)
  })

  it('只有截断、没有降级时，不该出现黄条那句', async () => {
    const wrapper = await renderUpload([
      row(4, {
        ...baseParsed,
        _meta: { truncation: { truncated: true, dropped_chars: 90, dropped_sections: ['其他'] } },
      }),
    ])

    expect(wrapper.text()).toContain('解析丢弃了 1 个低优先级段落')
    expect(wrapper.text()).not.toContain('解析不完整')
  })

  it('一次就合规的解析：两句都不出现', async () => {
    const wrapper = await renderUpload([row(5, { ...baseParsed })])

    expect(wrapper.text()).not.toContain('解析丢弃')
    expect(wrapper.text()).not.toContain('解析不完整')
  })

  it('老行根本没有 _meta 这个键时不报错、也不画提示', async () => {
    // 库里 25 份已落解析结果全都没有 `_meta`（那是这一轮才加上的），
    // 取数路径必须对"整个键不存在"成立，否则列表页整片白屏。
    const wrapper = await renderUpload([row(6, baseParsed), row(7, null)])

    expect(wrapper.text()).not.toContain('解析丢弃')
    expect(wrapper.text()).not.toContain('解析不完整')
    expect(wrapper.findAll('.resume-card').length).toBe(2)
  })
})
