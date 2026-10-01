import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElButton } from 'element-plus'

import ResumeOptimizePane from '@/features/analysis/components/ResumeOptimizePane.vue'
import { installElement } from '@/plugins/element'

/* D65 把「简历优化建议」标签页搬进 components/ResumeOptimizePane.vue。
   这个面板是五块内容 + 一颗会发事的按钮，所以两边的形状都要钉：
   - 内容侧：`suggestions` 可能是**整个 undefined**（记录里就没这段），模板里每一处都带 `?.` 与 `|| []`
     回退，这条要钉住——漏一处就是 `Cannot read properties of undefined`，整页白屏；
   - 出口侧：面板只发 `generate`，请求、成功提示、跳转、解锁全在页面（只有页面知道 resume_id）。
     守卫形状照 D59：这一条路上有按钮，所以是 `:loading`，不是函数级的提前返回。 */

const SUGGESTIONS = {
  overall: '整体结构可用，项目段太薄',
  sections: [
    { section: '工作经历', suggestions: ['量化产出', '补技术栈'] },
    { section: '项目', suggestions: ['写清你的角色'] },
  ],
  keywords_to_add: ['K8s', 'Go'],
  keywords_to_remove: ['精通'],
  format_tips: ['一页 A4', '时间倒序'],
}

function render(props = {}) {
  return mount(ResumeOptimizePane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props: { suggestions: null, busy: false, ...props },
  })
}

const generateButton = () => [...document.querySelectorAll('.generate-area button')][0]

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('简历优化面板', () => {
  it('suggestions 整个缺失也不炸：五块都空着，但那颗按钮还在', () => {
    const wrapper = render()
    expect(wrapper.find('.el-alert').exists()).toBe(true)
    expect(document.querySelectorAll('.el-collapse-item__header').length).toBe(0)
    expect(document.querySelectorAll('.el-tag').length).toBe(0)
    expect(document.querySelectorAll('li').length).toBe(0)
    expect(generateButton()).toBeTruthy()
  })

  it('总评为空串时 alert 就是空的，不写「undefined」上去', () => {
    render({ suggestions: {} })
    expect(document.querySelector('.el-alert').textContent).not.toContain('undefined')
  })

  it('分段建议的标题带【】，条目在收起状态也已经挂在 DOM 上', () => {
    render({ suggestions: SUGGESTIONS })
    const headers = [...document.querySelectorAll('.el-collapse-item__header')]
    expect(headers.map((h) => h.textContent.trim())).toEqual(['【工作经历】', '【项目】'])
    const items = [...document.querySelectorAll('.el-collapse-item li')].map((li) =>
      li.textContent.trim()
    )
    expect(items).toEqual(['量化产出', '补技术栈', '写清你的角色'])
  })

  it('补充的关键词是绿的、要删的是红的，两列各归各', () => {
    render({ suggestions: SUGGESTIONS })
    const cols = [...document.querySelectorAll('.el-col')]
    expect(
      cols.map((c) => [
        c.querySelector('h4').textContent.trim(),
        [...c.querySelectorAll('.el-tag')].map(
          (t) => `${t.textContent.trim()}:${t.className.match(/el-tag--(success|danger)/)[0]}`
        ),
      ])
    ).toEqual([
      ['建议补充关键词', ['K8s:el-tag--success', 'Go:el-tag--success']],
      ['建议删除', ['精通:el-tag--danger']],
    ])
  })

  it('排版建议是一列纯文本，跟分段建议不是一套结构', () => {
    render({ suggestions: SUGGESTIONS })
    const tips = [...document.querySelectorAll('li')]
      .filter((li) => !li.closest('.el-collapse-item'))
      .map((li) => li.textContent.trim())
    expect(tips).toEqual(['一页 A4', '时间倒序'])
  })

  it('按钮只发 generate 这一个出口，点两趟发两趟（面板自己不锁）', async () => {
    const wrapper = render({ suggestions: SUGGESTIONS })
    generateButton().click()
    generateButton().click()
    await flushPromises()
    expect(wrapper.emitted('generate')).toHaveLength(2)
    expect(Object.keys(wrapper.emitted())).toEqual(['generate'])
  })

  it('busy 时那颗按钮既转圈又点不出第二趟', async () => {
    const wrapper = render({ suggestions: SUGGESTIONS, busy: true })
    const button = generateButton()
    expect(button.className).toContain('is-loading')
    expect(button.disabled).toBe(true)
    button.click()
    await flushPromises()
    expect(wrapper.emitted('generate')).toBeUndefined()
    expect(wrapper.findComponent(ElButton).props('loading')).toBe(true)
  })

  it('busy 也同步写在按钮文案上（生成中／🚀 两行字是同一条 props 的产物）', () => {
    render({ suggestions: SUGGESTIONS, busy: true })
    expect(generateButton().textContent.trim()).toBe('生成中…')
  })

  it('不传 busy 时默认就是能点的那一档，文案也换回未生成', async () => {
    const wrapper = render({ suggestions: SUGGESTIONS })
    expect(generateButton().disabled).toBe(false)
    expect(generateButton().textContent).toContain('生成优化版简历')
    generateButton().click()
    await flushPromises()
    expect(wrapper.emitted('generate')).toEqual([[]])
  })
})
