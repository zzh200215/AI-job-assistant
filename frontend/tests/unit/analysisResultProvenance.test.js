/**
 * 结果页那句"底账"（D14）：这次分析是几发模型调用换来的、其中几发没成功。
 *
 * 起因是 2026-11-14 真 provider 实测：7 发里 4 发 429、分数只来自规则臂，而屏幕上写着
 * "分析完成，匹配度 57"。后端现在按 `prompt_trace` 汇总成 `provenance`，这里只决定怎么说话。
 *
 * 两条边界：
 * 1. 干净的一发不显示——正常分析不该挂一句免责声明；
 * 2. 没有 `provenance`（老记录、非编排路径）也不显示，但**不许把它当成"一切正常"**：
 *    那是"查不到"，不是"没问题"。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import AnalysisResult from '@/features/analysis/views/AnalysisResult.vue'
import { installElement } from '@/plugins/element'

const state = vi.hoisted(() => ({ provenance: null }))

vi.mock('@/api/analysis', () => ({
  getAnalysis: vi.fn(async () => ({
    id: 85,
    match_score: 57,
    match_report: { summary: '可以试试' },
    provenance: state.provenance,
  })),
  regenOptimize: vi.fn(async () => ({})),
  regenInterview: vi.fn(async () => ({})),
  getAnalysisReferences: vi.fn(async () => ({ references: [] })),
}))

vi.mock('@/api/agent', () => ({
  startAgentAnalysis: vi.fn(async () => ({ task_id: 't1' })),
  getAgentTask: vi.fn(async () => ({ status: 'running' })),
  getAgentSteps: vi.fn(async () => ({ steps: [] })),
}))

vi.mock('@/api/resume', () => ({
  getResume: vi.fn(async () => ({ id: 7, parsed: {} })),
  getResumeList: vi.fn(async () => ({ items: [] })),
  generateOptimized: vi.fn(async () => ({})),
}))

vi.mock('@/api/jd', () => ({
  getJD: vi.fn(async () => ({ id: 3 })),
  getJDList: vi.fn(async () => ({ items: [] })),
}))

async function renderRecord() {
  const route = {
    path: '/analysis/:id',
    name: 'analysis-detail',
    component: { template: '<div />' },
  }
  const router = createRouter({ history: createMemoryHistory(), routes: [route] })
  await router.push('/analysis/85')
  await router.isReady()
  mount(AnalysisResult, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
}

const text = () => document.body.textContent.replace(/\s+/g, ' ')

beforeEach(() => {
  document.body.innerHTML = ''
  state.provenance = null
})

describe('结果页的模型调用底账', () => {
  it('有失败/降级时，如实写出几发、谁答的、几发没成功', async () => {
    state.provenance = {
      task_id: 109,
      task_status: 'completed',
      calls: 7,
      by_source: { real: 1, fallback_model: 1, unknown: 5 },
      failed: 4,
      degraded: 6,
    }
    await renderRecord()

    expect(text()).toContain('本次分析共 7 发模型调用')
    expect(text()).toContain('4 发没成功')
    expect(text()).toContain('由兜底规则补出')
  })

  it('干净的一发不挂免责声明', async () => {
    state.provenance = {
      task_id: 109,
      task_status: 'completed',
      calls: 3,
      by_source: { real: 3 },
      failed: 0,
      degraded: 0,
    }
    await renderRecord()

    expect(text()).not.toContain('本次分析共')
  })

  it('没有底账（老记录）时也不说话，而不是说"一切正常"', async () => {
    state.provenance = null
    await renderRecord()

    expect(text()).not.toContain('本次分析共')
    expect(text()).toContain('57') // 分数照常显示
  })
})
