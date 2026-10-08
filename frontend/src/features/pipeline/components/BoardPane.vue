<script setup>
import { ref } from 'vue'

import {
  Clock,
  Coin,
  Histogram,
  MoreFilled,
  OfficeBuilding,
  Search,
  WarningFilled,
} from '@element-plus/icons-vue'
import { monthDay } from '@/utils/format/date'
import { followUpDays, followUpLevel, needsFollowUp } from '@/features/pipeline/lib/pipelineBoard'

/* 看板列，D63 从 PipelineKanban.vue 搬出来。归属仍是 D44 的 A 方案，但这一块和统计那块
   不一样：**它有写操作**，所以三条出口全部走 emit——
     · `command(cmd, card)`：卡片右上那个下拉（详情 / AI / 模拟面试 / 标记拒绝 / 放弃 / 删除），
       页面收到后交给 D58 那份共用分发器 `runCardCommand`；
     · `move(card, stage)`：拖到某一列。被拖的是哪张卡是**这一块的本地状态**（dragCard 搬进来了），
       而"要不要发这一发、失败怎么回滚、乐观更新改哪个数组"留在页面——那涉及写 `kanban`，
       面板不该改 props；
     · `go-recommend` / `open-add`：空态里那两个按钮。
   跟进提醒（几天没回复、什么颜色）按 D57 的口径吃入参 `now`：页面在渲染时把 `now()` 递进来，
   时机和搬之前一模一样（也是每次渲染现取），面板自己不调 Date.now()。
   `:disabled="writeBusy"` 那两个下拉是 D59 那把锁的一部分：锁在页面，这里只是把值传进来。 */
defineProps({
  kanban: {
    type: /** @type {import('vue').PropType<import('../lib/pipelineBoard').Kanban>} */ (Object),
    required: true,
  },
  columns: {
    type: /** @type {import('vue').PropType<import('../lib/pipelineBoard').BoardColumn[]>} */ (
      Array
    ),
    required: true,
  },
  totalCards: { type: Number, required: true },
  writeBusy: { type: Boolean, required: true },
  now: { type: Number, required: true },
})

const emit = defineEmits(['command', 'move', 'go-recommend', 'open-add'])

const dragCard = ref(null)

function onDragStart(e, card) {
  dragCard.value = card
  e.dataTransfer.effectAllowed = 'move'
}

function onDrop(targetStage) {
  if (!dragCard.value) return
  emit('move', dragCard.value, targetStage)
  dragCard.value = null
}
</script>

