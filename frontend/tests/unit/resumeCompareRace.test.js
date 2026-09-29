import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ResumeCompare from '@/features/resume/views/ResumeCompare.vue'
import { installElement } from '@/plugins/element'

/* 简历工作台这页有 3 个"响应落地直接写业务 ref、且用户能把它叠成两个在途"的函数：
   - loadDiff：版本选择器与基准选择器都直接触发它，两个选择器都没有 loading；
   - loadWorkspace：挂在 AI 优化 / 保存 / 定制 三个动作的尾巴上，而这三个按钮各自只锁自己的
     loading 位——优化仍在途时"保存修改"是可点的，于是两次工作台重取交叠；
   - setSuggestionDecision：每条建议的采纳/忽略按钮都没有 disabled，两次 POST 的响应各自带着
     整份 decision 映射，后落地的会把另一条建议刚打上的标记冲回去。
   证否的那两个（loadJobs 只被 onMounted 与自隐藏的 @retry 触发；onPreviewAts / onExport 只有
   一个入口且入口带 :loading）写在 D29 的账上，不在这里装。 */

const api = vi.hoisted(() => ({
  jd: { getJDList: vi.fn() },
  targets: { recommendPipelineResumeVersion: vi.fn() },
  resume: {
    createResumeVersion: vi.fn(),
    downloadResumeExport: vi.fn(),
    generateOptimized: vi.fn(),
    getResumeVersionDiff: vi.fn(),
    getResumeVersions: vi.fn(),
    previewResumeAts: vi.fn(),
    saveResumeSuggestionDecision: vi.fn(),
    tailorResume: vi.fn(),
    updateResumeVersion: vi.fn(),
  },
}))

vi.mock('@/api/jd', () => api.jd)
vi.mock('@/api/targets', () => api.targets)
vi.mock('@/api/resume', () => api.resume)

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { resolve, reject, promise }
}

const inflight = {}

function hang(group, name) {
  inflight[name] = []
  api[group][name] = vi.fn((...args) => {
    const record = { args, ...deferred() }
    inflight[name].push(record)
    return record.promise
  })
}

const lastOf = (name) => [...inflight[name]].pop()
const firstOf = (name) => inflight[name][0]
const countOf = (name) => inflight[name].length

async function settle(record, value) {
  record.resolve(value)
  await flushPromises()
}

const version = (id, content, changeLog = []) => ({
  id,
  label: `版本 ${id}`,
  content,
  format: 'md',
  version_type: 'ai',
  created_at: '2026-09-02T00:00:00Z',
  change_log: changeLog,
  suggestion_decisions: {},
  target_jd_id: null,
  ats_snapshot: null,
})

const workspace = (versions, originalContent = '原始内容') => ({
  original: { content: originalContent, created_at: '2026-09-01T00:00:00Z' },
  versions,
})

const diff = (added) => ({
  summary: { added_lines: added, removed_lines: 0, unchanged_lines: 4 },
  lines: [{ type: 'added', content: `新增行 ${added}` }],
})

let router

async function renderWorkspace(snapshot) {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/resume/:id', name: 'resume-compare', component: { template: '<div />' } }],
  })
  router.push('/resume/7')
  await router.isReady()
  const wrapper = mount(ResumeCompare, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await settle(lastOf('getResumeVersions'), snapshot)
  await flushPromises()
  return wrapper
}

function pick(wrapper, selector, value) {
  const select = wrapper.findComponent(selector)
  expect(select, `${selector} 没渲染出来，测试前提不成立`).toBeTruthy()
  select.vm.$emit('update:modelValue', value)
  select.vm.$emit('change', value)
  return flushPromises()
}

function buttonByText(wrapper, text) {
  const found = wrapper.findAll('button').find((b) => b.text().includes(text))
  expect(found, `找不到文案含「${text}」的按钮，测试前提不成立`).toBeTruthy()
  return found
}

function addedLines() {
  const el = document.querySelector('.diff-summary .added')
  return el ? el.textContent.trim() : null
}

function editorValue() {
  const el = document.querySelector('.resume-editor textarea')
  return el ? el.value : null
}

function suggestionButton(label) {
  const el = document.querySelector(`button[aria-label="${label}"]`)
  expect(el, `找不到「${label}」按钮，测试前提不成立`).toBeTruthy()
  return el
}

function clickByAria(label) {
  suggestionButton(label).click()
  return flushPromises()
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  for (const key of Object.keys(inflight)) delete inflight[key]

  api.jd.getJDList.mockResolvedValue({ items: [] })
  api.resume.createResumeVersion.mockResolvedValue({ id: 11 })
  api.resume.previewResumeAts.mockResolvedValue({ score: 80 })
  api.resume.downloadResumeExport.mockResolvedValue(new Blob(['x']))
  api.targets.recommendPipelineResumeVersion.mockResolvedValue({ recommended: null })

  hang('resume', 'getResumeVersions')
  hang('resume', 'getResumeVersionDiff')
  hang('resume', 'generateOptimized')
  hang('resume', 'updateResumeVersion')
  hang('resume', 'saveResumeSuggestionDecision')
})

