import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElDropdown, ElTable } from 'element-plus'

import ListPane from '@/features/pipeline/components/ListPane.vue'
import { installElement } from '@/plugins/element'

/* D64 把列表视图（批量栏 + 那张 11 列的表）搬进 components/ListPane.vue。归属和 D63 的看板列
   同一条判据：数据、写与锁留在页面，面板只画 + 发事件。

   一条纠正值得记着：我第一版探针在 mount 之后**没有 flush** 就读 DOM，看到
   `.el-table__body tr` 的 textContent 是空的，于是写下"jsdom 里 el-table 画不出格子"。
   加上 `await flushPromises()` 之后每行每一格都在（阶段标签、跟进那颗、匹配度、日期）。
   所以那不是环境的洞，是我读得太早——下面的行内断言因此是真钉东西，不是退而求其次。 */

vi.mock('@/plugins/element-services', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve('confirm')) },
}))

const DAY = 86400000
const NOW = Date.now()
const ago = (days, base = NOW) => new Date(base - days * DAY).toISOString()

const ROWS = [
  {
    id: 1,
    title: '岗位一',
    company: 'A',
    stage: 'applied',
    match_score: 82.6,
    update_time: ago(3.2),
    resume_version_label: 'Go 版',
    source: 'Boss直聘',
    create_time: '2026-09-01T08:00:00Z',
    jd_id: 11,
  },
  {
    id: 2,
    title: '岗位二',
    company: 'B',
    stage: 'interview',
    interview_at: '2026-10-09T10:00:00Z',
    create_time: '2026-09-02T08:00:00Z',
    jd_id: 12,
  },
]

function renderPane(extra = {}) {
  return mount(ListPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: { rows: ROWS, selectedCount: 0, writeBusy: false, now: NOW, ...extra },
  })
}

function batchButtons() {
  return [...document.querySelectorAll('.batch-bar button')]
}

function buttonIn(bar, label) {
  return bar.find((b) => b.textContent.includes(label))
}

function rowText(index) {
  return document.querySelectorAll('.el-table__body tr')[index]?.textContent?.trim() ?? null
}

