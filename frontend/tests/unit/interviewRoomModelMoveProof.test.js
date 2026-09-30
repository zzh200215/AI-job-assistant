import { describe, expect, it } from 'vitest'

import * as room from '@/features/interview/lib/interviewRoomModel'

/* D60 把 InterviewRoom 的显示层搬进 lib。这页**此前一条测试都没有**（`grep InterviewRoom tests/`
   只命中棘轮与路由），所以这一刀真正的交付不是行数，而是"候选人看到的每一句文案第一次有门看着"。
   下面钉的都是搬运动作会碰坏的东西：门槛边界、按关键词分流的那三条、以及"没有分数不能写成差评"。 */

describe('阶段门槛：轮次与追问切成四段', () => {
  it('第 2 轮还在开场摸底，第 3 轮起进核心深挖', () => {
    expect(room.phaseOf({ round: 2, isFollowUp: false }).title).toBe('开场摸底')
    expect(room.phaseOf({ round: 3, isFollowUp: false }).title).toBe('核心深挖')
  })

  it('前两轮压过追问：追问段只从第 3 轮起出现（这是代码里的先后，不是我以为的）', () => {
    /* 写这条之前我假定"追问优先"，实测正好相反：`round <= 2` 那支排在 isFollowUp 之前。
       搬家不改行为，所以钉现状。 */
    expect(room.phaseOf({ round: 1, isFollowUp: true }).title).toBe('开场摸底')
    expect(room.phaseOf({ round: 2, isFollowUp: true }).title).toBe('开场摸底')
    expect(room.phaseOf({ round: 3, isFollowUp: true }).title).toBe('追问深挖')
  })

  it('第 6 轮仍是核心深挖，第 7 轮才收口', () => {
    expect(room.phaseOf({ round: 6, isFollowUp: false }).title).toBe('核心深挖')
    expect(room.phaseOf({ round: 7, isFollowUp: false }).title).toBe('收口判断')
  })

  it('每段还带一句给候选人看的话术，不能只搬标题', () => {
    expect(room.phaseOf({ round: 1, isFollowUp: false }).desc).toBe(
      '先判断你的表达、基础理解和切题速度。'
    )
    expect(room.phaseOf({ round: 9, isFollowUp: false }).desc).toBe(
      '通过场景题和综合题判断稳定性、广度与上限。'
    )
  })
})

describe('按题目关键词分流的三条：提示、建议结构、本题提醒', () => {
  it('四类问题各有自己的建议回答结构', () => {
    expect(room.answerStructure('项目经历')).toEqual(['背景', '目标', '动作', '结果', '复盘'])
    expect(room.answerStructure('技术能力')).toEqual([
      '先给结论',
      '说明原理',
      '举项目例子',
      '补充边界和取舍',
    ])
    expect(room.answerStructure('场景设计')).toEqual(['先判断', '列方案', '说取舍', '讲风险和落地'])
    expect(room.answerStructure('通用问题')).toEqual(['结论', '案例', '动作', '结果', '反思'])
  })

  it('面试官那句"重点看什么"跟着同一套分流走', () => {
    expect(room.interviewerHint({ isFollowUp: false, category: '项目经历' })).toBe(
      '重点看你做了什么、为什么这么做、结果如何'
    )
    expect(room.interviewerHint({ isFollowUp: false, category: '技术能力' })).toBe(
      '重点看原理、边界条件和取舍'
    )
    expect(room.interviewerHint({ isFollowUp: false, category: '场景设计' })).toBe(
      '重点看判断思路、风险和落地能力'
    )
    expect(room.interviewerHint({ isFollowUp: false, category: '动机' })).toBe(
      '重点看动机、表达和案例完整性'
    )
  })

  it('追问压过分类：是追问就只说补细节，不再念分类话术', () => {
    expect(room.interviewerHint({ isFollowUp: true, category: '技术能力' })).toBe(
      '你刚才的回答还不够扎实，正在触发追问'
    )
    expect(room.questionHelperText({ isFollowUp: true, category: '技术能力' })).toBe(
      '这类追问通常不是再说一遍，而是要补细节、数据、取舍或具体案例。'
    )
  })

  it('本题提醒与分类一一对应，且技术优先于项目（一条含两个词时的口径）', () => {
    expect(room.questionHelperText({ isFollowUp: false, category: '技术能力' })).toBe(
      '避免只背概念，最好带一个真实项目中的使用场景。'
    )
    expect(room.questionHelperText({ isFollowUp: false, category: '项目经历' })).toBe(
      '优先说你的个人贡献，不要只说团队做了什么。'
    )
    expect(room.questionHelperText({ isFollowUp: false, category: '场景题' })).toBe(
      '先给思路框架，再展开关键动作。'
    )
    expect(room.questionHelperText({ isFollowUp: false, category: '' })).toBe(
      '先说结论，再用一段具体经历支撑。'
    )
    /* 三条分流对关键词的先后**不一致**：hint 与 structure 先看"项目"，helper 先看"技术"。
       一条同时含两个词的分类因此会得到项目味的结构与提示、技术味的提醒。后端 `_map_category`
       的四个取值各只含一个关键词（通用/HR、技术基础、项目经验、场景应对），所以这条走不到；
       能走到的只有租户在题库里手写分类那条路（企业侧，按 §2 冻结）。搬家不改行为，
       把三种先后各自钉住。 */
    expect(room.answerStructure('技术项目混合题')).toEqual(room.answerStructure('项目经历'))
    expect(room.interviewerHint({ isFollowUp: false, category: '技术项目混合题' })).toBe(
      room.interviewerHint({ isFollowUp: false, category: '项目经历' })
    )
    expect(room.questionHelperText({ isFollowUp: false, category: '技术项目混合题' })).toBe(
      room.questionHelperText({ isFollowUp: false, category: '技术能力' })
    )
  })
})

