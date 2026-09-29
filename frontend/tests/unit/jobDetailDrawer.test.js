import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import JobDetailDrawer from '@/features/jobs/components/JobDetailDrawer.vue'
import { installElement } from '@/plugins/element'

/* D36 的第二刀：职位详情抽屉搬出 JobSearch.vue。
   盯的是"父页面算好传进来的三个值（阶段标签 / 是否在清单 / 是否在对比）真的驱动了按钮文案"，
   以及五个按钮各发对它自己的事件——这三样原来是靠父组件里的函数在模板里现调的，
   搬成 props 之后一旦接错，屏幕上就是"已加入的岗位还写着加入清单"。 */

const job = {
  uid: 'search-1',
  id: 101,
  title: '后端工程师',
  company: '某科技公司',
  salary: '30-50K',
  location: '北京',
  experience: '3-5 年',
  education: '本科',
  skillTags: ['Python', 'FastAPI'],
  summary: '负责召回与编排服务。',
  rawText: '完整 JD 正文',
  sourceUrl: 'https://example.com/job/101',
}

function mountDrawer(props = {}) {
  return mount(JobDetailDrawer, {
    attachTo: document.body,
    props: { modelValue: true, job, ...props },
    global: { plugins: [installElement] },
  })
}

function actionButtons(wrapper) {
  return wrapper.findAll('.drawer-actions button').map((b) => b.text().replace(/\s+/g, ' ').trim())
}

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('详情抽屉搬到子组件之后', () => {
  it('加载态只出转圈，不出内容', async () => {
    const wrapper = mountDrawer({ loading: true })
    await flushPromises()

    expect(document.querySelector('.drawer-loading')).toBeTruthy()
    expect(document.querySelector('.drawer-header')).toBeFalsy()
    wrapper.unmount()
  })

  it('字段照常渲染，三个派生值驱动按钮文案', async () => {
    const wrapper = mountDrawer({ statusText: '已约面', shortlisted: true, compared: false })
    await flushPromises()

    expect(document.querySelector('.drawer-company').textContent.trim()).toBe('某科技公司')
    expect(document.querySelector('.drawer-content').textContent.trim()).toBe('完整 JD 正文')
    expect(
      [...document.querySelectorAll('.drawer-tags .el-tag')].map((n) => n.textContent.trim())
    ).toEqual(['Python', 'FastAPI'])
    expect(actionButtons(wrapper)).toEqual([
      '移出清单',
      '已约面',
      '加入对比',
      '投递解读',
      '直接分析',
    ])
    wrapper.unmount()
  })

  it('五个按钮各发自己的事件，不带别的行为', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    const buttons = wrapper.findAll('.drawer-actions button')
    for (const b of buttons) await b.trigger('click')
    await flushPromises()

    for (const evt of ['shortlist', 'pipeline', 'compare', 'explain', 'analyze']) {
      expect(wrapper.emitted(evt)?.length, `${evt} 没有发出来`).toBe(1)
    }
    wrapper.unmount()
  })

  it('投递解读在途时按钮转圈，解读结果按字段渲染', async () => {
    const wrapper = mountDrawer({
      explainLoading: true,
      explainResult: {
        recommendation: '优先投递',
        overall_score: 82,
        overall_reason: '技能重合高',
        risk_points: ['样本少'],
        optimization_suggestions: ['补项目量化'],
      },
    })
    await flushPromises()

    expect(document.querySelector('.drawer-actions button:nth-child(4)').className).toContain(
      'is-loading'
    )
    const box = document.querySelector('.explain-box')
    expect(box.textContent).toContain('82 分')
    expect(box.textContent).toContain('技能重合高')
    expect(box.textContent).toContain('样本少')
    expect(box.textContent).toContain('补项目量化')
    wrapper.unmount()
  })

  it('没有投递解读结果时不渲染那一节', async () => {
    const wrapper = mountDrawer({ explainResult: null })
    await flushPromises()

    expect(document.querySelector('.explain-box')).toBeFalsy()
    expect(document.body.textContent).not.toContain('投递判断')
    wrapper.unmount()
  })
})
