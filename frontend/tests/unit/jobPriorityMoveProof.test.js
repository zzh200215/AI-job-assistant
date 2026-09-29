import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import {
  calculateApplicationPriority,
  normalizeJob,
  salaryMid,
  uniqueList,
} from '@/features/jobs/lib/jobModel'

/* D41 把这两个函数从 JobSearch.vue 搬进 lib，唯一改动是把 `city.value` 换成入参。
   下面这段是**搬家前的原函数**，逐字抄自 HEAD:frontend/src/features/jobs/views/JobSearch.vue，
   只把 `city.value` 改成 `cityRef.value`、把 `salaryMid` 换成本文件里显式 import 的同一个实现。
   留着它只服务一个问题：搬完的分数是不是一个都没变。 */
const cityRef = ref('')
function oldCalculateApplicationPriority(job) {
  let score = 45
  const reasons = []

  const salaryScore = salaryMid(job.salary)
  if (salaryScore >= 35) {
    score += 16
    reasons.push('薪资带更强')
  } else if (salaryScore >= 25) {
    score += 10
    reasons.push('薪资有竞争力')
  }

  if ((job.skillTags || []).length >= 6) {
    score += 10
    reasons.push('技能画像完整')
  } else if ((job.skillTags || []).length >= 3) {
    score += 6
  }

  if (job.location && cityRef.value && job.location.includes(cityRef.value)) {
    score += 8
    reasons.push('城市匹配')
  }

  if (job.local) {
    score += 6
    reasons.push('已落库可直接分析')
  }

  if (typeof job.matchScore === 'number' && job.matchScore > 0) {
    score += Math.round(job.matchScore * 0.28)
    reasons.push('推荐匹配度较高')
  }

  if (job.salaryMatch) score += 4
  if (job.locationMatch) score += 4
  if (job.experienceMatch) score += 4

  const finalScore = Math.max(0, Math.min(100, score))
  const label = finalScore >= 82 ? '优先投递' : finalScore >= 66 ? '值得投递' : '先观察'
  return {
    priorityScore: finalScore,
    priorityLabel: label,
    priorityReason: reasons.slice(0, 3).join(' / ') || '信息尚不完整，建议先观察',
  }
}

const salaryBands = [
  '面议',
  '10K-15K',
  '20K-30K',
  '25K-35K',
  '35K-60K',
  '50K-80K',
  '15-20K',
  '',
  '13K-26K·15薪',
]
const cities = ['', '北京', '上海', '深圳', '杭州', '远程']
const skillCounts = [0, 1, 2, 3, 5, 6, 9]
const matchScores = [undefined, 0, 40, 72, 99]
const flags = [true, false]

const jobs = []
for (const salary of salaryBands)
  for (const city of cities)
    for (const n of skillCounts)
      for (const matchScore of matchScores)
        for (const local of flags)
          for (const salaryMatch of flags)
            jobs.push({
              uid: `f-${jobs.length}`,
              id: jobs.length,
              title: `岗位 ${jobs.length}`,
              company: '某公司',
              location: city,
              salary,
              skillTags: Array.from({ length: n }, (_, i) => `技能${i}`),
              summary: '',
              rawText: '',
              source: 'local',
              sourceUrl: '',
              local,
              matchScore,
              salaryMatch: salaryMatch && salary !== '面议',
              locationMatch: !salaryMatch,
              experienceMatch: local,
            })

describe('D41 搬家：分数与搬家前逐条相同', () => {
  it(`覆盖 ${jobs.length} 种形状 × 6 个城市筛选，一个分数都不差`, () => {
    for (const needle of cities) {
      cityRef.value = needle
      for (const job of jobs) {
        expect(
          calculateApplicationPriority(job, needle),
          `city=${needle} 上第 ${job.id} 号形状变了`
        ).toEqual(oldCalculateApplicationPriority(job))
      }
    }
    cityRef.value = ''
  })

  it('normalizeJob 也一样：uid、兜底字段、优先级三者都不差', () => {
    const raws = [
      {},
      {
        id: 1,
        title: '后端',
        salary_range: '20K-40K',
        skill_tags: ['Go', 'K8s'],
        source: 'crawled',
      },
      {
        external_id: 'x9',
        job_title: '算法',
        experience_requirement: '3年+',
        education_requirement: '硕士',
      },
      { title: '前端', skillTags: ['Vue'], jd_summary: '摘要', _local_db: true, source: 'manual' },
      { id: 5, salary: '35K-70K', location: '北京', source: 'boss', raw_text: 'JD 原文' },
    ]
    for (const needle of cities) {
      cityRef.value = needle
      for (const [index, raw] of raws.entries()) {
        const seed = `local-${index}`
        const salary = raw.salary || raw.salary_range || '薪资面议'
        const skillTags = uniqueList(raw.skill_tags || raw.skillTags || [])
        const normalized = {
          uid: `${seed}-${raw.id || raw.external_id || raw.title || 'job'}`,
          id: raw.id || null,
          title: raw.title || raw.job_title || '未知岗位',
          company: raw.company || '未知公司',
          location: raw.location || '',
          salary,
          experience: raw.experience || raw.experience_requirement || '',
          education: raw.education || raw.education_requirement || '',
          industry: raw.industry || '',
          skillTags,
          summary: raw.jd_summary || raw.match_reason || '',
          rawText: raw.raw_text || '',
          source: raw.source || 'local',
          sourceUrl: raw.source_url || '',
          local:
            !!raw._local_db ||
            ['local', 'imported', 'api', 'manual', 'crawled'].includes(raw.source),
        }
        expect(
          normalizeJob(raw, seed, needle),
          `city=${needle} 上第 ${index} 份原始 JD 归一结果变了`
        ).toEqual({ ...normalized, ...oldCalculateApplicationPriority(normalized) })
      }
    }
    cityRef.value = ''
  })
})