describe('分数出口：没有分数不等于差评', () => {
  it('面试分的四档文案', () => {
    expect(room.performanceSummaryOf(88)).toBe('回答有说服力')
    expect(room.performanceSummaryOf(75)).toBe('整体不错，但还能再深入')
    expect(room.performanceSummaryOf(60)).toBe('基本覆盖，但说服力一般')
    expect(room.performanceSummaryOf(40)).toBe('回答偏弱，容易触发追问')
  })

  it('55 与 70 这两道分界各自归档', () => {
    expect(room.performanceSummaryOf(55)).toBe('基本覆盖，但说服力一般')
    expect(room.performanceSummaryOf(54)).toBe('回答偏弱，容易触发追问')
    expect(room.performanceSummaryOf(70)).toBe('整体不错，但还能再深入')
  })

  it('没有分数写"评分暂未生成"，而不是"回答偏弱"', () => {
    /* 后端可能一条 evaluation 都没发。把缺数据渲染成差评，是对候选人说假话。 */
    for (const value of [null, undefined, '', 'abc']) {
      expect(room.performanceSummaryOf(value)).toBe('评分暂未生成')
    }
  })

  it('侧栏"当前判断"同样有 unknown 这一档', () => {
    expect(room.recentSignalOf(90)).toBe('表现强')
    expect(room.recentSignalOf(72)).toBe('较稳')
    expect(room.recentSignalOf(58)).toBe('可继续')
    expect(room.recentSignalOf(20)).toBe('风险偏高')
    expect(room.recentSignalOf(undefined)).toBe('待观察')
  })
})

