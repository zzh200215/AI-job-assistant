<template>
  <el-alert :title="suggestions?.overall || ''" type="success" :closable="false" />
  <el-collapse class="mt">
    <el-collapse-item
      v-for="(s, i) in suggestions?.sections || []"
      :key="i"
      :title="`【${s.section}】`"
    >
      <ul>
        <li v-for="(x, j) in s.suggestions" :key="j">{{ x }}</li>
      </ul>
    </el-collapse-item>
  </el-collapse>
  <el-row :gutter="16" class="mt">
    <el-col :span="12">
      <h4>建议补充关键词</h4>
      <el-tag
        v-for="k in suggestions?.keywords_to_add || []"
        :key="k"
        type="success"
        style="margin: 2px"
        >{{ k }}</el-tag
      >
    </el-col>
    <el-col :span="12">
      <h4>建议删除</h4>
      <el-tag
        v-for="k in suggestions?.keywords_to_remove || []"
        :key="k"
        type="danger"
        style="margin: 2px"
        >{{ k }}</el-tag
      >
    </el-col>
  </el-row>
  <h4 class="mt">排版建议</h4>
  <ul>
    <li v-for="(x, i) in suggestions?.format_tips || []" :key="i">
      {{ x }}
    </li>
  </ul>
  <el-divider />
  <div class="generate-area">
    <p class="generate-desc">基于以上优化建议，AI 可自动生成一份完整的优化版简历</p>
    <el-button type="primary" size="large" :loading="busy" @click="emit('generate')">
      <el-icon><EditPen /></el-icon>
      {{ busy ? '生成中…' : '🚀 生成优化版简历' }}
    </el-button>
  </div>
</template>

<script setup>
import { EditPen } from '@element-plus/icons-vue'

const emit = defineEmits(['generate'])

/* 简历优化面板：D65 从 SmartAnalysis.vue 搬出来。整段模板只有两类改动，逐条点名：
   ① `result.optimize_suggestions?.X` → `suggestions?.X`（每一处仍带回退，页面在
      `v-if="result"` 里递 `result.optimize_suggestions`，所以这个 prop 可能整个是 undefined）；
   ② 那颗生成按钮从 `:loading="genOptimizing"` + `@click="onGenerateOptimized"` 换成
      `:loading="busy"` + `@click` 发 `generate` 事件——请求、成功提示、跳转、解锁
      全部留在页面，因为只有页面知道 resume_id。守卫形状照 D59：有按钮就上 `:loading`。 */
defineProps({
  suggestions: { type: Object, default: null },
  busy: { type: Boolean, default: false },
})
</script>

<style scoped>
/* Generate area */
.generate-area {
  text-align: center;
  padding: 16px 0;
}
.generate-desc {
  color: var(--app-muted);
  font-size: 13px;
  margin-bottom: 12px;
}
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