<template>
  <div class="kanban-board">
    <el-empty v-if="totalCards === 0" :image-size="120" description="还没有任何投递记录">
      <template #description>
        <span>去岗位推荐中一键加入看板，或手动新增投递记录</span>
      </template>
      <el-button type="primary" @click="emit('go-recommend')">
        <el-icon><Search /></el-icon> 去岗位推荐
      </el-button>
      <el-button @click="emit('open-add')">手动新增</el-button>
    </el-empty>

    <template v-else>
      <div
        v-for="col in columns"
        :key="col.key"
        class="kanban-col"
        :class="col.accent"
        @dragover.prevent
        @drop="onDrop(col.key)"
      >
        <div class="col-header">
          <div class="col-dot" :class="'dot-' + col.accent" />
          <h3>{{ col.label }}</h3>
          <span class="col-count">{{ (kanban[col.key] || []).length }}</span>
        </div>

        <div class="col-body">
          <div
            v-for="card in kanban[col.key] || []"
            :key="card.id"
            class="kanban-card"
            draggable="true"
            @dragstart="onDragStart($event, card)"
          >
            <div class="card-top">
              <strong class="card-title">{{ card.title || card.company || '未命名岗位' }}</strong>
              <el-dropdown
                trigger="click"
                :disabled="writeBusy"
                @command="(cmd) => emit('command', cmd, card)"
              >
                <el-icon class="card-more"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="detail">查看详情</el-dropdown-item>
                    <el-dropdown-item command="analyze">AI分析</el-dropdown-item>
                    <el-dropdown-item v-if="col.key === 'interview'" command="interview"
                      >模拟面试</el-dropdown-item
                    >
                    <el-dropdown-item
                      command="reject"
                      divided
                      style="color: color-mix(in srgb, var(--app-danger), white 20%)"
                      >标记拒绝</el-dropdown-item
                    >
                    <el-dropdown-item command="abandon" style="color: var(--app-muted)"
                      >放弃</el-dropdown-item
                    >
                    <el-dropdown-item
                      command="delete"
                      style="color: color-mix(in srgb, var(--app-danger), white 20%)"
                      >删除</el-dropdown-item
                    >
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <div v-if="card.company" class="card-company">
              <el-icon><OfficeBuilding /></el-icon> {{ card.company }}
            </div>

            <div class="card-meta">
              <span v-if="card.salary_range"
                ><el-icon><Coin /></el-icon> {{ card.salary_range }}</span
              >
              <span v-if="card.match_score" class="card-score">
                <el-icon><Histogram /></el-icon> {{ Math.round(card.match_score) }}分
              </span>
            </div>
            <el-tag
              v-if="card.resume_version_label"
              class="resume-version-tag"
              size="small"
              effect="plain"
            >
              {{ card.resume_version_label }}
            </el-tag>

            <div v-if="card.interview_at && col.key === 'interview'" class="card-interview">
              <el-icon><Clock /></el-icon>
              {{ monthDay(card.interview_at) }}
            </div>

            <div class="card-footer">
              <!-- 跟进提醒 -->
              <div
                v-if="needsFollowUp(card)"
                :class="'card-follow follow-' + followUpLevel(card, now)"
              >
                <el-icon><WarningFilled /></el-icon> {{ followUpDays(card, now) }}天未回复
              </div>
              <span class="card-date">{{ monthDay(card.create_time) }}</span>
              <el-tag v-if="card.source" size="small" type="info">{{ card.source }}</el-tag>
            </div>
          </div>

          <div v-if="!(kanban[col.key] || []).length" class="col-empty">暂无{{ col.label }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 这 37 条是从页面**原文复制**的第二份（同 D44/D45/D51/D52/D62：scoped 不跨组件，
   而 `.follow-<level>`、`.dot-<accent>`、`.card-follow follow-<level>` 这些类名都是拼出来的，静态切分会整条切错）。页面那一份一条没删。 */

/* Board */
.kanban-board {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 16px;
}

.kanban-board {
  flex-wrap: wrap;
}

.kanban-col {
  min-width: 240px;
  max-width: 300px;
  flex: 1;
  background: var(--app-bg);
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--app-line);
  display: flex;
  flex-direction: column;
}

.kanban-col {
  max-width: none;
  min-width: 200px;
}

.kanban-col {
  min-width: 180px;
}

.col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-sm, 8px) var(--app-radius-sm, 8px) 0 0;
}

.col-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* `slate` 这一档原来是手挑的灰蓝，与下面 `gray` 那档几乎同值（现取 148,163,184 对 156,163,175）。
   它不进任何令牌族，所以在浅色主题下会跟着掉线（灰蓝压白只剩 2.3 上下）。换 `--app-muted`：
   深色工作台里作为图形压在列头 6.83 → 6.34（门槛 3:1，见 WCAG 1.4.11），且跟着主题走。
   StatsPane 的 `.fill-slate` 是同一档的另一份副本，两处一起换。 */
.dot-slate {
  background: var(--app-muted);
}

.dot-blue {
  background: var(--app-primary);
}

.dot-amber {
  background: var(--app-warning);
}

.dot-violet {
  background: var(--app-violet);
}

.dot-green {
  background: var(--app-success);
}

.dot-red {
  background: var(--app-danger);
}

.dot-gray {
  background: #9ca3af;
}

.col-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  flex: 1;
}

.col-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-muted);
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: var(--app-radius-xs, 8px);
}

