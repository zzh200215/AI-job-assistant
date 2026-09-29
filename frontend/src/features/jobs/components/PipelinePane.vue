<template>
  <div class="pipeline-toolbar">
    <div class="recommend-left">
      <span class="toolbar-title">用一个看板推进真实投递流程</span>
      <span class="toolbar-sub"> {{ entries.length }} 条记录，{{ activeCount }} 条仍在推进 </span>
    </div>
    <div class="recommend-actions">
      <el-input
        :model-value="filters.keyword"
        @update:model-value="(value) => $emit('update:filters', patch('keyword', value))"
        clearable
        size="small"
        placeholder="搜索岗位、公司、备注或下一步动作"
        class="pipeline-search"
      />
      <el-select
        :model-value="filters.stage"
        @update:model-value="(value) => $emit('update:filters', patch('stage', value))"
        placement="bottom-start"
        :fallback-placements="['bottom-start']"
        size="small"
        class="pipeline-stage-select"
      >
        <el-option label="全部阶段" value="all" />
        <el-option
          v-for="stage in pipelineStages"
          :key="stage.key"
          :label="stage.label"
          :value="stage.key"
        />
      </el-select>
      <el-button text :disabled="!stats.rejected" @click="$emit('clear-rejected')">
        清理已淘汰
      </el-button>
    </div>
  </div>

  <div class="pipeline-overview">
    <button
      v-for="stage in pipelineStages"
      :key="stage.key"
      type="button"
      class="pipeline-stage-pill"
      :class="{ active: filters.stage === stage.key }"
      @click="
        $emit('update:filters', patch('stage', filters.stage === stage.key ? 'all' : stage.key))
      "
    >
      <strong>{{ stats[stage.key] || 0 }}</strong>
      <span>{{ stage.label }}</span>
    </button>
  </div>

  <div class="pipeline-board">
    <section v-for="stage in visibleStages" :key="stage.key" class="pipeline-column">
      <div class="pipeline-column-head">
        <div>
          <strong>{{ stage.label }}</strong>
          <small>{{ byStage[stage.key]?.length || 0 }} 个岗位</small>
        </div>
        <el-tag size="small" effect="plain">{{ stage.hint }}</el-tag>
      </div>
      <p class="pipeline-column-note">{{ stage.description }}</p>

      <div v-if="byStage[stage.key]?.length" class="pipeline-cards">
        <article v-for="entry in byStage[stage.key]" :key="entry.entryId" class="pipeline-card">
          <div class="pipeline-card-head">
            <div>
              <h3>{{ entry.title }}</h3>
              <p>{{ entry.company }} · {{ entry.salary }}</p>
            </div>
            <el-tag :type="priorityTagType(entry.priorityLabel)" effect="dark" size="small">
              {{ entry.priorityLabel || '跟进中' }}
            </el-tag>
          </div>

          <div class="pipeline-meta">
            <span>{{ entry.location || '地点待补充' }}</span>
            <span v-if="entry.resumeName">{{ entry.resumeName }}</span>
            <span>更新于 {{ compactDateTime(entry.updatedAt, '--') }}</span>
          </div>

          <el-input
            v-model="entry.nextAction"
            size="small"
            placeholder="下一步动作，例如：周四前完成定制简历"
            @change="$emit('touch', entry)"
          />

          <div class="pipeline-form-row">
            <el-date-picker
              v-model="entry.followUpAt"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              placeholder="下次跟进日期"
              class="pipeline-date"
              @change="$emit('touch', entry)"
            />
            <el-select
              :model-value="entry.stage"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              size="small"
              class="pipeline-stage-select"
              @change="(value) => $emit('update-stage', entry, value)"
            >
              <el-option
                v-for="option in pipelineStages"
                :key="option.key"
                :label="option.label"
                :value="option.key"
              />
            </el-select>
          </div>

          <el-input
            v-model="entry.note"
            type="textarea"
            :rows="3"
            resize="none"
            placeholder="记录内推、沟通反馈、风险点或面试结论"
            @change="$emit('touch', entry)"
          />

          <div class="pipeline-history" v-if="entry.stageHistory.length">
            <span>{{ pipelineHistoryText(entry.stageHistory) }}</span>
          </div>

          <div class="pipeline-actions">
            <el-button size="small" @click="$emit('open', entry)">详情</el-button>
            <el-button size="small" @click="$emit('prefill', pipelineEntryToJob(entry))"
              >带入分析</el-button
            >
            <el-button
              size="small"
              type="primary"
              @click="$emit('analyze', pipelineEntryToJob(entry))"
            >
              直接分析
            </el-button>
            <el-button text type="danger" @click="$emit('remove', entry.entryId)">移除</el-button>
          </div>
        </article>
      </div>

      <el-empty v-else :image-size="68" :description="stage.emptyText" />
    </section>
  </div>

  <AppLoadError v-if="error" title="跟进记录拉取失败" :message="error" @retry="$emit('refresh')" />
  <el-empty
    v-else-if="!entries.length"
    description="先从实时搜索、岗位仓库或智能推荐里把岗位加入流程，页面会自动保存你的跟进记录。"
  />
