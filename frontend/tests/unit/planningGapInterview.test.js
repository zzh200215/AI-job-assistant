import { describe, expect, it } from 'vitest'

import {
  attachInterviewToSkillGaps,
  gapFacts,
  interviewGapText,
} from '@/features/planning/lib/planningModel'

/* 回流②的前端数据形状：后端只在"同名缺口"上贴 interview，前端只负责原样带出与格式化。
   不在前端另造一条"看起来像"的证据。 */

describe('职业方向缺口里的面试证据', () => {
  it('gapFacts 原样带出 interview，不自己编', () => {
    const facts = gapFacts({
      gap_skills: [
        {
          skill: 'Kafka',
          required_count: 2,
          nice_count: 0,
          interview: {
            sessions: 2,
            avg_score: 55,
            evidence: [{ question: 'Kafka 消费语义' }],
          },
        },
        { skill: 'MySQL', required_count: 1 },
      ],
    })

    expect(facts[0].interview.sessions).toBe(2)
    expect(facts[1].interview).toBeNull()
  })

  it('interviewGapText 把场次/均分/最近一问串成一句', () => {
    expect(
      interviewGapText({
        sessions: 2,
        avg_score: 55,
        evidence: [{ question: 'Kafka 消费语义' }],
      })
    ).toBe('上次面试 2 场考到，均分 55，最近一问：Kafka 消费语义')
  })

  it('没有证据时返回空串', () => {
    expect(interviewGapText(null)).toBe('')
    expect(interviewGapText({})).toBe('')
  })

  it('完整规划的技能缺口按归一化拼写贴证据，匹配不上就保持 null', () => {
    const rows = attachInterviewToSkillGaps(
      [{ skill: 'kafka', priority: '高' }, { skill: 'Redis' }],
      {
        skill_weaknesses: [
          {
            skill: 'Kafka',
            canonical: 'kafka',
            sessions: 2,
            avg_score: 55,
            evidence: [{ question: 'Kafka 消费语义' }],
          },
        ],
      }
    )

    expect(rows[0].interview.sessions).toBe(2)
    expect(rows[1].interview).toBeNull()
  })

  it('缺口带 canonical 时按它匹配，别名不再漏（K8s vs Kubernetes）', () => {
    const profile = {
      skill_weaknesses: [
        {
          skill: 'Kubernetes',
          canonical: 'kubernetes',
          sessions: 1,
          avg_score: 50,
          evidence: [{ question: 'K8s 的调度' }],
        },
      ],
    }

    const [aliased, legacy] = attachInterviewToSkillGaps(
      [{ skill: 'K8s', canonical: 'kubernetes' }, { skill: 'K8s' }],
      profile
    )

    expect(aliased.interview.sessions).toBe(1)
    // 老记录没有 canonical，退回拼写比较：k8s 与 kubernetes 不同，不硬贴。
    expect(legacy.interview).toBeNull()
  })
})
