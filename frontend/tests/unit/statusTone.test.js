import { describe, expect, it } from 'vitest'
import {
  INTERVIEW_STATUS_TAGS,
  TAG_TYPES,
  TASK_STATUS_TAGS,
  tagTypeFor,
} from '../../src/utils/statusTone'

const TABLES = { TASK_STATUS_TAGS, INTERVIEW_STATUS_TAGS }

describe('statusTone', () => {
  it('only ever names an el-tag type', () => {
    for (const [name, table] of Object.entries(TABLES)) {
      for (const [status, tag] of Object.entries(table)) {
        expect(TAG_TYPES, `${name}.${status}`).toContain(tag)
      }
    }
  })

  it('says the same colour for a status two pages share', () => {
    // 收敛前实测：`running` 在任务中心是蓝、在两个 agent 页是橙；`ongoing` 在房间页
    // 是绿、在设置页是橙。同名状态跨页不同色就是这一条要拦的事。
    const shared = Object.keys(TASK_STATUS_TAGS).filter((k) => k in INTERVIEW_STATUS_TAGS)
    expect(shared).toContain('completed')
    for (const key of shared) {
      expect(tagTypeFor(INTERVIEW_STATUS_TAGS, key), key).toBe(tagTypeFor(TASK_STATUS_TAGS, key))
    }
  })

  it('keeps green meaning "finished" only', () => {
    const greens = Object.entries(TABLES).flatMap(([name, t]) =>
      Object.entries(t)
        .filter(([, tag]) => tag === 'success')
        .map(([status]) => `${name}.${status}`)
    )
    expect(greens.sort()).toEqual(['INTERVIEW_STATUS_TAGS.completed', 'TASK_STATUS_TAGS.completed'])
  })

  it('marks every in-progress state as primary, not as a warning', () => {
    // 橙在这两套里留给"部分完成 / 需要看一眼"，进行中不该抢它的语义
    expect(TASK_STATUS_TAGS.running).toBe('primary')
    for (const status of ['connecting', 'ongoing', 'evaluating']) {
      expect(INTERVIEW_STATUS_TAGS[status], status).toBe('primary')
    }
    expect(tagTypeFor(TASK_STATUS_TAGS, 'partial')).toBe('warning')
    expect(tagTypeFor(TASK_STATUS_TAGS, 'failed')).toBe('danger')
  })

  it('treats an unknown status as unknown, not as a failure', () => {
    for (const table of Object.values(TABLES)) {
      expect(tagTypeFor(table, 'brand_new_backend_state')).toBe('info')
      expect(tagTypeFor(table, undefined)).toBe('info')
      expect(tagTypeFor(table, null)).toBe('info')
    }
  })
})
