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
        <li v-for="(x, i) in strengths" :key="i">
          <b>{{ x.item || x }}</b>
          <span v-if="x.impact">：{{ x.impact }}</span>
          <span v-if="x.evidence" class="muted">（{{ x.evidence }}）</span>
        </li>
      </ul>
    </el-col>
    <el-col :span="8">
      <h4>差距</h4>
      <ul>
        <li v-for="(x, i) in gaps" :key="i">
          <b>{{ x.item || x }}</b>
          <span v-if="x.action">：{{ x.action }}</span>
          <span v-if="x.impact && !x.action">：{{ x.impact }}</span>
          <el-tag
            v-if="x.severity"
            size="small"
            :type="x.severity === '高' ? 'danger' : x.severity === '中' ? 'warning' : 'info'"
            style="margin-left: 4px"
            >{{ x.severity }}</el-tag
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
defineProps({
  matchedSkills: {
    type: /** @type {import('vue').PropType<string[]>} */ (Array),
    default: () => [],
  },
  missingSkills: {
    type: /** @type {import('vue').PropType<string[]>} */ (Array),
    default: () => [],
  },
  /* strengths / gaps / riskPoints 这三条**没有**上元素类型，是量过之后停的手：它们的条目有两代写法
     （裸字符串 或 带 item/impact/evidence/action/severity 的对象），模板里那句 `x.item || x`
     就是在同时吃两种。类型只能写成 `string | RubricPoint` 的联合，而联合要求模板先收窄——收窄之后
     "对象但没有 item"那一支会从"打印整个对象"变成"打印空"，那是候选人可见的变化。
     记在 docs/upgrade-plan.md §10.23，由产品拍；拍之前这里保持 unknown。 */
  strengths: { type: Array, default: () => [] },
  gaps: { type: Array, default: () => [] },
  riskPoints: { type: Array, default: () => [] },
})
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
.mb {
  margin-bottom: 8px;
}
</style>
