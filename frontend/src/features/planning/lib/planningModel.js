/* 职业规划页的数据形状层：从 CareerPlanning.vue 搬出来的一组纯函数与常量。
   这一页脚本 637 行里有 ~110 行是"把后端返回的规划报告读成能画的东西"：选项文案、覆盖率取整、
   技能缺口的事实串、雷达多边形坐标、优先级/复杂度/步骤三张 el-tag 色表、步骤图标。它们不发请求、
   不读任何 ref，所以搬过来不需要改判据，只把雷达的两个几何常量一起搬走。
   雷达常量导出后在本页以 `centerPoint` / `radarRadius` 的名字用（模板里 SVG 的 x1/y1 也读它们）。 */
import { CircleCloseFilled, Loading, SuccessFilled, WarningFilled } from '@element-plus/icons-vue'

export const RADAR_CENTER_POINT = 160
export const RADAR_RADIUS = 116

export function resumeOptionLabel(item) {
  const name = item.name || item.parsed?.name || item.file_name
  const title = item.parsed?.current_title || '待补充职称'
  return `${name} · ${title}`
}

export function jdOptionLabel(item) {
  const company = item.company || '未填写公司'
  return `${item.title} · ${company}`
}

/** 覆盖率是小数（0.34），取整成百分数；不是数字就返回 null 让调用方自己决定不显示。 */
export function coveragePct(item) {
  return Number.isFinite(item?.coverage) ? Math.round(item.coverage * 100) : null
}

export function gapFacts(item) {
  return (item?.gap_skills || []).map((row) => {
    const parts = []
    if (row.required_count) parts.push(`${row.required_count} 条岗位必备`)
    if (row.nice_count) parts.push(`${row.nice_count} 条列为加分`)
    return { skill: row.skill, detail: parts.join('，') || '仅个别岗位提及' }
  })
}

/** 支撑这条方向的岗位样本：最多列出 4 个 id，多的用"等"收尾。 */
export function sampleIdText(ids) {
  const list = ids || []
  if (!list.length) return ''
  return list.slice(0, 4).join('、') + (list.length > 4 ? ' 等' : '')
}

/* 分数不是有限数字就当 0。这条改的是**只夹一次**的那些调用点：`career_planning` 是 LLM 的原始
   JSON（`agents/career_agent.py:55` 的 `chat_json`，没有任何 schema 约束分数必须是数字），模型写
   成"约80"时旧实现返回 NaN，页面上"95 分提升空间"变成"NaN 分提升空间"、分数列也是 NaN，
   `width: NaN%` 被浏览器直接忽略。
   雷达折线**当时并没有坏**：页面在 `map(safeScore)` 之后又在 `makeRadarPolygon` 里夹一次，而
   `Number(NaN || 0)` 恰好是 0——这条意外的重夹不该成为依赖，所以判据在这里收口。
   留着的口径问题（"读不懂的分数该画 0 还是该标暂无数据"）见 §10.20。 */
export function safeScore(value) {
  const number = Number(value || 0)
  if (!Number.isFinite(number)) return 0
  return Math.max(0, Math.min(100, Math.round(number)))
}

/** 雷达折线：从正上方开始均分角度，分数按 0-100 映射到半径。 */
export function makeRadarPolygon(scores) {
  const count = scores.length
  if (!count) return ''
  return scores
    .map((score, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count
      const radius = (safeScore(score) / 100) * RADAR_RADIUS
      const x = RADAR_CENTER_POINT + Math.cos(angle) * radius
      const y = RADAR_CENTER_POINT + Math.sin(angle) * radius
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

export function joinedText(value) {
  if (!Array.isArray(value) || !value.length) return ''
  return value.join(' / ')
}

export function priorityTag(priority) {
  return (
    {
      高: 'danger',
      中: 'warning',
      低: 'info',
    }[priority] || 'info'
  )
}

export function complexityTag(complexity) {
  return (
    {
      困难: 'danger',
      中等: 'warning',
      简单: 'success',
    }[complexity] || 'info'
  )
}

export function stepLabel(name) {
  return (
    {
      intent_recognition: '意图识别',
      resume_parse: '简历解析',
      jd_parse: 'JD 解析',
      task_planning: '任务规划',
      knowledge_retrieval: '知识检索',
      matching_analysis: '匹配分析',
      resume_optimization: '简历优化',
      interview_question_generation: '面试题生成',
      self_check: '自我校验',
      final_report: '汇总报告',
      career_planning: '职业规划',
    }[name] || name
  )
}

export function statusText(status) {
  return (
    {
      pending: '等待中',
      running: '执行中',
      completed: '已完成',
      failed: '失败',
      skipped: '跳过',
    }[status] || status
  )
}

export function stepType(status) {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'primary'
  if (status === 'failed') return 'danger'
  return 'info'
}

export function stepIcon(status) {
  if (status === 'completed') return SuccessFilled
  if (status === 'running') return Loading
  if (status === 'failed') return CircleCloseFilled
  return WarningFilled
}
