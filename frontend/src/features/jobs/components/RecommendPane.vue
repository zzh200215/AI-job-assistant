<template>
  <div class="recommend-toolbar">
    <div class="recommend-left">
      <span class="toolbar-title">以当前简历为中心的岗位匹配</span>
      <span class="toolbar-sub" v-if="resumeName">{{ resumeName }}</span>
    </div>
    <div class="recommend-actions">
      <el-input
        :model-value="filters.location"
        clearable
        size="small"
        placeholder="地点偏好"
        class="mini-input"
        @update:model-value="(value) => $emit('update:filters', patch('location', value))"
      />
      <el-input
        :model-value="filters.industry"
        clearable
        size="small"
        placeholder="行业偏好"
        class="mini-input"
        @update:model-value="(value) => $emit('update:filters', patch('industry', value))"
      />
      <el-button size="small" type="primary" :disabled="!resumeSelected" @click="$emit('refresh')">
        更新推荐
      </el-button>
    </div>
  </div>

  <div v-if="loading" class="state-box">
    <el-icon class="is-loading"><Loading /></el-icon>
    <span>正在根据简历生成匹配结果...</span>
  </div>

  <AppLoadError
    v-else-if="error"
    title="推荐结果拉取失败"
    :message="error"
    @retry="$emit('refresh')"
  />

  <div v-else-if="jobs.length" class="recommend-grid">
    <article v-for="job in jobs" :key="job.uid" class="recommend-card">
      <div class="recommend-score">
        <strong>{{ job.matchScore }}</strong>
        <span>匹配分</span>
      </div>
      <div class="recommend-body">
        <div class="job-title-row">
          <h3>{{ job.title }}</h3>
          <el-tag :type="recommendTagType(job.recommendationType)" effect="dark" size="small">
            {{ job.recommendationType }}
          </el-tag>
        </div>

        <p class="job-company">
          <el-icon><OfficeBuilding /></el-icon>
          {{ job.company }} / {{ job.location || '地点待补充' }}
        </p>

        <div class="job-facts compact">
          <span class="fact-emphasis">{{ job.salary }}</span>
          <span>{{ job.industry || '行业待补充' }}</span>
        </div>

        <div class="priority-row compact">
          <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
            {{ job.priorityLabel }} / {{ job.priorityScore }}
          </el-tag>
          <span class="priority-reason">{{ job.priorityReason }}</span>
        </div>

        <p class="recommend-reason">{{ job.matchReason }}</p>

        <div class="recommend-tags">
          <div v-if="job.skillOverlap.length" class="tag-group">
            <span class="tag-label ok">重合</span>
            <el-tag
              v-for="tag in job.skillOverlap.slice(0, 6)"
              :key="tag"
              size="small"
              type="success"
              effect="plain"
            >
              {{ tag }}
            </el-tag>
          </div>
          <div v-if="job.skillGap.length" class="tag-group">
            <span class="tag-label gap">缺口</span>
            <el-tag
              v-for="tag in job.skillGap.slice(0, 6)"
              :key="tag"
              size="small"
              type="danger"
              effect="plain"
            >
              {{ tag }}
            </el-tag>
          </div>
        </div>

        <div class="recommend-signals">
          <span :class="signalClass(job.salaryMatch)"
            >薪资{{ job.salaryMatch ? '匹配' : '待评估' }}</span
          >
          <span :class="signalClass(job.locationMatch)"
            >地点{{ job.locationMatch ? '匹配' : '待协商' }}</span
          >
          <span :class="signalClass(job.experienceMatch)"
            >经验{{ job.experienceMatch ? '合适' : '有偏差' }}</span
          >
        </div>

        <div class="job-actions">
          <el-button size="small" @click="$emit('detail', job)">查看详情</el-button>
          <el-button size="small" @click="$emit('pipeline', job)">
            {{ pipelineStatusText(job) || '加入流程' }}
          </el-button>
          <el-button size="small" @click="$emit('compare', job)">
            {{ comparedUids.includes(job.uid) ? '取消对比' : '加入对比' }}
          </el-button>
          <el-button size="small" @click="$emit('shortlist', job)">
            {{ isShortlisted(job) ? '已在清单' : '加入清单' }}
          </el-button>
          <el-button size="small" type="primary" @click="$emit('analyze', job)">直接分析</el-button>
        </div>
      </div>
    </article>
  </div>

  <el-empty
    v-else
    :description="
      resumeSelected
        ? '还没有足够贴合的推荐结果，可以先补充岗位池。'
        : '先选择一份简历，再获取推荐岗位。'
    "
  />