.col-body {
  padding: 8px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}

.col-empty {
  text-align: center;
  padding: 24px 0;
  color: var(--app-muted);
  font-size: 13px;
}

/* Card */
.kanban-card {
  padding: 14px;
  border-radius: var(--app-radius-xs, 6px);
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  cursor: grab;
  transition:
    box-shadow 0.15s ease,
    transform 0.15s ease;
}

.kanban-card:hover {
  box-shadow: var(--app-shadow);
  transform: translateY(-1px);
}

.kanban-card:active {
  cursor: grabbing;
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-more {
  cursor: pointer;
  color: var(--app-muted);
  padding: 2px;
  border-radius: var(--app-radius-xs, 8px);
  flex-shrink: 0;
}

.card-company {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 13px;
  color: var(--app-muted);
}

.card-meta {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-muted);
}

.card-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-score {
  /* 实测 3.39：`--app-primary` 本体当文字压在卡片面上（12px 常规字重要 4.5）。
     抬一档与全仓"分数当文字读"那条口径一致（同一支蓝混白 25% → 5.08）。 */
  color: color-mix(in srgb, var(--app-primary), white 25%);
  font-weight: 600;
}

.card-interview {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: var(--app-radius-xs, 8px);
  /* 面试档那一条是紫底座：底换成 tone 混 `--app-bg`，前景按 /home 图标座量出的幅度混白
     （紫档直接压深底只有 2.92，抬到 34% 才 5.70）。 */
  background: color-mix(in srgb, var(--app-violet), var(--app-bg) 86%);
  color: color-mix(in srgb, var(--app-violet), white 34%);
  font-size: 12px;
  font-weight: 600;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--app-line);
}

.card-date {
  font-size: 11px;
  color: var(--app-muted);
}

/* 跟进提醒 */
.card-follow {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  margin-bottom: 4px;
}

.resume-version-tag {
  max-width: 100%;
  margin-top: 8px;
  /* §10.36(c)（D155）：这里原来是仓里那一族唯一还留着的手挑暗蓝，D148 收了同值的另一处
     （ListPane 的 `.version-cell`）却没收到这颗挂在 `<el-tag>` 上的座。D154 现量它压在 plain
     通道的底上是 2.56（12px / 500 的字，门槛 4.5）。换成与 `.score-tone--good` 文字档同一配方
     （品牌蓝混白 25%，D148 同一对量过 5.30），并在守卫的座豁免表里删掉这一条。 */
  color: color-mix(in srgb, var(--app-primary), white 25%);
}

/* 跟进状态那三枚药丸：原来每枚都是"手挑浅底 + 同色系浅字"，实测最差 2.10（`.follow-ok`
   浅绿底压绿字）——浅底压浅字与深色工作台里读不出内容，是同一件事的两种表现。
   统一走这一族的座配方（底 = tone 混 `--app-bg` 86%、字 = tone，红按实测幅度混白）。
   ListPane 里有一份同形状的副本（D44 那族"复制不切"），两处一起改。
   D149：这份副本原本还带着第四条 `.follow-interview`，而看板不发它——面试时间在这里走
   `.card-interview`（`BoardPane.vue:151` 的条件是 `card.interview_at && col.key === 'interview'`）。
   面试卡在场时它 matched=0，把规则从活样式表里删掉整屏 349 个元素 0 处差异，所以它是死样式，已删；
   值域由 `states.js` 的 FOLLOW_UP_LEVELS 与那条双向守卫钉住（ListPane 那份仍在发，别一起删）。 */
.follow-danger {
  background: color-mix(in srgb, var(--app-danger), var(--app-bg) 86%);
  color: color-mix(in srgb, var(--app-danger), white 20%);
}

.follow-warn {
  background: color-mix(in srgb, var(--app-warning), var(--app-bg) 86%);
  color: var(--app-warning);
}

.follow-ok {
  background: color-mix(in srgb, var(--app-success), var(--app-bg) 86%);
  color: var(--app-success);
}
</style>
