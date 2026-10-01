import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { ElProgress } from 'element-plus'

import StagePane from '@/features/interview/components/StagePane.vue'
import QuestionPane from '@/features/interview/components/QuestionPane.vue'
import RoomAside from '@/features/interview/components/RoomAside.vue'
import { installElement } from '@/plugins/element'

/* D66 把 InterviewRoom 的三块展示面板搬出视图（实录那块另开一份文件，因为"滚动"这件事得单独证）。
   这三份钉的是**跟着 markup 一起搬进来的门槛与占位**：
   - 倒计时那格的红色门槛 `remaining <= 10`（10 与 11 之间分界，页面上只有这一处消费者）；
   - `round || 0` / `total || 0` 这两个"没有轮次就说 0"的兜底，以及进度条拿到的是哪个数；
   - 追问徽章只在 isFollowUp 时才多一枚；右栏「本题提醒」与题卡的结构建议是同一个数组；
   - 右栏技能条那一刀 `slice(0, 6)`：给 8 个只画 6 个。
   页面上那些字本身（阶段话术、题卡文案、侧栏统计口径）由既有的 interviewRoomRender 十组用例
   穿过这些边界钉着，这里不重复；这里钉的是"值递进来之后面板按自己的规矩画"。 */

const PHASE = { title: '核心深挖', desc: '围绕项目与技术选择追问' }

function mountStage(props = {}) {
  document.body.innerHTML = ''
  return mount(StagePane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: {
      phase: PHASE,
      round: 0,
      total: 0,
      remaining: 0,
      formattedRemaining: '00:00',
      formattedTime: '01:20',
      progress: 0,
      ...props,
    },
  })
}

function mountQuestion(props = {}) {
  document.body.innerHTML = ''
  return mount(QuestionPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: {
      persona: '',
      hint: '',
      category: '',
      isFollowUp: false,
      question: '',
      helperText: '',
      structure: [],
      ...props,
    },
  })
}

function mountAside(props = {}) {
  document.body.innerHTML = ''
  return mount(RoomAside, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: {
      session: null,
      answeredCount: 0,
      timeoutCount: 0,
      lastScore: null,
      recentSignal: '',
      structure: [],
      ...props,
    },
  })
}

/** 每格 pill 的文字（label + 数值挤在一起），断言的是"哪格说哪件事"。 */
const joined = (selector) =>
  [...document.querySelectorAll(selector)].map((el) => el.textContent.replace(/\s+/g, ' ').trim())

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('当前阶段面板', () => {
  it('三格计数、阶段话术各在其位', () => {
    const wrapper = mountStage({
      round: 3,
      total: 8,
      remaining: 42,
      formattedRemaining: '00:42',
      formattedTime: '05:10',
      progress: 38,
    })
    expect(document.querySelector('.stage-kicker').textContent.trim()).toBe('当前阶段')
    expect(document.querySelector('.stage-header h2').textContent.trim()).toBe('核心深挖')
    expect(document.querySelector('.stage-header p').textContent.trim()).toBe(
      '围绕项目与技术选择追问'
    )
    expect(joined('.meta-pill')).toEqual(['进度3 / 8', '单题倒计时00:42', '总用时05:10'])
    expect(wrapper.findComponent(ElProgress).props('percentage')).toBe(38)
  })

  it('轮次与总题数缺失时说的是 0 / 0，进度条拿到的是数字不是 undefined', () => {
    const wrapper = mountStage({ round: undefined, total: undefined, progress: undefined })
    expect(joined('.meta-pill')[0]).toBe('进度0 / 0')
    expect(wrapper.findComponent(ElProgress).props('percentage')).toBe(0)
  })

  it('红色门槛卡在 10：10 算危险，11 与 10.5 都不算', () => {
    mountStage({ remaining: 10 })
    expect(document.querySelectorAll('.meta-pill.danger').length).toBe(1)
    mountStage({ remaining: 11 })
    expect(document.querySelectorAll('.meta-pill.danger').length).toBe(0)
    mountStage({ remaining: 10.5 })
    expect(document.querySelectorAll('.meta-pill.danger').length).toBe(0)
  })
})

