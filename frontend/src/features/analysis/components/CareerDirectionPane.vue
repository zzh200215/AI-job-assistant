<template>
  <div v-if="loading" class="inline-loading">
    <el-icon class="is-loading" size="22"><Loading /></el-icon>
    <p>正在分析适合您的岗位方向...</p>
  </div>
  <template v-else-if="paths.length > 0">
    <el-alert
      :title="summary || `根据您的技能和经验，推荐以下 ${paths.length} 个岗位方向`"
      type="success"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />
    <div class="career-path-grid">
      <div
        v-for="(cp, i) in paths"
        :key="i"
        class="panel cp-card"
        :class="'cp-' + (cp.category === '高度匹配' ? 'high' : 'trans')"
      >
        <div class="panel-body">
          <div class="cp-header">
            <span class="cp-score" :class="scoreToneFillClass(cp.match_score)">{{
              cp.match_score
            }}</span>
            <div class="cp-info">
              <h4 class="cp-title">{{ cp.title }}</h4>
              <el-tag
                size="small"
                :type="cp.category === '高度匹配' ? 'success' : 'warning'"
                effect="dark"
                >{{ cp.category }}</el-tag
              >
              <span class="cp-seniority">{{ cp.seniority }}</span>
            </div>
          </div>
          <p class="cp-reason">{{ cp.reason }}</p>
          <div v-if="cp.matched_skills?.length" class="cp-skills">
            <span class="cp-skill-label">已具备：</span>
            <el-tag
              v-for="s in cp.matched_skills"
              :key="s"
              size="small"
              type="success"
              effect="plain"
              style="margin: 1px"
              >{{ s }}</el-tag
            >
          </div>
          <div v-if="cp.gap_skills?.length" class="cp-skills">
            <span class="cp-skill-label">需提升：</span>
            <el-tag
              v-for="s in cp.gap_skills"
              :key="s"
              size="small"
              type="danger"
              effect="plain"
              style="margin: 1px"
              >{{ s }}</el-tag
            >
          </div>
          <div v-if="cp.salary_range" class="cp-salary">💰 {{ cp.salary_range }}</div>
        </div>
      </div>
    </div>
  </template>
  <el-empty v-else description="暂无职业方向推荐（请先完成一键智能分析）" />
</template>

<script setup>
import { Loading } from '@element-plus/icons-vue'

import { scoreToneFillClass } from '@/utils/scoreTone'

/* 职业方向面板：D65 从 SmartAnalysis.vue 搬出来（「职业方向」标签页）。
   别跟 D51 的 `CareerPlanPane`（「职业规划」标签页）混：同一页两个都带 🎯 的标签页，
   一个吃 `useCareerPaths` 那条链的产物，一个吃记录里的 `career_planning` 对象。
   三个值都住在页面的链上，面板自己不发请求——链的令牌在页面（D50）。
   样式复制 "Loading state" + "Career paths" 两段，`.cp-score` 那 1 个白色前景字面量因此是从页面
   **重复**出来的第二份，不是新写的色值（它压在分数渐变上，D1 那轮就没动它）。
   这里不写那个 hex 本身：棘轮的 scriptColorLiterals 数 <script> 块里的字面量，分不清注释里的散文。 */
defineProps({
  loading: { type: Boolean, default: false },
  paths: {
    type: /** @type {import('vue').PropType<import('../lib/analysisModel').CareerPath[]>} */ (
      Array
    ),
    default: () => [],
  },
  summary: { type: String, default: '' },
})
</script>

<style scoped>
/* Loading state */
.inline-loading {
  text-align: center;
  padding: 40px 0;
  color: var(--app-muted);
}
.inline-loading p {
  margin: 8px 0 0;
}
/* Career paths */
.career-path-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cp-card {
  border-radius: var(--app-radius-sm, 12px);
}
.cp-high {
  border-left: 3px solid var(--app-success);
}
.cp-trans {
  border-left: 3px solid var(--app-warning);
}
.cp-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}
.cp-score {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
  /* §10.36(b) 走 ①：这颗座原先挂着 `data-value`，那一个类同时干两件事——`main.css:191` 的
     mono 数字排版，以及 `main.css:641` 主题网那条 `[class*='-value']{color:var(--app-text)!important}`。
     后者会整条盖掉 `.score-fill--*` 自己按档挑的前景（实测 2.38–3.57，见 D154），所以这里把
     类名摘掉、把排版自己接管：字体与字距逐条照 `data-value` 那两行写，只有颜色交还给分数座。 */
  font-family: var(--app-font-mono);
  letter-spacing: 0;
}
.cp-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cp-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.cp-seniority {
  font-size: 12px;
  color: var(--app-muted);
}
.cp-reason {
  font-size: 13px;
  color: var(--app-muted);
  margin: 4px 0;
}
.cp-skills {
  margin: 4px 0;
}
.cp-skill-label {
  font-size: 12px;
  color: var(--app-muted);
  margin-right: 4px;
}
.cp-salary {
  font-size: 13px;
  color: var(--app-warning);
  margin-top: 4px;
  font-weight: 600;
}
</style>
