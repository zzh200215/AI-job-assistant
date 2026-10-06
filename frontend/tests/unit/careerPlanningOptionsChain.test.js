import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { usePlanningOptions } from '@/features/planning/composables/usePlanningOptions'

/* D55 把选项链搬进 composable。这四条规则是这一页"选中的到底是谁"的全部口径，
   之前一条都没有测试：它们坏起来不是报错，而是**悄悄选错东西**——把没解析过的简历摆进列表、
   把已经删掉的简历继续当成选中项，或者列表取不到时把失败演成"你没有简历"。
   所以每条都配一次变异（见 upgrade-plan D55 的表）。 */

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { resolve, reject, promise }
}

const listCalls = []

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn((url, config) => {
      const record = { url, arg: config?.params, ...deferred() }
      listCalls.push(record)
      return record.promise
    }),
  },
}))

const PARSED = { current_title: '后端工程师' }

function resumeItems() {
  return [
    { id: 7, name: '后端三年', parsed: PARSED },
    { id: 8, name: '还没解析', parsed: null },
    { id: 9, name: '解析成空对象', parsed: {} },
    { id: 10, name: '只有 file_name', file_name: 'x.pdf', parsed: { a: 1 } },
  ]
}

function jdItems() {
  return [
    { id: 3, title: '平台后端', company: '示例' },
    { id: 4, title: '算法', company: '' },
  ]
}

async function refreshWith(resumes, jds) {
  const chain = usePlanningOptions()
  const p = chain.refreshBaseOptions()
  await flushPromises()
  const resumeCall = listCalls.find((c) => c.url === '/resume/list')
  const jdCall = listCalls.find((c) => c.url === '/jd/list')
  if (resumes === 'reject') {
    resumeCall.reject(new Error('网络中断'))
  } else {
    resumeCall.resolve({ items: resumes, total: resumes.length })
  }
  if (jds !== 'reject') jdCall.resolve({ items: jds, total: jds.length })
  await p
  await flushPromises()
  return chain
}

/* §10.9 ①（D124）之后，`usePlanningOptions()` 里那一句 `useSelectionStore()` 要一个活的 pinia。
   应用里它只从组件 setup 被调用，pinia 那时已经装好；这里**不挂组件**、直接调 composable，
   所以必须自己把 pinia 摆上——否则不是断言变红，是 composable 在第一行就抛。 */
beforeEach(() => setActivePinia(createPinia()))

describe('选项链的四条口径', () => {
  beforeEach(() => {
    listCalls.length = 0
    localStorage.clear()
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'smoke', role: 'candidate' }))
  })

  it('只有解析过的简历才进列表', async () => {
    const chain = await refreshWith(resumeItems(), jdItems())
    expect(chain.resumeOptions.value.map((r) => r.id)).toEqual([7, 10])
    expect(chain.jdOptions.value.map((j) => j.id)).toEqual([3, 4])
  })

  it('没选中过时自动取第一份简历，JD 永远不自动取', async () => {
    const chain = await refreshWith(resumeItems(), jdItems())
    expect(chain.selectedResumeId.value).toBe(7)
    expect(chain.selectedJDId.value).toBeNull()

    // 已经有选择时不抢：用户选的是 10，刷新回来不能把他挪回第一份
    const other = usePlanningOptions()
    other.selectedResumeId.value = 10
    other.selectedJDId.value = 4
    const p = other.refreshBaseOptions()
    await flushPromises()
    listCalls.at(-2).resolve({ items: resumeItems(), total: 4 })
    listCalls.at(-1).resolve({ items: jdItems(), total: 2 })
    await p
    expect(other.selectedResumeId.value).toBe(10)
    expect(other.selectedJDId.value).toBe(4)
  })

  it('选中的项被删掉了就置空，而不是留着当一个悬空的 id', async () => {
    const chain = await refreshWith(resumeItems(), jdItems())
    expect(chain.selectedResumeId.value).toBe(7)
    chain.selectedJDId.value = 3 // 用户挑了一个 JD

    const p = chain.refreshBaseOptions()
    await flushPromises()
    listCalls.at(-2).resolve({ items: [{ id: 10, parsed: { a: 1 } }], total: 1 })
    listCalls.at(-1).resolve({ items: [{ id: 4, title: '算法' }], total: 1 })
    await p
    // 简历 7 不在新列表里 → 置空 → 又被"没选中过就取第一份"接走成 10
    expect(chain.selectedResumeId.value).toBe(10)
    // JD 3 也不在新列表里 → 置空，且**没有**自动取第一条的规则（那条只对简历成立）
    expect(chain.selectedJDId.value).toBeNull()
    expect(chain.selectedResume.value?.id).toBe(10)

    const p2 = chain.refreshBaseOptions()
    await flushPromises()
    listCalls.at(-2).resolve({ items: [], total: 0 })
    listCalls.at(-1).resolve({ items: [], total: 0 })
    await p2
    expect(chain.selectedResumeId.value).toBeNull()
    expect(chain.selectedJDId.value).toBeNull()
    // 选中项一旦置空，派生值必须跟着变 null，不能还指着上一次列表里的对象
    expect(chain.selectedResume.value).toBeNull()
    expect(chain.selectedJD.value).toBeNull()
  })

  it('取不到列表时说"取不到"，不说"你没有简历"', async () => {
    const chain = await refreshWith('reject', jdItems())
    expect(chain.baseOptionsError.value).toBe(true)
    expect(chain.resumeOptions.value).toEqual([])
    expect(chain.jdOptions.value).toEqual([])
    expect(chain.optionsLoading.value).toBe(false)
    expect(chain.selectedResumeId.value).toBeNull()

    // 重试成功之后错误位要自己收回去
    const p = chain.refreshBaseOptions()
    await flushPromises()
    listCalls.at(-2).resolve({ items: resumeItems(), total: 4 })
    listCalls.at(-1).resolve({ items: jdItems(), total: 2 })
    await p
    expect(chain.baseOptionsError.value).toBe(false)
    expect(chain.selectedResumeId.value).toBe(7)
  })
})

describe('刚创建的目标 JD 要立刻可选', () => {
  beforeEach(() => {
    listCalls.length = 0
    localStorage.clear()
  })

  it('插到最前面，同一个 id 不插第二次', async () => {
    const chain = await refreshWith(resumeItems(), jdItems())
    expect(chain.jdOptions.value.map((j) => j.id)).toEqual([3, 4])

    chain.adoptJD({ id: 11, title: '目标岗位', company: '职业规划目标' })
    expect(chain.jdOptions.value.map((j) => j.id)).toEqual([11, 3, 4])

    chain.adoptJD({ id: 11, title: '目标岗位', company: '职业规划目标' })
    chain.adoptJD({ id: 3, title: '平台后端', company: '示例' })
    expect(chain.jdOptions.value.map((j) => j.id)).toEqual([11, 3, 4])
    expect(chain.selectedJD.value).toBeNull() // adopt 不改选择，选中是调用方的事
  })
})