describe('题卡面板', () => {
  it('题目、分类、面试官两行、建议结构五格', () => {
    mountQuestion({
      persona: '资深后端面试官',
      hint: '先给结论再展开',
      category: '项目深挖',
      question: '讲讲你最有把握的一个系统',
      helperText: '说清取舍与结果',
      structure: ['结论', '背景', '动作', '结果', '反思'],
    })
    expect(document.querySelector('.interviewer-name').textContent.trim()).toBe('资深后端面试官')
    expect(document.querySelector('.interviewer-role').textContent.trim()).toBe('先给结论再展开')
    expect(joined('.question-meta')).toEqual(['项目深挖'])
    expect(document.querySelector('.question-card h3').textContent.trim()).toBe(
      '讲讲你最有把握的一个系统'
    )
    expect(document.querySelector('.question-helper').textContent.trim()).toBe('说清取舍与结果')
    expect(joined('.structure-tips span')).toEqual(['结论', '背景', '动作', '结果', '反思'])
  })

  it('追问时才多那一枚徽章，分类徽章不因此消失', () => {
    mountQuestion({ category: '项目深挖' })
    expect(joined('.question-badge')).toEqual(['项目深挖'])
    mountQuestion({ category: '项目深挖', isFollowUp: true })
    expect(joined('.question-badge')).toEqual(['项目深挖', '追问'])
    /* 这一枚靠的是页面递进来的 `store.isFollowUp`：递成"有没有上一题"就会永远亮着。 */
  })

  it('值还没到齐时整块不炸，空的就是空的', () => {
    const wrapper = mountQuestion()
    expect(wrapper.find('h3').text()).toBe('')
    expect(document.querySelectorAll('.structure-tips span').length).toBe(0)
    expect(document.querySelector('.question-meta').textContent.trim()).toBe('')
  })
})

describe('右栏三块', () => {
  it('岗位聚焦：标题与公司各有各的占位', () => {
    mountAside({
      session: {
        jd_summary: { title: '后端工程师', company: '某云厂商', required_skills: ['Go', 'K8s'] },
      },
    })
    expect(document.querySelector('.side-block strong').textContent.trim()).toBe('后端工程师')
    expect(document.querySelector('.side-block p').textContent.trim()).toBe('某云厂商')
    expect(joined('.skill-grid span')).toEqual(['Go', 'K8s'])

    mountAside()
    expect(document.querySelector('.side-block strong').textContent.trim()).toBe('目标岗位')
    expect(document.querySelector('.side-block p').textContent.trim()).toBe('未填写公司')
    expect(document.querySelectorAll('.skill-grid span').length).toBe(0)
  })

  it('技能条只取前六枚——给八个画八个就把这一列撑爆了', () => {
    const many = Array.from({ length: 8 }, (_, i) => `技能${i}`)
    mountAside({ session: { jd_summary: { required_skills: many } } })
    expect(joined('.skill-grid span')).toEqual([
      '技能0',
      '技能1',
      '技能2',
      '技能3',
      '技能4',
      '技能5',
    ])
  })

  it('表现速览：四格按各自口径，最近得分没有时是 --', () => {
    mountAside({
      answeredCount: 4,
      timeoutCount: 1,
      lastScore: { score: 78, improvement: '把取舍讲完' },
      recentSignal: '稳定',
    })
    expect(joined('.snapshot-item')).toEqual([
      '已评分题数4',
      '超时次数1',
      '最近得分78',
      '当前判断稳定',
    ])
    expect(document.querySelector('.snapshot-note').textContent).toContain('把取舍讲完')

    mountAside()
    expect(joined('.snapshot-item')).toEqual(['已评分题数0', '超时次数0', '最近得分--', '当前判断'])
    expect(document.querySelector('.snapshot-note')).toBeNull()
  })

  it('最近得分只有 score 而没有 improvement 时，那一行不留', () => {
    mountAside({ lastScore: { score: 60 } })
    expect(joined('.snapshot-item')[2]).toBe('最近得分60')
    expect(document.querySelector('.snapshot-note')).toBeNull()
  })

  it('本题提醒画成 li，跟题卡那五格是同一个数组', () => {
    mountAside({ structure: ['结论', '结果'] })
    expect(joined('.hint-list li')).toEqual(['结论', '结果'])
    expect(document.querySelectorAll('.hint-list span').length).toBe(0)
  })
})
