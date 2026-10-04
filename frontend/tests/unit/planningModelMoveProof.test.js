import { describe, expect, it } from 'vitest'

import {
  complexityTag,
  coveragePct,
  gapFacts,
  jdOptionLabel,
  joinedText,
  makeRadarPolygon,
  priorityTag,
  resumeOptionLabel,
  sampleIdText,
  statusText,
  stepIcon,
  stepLabel,
  stepType,
} from '@/features/planning/lib/planningModel'

import { CircleCloseFilled, Loading, SuccessFilled, WarningFilled } from '@element-plus/icons-vue'

/* D53 把 14 个纯函数从 CareerPlanning.vue 搬进 lib，判据一个字没改（这一批本来就不读 ref，
   所以不像 D49 那样要把隐式读取改成参数）。下面这组 old* 是**搬家前的原函数**，逐字抄自
   HEAD:frontend/src/features/planning/views/CareerPlanning.vue，只把页面里那两条
   `const centerPoint = 160` / `const radarRadius = 116` 就地写回它们自己。
   D113（§10.20）之后 `safeScore` 不在这个 lib 里了：它变成 `@/utils/aiScore` 的 `readScore`，
   判据也**故意**改了（读不懂 → null 而不是 0），所以它由 `aiScore.test.js` 钉。这里留下的
   是"搬家不夹带口径决定"那一半：`oldSafeScore` 仍然当作**雷达几何**的参照物在比。 */

const OLD_CENTER = 160
const OLD_RADIUS = 116

function oldSafeScore(value) {
  const number = Number(value || 0)
  return Math.max(0, Math.min(100, Math.round(number)))
}

