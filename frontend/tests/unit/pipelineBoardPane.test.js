import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElDropdown } from 'element-plus'

import BoardPane from '@/features/pipeline/components/BoardPane.vue'
import { installElement } from '@/plugins/element'
import { columns } from '@/features/pipeline/lib/pipelineBoard'

/* D63 把看板列搬进面板。页面的那几套用例（写互斥 11 条、卡片命令 6 条、竞态 3 条）已经会
   穿过 DOM 打到这块，但它们都是**经过页面**的：面板自己的 props 接错时，页面那份传参同样错，
   两边一起绿。这里直挂面板，钉两件页面用例覆盖不到的事：
   ① 跟进那颗提醒（"几天没回复"与它的颜色档）此前**一条断言都没有**——而它现在吃的 `now`
      是跨组件边界传进来的，接错不会报错，只会让卡片安静地少一块；
   ② 面板的三条出口（command / move / 空态那两个按钮）到底发了什么载荷。 */

const DAY = 86400000
const ago = (days) => new Date(Date.now() - days * DAY).toISOString()
const NOW = Date.now()

function card(id, extra = {}) {
  return { id, title: `投递-${id}`, company: '某公司', stage: 'applied', ...extra }
}

function renderBoard(kanban = {}, extra = {}) {
  return mount(BoardPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: {
      kanban,
      columns,
      totalCards: Object.values(kanban).reduce((s, list) => s + list.length, 0),
      writeBusy: false,
      now: NOW,
      ...extra,
    },
  })
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('看板面板画出了什么', () => {
  it('跟进那颗谁画、谁不画：只有已投递与笔试、且要有 update_time；天数只决定颜色', () => {
    /* 我一开始写的是"没满 3 天不出现"——**错了**，那是 `followUpCount`（顶部那句"超 3 天未回复"）
       的门槛。卡片这颗的判据是 lib 的 `needsFollowUp`：已投递 / 笔试两列、有 update_time 就画，
       天数只挑颜色（>=3 warn、>=7 danger、其余 ok）。这条被当场打红才纠正过来。 */
    const wrapper = renderBoard({
      applied: [
        card(1, { update_time: ago(3.2) }),
        card(2, { update_time: ago(9.4) }),
        card(3, { update_time: ago(1.1) }),
        card(4),
      ],
      interview: [card(5, { stage: 'interview', update_time: ago(12) })],
      written_test: [card(6, { update_time: ago(4) })],
    })
    const chips = wrapper.findAll('.card-follow')
    expect(chips).toHaveLength(4)
    expect(chips.map((n) => n.text().trim())).toEqual([
      '3天未回复',
      '9天未回复',
      '1天未回复',
      '4天未回复',
    ])
    expect(
      chips.map((n) =>
        n
          .classes()
          .filter((c) => c.startsWith('follow-'))
          .join('')
      )
    ).toEqual(['follow-warn', 'follow-danger', 'follow-ok', 'follow-warn'])
  })

  it('卡片其余字段：分数取整、面试日期、简历版本标签与来源', () => {
    const wrapper = renderBoard({
      interview: [
        card(7, {
          match_score: 82.6,
          interview_at: '2026-10-09T10:00:00Z',
          resume_version_label: '后端 Go 版',
          source: 'Boss直聘',
        }),
      ],
    })
    const titles = wrapper.findAll('.card-title')
    expect(titles).toHaveLength(1)
    expect(titles[0].text()).toBe('投递-7')
    expect(wrapper.find('.card-score').text()).toContain('83分')
    expect(wrapper.find('.card-interview').text()).toContain('10月9日')
    expect(wrapper.find('.resume-version-tag').text()).toBe('后端 Go 版')
    expect(wrapper.find('.card-footer').text()).toContain('Boss直聘')
    // 面试列才有那颗「模拟面试」
    expect(wrapper.findAllComponents(ElDropdown)).toHaveLength(1)
  })

  it('空看板：空态在，两个按钮各发一条自己的事件', async () => {
    const wrapper = renderBoard({})
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    const byText = (label) => wrapper.findAll('button').find((b) => b.text().trim() === label)
    await byText('去岗位推荐').trigger('click')
    await byText('手动新增').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('go-recommend')).toHaveLength(1)
    expect(wrapper.emitted('open-add')).toHaveLength(1)
  })
})

describe('看板面板的三条出口', () => {
  it('下拉里的命令原样发出去，带上这张卡', async () => {
    const wrapper = renderBoard({ applied: [card(11)] })
    wrapper.findAllComponents(ElDropdown)[0].vm.$emit('command', 'reject')
    await flushPromises()
    const emitted = wrapper.emitted('command')
    expect(emitted).toHaveLength(1)
    expect(emitted[0][0]).toBe('reject')
    expect(emitted[0][1].id).toBe(11)
  })

  it('拖到别的列 → move 带上这张卡与目标列的 key', async () => {
    const wrapper = renderBoard({ applied: [card(12)] })
    const cardEl = document.querySelector('.kanban-card')
    cardEl.dispatchEvent(
      Object.assign(new Event('dragstart', { bubbles: true }), {
        dataTransfer: { effectAllowed: '' },
      })
    )
    const target = [...document.querySelectorAll('.kanban-col')].find((el) =>
      el.querySelector('h3')?.textContent.includes('Offer')
    )
    expect(target, '没有 Offer 那一列，测试前提不成立').toBeTruthy()
    target.dispatchEvent(new Event('drop', { bubbles: true }))
    await flushPromises()
    const moved = wrapper.emitted('move')
    expect(moved).toHaveLength(1)
    expect(moved[0].map((v) => (typeof v === 'object' ? v.id : v))).toEqual([12, 'offer'])
    // 拖完就把本地那份"正在拖的卡"丢掉：同一张卡不该再拖第二次
    target.dispatchEvent(new Event('drop', { bubbles: true }))
    await flushPromises()
    expect(wrapper.emitted('move')).toHaveLength(1)
  })

  it('writeBusy 时两张卡的下拉都是禁用的（D59 那把锁穿过 props）', () => {
    const wrapper = renderBoard({ applied: [card(1), card(2)] }, { writeBusy: true })
    const dropdowns = wrapper.findAllComponents(ElDropdown)
    expect(dropdowns).toHaveLength(2)
    expect(dropdowns.map((d) => d.props('disabled'))).toEqual([true, true])
  })
})
