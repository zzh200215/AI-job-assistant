import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SearchPane from '@/features/jobs/components/SearchPane.vue'
import { installElement } from '@/plugins/element'

/* D229：外部抓取失败时，"为什么"必须上屏。原先 `SearchPane.vue` 那条红色标签写着
   `v-if="searchError && !isDemo"`——正好把最需要解释的那一档（降级成演示数据）吃掉，
   而同一时刻后端也把 `error` 置成了 null（那半边由
   `backend/tests/test_external_search_fallback_reason.py` 钉）。
   两句要并存：警告条说"是什么"（当前为演示数据），红色标签说"为什么"（渠道没返回）。
   这里用的是 API 层组装的那句中文——爬虫内部串不许上屏，同 D92 那条口径。 */

const REASON = '外部岗位渠道这次没有返回数据（可能被限流或需要身份验证）'

const demoJob = {
  uid: 'demo-1',
  title: '演示岗位',
  company: '演示公司',
  location: '北京',
  salary: '15k-25k',
  salaryMin: 15,
  salaryMax: 25,
  skillTags: [],
  source: '_mock',
}

function render(over = {}) {
  return mount(SearchPane, {
    global: { plugins: [installElement] },
    props: {
      jobs: [demoJob],
      hasSearched: true,
      resultMode: 'demo_fallback',
      isDemo: true,
      searchError: REASON,
      stateText: '演示数据',
      bannerTitle: '当前展示演示岗位数据',
      bannerDesc: '当前结果主要用于演示流程，建议补充真实搜索或导入岗位后再做判断。',
      bannerClass: 'is-demo',
      isShortlisted: () => false,
      pipelineStatusText: () => '',
      ...over,
    },
  })
}

function dangerTags(wrapper) {
  return wrapper.findAll('.el-tag--danger').map((t) => t.text())
}

describe('降级到演示数据时，失败原因仍然要看得见', () => {
  it('演示态：警告条与原因标签并存', () => {
    const wrapper = render()
    const text = wrapper.text()

    expect(text).toContain('当前为演示数据')
    expect(dangerTags(wrapper), '演示态把原因吃掉了，候选人只剩一句"这是演示数据"').toContain(
      REASON
    )
  })

  it('本地库降级态：原因照旧上屏（这条行为本来就有，钉住别改坏）', () => {
    const wrapper = render({ isDemo: false, resultMode: 'local_fallback', stateText: '本地职位库' })

    expect(dangerTags(wrapper)).toContain(REASON)
    expect(wrapper.text()).not.toContain('当前为演示数据')
  })

  it('没有失败原因时不许凭空造一句', () => {
    const wrapper = render({ searchError: '' })

    expect(dangerTags(wrapper)).toEqual([])
    expect(wrapper.text()).toContain('当前为演示数据')
  })
})
