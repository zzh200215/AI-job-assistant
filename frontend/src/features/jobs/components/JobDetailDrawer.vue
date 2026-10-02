<script setup>
import { Loading } from '@element-plus/icons-vue'
import { priorityTagType } from '@/utils/statusTone'

/* 职位详情抽屉：从 JobSearch.vue 搬出来的第二块。
   与对比弹窗不同，这里一次只看一个岗位，所以"是否在清单里 / 在不在对比里 / 走到哪个阶段"
   都由父页面算成普通值传进来，而不是传函数——保持单一真相，又不需要函数 prop。 */
defineProps({
  job: {
    type: /** @type {import('vue').PropType<import('../lib/jobModel').Job | null>} */ (Object),
    default: null,
  },
  loading: { type: Boolean, default: false },
  statusText: { type: String, default: '' },
  shortlisted: { type: Boolean, default: false },
  compared: { type: Boolean, default: false },
  explainResult: { type: Object, default: null },
  explainLoading: { type: Boolean, default: false },
})
const emit = defineEmits(['shortlist', 'pipeline', 'compare', 'explain', 'analyze'])
const visible = defineModel({ type: Boolean })
</script>

<template>
  <el-drawer v-model="visible" size="48%" :title="job?.title || '职位详情'">
    <div v-if="loading" class="drawer-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>正在加载职位详情...</span>
    </div>
    <template v-else-if="job">
      <div class="drawer-header">
        <div>
          <p class="drawer-company">{{ job.company }}</p>
          <div class="job-facts compact">
            <span class="fact-emphasis">{{ job.salary }}</span>
            <span>{{ job.location || '地点待补充' }}</span>
            <span>{{ job.experience || '经验不限' }}</span>
            <span>{{ job.education || '学历不限' }}</span>
          </div>
        </div>
        <div class="drawer-actions">
          <el-button size="small" @click="emit('shortlist')">
            {{ shortlisted ? '移出清单' : '加入清单' }}
          </el-button>
          <el-button size="small" @click="emit('pipeline')">
            {{ statusText || '加入流程' }}
          </el-button>
          <el-button size="small" @click="emit('compare')">
            {{ compared ? '取消对比' : '加入对比' }}
          </el-button>
          <el-button size="small" :loading="explainLoading" @click="emit('explain')">
            投递解读
          </el-button>
          <el-button size="small" type="primary" @click="emit('analyze')"> 直接分析</el-button>
        </div>
      </div>

      <div v-if="job.skillTags.length" class="drawer-tags">
        <el-tag v-for="tag in job.skillTags" :key="tag" effect="plain" size="small">{{
          tag
        }}</el-tag>
      </div>

      <div class="drawer-section">
        <h4>岗位摘要</h4>
        <p>{{ job.summary || '暂无岗位摘要' }}</p>
      </div>

      <div v-if="explainResult" class="drawer-section">
        <h4>投递判断</h4>
        <div class="explain-box">
          <div class="explain-top">
            <el-tag :type="priorityTagType(explainResult.recommendation)" effect="dark">
              {{ explainResult.recommendation }}
            </el-tag>
            <strong>{{ explainResult.overall_score }} 分</strong>
          </div>
          <p>{{ explainResult.overall_reason }}</p>
          <div v-if="explainResult.risk_points?.length" class="explain-list">
            <span>风险点</span>
            <ul>
              <li v-for="item in explainResult.risk_points.slice(0, 3)" :key="item">
                {{ item }}
              </li>
            </ul>
          </div>
          <div v-if="explainResult.optimization_suggestions?.length" class="explain-list">
            <span>建议</span>
            <ul>
              <li v-for="item in explainResult.optimization_suggestions.slice(0, 3)" :key="item">
                {{ item }}
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div class="drawer-section">
        <h4>完整 JD</h4>
        <pre class="drawer-content">{{ job.rawText || job.summary || '暂无完整内容' }}</pre>
      </div>

      <div v-if="job.sourceUrl" class="drawer-section">
        <h4>来源链接</h4>
        <el-link :href="job.sourceUrl" target="_blank" type="primary"> 打开原始职位链接 </el-link>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.drawer-loading {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--app-muted);
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.drawer-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.drawer-section + .drawer-section {
  margin-top: 18px;
}

.drawer-section h4 {
  margin: 0 0 10px;
}

.drawer-content {
  margin: 0;
  padding: 14px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
  white-space: pre-wrap;
  line-height: 1.7;
  font-family: inherit;
}

.explain-box {
  padding: 14px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
}

.explain-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.explain-list span {
  display: block;
  margin-top: 10px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--app-muted);
}

/* 这条也是复制：.drawer-header 原本在父级一条 10 选择器的响应式分组里，
   那组其余选择器留在父页面。 */
@media (max-width: 1180px) {
  .drawer-header {
    flex-direction: column;
    align-items: stretch;
  }
}

/* 下面这些是"复制"而不是"搬"：这些类在 JobSearch 留下的卡片上还在用，
   整条搬走会让那些卡片掉样式。 */
.drawer-company,
.drawer-section p {
  color: var(--app-muted);
}

.drawer-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.job-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.job-facts span {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--app-bg);
  font-size: 13px;
}

.job-facts.compact {
  margin-top: 10px;
}

.fact-emphasis {
  color: var(--app-primary, #7c6cff);
  font-weight: 700;
}
</style>
