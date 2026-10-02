<template>
  <div v-if="report">
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="候选人">{{
        report.summary?.candidate_name || '-'
      }}</el-descriptions-item>
      <el-descriptions-item label="目标岗位">{{
        report.summary?.target_position || '-'
      }}</el-descriptions-item>
      <el-descriptions-item label="推荐建议">{{ recommendation }}</el-descriptions-item>
      <el-descriptions-item label="综合评价" :span="2">{{ evaluation }}</el-descriptions-item>
    </el-descriptions>
    <h4 class="mt">投递建议</h4>
    <el-table :data="report.action_items || []" size="small" class="mt">
      <el-table-column prop="priority" label="优先级" width="80">
        <template #default="{ row }">
          <el-tag
            :type="row.priority === '高' ? 'danger' : row.priority === '中' ? 'warning' : 'info'"
            size="small"
            >{{ row.priority }}</el-tag
          >
        </template>
      </el-table-column>
      <el-table-column prop="action" label="行动" />
      <el-table-column prop="reason" label="原因" show-overflow-tooltip />
    </el-table>
    <h4 class="mt">发展建议</h4>
    <el-row :gutter="16">
      <el-col :span="12">
        <div class="dev-card">
          <h5>短期</h5>
          <ul>
            <li v-for="(s, i) in report.development_advice?.short_term || []" :key="i">
              {{ s }}
            </li>
          </ul>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="dev-card">
          <h5>长期</h5>
          <ul>
            <li v-for="(s, i) in report.development_advice?.long_term || []" :key="i">
              {{ s }}
            </li>
          </ul>
        </div>
      </el-col>
    </el-row>
  </div>
  <el-empty v-else description="暂无综合评价" />
</template>

<script setup>
/* 综合评价面板：D65 从 SmartAnalysis.vue 搬出来。两个字符串是页面 localize 过的成品
   （`localizeRecommendationText` / `localizeSentence`），面板只画；
   `report` 就是页面的 `finalReport`（记录里的 `final_report`，没有则为 null → 走空态那一支）。 */
defineProps({
  report: { type: Object, default: null },
  recommendation: { type: String, default: '' },
  evaluation: { type: String, default: '' },
})
</script>

<style scoped>
/* Dev card */
.dev-card {
  padding: 14px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--el-border-color);
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
