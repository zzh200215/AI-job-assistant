<template>
  <div class="result-toolbar">
    <div>
      <strong>{{ jobs.length }}</strong>
      <span class="toolbar-sub">个岗位</span>
      <span v-if="savedCount" class="toolbar-meta">其中 {{ savedCount }} 个已落库</span>
    </div>
    <div class="toolbar-actions">
      <el-button size="small" plain :disabled="compareCount < 2" @click="$emit('open-compare')">
        对比 {{ compareCount }} 个岗位
      </el-button>
      <el-tag v-if="resultMode && !isDemo" type="info" effect="plain">{{ stateText }}</el-tag>
      <el-tag v-if="isDemo" type="warning" effect="plain">当前为演示数据</el-tag>
      <el-tag v-if="searchError && !isDemo" type="danger" effect="plain">{{ searchError }}</el-tag>
    </div>
  </div>

  <div v-if="hasSearched" class="result-source-note" :class="bannerClass">
    <strong>{{ bannerTitle }}</strong>
    <span>{{ bannerDesc }}</span>
  </div>

  <div v-if="searching" class="state-box">
    <el-icon class="is-loading"><Loading /></el-icon>
    <span>{{ searchHint }}</span>
  </div>

  <div v-else-if="jobs.length" class="result-grid">
    <article v-for="job in jobs" :key="job.uid" class="job-shell">
      <div class="job-shell-top">
        <div>
          <div class="job-title-row">
            <h3>{{ job.title }}</h3>
            <span class="source-pill">{{ sourceText(job.source) }}</span>
            <span v-if="job.local" class="local-pill">已落库</span>
          </div>
          <p class="job-company">
            <el-icon><OfficeBuilding /></el-icon>
            {{ job.company }}
          </p>
        </div>
        <button type="button" class="bookmark-btn" @click="$emit('shortlist', job)">
          {{ isShortlisted(job) ? '移出清单' : '加入清单' }}
        </button>
      </div>

      <div class="job-facts">
        <span class="fact-emphasis">{{ job.salary }}</span>
        <span>{{ job.location || '地点待补充' }}</span>
        <span>{{ job.experience || '经验不限' }}</span>
        <span>{{ job.education || '学历不限' }}</span>
      </div>

      <div class="priority-row">
        <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
          {{ job.priorityLabel }} · {{ job.priorityScore }}
        </el-tag>
        <span class="priority-reason">{{ job.priorityReason }}</span>
      </div>

      <div class="job-tags" v-if="job.skillTags.length">
        <el-tag v-for="tag in job.skillTags.slice(0, 8)" :key="tag" size="small" effect="plain">
          {{ tag }}
        </el-tag>
      </div>

      <p class="job-summary">{{ job.summary || '暂无职位摘要' }}</p>

      <div class="job-actions">
        <el-button size="small" @click="$emit('detail', job)">查看详情</el-button>
        <el-button size="small" @click="$emit('pipeline', job)">
          {{ pipelineStatusText(job) || '加入流程' }}
        </el-button>
        <el-button size="small" @click="$emit('compare', job)">
          {{ comparedUids.includes(job.uid) ? '取消对比' : '加入对比' }}
        </el-button>
        <el-button size="small" @click="$emit('prefill', job)">带入分析</el-button>
        <el-button size="small" type="primary" @click="$emit('analyze', job)">直接分析</el-button>
      </div>
    </article>
  </div>

  <el-empty v-else-if="hasSearched" description="没有找到更贴近的岗位，换个关键词或城市试试。" />
  <el-empty v-else description="先发起一次搜索，系统会把结果同步到你的岗位工作台。" />
</template>

<script setup>
import { Loading, OfficeBuilding } from '@element-plus/icons-vue'
import { priorityTagType } from '@/utils/statusTone'
import { sourceText } from '@/features/jobs/lib/jobModel'

/* 实时搜索结果面板：D45 从 JobSearch.vue 搬出来。列表、筛选、四态口径都在页面的 useJobSearch 那条链里，
   这里只吃普通值 + 两个"规则在链上"的函数 prop：
   `pipelineStatusText` 读的是投递链的记录，`isShortlisted` 按 uid **或** id 匹配（搜索页与仓库页给同一个
   岗位造的 uid 前缀不同），把这两条规则抄进面板就会造成两份真相，所以函数传进来。
   对比那条只需要 uid，所以传的是 `comparedUids` 数组。 */
defineProps({
  jobs: { type: Array, required: true },
  searching: { type: Boolean, default: false },
  hasSearched: { type: Boolean, default: false },
  searchHint: { type: String, default: '' },
  searchError: { type: String, default: '' },
  isDemo: { type: Boolean, default: false },
  resultMode: { type: String, default: '' },
  savedCount: { type: Number, default: 0 },
  stateText: { type: String, default: '' },
  bannerTitle: { type: String, default: '' },
  bannerDesc: { type: String, default: '' },
  bannerClass: { type: String, default: '' },
  compareCount: { type: Number, default: 0 },
  comparedUids: { type: Array, default: () => [] },
  isShortlisted: { type: Function, required: true },
  pipelineStatusText: { type: Function, required: true },
})

defineEmits(['open-compare', 'detail', 'pipeline', 'compare', 'shortlist', 'prefill', 'analyze'])
</script>

<style scoped>
/* 这些规则是从 JobSearch.vue 的样式里**复制**来的：scoped 样式不跨组件边界，
   而父页面那份一条都没删（D44 的结论：静态切分会把 signalClass() 这类动态类名误判成死选择器，
   删掉就是没人能看见的视觉回归）。代价记在棘轮的色值预算里。 */
null {
  .result-source-note {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 16px;
    padding: 12px 14px;
    border-radius: var(--app-radius-xs, 8px);
    border: 1px solid var(--app-line);
    background: rgba(255, 255, 255, 0.58);
  }

  .result-source-note.is-loading {
    border-color: rgba(124, 108, 255, 0.16);
  }

  .priority-reason,
  .toolbar-sub,
  .toolbar-meta,
  .job-summary {
    color: var(--app-muted);
  }

  .bookmark-btn:hover {
    transform: translateY(-1px);
    border-color: var(--app-line);
  }

  .result-toolbar {
    margin: 0;
    font-size: 20px;
  }

  .result-toolbar {
    margin-bottom: 14px;
  }

  .toolbar-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
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

  .result-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }

  .job-shell {
    position: relative;
    padding: 18px;
    border-radius: var(--app-radius-sm, 12px);
    border: 1px solid var(--app-line);
    background: rgba(255, 255, 255, 0.98);
  }

  .job-shell-top {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
  }

  .job-title-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }

  .source-pill,
  .local-pill {
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 12px;
  }

  .source-pill {
    background: rgba(45, 108, 223, 0.1);
    color: var(--app-primary, #3b82f6);
  }

  .local-pill {
    background: rgba(44, 143, 105, 0.12);
    color: var(--app-success, #14b8a6);
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

  .fact-emphasis {
    color: var(--app-primary, #7c6cff);
    font-weight: 700;
  }

  .job-tags {
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

  .job-summary {
    margin: 14px 0 0;
    line-height: 1.7;
    min-height: 48px;
  }

  .job-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
  }

  .bookmark-btn {
    border: 1px solid var(--app-line);
    background: var(--app-surface-strong);
    border-radius: var(--app-radius-xs, 8px);
    cursor: pointer;
    transition: 0.2s ease;
  }

  .bookmark-btn {
    padding: 8px 12px;
  }
}
@media (max-width: 1180px) {
  .result-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .result-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
