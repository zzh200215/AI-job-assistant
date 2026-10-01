import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import InterviewQuestionsPane from '@/features/analysis/components/InterviewQuestionsPane.vue'
import { installElement } from '@/plugins/element'

/* D65 把「个性化面试题」标签页搬进 components/InterviewQuestionsPane.vue。
   这块的价值全在**字段回退**上：面试题对象有新旧两代写法（`question`/`q`、`focus`/`intent`、
   `suggested_answer`/`expected_answer`/`ref_answer`），后端两种都可能给。少读一个键不会报错，
   只会屏幕上出现一个空荡荡的题卡，所以这一份测试按"每代字段各来一张卡"来铺夹具。
   分组本身（新键 hr_questions 与 legacy 键 tech 怎么并成一组、组标题从哪张表来）是 lib 的活，
   页面调完把 `groups` 递进来；面板这边只钉两件事：标题走 lib 的 `groupTitle`，
   以及**每组各自从 Q1 数起**（跨组连续编号是另一种读法，屏幕上看得出来）。 */

const GROUPS = {
  hr_questions: [
    {
      question: '为什么离开上一家',
      focus: '稳定性',
      suggested_answer: '讲成长',
      preparation_tips: '备一个具体例子',
    },
    { q: '介绍一次冲突', intent: '沟通' },
  ],
  tech_questions: [{ q: '解释事件循环', expected_answer: '单线程 + 任务队列' }],
}

function render(props = {}) {
  return mount(InterviewQuestionsPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: { groups: {}, ...props },
  })
}

const groupTitles = () => [...document.querySelectorAll('h4')].map((h) => h.textContent.trim())

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('个性化面试题面板', () => {
  it('一个组都没有时是空态，不是没有题卡的空白', () => {
    render()
    expect(document.querySelector('.el-empty').textContent).toContain('暂无面试题')
    expect(document.querySelectorAll('.q-card').length).toBe(0)
  })

  it('每组一个标题，标题来自 lib 那张表而不是键名本身', () => {
    render({ groups: GROUPS })
    const titles = groupTitles()
    expect(titles).toEqual(['HR 题', '技术题'])
    expect(titles.some((t) => /^(hr|tech)_questions$/.test(t))).toBe(false)
  })

  it('四行内容各认各的回退：新键、legacy 键、三代的参考答案键', () => {
    render({ groups: GROUPS })
    const cards = [...document.querySelectorAll('.q-card')].map((c) => ({
      q: c.querySelector('.q').textContent.replace(/\s+/g, ' ').trim(),
      intent: c.querySelector('.q-intent').textContent.replace(/\s+/g, ' ').trim(),
      answer: c.querySelector('.q-answer').textContent.replace(/\s+/g, ' ').trim(),
      tip: c.querySelector('.q-tip')?.textContent.trim() ?? null,
    }))
    expect(cards).toEqual([
      {
        q: 'Q1：为什么离开上一家',
        intent: '考察点：稳定性',
        answer: '参考答案：讲成长',
        tip: '备考建议：备一个具体例子',
      },
      {
        q: 'Q2：介绍一次冲突',
        intent: '考察点：沟通',
        answer: '参考答案：',
        tip: null,
      },
      {
        q: 'Q1：解释事件循环',
        intent: '考察点：',
        answer: '参考答案：单线程 + 任务队列',
        tip: null,
      },
    ])
  })

  it('第三个参考答案键 ref_answer 也认（只写前两代就漏了它）', () => {
    render({
      groups: { tech_questions: [{ question: 'Q', ref_answer: '按 ref_answer 给的答案' }] },
    })
    expect(document.querySelector('.q-answer').textContent).toContain('按 ref_answer 给的答案')
  })

  it('题号每组各自从 1 起，不是整页连续编号', () => {
    render({
      groups: {
        hr_questions: [{ question: '甲' }, { question: '乙' }, { question: '丙' }],
        tech_questions: [{ question: '丁' }],
      },
    })
    expect([...document.querySelectorAll('.q-card .q b')].map((b) => b.textContent.trim())).toEqual(
      ['Q1：', 'Q2：', 'Q3：', 'Q1：']
    )
  })
})
