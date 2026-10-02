<script setup>
import { priorityTagType } from '@/utils/statusTone'

/* 岗位对比弹窗：从 JobSearch.vue 搬出来的一块纯展示浮层。
   `statusText` 是一个函数 prop——投递阶段标签只有父页面那份 pipeline 状态知道，
   把它复制成 job 上的字段会造出一份会过期的第二真相，所以让调用方把唯一来源传进来。 */
const props = defineProps({
  jobs: {
    type: /** @type {import('vue').PropType<import('../lib/jobModel').Job[]>} */ (Array),
    default: () => [],
  },
  statusText: { type: Function, required: true },
})
const emit = defineEmits(['detail', 'pipeline', 'remove', 'analyze'])
const visible = defineModel({ type: Boolean })
</script>

<template>
  <el-dialog v-model="visible" width="980px" title="岗位对比">
    <div v-if="props.jobs.length" class="compare-grid">
      <div v-for="job in props.jobs" :key="job.uid" class="compare-card">
        <div class="compare-head">
          <h3>{{ job.title }}</h3>
          <el-tag :type="priorityTagType(job.priorityLabel)" effect="dark" size="small">
            {{ job.priorityLabel }} · {{ job.priorityScore }}
          </el-tag>
        </div>
        <p class="compare-company">{{ job.company }}</p>
        <div class="compare-meta">
          <span>{{ job.salary }}</span>
          <span>{{ job.location || '地点待补充' }}</span>
          <span>{{ job.experience || '经验不限' }}</span>
        </div>
        <p class="compare-reason">{{ job.priorityReason }}</p>
        <div class="compare-tags" v-if="job.skillTags?.length">
          <el-tag v-for="tag in job.skillTags.slice(0, 8)" :key="tag" size="small" effect="plain">{{
            tag
          }}</el-tag>
        </div>
        <p class="compare-summary">{{ job.summary || '暂无摘要' }}</p>
        <div class="compare-actions">
          <el-button size="small" @click="emit('detail', job)">详情</el-button>
          <el-button size="small" @click="emit('pipeline', job)">
            {{ props.statusText(job) || '加入流程' }}
          </el-button>
          <el-button size="small" @click="emit('remove', job)">移出对比</el-button>
          <el-button size="small" type="primary" @click="emit('analyze', job)">分析</el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.compare-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.compare-card {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid var(--app-line);
}

.compare-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.compare-head h3 {
  margin: 0;
  font-size: 18px;
}

/* 这三条在 JobSearch.vue 里原本和 .rewrite-note/.priority-reason 共用一条规则；
   那些类留在父组件，所以只能把声明复制过来，不能整条搬走。 */
.compare-reason,
.compare-summary,
.compare-company {
  color: var(--app-muted);
}

.compare-company {
  margin: 8px 0 0;
}

.compare-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.compare-meta span {
  padding: 5px 8px;
  border-radius: 999px;
  background: var(--app-bg);
  font-size: 12px;
}

.compare-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.compare-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

@media (max-width: 1180px) {
  /* 同样是从父级那条 8 类共用的媒体查询里拆出来的一份 */
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>