describe('简历工作台：后发起的那一次必须赢，而不是后完成的那一次', () => {
  it('换基准版本时，旧基准的差异不能盖掉新基准的', async () => {
    const wrapper = await renderWorkspace(workspace([version(11, '甲内容'), version(12, '乙内容')]))
    await pick(wrapper, '.version-select', 11)
    const first = lastOf('getResumeVersionDiff')
    expect(first, '选版本没触发差异请求，测试前提不成立').toBeTruthy()
    expect(first.args[2], '初始基准应是原始简历').toBe(null)

    await pick(wrapper, '.baseline-select', 12)
    const second = lastOf('getResumeVersionDiff')
    expect(second).not.toBe(first)
    expect(second.args[2]).toBe(12)

    await settle(second, diff(7))
    expect(addedLines()).toBe('+7')

    await settle(first, diff(3))
    expect(addedLines(), '旧基准的差异结果回到了屏幕上').toBe('+7')
    wrapper.unmount()
  })

  it('AI 优化的工作台重取还在途时，保存的那一次不能被它顶回去', async () => {
    const wrapper = await renderWorkspace(workspace([version(11, '甲内容'), version(12, '乙内容')]))
    await pick(wrapper, '.version-select', 11)
    await settle(lastOf('getResumeVersionDiff'), diff(1))

    await buttonByText(wrapper, 'AI 优化').trigger('click')
    await settle(lastOf('generateOptimized'), { version_id: 12 })
    const optimizing = lastOf('getResumeVersions')
    expect(optimizing, '优化没有在重取工作台，测试前提不成立').toBeTruthy()

    // 真实动作：优化按钮锁的是它自己的 loading，"保存修改"在此期间可点
    await buttonByText(wrapper, '保存修改').trigger('click')
    await settle(lastOf('updateResumeVersion'), { id: 11 })
    const saving = lastOf('getResumeVersions')
    expect(saving).not.toBe(optimizing)

    await settle(saving, workspace([version(11, '保存后的内容'), version(12, '乙内容')]))
    expect(editorValue()).toBe('保存后的内容')

    await settle(optimizing, workspace([version(11, '保存后的内容'), version(12, '优化版内容')]))
    expect(editorValue(), '编辑器内容被旧那一轮的工作台快照换掉了').toBe('保存后的内容')
    expect(wrapper.findComponent('.version-select').props('modelValue')).toBe(11)
    wrapper.unmount()
  })

  it('两条建议的采纳/忽略不能互相冲掉：前一次没落地时后一次不许发出去', async () => {
    const log = [
      { section: 'A', reason: '理由一' },
      { section: 'B', reason: '理由二' },
    ]
    const wrapper = await renderWorkspace(workspace([version(11, '甲内容', log)]))
    await pick(wrapper, '.version-select', 11)
    await settle(lastOf('getResumeVersionDiff'), diff(1))

    await clickByAria('采纳建议 1')
    const first = lastOf('saveResumeSuggestionDecision')
    expect(first, '点采纳没发请求，测试前提不成立').toBeTruthy()

    // 真实动作：这两个圆圈按钮今天没有任何 disabled，第一条还没落地就能点第二条
    expect(
      suggestionButton('忽略建议 2').disabled,
      '上一条决定还没落地，这条建议的操作按钮就应该锁住'
    ).toBe(true)

    await settle(first, { id: 11, suggestion_decisions: { 0: 'accepted' } })
    expect(suggestionButton('采纳建议 1').className).toContain('el-button--success')

    await clickByAria('忽略建议 2')
    await settle(lastOf('saveResumeSuggestionDecision'), {
      id: 11,
      suggestion_decisions: { 0: 'accepted', 1: 'ignored' },
    })
    expect(countOf('saveResumeSuggestionDecision')).toBe(2)
    expect(suggestionButton('忽略建议 2').className).toContain('el-button--info')
    expect(suggestionButton('采纳建议 1').className).toContain('el-button--success')
    wrapper.unmount()
  })
})

describe('对照组：单次触发必须照常写入', () => {
  it('只换一次基准时差异照常出来', async () => {
    const wrapper = await renderWorkspace(workspace([version(11, '甲内容'), version(12, '乙内容')]))
    await pick(wrapper, '.version-select', 11)
    await settle(lastOf('getResumeVersionDiff'), diff(5))

    expect(addedLines()).toBe('+5')
    wrapper.unmount()
  })

  it('没有被顶掉的保存流程照常把新内容放回编辑器', async () => {
    const wrapper = await renderWorkspace(workspace([version(11, '甲内容')]))
    await pick(wrapper, '.version-select', 11)
    await settle(lastOf('getResumeVersionDiff'), diff(1))

    await buttonByText(wrapper, '保存修改').trigger('click')
    await settle(lastOf('updateResumeVersion'), { id: 11 })
    await settle(lastOf('getResumeVersions'), workspace([version(11, '保存后的内容')]))

    expect(editorValue()).toBe('保存后的内容')
    wrapper.unmount()
  })

  it('一条建议顺序点两次（先采纳后忽略）时第二次照常生效', async () => {
    const log = [{ section: 'A', reason: '理由一' }]
    const wrapper = await renderWorkspace(workspace([version(11, '甲内容', log)]))
    await pick(wrapper, '.version-select', 11)
    await settle(lastOf('getResumeVersionDiff'), diff(1))

    await clickByAria('采纳建议 1')
    await settle(firstOf('saveResumeSuggestionDecision'), {
      id: 11,
      suggestion_decisions: { 0: 'accepted' },
    })
    await clickByAria('忽略建议 1')
    await settle(lastOf('saveResumeSuggestionDecision'), {
      id: 11,
      suggestion_decisions: { 0: 'ignored' },
    })

    expect(countOf('saveResumeSuggestionDecision')).toBe(2)
    expect(suggestionButton('忽略建议 1').className).toContain('el-button--info')
    wrapper.unmount()
  })
})