function cellsBy(selector) {
  return [...document.querySelectorAll(selector)].map((n) => [n.className, n.textContent.trim()])
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('列表面板：行里的每一格', () => {
  it('阶段标签、跟进那颗、匹配度取整、未记录占位、面试时间，一格一格对', async () => {
    const wrapper = renderPane()
    await flushPromises()
    // props('data') 拿到的是响应式包装后的副本，所以按内容比而不按同一性
    expect(wrapper.findComponent(ElTable).props('data')).toEqual(ROWS)

    expect(rowText(0)).toContain('岗位一')
    expect(rowText(0)).toContain('已投递')
    expect(rowText(0)).toContain('3天')
    expect(rowText(0)).toContain('83分') // 82.6 → 取整
    expect(rowText(0)).toContain('Go 版')
    expect(rowText(1)).toContain('面试')
    expect(rowText(1)).toContain('未记录') // 第二张卡没有 resume_version_label
    expect(rowText(1)).toContain('10月9日 18:00')

    expect(cellsBy('[class*="follow-"]')).toContainEqual(['follow-warn', '3天'])
    // 匹配度那一格走 scoreToneClass：同一个分数在页面上只能有一个色档
    expect(cellsBy('[class*="score-level"]')).toEqual([['score-level score-level--good', '83分']])
  })

  it('`now` 只动跟进那一颗：推后 7 天，它换数换色，其余格子照旧', async () => {
    const before = renderPane()
    await flushPromises()
    const text0 = rowText(0)
    expect(document.querySelector('[class*="follow-"]').className).toContain('follow-warn')
    before.unmount()
    document.body.innerHTML = ''

    renderPane({ now: NOW + 7 * DAY })
    await flushPromises()
    // 3.2 + 7 = 10.2 天 → 跨过 7 天的门槛：warn 变 danger，数字换成 10
    expect(document.querySelector('[class*="follow-"]').className).toContain('follow-danger')
    expect(rowText(0)).toContain('10天')
    expect(rowText(0)).not.toBe(text0)
    expect(rowText(0)).toContain('已投递')
    expect(rowText(0)).toContain('83分')
    expect(rowText(0)).toContain('Go 版')
  })

  it('行内那颗下拉把命令与这一行一起发出去', async () => {
    const wrapper = renderPane()
    await flushPromises()
    const dropdowns = wrapper.findAllComponents(ElDropdown)
    expect(dropdowns).toHaveLength(2) // 两张卡各一个
    dropdowns[1].vm.$emit('command', 'reject')
    await flushPromises()
    const emitted = wrapper.emitted('command')
    expect(emitted).toHaveLength(1)
    expect(emitted[0][0]).toBe('reject')
    expect(emitted[0][1].id).toBe(2)
  })

  it('「详情」与「AI」两颗按钮也走同一条 command 出口（少了一条平行通道）', async () => {
    /* 搬之前这两颗是绕开 D58 那份分发器的：一个直接调 openCardDetail、一个直接 router.push。
       现在它们和下拉共用同一个 `command`，页面那头进的还是同一个 runCardCommand。
       AI 那条的 URL 形状没动（'/smart-analysis?jd_id=' + (row.jd_id || '')）。 */
    const wrapper = renderPane()
    await flushPromises()
    const row0 = document.querySelectorAll('.el-table__body tr')[0]
    buttonIn([...row0.querySelectorAll('button')], '详情').click()
    buttonIn([...row0.querySelectorAll('button')], 'AI').click()
    await flushPromises()
    expect(wrapper.emitted('command').map((e) => [e[0], e[1].id])).toEqual([
      ['detail', 1],
      ['analyze', 1],
    ])
  })
})

describe('列表面板：批量栏与三条出口', () => {
  it('没勾选就没有批量栏；勾了才出现，并说清是几项', async () => {
    const closed = renderPane()
    await flushPromises()
    expect(closed.find('.batch-bar').exists()).toBe(false)
    closed.unmount()
    document.body.innerHTML = ''

    renderPane({ selectedCount: 2 })
    await flushPromises()
    expect(document.querySelector('.batch-info').textContent.replace(/\s+/g, '')).toBe('已选2项')
    expect(batchButtons().map((b) => b.textContent.trim())).toEqual([
      '批量移至面试',
      '批量移至Offer',
      '批量标记拒绝',
      '取消选择',
    ])
  })

  it('三颗批量按钮各发自己那个阶段，取消选择另发一条', async () => {
    const wrapper = renderPane({ selectedCount: 1 })
    await flushPromises()
    buttonIn(batchButtons(), '批量移至面试').click()
    buttonIn(batchButtons(), '批量移至Offer').click()
    buttonIn(batchButtons(), '批量标记拒绝').click()
    buttonIn(batchButtons(), '取消选择').click()
    await flushPromises()
    expect(wrapper.emitted('batch-move')).toEqual([['interview'], ['offer'], ['rejected']])
    expect(wrapper.emitted('clear-selection')).toHaveLength(1)
  })

  it('writeBusy 时三颗批量按钮既禁用、点了也不发（D59 那把锁穿过 props）', async () => {
    const wrapper = renderPane({ selectedCount: 1, writeBusy: true })
    await flushPromises()
    expect(
      batchButtons()
        .slice(0, 3)
        .map((b) => b.disabled)
    ).toEqual([true, true, true])
    buttonIn(batchButtons(), '批量移至面试').click()
    await flushPromises()
    expect(wrapper.emitted('batch-move')).toBeUndefined()
  })

  it('表格的勾选原样转发给页面（页面才去做 id 集合）', async () => {
    const wrapper = renderPane()
    await flushPromises()
    wrapper.findComponent(ElTable).vm.$emit('selection-change', [ROWS[1]])
    await flushPromises()
    const emitted = wrapper.emitted('selection-change')
    expect(emitted).toHaveLength(1)
    expect(emitted[0][0].map((r) => r.id)).toEqual([2])
  })
})
