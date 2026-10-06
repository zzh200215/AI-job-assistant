import { interviewScoreTone } from '@/utils/scoreTone'

/* InterviewRoom 的显示层：把 pinia 的面试状态换算成候选人看到的每一句文案。
   这一层不读 ref、不碰 store、不发请求——所有输入都从参数进来，所以"第 3 轮之后换成
   核心深挖""没有分数时不能写『回答偏弱』"这类门槛第一次能被逐条钉住（D57 在同一页
   PipelineKanban 上做的是同一件事）。页面上的 computed 只是这里的一层薄包装。 */

/**
 * 一条面试会话消息。生产者只有 `stores/interview.js`（后端 `detail.messages` 原样进来 +
 * WS 到了自己 push 一条，字段就是这五个）。`metadata` 是后端那坨没有 schema 的负载
 * （问题的 round/total、评估的分数都在里面），所以它只能是 Record，不许在这里装精确。
 * @typedef {Object} InterviewMessage
 * @property {string} [role]
 * @property {string} [type]
 * @property {string} [content]
 * @property {Record<string, any>} [metadata]
 * @property {string} [timestamp]
 */

/**
 * `answerStructure` 给的那三行"先结论再细节"，面板按字符串数组渲染。
 * @typedef {string[]} AnswerStructure
 */

/**
 * 一种面试类型的题头配置：`InterviewSetup.vue` 里那五条内置 + 后端返回覆盖，
 * 面板与页面都读同一份，所以缺一个键就会画成 undefined。
 * @typedef {Object} InterviewTypeConfig
 * @property {string} label
 * @property {string} persona
 * @property {string} description
 * @property {string[]} focus
 * @property {string[]} [tags]
 */

export function speechStatusText({ supported, listening }) {
  if (!supported) {
    return '当前浏览器不支持语音输入，建议使用最新版 Chrome 或 Edge。'
  }
  if (listening) {
    return '正在听写，识别结果会自动追加到回答框。'
  }
  return '可使用语音输入，提交前仍可手动修改识别文本。'
}

export function spotlightQuestion(question) {
  return question?.content || '正在等待面试官提问...'
}

export function questionCategory(question) {
  return question?.metadata?.category || '通用问题'
}

export function sessionTitle(session) {
  return session?.jd_summary?.title || 'AI 模拟面试'
}

export function sessionSubtitle(session) {
  const company = session?.jd_summary?.company || '目标岗位'
  const candidate = session?.resume_summary?.name || '当前候选人'
  return `${candidate} · ${company}`
}

export function phaseOf({ round, isFollowUp }) {
  if (round <= 2) {
    return { title: '开场摸底', desc: '先判断你的表达、基础理解和切题速度。' }
  }
  if (isFollowUp) {
    return { title: '追问深挖', desc: '面试官正在确认你是否真正理解刚才提到的内容。' }
  }
  if (round <= 6) {
    return { title: '核心深挖', desc: '进入项目细节、技术原理或行为案例的主体考察。' }
  }
  return { title: '收口判断', desc: '通过场景题和综合题判断稳定性、广度与上限。' }
}

export function interviewerPersona(session) {
  const mapping = {
    tech: '技术面试官',
    hr: '招聘经理 / HR',
    comprehensive: '综合面试官',
  }
  return mapping[session?.interview_type] || 'AI 面试官'
}

export function interviewerHint({ isFollowUp, category }) {
  if (isFollowUp) return '你刚才的回答还不够扎实，正在触发追问'
  if (category.includes('项目')) return '重点看你做了什么、为什么这么做、结果如何'
  if (category.includes('技术')) return '重点看原理、边界条件和取舍'
  if (category.includes('场景')) return '重点看判断思路、风险和落地能力'
  return '重点看动机、表达和案例完整性'
}

export function answerStructure(category) {
  if (category.includes('项目')) {
    return ['背景', '目标', '动作', '结果', '复盘']
  }
  if (category.includes('技术')) {
    return ['先给结论', '说明原理', '举项目例子', '补充边界和取舍']
  }
  if (category.includes('场景')) {
    return ['先判断', '列方案', '说取舍', '讲风险和落地']
  }
  return ['结论', '案例', '动作', '结果', '反思']
}

export function questionHelperText({ isFollowUp, category }) {
  if (isFollowUp) {
    return '这类追问通常不是再说一遍，而是要补细节、数据、取舍或具体案例。'
  }
  if (category.includes('技术')) {
    return '避免只背概念，最好带一个真实项目中的使用场景。'
  }
  if (category.includes('项目')) {
    return '优先说你的个人贡献，不要只说团队做了什么。'
  }
  if (category.includes('场景')) {
    return '先给思路框架，再展开关键动作。'
  }
  return '先说结论，再用一段具体经历支撑。'
}

export function inputPlaceholderOf({ status, roundRemaining }) {
  if (status === 'evaluating') return '面试官正在评估上一题，请稍等...'
  if (roundRemaining <= 10) return '时间不多了，先给结论，再补关键细节...'
  return '输入你的回答...'
}

export function answeredCountOf(messages) {
  return messages.filter((msg) => msg.type === 'evaluation').length
}
export function timeoutCountOf(messages) {
  return messages.filter((msg) => msg.type === 'system' && msg.content.includes('超时')).length
}

const SIGNAL_BY_TONE = {
  high: '表现强',
  good: '较稳',
  warn: '可继续',
  risk: '风险偏高',
  unknown: '待观察',
}

export function recentSignalOf(score) {
  return SIGNAL_BY_TONE[interviewScoreTone(score)]
}

const STATUS_LABELS = {
  idle: '未开始',
  connecting: '连接中',
  ongoing: '进行中',
  evaluating: '评估中',
  completed: '已完成',
  error: '异常',
}

export function statusLabelOf(status) {
  return STATUS_LABELS[status] || status
}

export function messageRowClass(msg) {
  return {
    'row-ai': msg.type === 'question',
    'row-user': msg.type === 'answer',
    'row-system': msg.type === 'system' || msg.type === 'end',
  }
}

const PERFORMANCE_SUMMARY_BY_TONE = {
  high: '回答有说服力',
  good: '整体不错，但还能再深入',
  warn: '基本覆盖，但说服力一般',
  risk: '回答偏弱，容易触发追问',
  // 没有分就不写"回答偏弱"——那是把缺数据说成了差评
  unknown: '评分暂未生成',
}

export function performanceSummaryOf(score) {
  return PERFORMANCE_SUMMARY_BY_TONE[interviewScoreTone(score)]
}

/* 这两个开关以前还各带一条 `!wsConnecting`，而 `wsConnecting` 就是 `status === 'connecting'`：
   同一个值既等于 'ongoing' 又不等于 'connecting'，那条永不成立，搬家时按定义删掉。 */
export function sendEnabled({ text, status }) {
  return text.trim().length > 0 && status === 'ongoing'
}

export function speechEnabled({ supported, status }) {
  return supported && status === 'ongoing'
}
