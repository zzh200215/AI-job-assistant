import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ExplainPane from '@/features/analysis/components/ExplainPane.vue'
import ReferencesPane from '@/features/analysis/components/ReferencesPane.vue'
import { installElement } from '@/plugins/element'

/* D52 搬出来的两个面板。两边都在测**边界**而不是复述 lib 的规则：
   - ExplainPane 只拿到 `explainResult`，推荐标签 / 两列缺口合并 / 句子本地化都在面板里推；
     这些规则的正文住在 lib 与 utils（`analysisModelMoveProof.test.js` 已逐条钉死），
     这里只钉"喂进去的形状能不能长出来"。
   - ReferencesPane 唯一跨边界的是"展开了哪几份文档"：值归页面的链持有，面板只能写回事件。 */

const WEIGHTS = {
  skill: 0.35,
  project: 0.2,
  experience: 0.2,
  education: 0.1,
  keyword: 0.1,
  bonus: 0.05,
}

function mountExplain(props = {}) {
  return mount(ExplainPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props,
  })
}

function mountRefs(props = {}) {
  return mount(ReferencesPane, {
    attachTo: document.body,
    global: { plugins: [installElement] },
    props,
  })
}

function texts(wrapper, selector) {
  return wrapper.findAll(selector).map((n) => n.text().trim())
}

describe('匹配度解释面板', () => {
  it('没有结果时是空态，加载中时是转圈，两者都不给半截的评分卡', () => {
    expect(mountExplain().text()).toContain('完成智能分析后可在这里查看匹配度解释')
    expect(mountExplain({ loading: true }).text()).toContain('正在生成匹配度解释')
    expect(mountExplain({ loading: true }).find('.explain-hero').exists()).toBe(false)
  })

  it('推荐文案走本地化后再查色表：可以投递是蓝，未知是灰', () => {
    const wrapper = mountExplain({
      explainResult: {
        overall_score: 82,
        recommendation: '可以投递',
        overall_reason: 'skills are close',
        weights_used: WEIGHTS,
        dimensions: [],
        skill_match: {},
      },
    })
    const tag = wrapper.find('.explain-score-info .el-tag')
    expect(tag.classes().join(' ')).toContain('el-tag--primary')
    expect(tag.text()).toBe('可以投递')
  })

  it('必需列与加分列合成一列，重复的那项留在必需列的位置', () => {
    const wrapper = mountExplain({
      explainResult: {
        overall_score: 60,
        recommendation: '谨慎投递',
        overall_reason: '',
        weights_used: WEIGHTS,
        dimensions: [],
        skill_match: {
          matched: ['Go'],
          missing_required: ['Rust'],
          missing_nice: ['K8s', 'Rust'],
        },
      },
    })
    expect(texts(wrapper, '.el-col')[0]).toContain('Go')
    expect(texts(wrapper, '.el-col')[1]).toEqual(expect.stringContaining('Rust'))
    const missingCol = wrapper.findAll('.el-col')[1]
    expect(missingCol.findAll('.el-tag').map((t) => t.text())).toEqual(['Rust', 'K8s'])
    expect(wrapper.findAll('.el-tag--success').length).toBe(1)
  })

  it('六维评分每一维都有条、分数与理由', () => {
    const wrapper = mountExplain({
      explainResult: {
        overall_score: 71,
        recommendation: '可以投递',
        overall_reason: '',
        weights_used: WEIGHTS,
        skill_match: {},
        dimensions: [
          { name: '技能', weight: 0.35, score: 80, reason: 'gap', details: ['d1'] },
          { name: '经验', weight: 0.2, score: 40, reason: 'short', details: [] },
        ],
      },
    })
    expect(texts(wrapper, '.dim-name')).toEqual(['技能', '经验'])
    expect(texts(wrapper, '.dim-score')).toEqual(['80.0', '40.0'])
    expect(texts(wrapper, '.dim-w')).toEqual(['权重 35%', '权重 20%'])
    expect(wrapper.findAll('.dim-fill').length).toBe(2)
    expect(wrapper.find('.dim-details').exists()).toBe(true)
  })
})

describe('引用来源面板', () => {
  const DOCS = [
    {
      doc_title: '简历模板 A',
      doc_type: 'resume_template',
      chunks: [{ text: '片段一', score: 0.91 }],
    },
    {
      doc_title: '能力模型 B',
      doc_type: 'skill_model',
      chunks: [{ text: '片段二', score: 0.42 }],
    },
  ]

  it('在飞 / 空 / 有内容三种状态各说各的话', () => {
    expect(mountRefs({ loading: true }).text()).toContain('正在检索引用来源')
    expect(mountRefs({}).text()).toContain('暂无引用知识')
    const wrapper = mountRefs({ references: DOCS })
    expect(texts(wrapper, '.ref-doc-title')).toEqual(['简历模板 A', '能力模型 B'])
    expect(wrapper.find('.rag-confidence').exists()).toBe(false)
  })

  it('文档类型走 lib 的表，相似度按分数分档', () => {
    const wrapper = mountRefs({
      references: DOCS,
      analysisConfidence: { score: 0.6, level: 'medium' },
    })
    expect(texts(wrapper, '.ref-title .el-tag')).toEqual(['简历模板', '能力模型'])
    const scores = wrapper.findAll('.ref-chunk-header .el-tag').map((t) => t.text())
    expect(scores).toEqual(['相似度 91.0%', '相似度 42.0%'])
    expect(wrapper.find('.rag-confidence-title').text()).toContain('本次检索可信度')
  })

  it('展开哪几份文档不自己改状态，而是写回 update:refOpenDocs', async () => {
    const wrapper = mountRefs({ references: DOCS, refOpenDocs: [0] })
    await wrapper.findAll('.el-collapse-item__header')[1].trigger('click')
    /* 这是这条接口唯一可观测的契约。两件事都在此记下：
       - 面板改成"自己 ref 一份、不发事件"→ 这条红（实测：1 红 / 页面那 12 条照旧绿）；
       - 但反过来**不成立**：删掉页面上的 `v-model:ref-open-docs` 绑定，所有测试照旧全绿，
         因为 el-collapse 没有受控值时也按内部状态展开。所以这条钉的是接口形状，不是一条缺陷。 */
    expect(wrapper.emitted('update:refOpenDocs')).toBeTruthy()
    expect(wrapper.emitted('update:refOpenDocs').at(-1)).toEqual([[0, 1]])
  })
})
