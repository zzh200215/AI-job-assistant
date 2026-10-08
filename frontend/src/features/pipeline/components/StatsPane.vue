<script setup>
import { computed } from 'vue'

import { ArrowRight } from '@element-plus/icons-vue'
import {
  conversionRate as boardConversionRate,
  funnelPercent as boardFunnelPercent,
  funnelRows,
  rejectionRate as boardRejectionRate,
  stageToRate as boardStageToRate,
} from '@/features/pipeline/lib/pipelineBoard'

/* 转化分析与简历版本表现这两块面板，D62 从 PipelineKanban.vue 搬出来。
   归属拍法沿用 D44 的 A 方案：**数据留在页面**——`counts` 由页面的看板算出，
   `versionPerformance` 是页面另一条请求，`avgResponseDays` 要读时间（D57 把 `now` 做成入参
   就是为了这件事：面板自己调 Date.now() 会把那条判据又变回测不出来）。
   面板没有写操作，所以一个 emit 都没有。
   下面这五个包装是**跟着模板一起搬过来的**（模板那 86 行一个字没改，除了一件：`showStats`
   由页面统一挡住面板根节点，所以两块各自的 `v-if` 里少掉这一项）。规则仍然只在
   `lib/pipelineBoard.js` 里有一份，这里是把 props 递进去的那只手——同 D52 的口径。 */
const props = defineProps({
  counts: {
    type: /** @type {import('vue').PropType<import('../lib/pipelineBoard').StageCounts>} */ (
      Object
    ),
    required: true,
  },
  totalCards: { type: Number, required: true },
  avgResponseDays: { type: [String, Number], required: true },
  versionPerformance: {
    type: /** @type {import('vue').PropType<import('../lib/pipelineBoard').VersionPerformance[]>} */ (
      Array
    ),
    default: () => [],
  },
})

const funnelData = computed(() => funnelRows(props.counts))
const rejectionRate = computed(() => boardRejectionRate(props.counts, props.totalCards))
const conversionRate = (stage) => boardConversionRate(props.counts, props.totalCards, stage)
const funnelPercent = (count) => boardFunnelPercent(count, funnelData.value)
const stageToRate = (from, to) => boardStageToRate(props.counts, from, to)
</script>

