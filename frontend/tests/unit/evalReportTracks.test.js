import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import EvalReport from '@/features/eval/views/EvalReport.vue'
import { installElement } from '@/plugins/element'
import { getEvalReportList, getEvalReportSummary } from '@/api/evaluation'

/* 2026-10-16 盘 P2 时照见的既有缺陷：后端 `SUPPORTED_REPORT_TYPES` 有 rag/agent/recommend 三型、
   AI 发布门 `AI_RELEASE_REQUIRED_EVALUATION_TYPES` 也要求 recommend，而这个页面**只列 RAG 与 Agent**
   ——第三轨在页面上根本不存在（"recommend" 在文件里出现 0 次）。
   修法不是再复制两支 v-if，是把类型收成一处 `REPORT_TYPES`；这一组就是钉"四轨都在页面上、
   且 parse 的语义臂没跑时不许显示成 0"。少了这条，下一轨加进来又会静默漏一处分支。 */

vi.mock('@/api/evaluation', () => ({
  getEvalReportSummary: vi.fn(),
  getEvalReportList: vi.fn(),
  getEvalReportDetail: vi.fn(),
  compareEvalReports: vi.fn(),
}))

function row(type, filename, metrics, extra = {}) {
  return {
    report_id: filename,
    filename,
    report_type: type,
    generated_at: '2026-10-16T12:00:00+00:00',
    eval_set: `tests/eval/${type}.jsonl`,
    total: 42,
    thresholds: {},
    metrics,
    ...extra,
  }
}

const SUMMARY = {
  counts: { rag: 1, agent: 1, recommend: 1, parse: 2 },
  latest_by_type: {
    rag: row('rag', 'rag_eval_a.json', { recall: 0.9, mrr: 0.8, keyword_hit_rate: 0.7 }),
    agent: row('agent', 'agent_eval_a.json', { mae: 6, spearman_rho: 0.9, hit_tol10: 20 }),
    recommend: row('recommend', 'recommend_eval_a.json', {
      skill_match_accuracy: 1,
      jd_explanation_consistency: 1,
      recommendation_explainability: 0.8,
    }),
    parse: row('parse', 'parse_eval_b.json', {
      truncated_rate: 0.0476,
      tail_keep_rate: 1,
      first_pass_rate: 0.9,
      skills_f1: 0.7467,
    }),
  },
}

async function renderPage(summary = SUMMARY, list = Object.values(SUMMARY.latest_by_type)) {
  getEvalReportSummary.mockResolvedValue({ ...summary })
  getEvalReportList.mockResolvedValue({ items: list, total: list.length })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/eval-reports', name: 'eval-reports', component: EvalReport }],
  })
  await router.push('/eval-reports')
  await router.isReady()
  const wrapper = mount(EvalReport, {
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('评测报表页认得全部四轨', () => {
  it('四张汇总卡都在，含以前根本不存在的 Recommend', async () => {
    const wrapper = await renderPage()
    const text = wrapper.text()
    for (const label of [
      '最新 RAG 评测',
      '最新 Agent 评测',
      '最新 Recommend 评测',
      '最新 Parse 评测',
    ]) {
      expect(text).toContain(label)
    }
  })

  it('两个类型下拉的选项来自同一张表，不是写死两支', async () => {
    const wrapper = await renderPage()
    const values = wrapper.findAllComponents({ name: 'ElOption' }).map((o) => o.props('value'))
    for (const key of ['rag', 'agent', 'recommend', 'parse']) {
      // 每个类型键至少在两个"类型下拉"里各出现一次；页面别处还有选报告的下拉，所以不数总数。
      expect(values.filter((v) => v === key).length).toBeGreaterThanOrEqual(2)
    }
    expect(values).toContain('') // 筛选下拉的"全部类型"
  })

  it('parse 那一行的核心指标用的是它自己的指标名，不是落到 Agent 的 else 分支', async () => {
    const wrapper = await renderPage()
    const parseRow = wrapper
      .findAll('.el-table__row')
      .find((r) => r.text().includes('parse_eval_b.json'))
    expect(parseRow).toBeTruthy()
    expect(parseRow.text()).toContain('段尾保全')
    expect(parseRow.text()).not.toContain('MAE')
  })

  it('语义臂没跑的那次要写成"未跑"，不许显示成 0', async () => {
    const mockOnly = row('parse', 'parse_eval_a.json', {
      truncated_rate: 0.0476,
      tail_keep_rate: 1,
      first_pass_rate: null,
      skills_f1: null,
    })
    const summary = {
      counts: SUMMARY.counts,
      latest_by_type: { ...SUMMARY.latest_by_type, parse: mockOnly },
    }
    const wrapper = await renderPage(summary)
    expect(wrapper.text()).toContain('语义臂未跑')
    const text = wrapper.text()
    expect(text).not.toMatch(/首发过校验\s*0(\.0+)?%/)
  })

  it('四轨全无报告时，每张卡各自说"暂无"，不是一片空白', async () => {
    const wrapper = await renderPage({ counts: {}, latest_by_type: {} }, [])
    expect(wrapper.text()).toContain('最新 Parse 评测')
    expect(wrapper.text()).toContain('暂无 Parse 报告')
    expect(wrapper.text()).toContain('暂无 Recommend 报告')
  })
})