describe('会话与状态的文案', () => {
  it('缺字段时用占位，而不是渲染 undefined', () => {
    expect(room.sessionTitle(null)).toBe('AI 模拟面试')
    expect(room.sessionTitle({ jd_summary: { title: '算法工程师' } })).toBe('算法工程师')
    expect(room.sessionSubtitle(null)).toBe('当前候选人 · 目标岗位')
    expect(room.sessionSubtitle({ jd_summary: { company: '某云' } })).toBe('当前候选人 · 某云')
    expect(room.interviewerPersona(null)).toBe('AI 面试官')
    expect(room.interviewerPersona({ interview_type: 'hr' })).toBe('招聘经理 / HR')
    expect(room.interviewerPersona({ interview_type: 'unknown-type' })).toBe('AI 面试官')
  })

  it('题目与分类的缺省值', () => {
    expect(room.spotlightQuestion(null)).toBe('正在等待面试官提问...')
    expect(room.spotlightQuestion({ content: '  ' })).toBe('  ') // 只有"没有 content"才回落到占位
    expect(room.questionCategory({})).toBe('通用问题')
    expect(room.questionCategory({ metadata: { category: '系统设计' } })).toBe('系统设计')
  })

  it('状态标签认六种，认不了就把原值念出来而不是空白', () => {
    expect(room.statusLabelOf('ongoing')).toBe('进行中')
    expect(room.statusLabelOf('evaluating')).toBe('评估中')
    expect(room.statusLabelOf('completed')).toBe('已完成')
    expect(room.statusLabelOf('weird')).toBe('weird')
  })

  it('语音那三句话按"支持 / 在听 / 可说"分开', () => {
    expect(room.speechStatusText({ supported: false, listening: false })).toBe(
      '当前浏览器不支持语音输入，建议使用最新版 Chrome 或 Edge。'
    )
    expect(room.speechStatusText({ supported: true, listening: true })).toBe(
      '正在听写，识别结果会自动追加到回答框。'
    )
    expect(room.speechStatusText({ supported: true, listening: false })).toBe(
      '可使用语音输入，提交前仍可手动修改识别文本。'
    )
  })

  it('输入框那三句：评估中优先于时间不多', () => {
    expect(room.inputPlaceholderOf({ status: 'ongoing', roundRemaining: 30 })).toBe(
      '输入你的回答...'
    )
    expect(room.inputPlaceholderOf({ status: 'ongoing', roundRemaining: 10 })).toBe(
      '时间不多了，先给结论，再补关键细节...'
    )
    expect(room.inputPlaceholderOf({ status: 'evaluating', roundRemaining: 3 })).toBe(
      '面试官正在评估上一题，请稍等...'
    )
  })
})

describe('记录统计与两个开关', () => {
  const MESSAGES = [
    { type: 'question', content: 'Q1' },
    { type: 'answer', content: 'A1' },
    { type: 'evaluation', metadata: { score: 80 } },
    { type: 'evaluation', metadata: { score: 60 } },
    { type: 'system', content: '答题超时，已进入下一题' },
    { type: 'system', content: '面试结束' },
  ]

  it('已评分题数按 evaluation 条数，超时次数要求正文里有"超时"', () => {
    expect(room.answeredCountOf(MESSAGES)).toBe(2)
    expect(room.timeoutCountOf(MESSAGES)).toBe(1)
    expect(room.answeredCountOf([])).toBe(0)
    // 答案正文里出现"超时"不算：它看的是 type
    expect(room.timeoutCountOf([{ type: 'answer', content: '我刚才超时了' }])).toBe(0)
  })

  it('四种消息行各归一类，end 与 system 同色', () => {
    expect(room.messageRowClass({ type: 'question' })).toEqual({
      'row-ai': true,
      'row-user': false,
      'row-system': false,
    })
    expect(room.messageRowClass({ type: 'answer' })['row-user']).toBe(true)
    expect(room.messageRowClass({ type: 'system' })['row-system']).toBe(true)
    expect(room.messageRowClass({ type: 'end' })['row-system']).toBe(true)
    expect(room.messageRowClass({ type: 'evaluation' })).toEqual({
      'row-ai': false,
      'row-user': false,
      'row-system': false,
    })
  })

  it('提交与语音两个开关：只有进行中才允许，空白正文不算正文', () => {
    expect(room.sendEnabled({ text: '我的回答', status: 'ongoing' })).toBe(true)
    expect(room.sendEnabled({ text: '   ', status: 'ongoing' })).toBe(false)
    expect(room.sendEnabled({ text: '我的回答', status: 'connecting' })).toBe(false)
    expect(room.sendEnabled({ text: '我的回答', status: 'evaluating' })).toBe(false)
    expect(room.speechEnabled({ supported: true, status: 'ongoing' })).toBe(true)
    expect(room.speechEnabled({ supported: false, status: 'ongoing' })).toBe(false)
    expect(room.speechEnabled({ supported: true, status: 'connecting' })).toBe(false)
  })
})
