<template>
  <div class="warehouse-toolbar">
    <el-input
      :model-value="filters.keyword"
      clearable
      size="small"
      class="warehouse-search"
      placeholder="按职位名、公司、城市筛选本地 JD"
      @update:model-value="(value) => $emit('update:filters', patch('keyword', value))"
    />
    <el-select
      :model-value="filters.source"
      placement="bottom-start"
      :fallback-placements="['bottom-start']"
      clearable
      size="small"
      placeholder="来源"
      @update:model-value="(value) => $emit('update:filters', patch('source', value))"
    >
      <el-option label="全部来源" value="" />
      <el-option label="导入" value="imported" />
      <el-option label="爬取" value="crawled" />
      <el-option label="API" value="api" />
      <el-option label="手工创建" value="manual" />
    </el-select>
    <el-select
      :model-value="filters.industry"
      placement="bottom-start"
      :fallback-placements="['bottom-start']"
      clearable
      size="small"
      placeholder="行业"
      @update:model-value="(value) => $emit('update:filters', patch('industry', value))"
    >
      <el-option label="互联网 / 科技" value="互联网" />
      <el-option label="人工智能" value="人工智能" />
      <el-option label="电商" value="电商" />
      <el-option label="通信" value="通信" />
    </el-select>
    <el-button text @click="$emit('refresh')">刷新仓库</el-button>
  </div>

  <div v-if="loading" class="state-box">
    <el-icon class="is-loading"><Loading /></el-icon>
    <span>正在加载本地岗位仓库...</span>
  </div>

  <div v-else-if="jobs.length" class="warehouse-list">
    <div v-for="job in jobs" :key="job.uid" class="warehouse-item">
      <div class="warehouse-main">
        <div class="warehouse-title-row">
          <h3>{{ job.title }}</h3>
          <el-tag size="small" effect="plain">{{ sourceText(job.source) }}</el-tag>
          <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
            {{ job.priorityLabel }}
          </el-tag>
        </div>
        <p class="warehouse-meta">
          {{ job.company }} / {{ job.location || '地点待补充' }} / {{ job.salary }}
        </p>
        <p class="warehouse-summary">{{ job.summary || '暂无摘要' }}</p>
      </div>
      <div class="warehouse-actions">
        <el-button size="small" @click="$emit('detail', job)">详情</el-button>
        <el-button size="small" @click="$emit('pipeline', job)">
          {{ pipelineStatusText(job) || '加入流程' }}
        </el-button>
        <el-button size="small" @click="$emit('compare', job)">
          {{ comparedUids.includes(job.uid) ? '取消对比' : '加入对比' }}
        </el-button>
        <el-button size="small" @click="$emit('prefill', job)">带入分析</el-button>
        <el-button size="small" type="primary" @click="$emit('analyze', job)">分析</el-button>
      </div>
    </div>
  </div>

  <!-- 失败态与"仓库是空的"是两回事 -->
  <AppLoadError
    v-else-if="error"
    title="本地岗位仓库加载失败"
    :message="error"
    @retry="$emit('refresh')"
  />

  <el-empty v-else description="岗位仓库还是空的，可以先搜索外部岗位或导入演示数据。" />
</template>

<script setup>
import { Loading } from '@element-plus/icons-vue'
import { priorityTagType } from '@/utils/statusTone'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import { sourceText } from '@/features/jobs/lib/jobModel'

/* 岗位仓库面板：D44 从 JobSearch.vue 搬出来，状态仍归页面的 useJobWarehouse 那条链。
   三个筛选框不能就地改 `filters`（`vue/no-mutating-props` 会拦，而且父页面的 `filteredLocalJobs`
   是从同一个 ref 算的），所以每次改动往上抛一份新对象，由父页面写回那个 ref。
   「加入流程」按钮的文案是流程链的事实，不归这里算，所以 `pipelineStatusText` 作为函数 prop 传进来——
   与 D36 的 `JobCompareDialog` 同一个做法。 */
const props = defineProps({
  jobs: { type: Array, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  filters: { type: Object, required: true },
  comparedUids: { type: Array, default: () => [] },
  pipelineStatusText: { type: Function, required: true },
})

defineEmits(['update:filters', 'refresh', 'detail', 'pipeline', 'compare', 'prefill', 'analyze'])

/** el-select / el-input 清空时给的是 undefined 或 null，筛选项的"没筛"约定是空串 */
function patch(key, value) {
  return { ...props.filters, [key]: value || '' }
}
</script>

<style scoped>
/* 以下每条都来自 JobSearch.vue 的选择器组，final 复合命中的才是本面板的：父页面那份样式**刻意留着没删**（静态切分看不见 `:class="signalClass(...)"` 这类动态类名，删错了就是没人能看见的视觉回归）。 */
.warehouse-toolbar {
  margin: 0;
  font-size: 20px;
}

.warehouse-summary {
  color: var(--app-muted);
}

.warehouse-toolbar {
  margin-bottom: 14px;
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

.warehouse-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.warehouse-meta {
  margin: 8px 0 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.warehouse-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.warehouse-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 16px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.warehouse-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
}

.warehouse-search {
  width: 260px;
}

@media (max-width: 1180px) {
  .warehouse-item {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .warehouse-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .warehouse-search {
    width: 100%;
  }
}
</style>
