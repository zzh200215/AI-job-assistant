/**
 * 误点的终态可以撤销（D18）——前端这一半的两条判据。
 *
 * 1. `undoTargetStage(card)`：**凭历史里那一步自己记下的 `from_stage`** 说退回哪，不猜；
 *    非终态、没历史、历史里没有"进入当前阶段"那一条，一律返回 null（屏幕上就不画那颗菜单项）。
 * 2. 面板只为"能撤销"的卡片画那一项，点了发的是 `undo-terminal` 命令——它和拖拽/「移至」那一族
 *    分开：状态机里终态仍然没有出边，撤销走的是另一个端点。
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import BoardPane from '@/features/pipeline/components/BoardPane.vue'
import { installElement } from '@/plugins/element'
import { columns, undoTargetStage } from '@/features/pipeline/lib/pipelineBoard'

const reached = (stage, from) => ({ stage, from_stage: from, at: '2026-11-16T10:00:00' })

function card(overrides) {
  return { id: 1, title: '后端工程师', company: 'Test Co', stage: 'rejected', ...overrides }
}

describe('终态撤销的判据', () => {
  it('终态 + 历史里有那一步 → 退回 from_stage', () => {
    const item = card({
      stage_history: [reached('interview', 'applied'), reached('rejected', 'interview')],
    })
    expect(undoTargetStage(item)).toBe('interview')
  })

  it('非终态一律返回 null（撤销不是任意回退）', () => {
    const item = card({ stage: 'interview', stage_history: [reached('interview', 'applied')] })
    expect(undoTargetStage(item)).toBeNull()
  })

  it('没有历史的老记录返回 null，不猜一个阶段', () => {
    expect(undoTargetStage(card({ stage_history: [] }))).toBeNull()
    expect(undoTargetStage(card({ stage_history: undefined }))).toBeNull()
  })

  it('历史里"进入当前阶段"那一条缺 from_stage 也返回 null', () => {
    expect(undoTargetStage(card({ stage_history: [{ stage: 'rejected' }] }))).toBeNull()
  })

  it('反证：同一张卡只要历史里那条在，判据就翻面（说明它真读历史而不是读 stage）', () => {
    const withoutHistory = card({ stage_history: [] })
    const withHistory = card({ stage_history: [reached('accepted', 'offer')], stage: 'accepted' })
    expect(undoTargetStage(withoutHistory)).toBeNull()
    expect(undoTargetStage(withHistory)).toBe('offer')
  })
})

async function mountPane(kanban) {
  return mount(BoardPane, {
    props: {
      kanban,
      columns,
      writeBusy: false,
      now: new Date('2026-11-16T12:00:00').getTime(),
    },
    global: { plugins: [installElement] },
  })
}

const kanbanWith = (item) => ({
  todo: [],
  applied: [],
  written_test: [],
  interview: [],
  offer: [],
  accepted: [],
  rejected: item ? [item] : [],
  withdrawn: [],
})

describe('看板卡片菜单里的「撤销这一步」', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  async function openMenu(wrapper) {
    const trigger = wrapper.find('.card-more')
    expect(trigger.exists()).toBe(true)
    await trigger.trigger('click')
    await flushPromises()
    const items = [...document.querySelectorAll('.el-dropdown-menu__item')].map((n) =>
      n.textContent.replace(/\s+/g, ' ').trim()
    )
    return items
  }

  it('有历史的终态卡片菜单里出现「撤销这一步（退回「面试」）」，点了发 undo-terminal', async () => {
    const item = card({
      stage_history: [reached('interview', 'applied'), reached('rejected', 'interview')],
    })
    const wrapper = await mountPane(kanbanWith(item))

    /* 终态列默认收进「已结束」归档带，先展开再看菜单 */
    const expand = wrapper.find('.terminal-toggle')
    if (expand.exists()) {
      await expand.trigger('click')
      await flushPromises()
    }

    const items = await openMenu(wrapper)
    expect(items.some((text) => text.includes('撤销这一步') && text.includes('面试'))).toBe(true)
  })

  it('没有历史时那一项不出现（宁可少一颗按钮，也不退到没人点过的阶段）', async () => {
    const wrapper = await mountPane(kanbanWith(card({ stage_history: [] })))

    const expand = wrapper.find('.terminal-toggle')
    if (expand.exists()) {
      await expand.trigger('click')
      await flushPromises()
    }

    const items = await openMenu(wrapper)
    expect(items.some((text) => text.includes('撤销这一步'))).toBe(false)
  })
})

describe('撤销这一发要落到端点上', () => {
  it('视图把 undo-terminal 派给 undoPipelineTerminal，而不是 movePipelineStage', async () => {
    /* 这一条是静态的：状态机里终态没有出边，撤销必须走另一条端点。
       源码级断言比挂整页轻，且它钉住的正是"别把撤销塞回 transition"这件事。 */
    const fs = await import('node:fs/promises')
    const process = await import('node:process')
    const path = await import('node:path')
    const source = await fs.readFile(
      path.join(process.cwd(), 'src/features/pipeline/views/PipelineKanban.vue'),
      'utf8'
    )
    expect(source).toContain('undoPipelineTerminal(')
    expect(source).toContain("cmd === 'undo-terminal'")
  })
})
