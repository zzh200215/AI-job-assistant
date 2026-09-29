import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import JobCompareDialog from '@/features/jobs/components/JobCompareDialog.vue'
import { installElement } from '@/plugins/element'

/* 这是 D36 从 JobSearch.vue 里搬出来的对比弹窗。测试盯的是"搬之前屏幕上的东西一件不少、
   点下去发的东西一件不变"：字段、按钮文案、四个事件各带哪一条 job，以及没有选择时不渲染网格。
   `statusText` 是函数 prop——阶段标签只有父页面那份 pipeline 状态知道，
   复制成 job 上的字段会造出一份会过期的第二真相。 */

const card = (uid, title, extra = {}) => ({
  uid,
  id: Number(uid.split('-')[1]) || null,
  title,
  company: `${title}公司`,
  salary: '30-50K',
  location: '北京',
  experience: '3-5 年',
  priorityLabel: '优先投递',
  priorityScore: 82,
  priorityReason: `${title} 的技能重合高`,
  skillTags: ['Python', 'FastAPI'],
  summary: `${title} 的摘要`,
  ...extra,
})

const jobs = [card('search-1', '后端工程师'), card('search-2', '前端工程师')]
const statusText = (job) => (job.title === '后端工程师' ? '已投递' : '')

function mountDialog(props = {}) {
  return mount(JobCompareDialog, {
    attachTo: document.body,
    props: {
      modelValue: true,
      jobs,
      statusText,
      ...props,
    },
    // EP 的 el-dialog 内容被它自己的 rendered 门挡住（jsdom 里没有过渡回调），
    // 而这次要保的是我们搬进去的那段网格与事件，所以把外壳桩成透传插槽。
    global: {
      plugins: [installElement],
      stubs: {
        'el-dialog': {
          inheritAttrs: false,
          template: '<div class="dialog-stub"><slot /></div>',
        },
      },
    },
  })
}

function texts(selector) {
  return [...document.querySelectorAll(selector)].map((n) =>
    n.textContent.replace(/\s+/g, ' ').trim()
  )
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('对比弹窗搬到子组件之后', () => {
  it('每张卡片的字段与按钮文案都照常渲染', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(document.querySelectorAll('.compare-card').length).toBe(2)
    expect(texts('.compare-head h3')).toEqual(['后端工程师', '前端工程师'])
    expect(texts('.compare-company')).toEqual(['后端工程师公司', '前端工程师公司'])
    expect(texts('.compare-reason')).toEqual(['后端工程师 的技能重合高', '前端工程师 的技能重合高'])
    expect(texts('.compare-summary')).toEqual(['后端工程师 的摘要', '前端工程师 的摘要'])
    expect(document.querySelectorAll('.compare-tags .el-tag').length).toBe(4)
    // 第一张已在流程里 -> 按钮写阶段名；第二张没写 -> 退回"加入流程"
    expect(texts('.compare-actions button').slice(0, 4)).toEqual([
      '详情',
      '已投递',
      '移出对比',
      '分析',
    ])
    expect(texts('.compare-actions button')[5]).toBe('加入流程')
    wrapper.unmount()
  })

  it('四个按钮各自把所属的那条 job 发出去', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const second = [...document.querySelectorAll('.compare-card')][1]
    const buttons = second.querySelectorAll('.compare-actions button')
    buttons[0].click()
    buttons[1].click()
    buttons[2].click()
    buttons[3].click()
    await flushPromises()

    expect(wrapper.emitted('detail')[0][0].uid).toBe('search-2')
    expect(wrapper.emitted('pipeline')[0][0].uid).toBe('search-2')
    expect(wrapper.emitted('remove')[0][0].uid).toBe('search-2')
    expect(wrapper.emitted('analyze')[0][0].uid).toBe('search-2')
    wrapper.unmount()
  })

  it('没选够岗位时不渲染网格（关闭状态也不该报错）', async () => {
    const wrapper = mountDialog({ jobs: [], modelValue: false })
    await flushPromises()

    expect(document.querySelector('.compare-grid')).toBeFalsy()
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    wrapper.unmount()
  })
})