</template>

<script setup>
import { Loading, OfficeBuilding } from '@element-plus/icons-vue'
import { priorityTagType } from '@/utils/statusTone'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import { recommendTagType, signalClass } from '@/features/jobs/lib/jobModel'

/* 智能推荐面板：D45 从 JobSearch.vue 搬出来。推荐列表与筛选都归页面的 useJobRecommend 那条链
   （那张链的分数还会随搜索表单的城市筛选即时重算，是 §10.18 记着的不对称），面板只吃值与发事件。
   两个规则留在链上、以函数 prop 传进来的原因与搜索面板一样：`isShortlisted` 按 uid 或 id 匹配，
   抄进面板就是两份真相。 */
const props = defineProps({
  jobs: {
    type: /** @type {import('vue').PropType<import('../lib/jobModel').Job[]>} */ (Array),
    required: true,
  },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  filters: {
    type: /** @type {import('vue').PropType<Record<string, string>>} */ (Object),
    required: true,
  },
  resumeName: { type: String, default: '' },
  resumeSelected: { type: [Number, String, Boolean], default: null },
  comparedUids: {
    type: /** @type {import('vue').PropType<string[]>} */ (Array),
    default: () => [],
  },
  isShortlisted: { type: Function, required: true },
  pipelineStatusText: { type: Function, required: true },
})

defineEmits(['update:filters', 'refresh', 'detail', 'pipeline', 'compare', 'shortlist', 'analyze'])

/** 两个筛选框不能就地改父页面的 ref（`vue/no-mutating-props`），改动整份抛回去 */
function patch(key, value) {
  return { ...props.filters, [key]: value || '' }
}
</script>

<style scoped>
/* 这些规则是从 JobSearch.vue 的样式里**复制**来的：scoped 样式不跨组件边界，
   而父页面那份一条都没删（D44 的结论：静态切分会把 signalClass() 这类动态类名误判成死选择器，
   删掉就是没人能看见的视觉回归）。代价记在棘轮的色值预算里。 */
.priority-reason,
.toolbar-sub,
.recommend-reason {
  color: var(--app-muted);
}

.recommend-toolbar {
  margin: 0;
  font-size: 20px;
}

.recommend-toolbar {
  margin-bottom: 14px;
}

.recommend-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.mini-input {
  width: 140px;
}

.state-box {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 140px;
  justify-content: center;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  color: var(--app-muted);
}

.recommend-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.recommend-card {
  position: relative;
  padding: 18px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  /* 与 `SearchPane.vue` 的 `.job-shell` 同批：这一整块自 `a55498c` 起被包进一个选择器写着
     `null` 的嵌套块而全死，D105 拆壳后这条第一次真的上屏。深色作用域里留字面量就是白卡，
     所以换成 `var(--app-surface)`。 */
  background: var(--app-surface);
}

.job-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.job-company {
  margin: 8px 0 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.job-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.job-facts.compact,
.priority-row.compact {
  margin-top: 10px;
}

.fact-emphasis {
  color: var(--app-primary, #7c6cff);
  font-weight: 700;
}

.recommend-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.priority-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.job-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.recommend-card {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 14px;
}

.recommend-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(180deg, var(--app-text, #18222f), #304151);
  color: #fff;
  min-height: 94px;
}

.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.tag-label {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 999px;
}

.tag-label.ok {
  background: rgba(44, 143, 105, 0.12);
  color: var(--app-success, #14b8a6);
}

.tag-label.gap {
  background: rgba(217, 111, 50, 0.12);
  color: var(--app-warning, #7c6cff);
}

.recommend-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
@media (max-width: 1180px) {
  .recommend-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .recommend-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .mini-input {
    width: 100%;
  }
}
</style>
