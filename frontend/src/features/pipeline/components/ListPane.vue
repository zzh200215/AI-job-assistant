<script setup>
import { MoreFilled, WarningFilled } from '@element-plus/icons-vue'
import { monthDayTime } from '@/utils/format/date'
import { MATCH_SCORE_BANDS, scoreToneClass } from '@/utils/scoreTone'
import {
  followUpDays,
  followUpLevel,
  needsFollowUp,
  stageLabel,
  stageTagType,
} from '@/features/pipeline/lib/pipelineBoard'

/* 列表视图（批量栏 + 11 列那张表），D64 从 PipelineKanban.vue 搬出来。归属和 D63 的看板列
   同一条判据：**行的数据、写与锁都留在页面**，面板只管画和把动作发出去——
     · `rows` 是页面的 `allCards`（看板对象扁平化来的），面板不自己拼；
     · `selectedCount` 只是"批量栏要不要出现 + 已选几项"那个数；勾选这件事由 el-table 自己管，
       面板把它的 selection-change 原样转发，页面拿行去算 id 集合；
     · 三颗批量按钮发 `batch-move(stage)`，取消选择发 `clear-selection`，行内的详情 / AI /
       下拉发 `command(cmd, row)`——详情与 AI 也走同一条 command，页面那头本来就是同一个
       `runCardCommand`（D58），搬之前那两个按钮是绕过分发器直接调 `openCardDetail` /
       `router.push` 的，字符串完全一致，所以这一路并进 command 是**少一条平行出口**，不是改行为；
     · `:disabled="writeBusy"` 那两个绑定吃页面的锁（D59）——批量三颗与行内下拉共用一把。
   跟进那颗和看板一样吃入参 `now`：页面在模板里 `:now="now()"`，每次渲染现取，与搬之前同时机。 */
defineProps({
  rows: {
    type: /** @type {import('vue').PropType<import('../lib/pipelineBoard').PipelineCard[]>} */ (
      Array
    ),
    required: true,
  },
  selectedCount: { type: Number, required: true },
  writeBusy: { type: Boolean, required: true },
  now: { type: Number, required: true },
})

const emit = defineEmits(['command', 'batch-move', 'clear-selection', 'selection-change'])
</script>

