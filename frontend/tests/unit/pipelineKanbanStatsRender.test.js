import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import PipelineKanban from '@/features/pipeline/views/PipelineKanban.vue'
import { installElement } from '@/plugins/element'

/* D57 把看板的统计与跟进判据搬进 `lib/pipelineBoard.js` 之后，页面上剩下一层薄包装
   （`conversionRate(stage)` → 把 `counts` 与 `totalCards` 递进去）。**包装传错参数是不报错的**：
   分母换成别的列、把 `kanban.value.interview` 当成 `applied` 传进去，屏幕只会显示一个别的数字。
   所以这里钉的是屏幕上那五个数字与顶部那句话，而不是 lib 的返回值（lib 那层由
   pipelineBoardMoveProof.test.js 逐条钉死）。
   时间相关的夹具用"距今 N 天"的小数天：3.2 天与 9.4 天在几小时内都不会跨过 3/7 的门槛，
   所以断言既确定又不会因跑在什么时候而抖。 */

const DAY = 86400000
const ago = (days) => new Date(Date.now() - days * DAY).toISOString()

const api = vi.hoisted(() => ({
  getKanban: vi.fn(),
  movePipelineStage: vi.fn(),
  createJobPipelineEntry: vi.fn(),
  deleteJobPipelineEntry: vi.fn(),
  getPipelineResumeVersions: vi.fn(),
  getPipelineResumeVersionStats: vi.fn(),
  updateJobPipelineEntry: vi.fn(),
}))

vi.mock('@/api/targets', () => api)
vi.mock('@/plugins/element-services', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve('confirm')) },
}))

const card = (id, stage, days) => ({
  id,
  title: `投递-${id}`,
  company: '某公司',
  stage,
  status: 'active',
  jd_id: null,
  create_time: '2026-01-01T00:00:00Z',
  ...(days === undefined ? {} : { update_time: ago(days) }),
})

function settled(promiseLike) {
  return promiseLike
}

async function renderKanban(stages) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/pipeline', name: 'pipeline', component: { template: '<div />' } }],
  })
  router.push('/pipeline')
  await router.isReady()
  api.getKanban.mockResolvedValue(settled({ stages }))
  api.getPipelineResumeVersions.mockResolvedValue(settled({ items: [] }))
  api.getPipelineResumeVersionStats.mockResolvedValue(settled({ items: [] }))
  const wrapper = mount(PipelineKanban, {
    attachTo: document.body,
    global: { plugins: [installElement, createPinia(), router] },
  })
  await flushPromises()
  return wrapper
}

function statValues(wrapper) {
  return wrapper.findAll('.stat-value').map((n) => n.text().trim())
}

/** 转化分析那块默认收着（`showStats` 起初是 false），点页眉那颗「查看统计」才展开。 */
async function openStats(wrapper) {
  const toggle = wrapper.findAll('button').find((b) => /查看统计|隐藏统计/.test(b.text()))
  expect(toggle, '页眉上没有「查看统计」按钮，测试前提不成立').toBeTruthy()
  await toggle.trigger('click')
  await flushPromises()
}

describe('看板上的统计数字来自 lib 的那几条判据', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('转化率、拒绝率与平均响应天数各是屏幕上那几个数', async () => {
    const wrapper = await renderKanban({
      todo: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }],
      applied: [card(5, 'applied', 3.2), card(6, 'applied', 9.4), card(7, 'applied')],
      written_test: [],
      interview: [{ id: 8 }, { id: 9 }],
      offer: [{ id: 10 }],
      accepted: [],
      rejected: [{ id: 11 }, { id: 12 }, { id: 13 }, { id: 14 }, { id: 15 }],
      withdrawn: [{ id: 16 }],
    })
    /* 六个格子：总投递 16；转化率分母是"经过本段之前 + 本段"——applied 3/7=43、
       interview 2/9=22、offer 1/10=10；拒绝率 (5+1)/16=38；
       平均响应只数有 update_time 的两张卡：(3+9)/2=6 天（第三张没有更新时间，不进来）。 */
    await openStats(wrapper)
    expect(statValues(wrapper)).toEqual(['16', '43%', '22%', '10%', '38%', '6d'])
  })

  it('顶部那句"现在该干什么"跟"等待跟进的条数"用同一批判据', async () => {
    const wrapper = await renderKanban({
      todo: [{ id: 1 }],
      applied: [card(2, 'applied', 3.2), card(3, 'applied', 1.1), card(4, 'applied', 7.5)],
      written_test: [card(5, 'written_test', 4.2)],
      interview: [],
      offer: [],
      rejected: [],
      withdrawn: [],
    })
    // 没有 offer、没有面试，但有 3 条等满 3 天的（3.2 / 7.5 / 4.2 天），1.1 天那条不算
    expect(wrapper.text()).toContain('有投递记录等待跟进，先处理超 3 天未回复的机会。')
    // 三个格子：待跟进 3、面试进行中 0、待决 Offer 0
    expect(wrapper.findAll('.focus-metrics b').map((n) => n.text())).toEqual(['3', '0', '0'])
    await openStats(wrapper)
    expect(statValues(wrapper)).toEqual(['5', '75%', '0%', '0%', '0%', '4d'])
  })

  it('转化分析默认收着：不点「查看统计」，面板整块都不在 DOM 里', async () => {
    /* D62 之后这块归 `showStats` 挡（面板自己的条件是 totalCards>0）。这条钉的是页面上
       那一句 `v-if="showStats"`：把它改成恒真，下面两条 expect 都会红（实测 P5）。 */
    const wrapper = await renderKanban({ applied: [{ id: 1 }], interview: [{ id: 2 }] })
    expect(wrapper.find('.stats-panel').exists()).toBe(false)
    expect(wrapper.find('.version-performance').exists()).toBe(false)
  })

  it('一张卡都没有时不除零：全是 0，天数说没有', async () => {
    const wrapper = await renderKanban({})
    // 一张卡都没有：整条"本周重点"与转化分析都不渲染（后者还要 showStats，但 totalCards=0 就够挡）
    expect(wrapper.find('.pipeline-focus-strip').exists()).toBe(false)
    await openStats(wrapper)
    expect(wrapper.find('.stats-panel').exists()).toBe(false)
    expect(statValues(wrapper)).toEqual([])
  })
})
