<template>
  <el-row :gutter="16">
    <el-col :span="12">
      <div class="skill-group">
        <h4>已匹配技能</h4>
        <el-tag v-for="s in matchedSkills" :key="s" type="success" style="margin: 2px">{{
          s
        }}</el-tag>
        <el-empty v-if="!matchedSkills.length" description="暂无" :image-size="40" />
      </div>
    </el-col>
    <el-col :span="12">
      <div class="skill-group">
        <h4>缺失技能</h4>
        <el-tag v-for="s in missingSkills" :key="s" type="danger" style="margin: 2px">{{
          s
        }}</el-tag>
        <el-empty v-if="!missingSkills.length" description="暂无" :image-size="40" />
      </div>
    </el-col>
  </el-row>
  <el-row :gutter="16" class="mt">
    <el-col :span="8">
      <h4>优势</h4>
      <ul>
        <li v-for="(r, i) in strengthRows" :key="i">
          <b v-if="r.label">{{ r.label }}</b>
          <span v-if="r.impact">{{ r.sep }}{{ r.impact }}</span>
          <span v-if="r.evidence" class="muted">（{{ r.evidence }}）</span>
        </li>
      </ul>
    </el-col>
    <el-col :span="8">
      <h4>差距</h4>
      <ul>
        <li v-for="(r, i) in gapRows" :key="i">
          <b v-if="r.label">{{ r.label }}</b>
          <span v-if="r.action">{{ r.sep }}{{ r.action }}</span>
          <span v-if="r.impact && !r.action">{{ r.sep }}{{ r.impact }}</span>
          <el-tag
            v-if="r.severity"
            size="small"
            :type="r.severity === '高' ? 'danger' : r.severity === '中' ? 'warning' : 'info'"
            style="margin-left: 4px"
            >{{ r.severity }}</el-tag
          >
        </li>
      </ul>
    </el-col>
    <el-col :span="8">
      <h4>风险</h4>
      <ul>
        <li v-for="(x, i) in riskPoints" :key="i">{{ x }}</li>
      </ul>
    </el-col>
  </el-row>
</template>

<script setup>
/* 技能匹配面板：D65 从 SmartAnalysis.vue 搬出来。
   三个列表（优势 / 差距 / 风险）是页面用 lib 规则处理过的**成品**
   （`normalizeLocalizedObjectList` / `normalizeLocalizedTextList`），面板只负责画；
   在这里再本地化一遍就是两份真相。
   样式复制的是页面 "List" 那一段（`ul` / `h4` / `.mt`）——元素选择器在 scoped 下**不跨组件**，
   不抄进来这些列表就丢间距了；父页面那 1092 行一行没删（D44 的口径）。 */
import { computed } from 'vue'

const props = defineProps({
  matchedSkills: {
    type: /** @type {import('vue').PropType<string[]>} */ (Array),
    default: () => [],
  },
  missingSkills: {
    type: /** @type {import('vue').PropType<string[]>} */ (Array),
    default: () => [],
  },
  /* strengths / gaps 的条目有两代写法：裸字符串，或 `normalizeLocalizedObjectList` 整出来的
     带 item/impact/evidence/action/severity 的对象。上一轮为了不给联合类型收窄，把这三条留成
     unknown（15 条类型错挂在账上，§10.23）。现在按 §10.23 选的那条路收口：`toRow` 一次收成
     一帧，模板不再判分支。
     候选人可见的那一处变化只在一支：**对象但没有 item** 时，原来那句 `x.item || x` 会把整个对象
     打印成 JSON（生产端 localizeSentence 给的是空串，所以这一支真到得了），现在 `<b>` 整颗不出、
     补语前面那颗冒号跟着撤，行里只剩 impact/action 与严重度标签。断言在
     tests/unit/skillsPane.test.js。
     同一族 `x.item || x` 在 AnalysisResult.vue:201/212 与 History.vue:162/172 还有四处，
     不在本刀里（面板各自收，见 D81）。 */
  strengths: {
    type: /** @type {import('vue').PropType<import('../lib/analysisModel').RubricEntry[]>} */ (
      Array
    ),
    default: () => [],
  },
  gaps: {
    type: /** @type {import('vue').PropType<import('../lib/analysisModel').RubricEntry[]>} */ (
      Array
    ),
    default: () => [],
  },
  riskPoints: {
    type: /** @type {import('vue').PropType<string[]>} */ (Array),
    default: () => [],
  },
})

/** 两代写法收成一帧。`sep` 是"有没有标签"决定的一颗冒号，收在这里是为了别让模板判三次。 */
function toRow(entry) {
  /** @type {import('../lib/analysisModel').RubricPoint} */
  const point = typeof entry === 'string' ? { item: entry } : entry || {}
  const label = String(point.item || '')
  return {
    label,
    sep: label ? '：' : '',
    impact: String(point.impact || ''),
    evidence: String(point.evidence || ''),
    action: String(point.action || ''),
    severity: String(point.severity || ''),
  }
}

const strengthRows = computed(() => props.strengths.map(toRow))
const gapRows = computed(() => props.gaps.map(toRow))
</script>

<style scoped>
/* List */
ul {
  padding-left: 16px;
  margin: 4px 0;
}
h4 {
  margin: 12px 0 6px;
}
h5 {
  margin: 0 0 8px;
}

.mt {
  margin-top: 16px;
}
</style>
