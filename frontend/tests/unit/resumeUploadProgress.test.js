import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick } from 'vue'

import ResumeUpload from '@/features/resume/views/ResumeUpload.vue'
import { installElement } from '@/plugins/element'

/* P5(d)：上传对话框要能看出"上传 → 解析 → 诊断"走到哪一步。
   旧实现里解析阶段进度条停在 100%，解析失败还会显示"上传失败"——两件事都不是视觉问题，
   是候选人不知道该等还是该换文件。 */

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

const parsed = { name: '测试用户', skills: ['Python'], work_experience: [] }

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function renderUpload() {
  api.getResumeList.mockResolvedValue({ items: [], total: 0 })
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
  wrapper.vm.showUpload = true
  await nextTick()
  return wrapper
}

const file = { name: 'resume.pdf', size: 1000 }

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  api.getResumeVersions.mockResolvedValue({ versions: [] })
  api.getResumeQuickScore.mockResolvedValue({ completeness_score: 60 })
  api.diagnoseResume.mockResolvedValue({})
  api.getRewriteSuggestions.mockResolvedValue({})
  api.applyResumeRewrites.mockResolvedValue({})
})

describe('上传 → 解析 → 诊断的进度', () => {
  it('上传阶段显示三步条和百分比，解析阶段不再装作 100%', async () => {
    const wrapper = await renderUpload()
    const upload = deferred()
    const parse = deferred()
    api.uploadResume.mockReturnValue(upload.promise)
    api.parseResume.mockReturnValue(parse.promise)

    const task = wrapper.vm.customUpload({ file })
    await nextTick()

    expect(wrapper.find('.upload-steps').text()).toContain('上传')
    expect(wrapper.find('.upload-steps').text()).toContain('解析')
    expect(wrapper.find('.upload-steps').text()).toContain('诊断')
    expect(wrapper.find('.el-progress').exists()).toBe(true)
    expect(wrapper.find('.progress-text').text()).toContain('正在上传文件')

    upload.resolve({ id: 99 })
    await flushPromises()

    expect(wrapper.vm.uploadStage).toBe('parsing')
    expect(wrapper.find('.el-progress').exists()).toBe(false)
    expect(wrapper.find('.parse-progress').text()).toContain('正在解析简历')
    expect(api.parseResume).toHaveBeenCalledWith(99)

    parse.resolve({ parsed })
    await task
    await flushPromises()

    expect(wrapper.vm.showParsed).toBe(true)
    expect(wrapper.vm.showUpload).toBe(false)
    expect(wrapper.vm.currentParsed.name).toBe('测试用户')

    const diagnoseButton = Array.from(document.querySelectorAll('button')).find((button) =>
      button.textContent.includes('开始 AI 诊断')
    )
    expect(diagnoseButton).toBeTruthy()
    diagnoseButton.click()
    await flushPromises()

    expect(api.diagnoseResume).toHaveBeenCalledWith(99, expect.anything(), expect.anything())
    expect(wrapper.vm.showDiagnosis).toBe(true)
  })

  it('解析炸了说解析失败，不把锅甩给上传', async () => {
    const wrapper = await renderUpload()
    const upload = deferred()
    const parse = deferred()
    api.uploadResume.mockReturnValue(upload.promise)
    api.parseResume.mockReturnValue(parse.promise)

    const task = wrapper.vm.customUpload({ file })
    upload.resolve({ id: 99 })
    await flushPromises()

    parse.reject(new Error('parse down'))
    await task
    await flushPromises()

    expect(wrapper.vm.uploadError).toContain('解析失败')
    expect(wrapper.vm.uploadError).not.toContain('上传失败')
    expect(wrapper.find('.upload-error').text()).toContain('解析失败')
  })

  it('上传炸了仍说上传失败', async () => {
    const wrapper = await renderUpload()
    const upload = deferred()
    api.uploadResume.mockReturnValue(upload.promise)

    const task = wrapper.vm.customUpload({ file })
    upload.reject(new Error('upload down'))
    await task
    await flushPromises()

    expect(wrapper.vm.uploadError).toContain('上传失败')
    expect(wrapper.vm.uploadStage).toBe('error')
  })
})