</template>

<script setup>
import { compactDateTime } from '@/utils/format/date'
import { priorityTagType } from '@/utils/statusTone'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import {
  pipelineEntryToJob,
  pipelineHistoryText,
  pipelineStages,
} from '@/features/jobs/lib/jobModel'

/* 投递流程面板：D44 从 JobSearch.vue 搬出来，数据仍归页面的 useJobPipeline 那条链——
 列表、分阶段计数、按阶段分组、可见阶段与筛选全部由父页面传进来，这里只发事件。
 两处要写清楚的既有形状：
 1) 卡片上的"下一步动作 / 下次跟进日期 / 备注"三个输入，写的仍是父页面链里的那几个 entry 对象。
    这不是本刀引入的：`vue/no-mutating-props` 不追进 v-for，所以它合法，但它是共享可变对象而不是
    单向数据流。要不要改成 emit 回写，是行为改动，不混在拆页里做。
 2) 筛选（关键词与阶段）走 update:filters 抛整份新对象，与仓库面板同一套做法。 */
const props = defineProps({
  entries: { type: Array, required: true },
  activeCount: { type: Number, default: 0 },
  stats: { type: Object, required: true },
  byStage: { type: Object, required: true },
  visibleStages: { type: Array, required: true },
  filters: { type: Object, required: true },
  error: { type: String, default: '' },
})

defineEmits([
  'update:filters',
  'refresh',
  'clear-rejected',
  'touch',
  'update-stage',
  'remove',
  'open',
  'prefill',
  'analyze',
])

/** 清空输入框给的是 undefined，而"没筛"在本页的约定是空串 */
function patch(key, value) {
  return { ...props.filters, [key]: value || '' }
}
</script>
<style scoped>
/* 同仓库面板：这些规则是从父页面**复制**来的，父页面那份保留；scoped 样式不跨组件边界，所以复制是必需的。 */
.toolbar-sub,
.pipeline-column-note,
.pipeline-meta {
  color: var(--app-muted);
}

.recommend-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.pipeline-toolbar,
.pipeline-form-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.pipeline-toolbar {
  justify-content: space-between;
  margin-bottom: 14px;
}

.pipeline-search {
  width: 260px;
}

.pipeline-stage-select {
  width: 150px;
}

.pipeline-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.pipeline-stage-pill {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.82);
}

.pipeline-stage-pill {
  text-align: left;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.pipeline-stage-pill:hover {
  transform: translateY(-1px);
  border-color: rgba(45, 108, 223, 0.28);
  box-shadow: 0 12px 24px rgba(21, 32, 43, 0.08);
}

.pipeline-board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}

.pipeline-column {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--app-line);
}

.pipeline-column-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.pipeline-column-note {
  margin: 8px 0 14px;
  line-height: 1.6;
  font-size: 13px;
}

.pipeline-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pipeline-card {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
}

.pipeline-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}

.pipeline-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12px;
}

.pipeline-form-row,
.pipeline-actions {
  margin-top: 10px;
}

.pipeline-date {
  flex: 1;
}

.pipeline-history {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.6;
}

.pipeline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 1180px) {
  .pipeline-overview {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .pipeline-toolbar,
  .pipeline-form-row {
    flex-direction: column;
    align-items: stretch;
  }

  .pipeline-search,
  .pipeline-stage-select,
  .pipeline-date {
    width: 100%;
  }
}
</style>