<template>
  <!-- 投递统计面板 -->
  <div v-if="totalCards > 0" class="stats-panel">
    <div class="stats-header">
      <h3>投递转化分析</h3>
    </div>
    <div class="stats-body">
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-value">{{ totalCards }}</span>
          <span class="stat-label">总投递</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ conversionRate('applied') }}%</span>
          <span class="stat-label">投递率</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ conversionRate('interview') }}%</span>
          <span class="stat-label">面试率</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ conversionRate('offer') }}%</span>
          <span class="stat-label">Offer率</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ rejectionRate }}%</span>
          <span class="stat-label">拒绝率</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ avgResponseDays }}</span>
          <span class="stat-label">平均响应(天)</span>
        </div>
      </div>
      <div class="stats-funnel">
        <div v-for="(stage, idx) in funnelData" :key="stage.key" class="funnel-bar-wrapper">
          <div class="funnel-label-row">
            <span class="funnel-label">{{ stage.label }}</span>
            <span class="funnel-count">{{ stage.count }}</span>
          </div>
          <div class="funnel-track">
            <div
              class="funnel-fill"
              :style="{ width: funnelPercent(stage.count) + '%' }"
              :class="'fill-' + stage.accent"
            />
          </div>
          <div v-if="idx < funnelData.length - 1" class="funnel-arrow">
            <el-icon><ArrowRight /></el-icon>
            <span class="funnel-rate">{{ stageToRate(stage.key, funnelData[idx + 1]?.key) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-if="versionPerformance.length" class="version-performance">
    <div class="version-performance-title">
      <div>
        <span class="section-kicker">Resume attribution</span>
        <h3>简历版本表现</h3>
      </div>
      <span>按已投递记录计算</span>
    </div>
    <div class="version-performance-list">
      <div
        v-for="item in versionPerformance"
        :key="item.resume_version_id"
        class="version-performance-row"
      >
        <div class="version-name">
          <strong>{{ item.label }}</strong>
          <span>{{ item.submitted }} 次投递</span>
        </div>
        <div class="version-metric">
          <strong>{{ item.interview_rate }}%</strong><span>面试率</span>
        </div>
        <div class="version-metric">
          <strong>{{ item.offer_rate }}%</strong><span>Offer 率</span>
        </div>
        <div class="version-outcomes">
          <span>{{ item.interviews }} 面试</span><span>{{ item.offers }} Offer</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 这 35 条规则是从页面**原文复制**过来的（脚本切片见 D62 的过程账）。
   不删页面那一份有两个实测理由：`.funnel-fill` 的配色走 `'fill-' + stage.accent`
   这种动态类名（D44 量过：静态切分会把 6 条 fill-* 整条切没），以及 scoped 样式不跨组件。
   代价记在 D62：这一页的色值与 css 分块都会涨。 */

.version-performance {
  margin-bottom: 16px;
  border: 1px solid var(--app-line);
  border-top: 3px solid var(--app-primary);
  border-radius: 8px;
  background: var(--app-surface-strong);
}

.version-performance-title {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--app-line);
}

.version-performance-title h3 {
  margin: 2px 0 0;
  font-size: 15px;
}

.version-performance-title > span,
.version-name span,
.version-metric span,
.version-outcomes {
  color: var(--app-muted);
  font-size: 12px;
}

.section-kicker {
  color: var(--app-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.version-performance-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.version-performance-row {
  display: grid;
  grid-template-columns: minmax(105px, 1fr) auto auto;
  gap: 14px;
  align-items: center;
  padding: 14px 16px;
  border-right: 1px solid var(--app-line);
  border-bottom: 1px solid var(--app-line);
}

.version-name,
.version-metric {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.version-name strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-metric {
  align-items: flex-end;
}

.version-metric strong {
  color: var(--app-primary);
  font-size: 17px;
}

.version-outcomes {
  grid-column: 1 / -1;
  display: flex;
  gap: 10px;
}

/* 统计面板 */
.stats-panel {
  background: var(--app-surface-strong);
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--app-line);
  box-shadow: var(--app-shadow-soft);
  overflow: hidden;
}

.stats-header {
  padding: 14px 20px;
  border-bottom: 1px solid var(--app-line);
}

.stats-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.stats-body {
  padding: 16px 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-item {
  text-align: center;
  padding: 12px 8px;
  border-radius: 6px;
  background: var(--app-bg);
}

.stat-value {
  display: block;
  font-size: 24px;
  font-weight: 800;
  color: var(--app-primary);
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: var(--app-muted);
  margin-top: 4px;
}

.stats-funnel {
  display: flex;
  align-items: center;
  gap: 8px;
}

.funnel-bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.funnel-label-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.funnel-label {
  color: var(--app-muted);
}

.funnel-count {
  font-weight: 700;
  color: var(--app-text);
}

.funnel-track {
  height: 24px;
  background: var(--el-fill-color);
  border-radius: 6px;
  overflow: hidden;
}

.funnel-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.4s ease;
}

.fill-slate {
  background: #94a3b8;
}

.fill-blue {
  background: var(--app-primary);
}

.fill-amber {
  background: var(--app-warning);
}

.fill-violet {
  background: var(--app-violet);
}

.fill-green {
  background: var(--app-success);
}

/* `.fill-red` 曾在这里（`var(--app-danger)`）：漏斗的色走 `'fill-' + stage.accent`，而
   `funnelRows()` 把列筛成 todo / applied / written_test / interview / offer 五段，rejected 与
   withdrawn 永远进不来 ⇒ 没人能发出它。D151 现取：五段全在屏（slate/blue/amber/violet/green），
   这条 matched=0，从活样式表删掉后整屏 423 个元素 0 处差异。域与这条判据见 constants/states.js 的
   FUNNEL_ACCENTS。*/

.funnel-arrow {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: var(--app-muted);
  margin-top: 2px;
}

.funnel-rate {
  color: var(--app-primary);
  font-weight: 600;
}
</style>