<template>
  <div class="list-view">
    <!-- 批量操作栏 -->
    <div v-if="selectedCount > 0" class="batch-bar">
      <span class="batch-info"
        >已选 <strong>{{ selectedCount }}</strong> 项</span
      >
      <el-button
        size="small"
        :loading="writeBusy"
        :disabled="writeBusy"
        @click="emit('batch-move', 'interview')"
        >批量移至面试</el-button
      >
      <el-button
        size="small"
        :loading="writeBusy"
        :disabled="writeBusy"
        @click="emit('batch-move', 'offer')"
        >批量移至Offer</el-button
      >
      <el-button
        size="small"
        :loading="writeBusy"
        :disabled="writeBusy"
        style="color: var(--app-danger)"
        @click="emit('batch-move', 'rejected')"
        >批量标记拒绝</el-button
      >
      <el-button size="small" text @click="emit('clear-selection')">取消选择</el-button>
    </div>

    <el-table
      :data="rows"
      style="width: 100%"
      @selection-change="(rows) => emit('selection-change', rows)"
      border
      stripe
      size="small"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column prop="title" label="岗位" min-width="160">
        <template #default="{ row }">
          <div class="list-title">{{ row.title || '未命名' }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="company" label="公司" width="120" />
      <el-table-column label="简历版本" min-width="130">
        <template #default="{ row }">
          <span v-if="row.resume_version_label" class="version-cell">{{
            row.resume_version_label
          }}</span>
          <span v-else class="follow-ok">未记录</span>
        </template>
      </el-table-column>
      <el-table-column label="阶段" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="stageTagType(row.stage)">{{ stageLabel(row.stage) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="跟进" width="100">
        <template #default="{ row }">
          <span v-if="needsFollowUp(row)" :class="'follow-' + followUpLevel(row, now)">
            <el-icon><WarningFilled /></el-icon> {{ followUpDays(row, now) }}天
          </span>
          <span v-else class="follow-ok">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="salary_range" label="薪资" width="100" />
      <el-table-column label="匹配度" width="80" align="center">
        <template #default="{ row }">
          <span
            v-if="row.match_score"
            :class="scoreToneClass(row.match_score, MATCH_SCORE_BANDS, 'score-level')"
            >{{ Math.round(row.match_score) }}分</span
          >
          <span v-else class="follow-ok">-</span>
        </template>
      </el-table-column>
      <el-table-column label="面试时间" width="110">
        <template #default="{ row }">
          <span v-if="row.interview_at" class="follow-interview">{{
            monthDayTime(row.interview_at)
          }}</span>
          <span v-else class="follow-ok">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="80" />
      <el-table-column label="创建时间" width="90">
        <template #default="{ row }">{{ monthDayTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click="emit('command', 'detail', row)">详情</el-button>
          <el-button text size="small" @click="emit('command', 'analyze', row)">AI</el-button>
          <el-dropdown
            trigger="click"
            :disabled="writeBusy"
            @command="(cmd) => emit('command', cmd, row)"
          >
            <el-button text size="small">
              <el-icon><MoreFilled /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="row.stage === 'interview'" command="interview"
                  >模拟面试</el-dropdown-item
                >
                <el-dropdown-item command="reject">标记拒绝</el-dropdown-item>
                <el-dropdown-item command="abandon">放弃</el-dropdown-item>
                <el-dropdown-item command="delete" divided style="color: var(--app-danger)"
                  >删除</el-dropdown-item
                >
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
/* 同 D44/D45/D51/D52/D62/D63：只复制不切。这 16 条是页面原文的第二份，页面那一条没删；
   `.follow-<level>` 与 `.score-level--<tone>` 都是拼出来的类名（`'follow-' + followUpLevel(...)`
   与 `scoreToneClass(..., 'score-level')`），静态切分会整条切错。 */

/* 列表视图 */
.list-view {
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--app-line);
  overflow: hidden;
}

.list-title {
  font-weight: 600;
  font-size: 14px;
}

/* 批量操作栏 */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  /* 这是**容器**（里面 `.batch-info` 的字色来自 `--app-text`，跟着主题走），所以用 92% 的一层
     淡色而不是图标座那 86%：底跟着 `--app-bg`，继承来的文字自动留在它该在的一侧。
     原来的组合是"主题浅字压浅色令牌底"，同一对令牌在 PromptTrace 那一列实测 1.04；
     **这一条自己没有上屏元素可量**（要勾选项才有 `.batch-bar`），属推导不是差分。 */
  background: color-mix(in srgb, var(--app-primary), var(--app-bg) 92%);
  border-bottom: 1px solid var(--app-line);
}

.batch-info {
  font-size: 13px;
  color: var(--app-text);
  margin-right: 8px;
}

.batch-info strong {
  color: var(--app-primary);
}

.version-cell {
  display: inline-block;
  max-width: 120px;
  overflow: hidden;
  color: #365c8d;
  text-overflow: ellipsis;
  vertical-align: bottom;
  white-space: nowrap;
}

.follow-danger {
  background: #fff3f0;
  color: #d46e6e;
}

.follow-warn {
  background: #fffaf1;
  color: #dc9c3f;
}

.follow-ok {
  background: #f0faf4;
  color: #67c23a;
}

.follow-interview {
  color: var(--app-violet);
  font-weight: 600;
}

.score-level {
  font-weight: 600;
}

.score-level--high {
  color: var(--app-score-high);
}

.score-level--good {
  color: var(--app-score-good);
}

.score-level--warn {
  color: var(--app-score-warn);
}

.score-level--risk {
  color: var(--app-score-risk);
}

.score-level--unknown {
  color: var(--app-score-unknown);
}
</style>