function oldMakeRadarPolygon(scores) {
  const count = scores.length
  if (!count) return ''
  return scores
    .map((score, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count
      const radius = (oldSafeScore(score) / 100) * OLD_RADIUS
      const x = OLD_CENTER + Math.cos(angle) * radius
      const y = OLD_CENTER + Math.sin(angle) * radius
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

const oldGapFacts = (item) =>
  (item?.gap_skills || []).map((row) => {
    const parts = []
    if (row.required_count) parts.push(`${row.required_count} 条岗位必备`)
    if (row.nice_count) parts.push(`${row.nice_count} 条列为加分`)
    return { skill: row.skill, detail: parts.join('，') || '仅个别岗位提及' }
  })

const oldResumeOptionLabel = (item) => {
  const name = item.name || item.parsed?.name || item.file_name
  const title = item.parsed?.current_title || '待补充职称'
  return `${name} · ${title}`
}

/* 这些向量**两端都可读**：新实现只在含读不懂成员时与搬家前不同，其余一个点都不差。 */
const scoreVectors = [
  [],
  [0],
  [100],
  [50, 50],
  [80, 20],
  [95, 60, 40],
  [10, 20, 30, 40, 50, 60],
  [-15, 130, 62.5],
]

/* D113 之前，这一条向量里混着 `[null, undefined, '42', 0]`——旧实现把 null/undefined 夹成 0
   照样画得出折线。现在它归到下面那条"故意不同"的用例里，因为把读不懂的分数摆在圆心正是这次
   要取消的那句谎。 */
const unreadableVectors = [
  [null, undefined, '42', 0],
  ['约80', '分数未知'],
  [80, NaN],
  [70, true],
]

describe('D53 搬家：输出与搬家前逐条相同', () => {
  it(`雷达折线在 ${scoreVectors.length} 组**两端都可读**的分数向量上一个点都不差`, () => {
    for (const vector of scoreVectors) {
      expect(makeRadarPolygon(vector), `${vector} 的折线变了`).toBe(oldMakeRadarPolygon(vector))
    }
  })

  it('技能缺口事实串一个不差', () => {
    for (const item of [
      undefined,
      {},
      { gap_skills: [] },
      { gap_skills: [{ skill: 'Go', required_count: 3, nice_count: 0 }] },
      { gap_skills: [{ skill: 'K8s', required_count: 0, nice_count: 2 }] },
      { gap_skills: [{ skill: 'Rust' }] },
      { gap_skills: [{ skill: 'A', required_count: 1, nice_count: 1 }, { skill: 'B' }] },
    ]) {
      expect(gapFacts(item)).toEqual(oldGapFacts(item))
    }
  })

  it('简历选项文案的三段回退一个不差', () => {
    for (const item of [
      { name: '主名', parsed: { name: '解析名', current_title: '后端' } },
      { parsed: { name: '解析名' } },
      { file_name: 'f.pdf' },
      { name: '主名', parsed: { current_title: '后端' } },
      { name: '只有名字' },
    ]) {
      expect(resumeOptionLabel(item)).toBe(oldResumeOptionLabel(item))
    }
  })
})

describe('钉死每条规则', () => {
  it('雷达折线：混进读不懂的分数就整条不画，而不是把它摆在圆心', () => {
    /* 这是这次**故意**与搬家前不同的那一处。旧实现把两类形状都"读出了分数"：
       `Number(null || 0)` 归成 0（于是那个角塌在圆心，等于说"你这项 0 分"），
       `Number('约80')` 得到 NaN 并一路传进 points 串（于是整张雷达静默不画）。
       现在 `readScore` 两种都返回 null，调用方（两屏）先把不可读的轴挑出去；这里再守一道，
       因为"把 null 悄悄当 0"正是这次要取消的谎，lib 不该留下第二条通往它的近路。
       可达性：`career_planning` 是 LLM 原始 JSON（career_agent.py:55 的 chat_json，无 schema 约束）。 */
    for (const vector of unreadableVectors) {
      expect(makeRadarPolygon(vector), `${vector} 竟然画出来了`).toBe('')
      expect(oldMakeRadarPolygon(vector), `${vector} 搬家前本来画得出`).not.toBe('')
    }
    // 反向证据：搬家前 NaN 真的会一路传进 points 串（`Number('约80')` 是 NaN，不是假值，
    // 旧实现那句 `value || 0` 挡不住它），而非法的 points 让整个 SVG 静默不画。
    expect(oldMakeRadarPolygon(['约80', '分数未知'])).toBe('NaN,NaN NaN,NaN')
  })

  it('雷达：没有维度就没有折线；正上方起步；分数按比例长短', () => {
    expect(makeRadarPolygon([])).toBe('')
    // 单点：角度 -90°，满分 116 的半径从圆心 160 向上
    expect(makeRadarPolygon([100])).toBe('160.00,44.00')
    // 两点：一个满分朝上、一个满分朝下
    expect(makeRadarPolygon([100, 100])).toBe('160.00,44.00 160.00,276.00')
    expect(makeRadarPolygon([80, 20])).toBe('160.00,67.20 160.00,183.20')
  })

  it('覆盖率：只有有限小数才转百分数', () => {
    expect([
      coveragePct({ coverage: 0.341 }),
      coveragePct({ coverage: 1 }),
      coveragePct({}),
    ]).toEqual([34, 100, null])
    expect(coveragePct({ coverage: '0.5' })).toBeNull()
    expect(coveragePct(undefined)).toBeNull()
    expect(coveragePct({ coverage: NaN })).toBeNull()
  })

  it('技能缺口事实串：必备与加分并列，都没有就是"仅个别岗位提及"', () => {
    expect(gapFacts({ gap_skills: [{ skill: 'Go', required_count: 3, nice_count: 2 }] })).toEqual([
      { skill: 'Go', detail: '3 条岗位必备，2 条列为加分' },
    ])
    expect(gapFacts({ gap_skills: [{ skill: 'Rust' }] })).toEqual([
      { skill: 'Rust', detail: '仅个别岗位提及' },
    ])
    expect(gapFacts({})).toEqual([])
  })

  it('样本 id：空串、最多四个、超出加"等"', () => {
    expect(sampleIdText(undefined)).toBe('')
    expect(sampleIdText([])).toBe('')
    expect(sampleIdText([1, 2])).toBe('1、2')
    expect(sampleIdText([1, 2, 3, 4])).toBe('1、2、3、4')
    expect(sampleIdText([1, 2, 3, 4, 5, 6])).toBe('1、2、3、4 等')
  })

  it('列表拼接只认数组', () => {
    expect(joinedText(['a', 'b'])).toBe('a / b')
    expect(joinedText([])).toBe('')
    expect(joinedText('a')).toBe('')
    expect(joinedText(null)).toBe('')
  })

  it('两张 el-tag 色表的边界与兜底', () => {
    expect([priorityTag('高'), priorityTag('中'), priorityTag('低'), priorityTag('怪')]).toEqual([
      'danger',
      'warning',
      'info',
      'info',
    ])
    expect([
      complexityTag('困难'),
      complexityTag('中等'),
      complexityTag('简单'),
      complexityTag(undefined),
    ]).toEqual(['danger', 'warning', 'success', 'info'])
  })

  it('步骤名、状态文案、状态色与状态图标四件事各自认这套枚举', () => {
    expect(stepLabel('task_planning')).toBe('任务规划')
    expect(stepLabel('career_planning')).toBe('职业规划')
    expect(stepLabel('interview_question_generation')).toBe('面试题生成')
    expect(stepLabel('never_seen')).toBe('never_seen')
    expect(statusText('skipped')).toBe('跳过')
    expect(statusText('weird')).toBe('weird')
    expect([
      stepType('completed'),
      stepType('running'),
      stepType('failed'),
      stepType('pending'),
      stepType('skipped'),
    ]).toEqual(['success', 'primary', 'danger', 'info', 'info'])
    expect([
      stepIcon('completed'),
      stepIcon('running'),
      stepIcon('failed'),
      stepIcon('pending'),
    ]).toEqual([SuccessFilled, Loading, CircleCloseFilled, WarningFilled])
  })

  it('JD 选项文案：公司缺失时写"未填写公司"', () => {
    expect(jdOptionLabel({ title: '后端', company: '示例' })).toBe('后端 · 示例')
    expect(jdOptionLabel({ title: '后端' })).toBe('后端 · 未填写公司')
  })
})
