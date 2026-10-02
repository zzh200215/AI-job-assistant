<template>
  <div v-if="loading" class="inline-loading">
    <el-icon class="is-loading" size="22"><Loading /></el-icon>
    <p>正在检索引用来源…</p>
  </div>
  <template v-else-if="references.length > 0 || analysisConfidence">
    <div v-if="analysisConfidence" class="rag-confidence">
      <div class="rag-confidence-main">
        <div class="rag-badge" :class="`badge-${analysisConfidence.level || 'low'}`">
          {{ analysisConfidence.score ?? 0 }}
        </div>
        <div class="rag-confidence-copy">
          <div class="rag-confidence-title">
            本次检索可信度
            <el-tag size="small" :type="confidenceTagType(analysisConfidence.level)">{{
              analysisConfidence.label || '-'
            }}</el-tag>
          </div>
          <div class="rag-confidence-summary">
            {{ analysisConfidence.summary || '暂无可信度说明' }}
          </div>
          <div v-if="referenceQuery" class="rag-confidence-query">
            检索查询：{{ referenceQuery }}
          </div>
        </div>
      </div>
      <div v-if="analysisConfidence.breakdown?.length" class="rag-breakdown">
        <div
          v-for="item in analysisConfidence.breakdown"
          :key="item.name"
          class="rag-breakdown-item"
        >
          <span>{{ item.name }}</span>
          <strong class="data-value">{{ item.score }}</strong>
          <em>{{ item.detail }}</em>
        </div>
      </div>
      <div v-if="analysisConfidence.risks?.length" class="rag-risk-list">
        <span class="rag-risk-label">风险提示</span>
        <span v-for="risk in analysisConfidence.risks" :key="risk" class="rag-risk-item">{{
          risk
        }}</span>
      </div>
    </div>
    <el-alert
      v-if="references.length > 0"
      title="本次分析参考了以下知识库文档"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />
    <el-collapse v-if="references.length > 0" v-model="openDocs">
      <el-collapse-item
        v-for="(doc, i) in references"
        :key="i"
        :title="`${doc.doc_title}  (${typeLabel(doc.doc_type)})`"
        :name="i"
      >
        <template #title>
          <div class="ref-title">
            <el-icon><Document /></el-icon>
            <span class="ref-doc-title">{{ doc.doc_title }}</span>
            <el-tag size="small" type="info" effect="plain">{{ typeLabel(doc.doc_type) }}</el-tag>
          </div>
        </template>
        <div class="ref-chunks">
          <div v-for="(chunk, j) in doc.chunks" :key="j" class="ref-chunk-item">
            <div class="ref-chunk-header">
              <span class="ref-chunk-num">片段 #{{ j + 1 }}</span>
              <el-tag size="small" :type="scoreTagType(chunk.score)" effect="plain"
                >相似度 {{ (chunk.score * 100).toFixed(1) }}%</el-tag
              >
            </div>
            <el-input
              :model-value="chunk.text"
              type="textarea"
              :rows="2"
              readonly
              class="ref-chunk-text"
            />
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </template>
  <el-empty v-else description="暂无引用知识（知识库为空或未检索到相关文档）" />
</template>

<script setup>
import { computed } from 'vue'

import { Document, Loading } from '@element-plus/icons-vue'

import { confidenceTagType, scoreTagType, typeLabel } from '@/features/analysis/lib/analysisModel'

/* 引用来源面板：D52 从 SmartAnalysis.vue 搬出来。
   链上的四个值（在飞 / 列表 / 检索词 / 可信度）从页面递进来；展开哪几份文档是**这一链**的 UI 状态，
   仍由页面侧的 composable 持有，面板只通过 `update:refOpenDocs` 写回去——原因和 D44 一样：
   结果区整块是 `v-if="result"`，面板自己持有的话，重跑一次分析会把用户展开的文档重新折上。
   `analysisConfidence` 也在页面上算：它同时给首屏 hero 与评分区那一段用（三处读同一个值，两块的
   形状不同：评分区取 `signals`，这里取 `breakdown` 与 `risks`）。
   样式是从页面**复制**的（"RAG Confidence / References / Loading state" 三段），页面那 1092 行没删。 */
const props = defineProps({
  loading: { type: Boolean, default: false },
  references: {
    type: /** @type {import('vue').PropType<import('../lib/analysisModel').ReferenceDoc[]>} */ (
      Array
    ),
    default: () => [],
  },
  referenceQuery: { type: String, default: '' },
  analysisConfidence: { type: Object, default: null },
  refOpenDocs: { type: Array, default: () => [0] },
})

const emit = defineEmits(['update:refOpenDocs'])

const openDocs = computed({
  get: () => props.refOpenDocs,
  set: (value) => emit('update:refOpenDocs', value),
})
</script>

<style scoped>
/* RAG Confidence */
.rag-confidence {
  margin-top: 16px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
}

.rag-confidence-main {
  display: flex;
  gap: 14px;
  align-items: center;
}

.rag-badge {
  width: 56px;
  height: 56px;
  border-radius: var(--app-radius-xs, 8px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.rag-confidence-copy {
  flex: 1;
  min-width: 0;
}

.rag-confidence-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
}

.rag-confidence-summary {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
}

.rag-confidence-query {
  margin-top: 6px;
  color: var(--app-muted);
  font-size: 12px;
  word-break: break-all;
}

.rag-confidence-metrics {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.rag-metric {
  padding: 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-surface-strong);
  border: 1px solid var(--el-border-color);
}

.rag-metric span {
  display: block;
  color: var(--app-muted);
  font-size: 11px;
  margin-bottom: 4px;
}

.rag-metric strong {
  font-size: 16px;
}

.rag-breakdown {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.rag-breakdown-item {
  padding: 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-surface-strong);
  border: 1px solid var(--el-border-color);
}

.rag-breakdown-item span,
.rag-breakdown-item strong,
.rag-breakdown-item em {
  display: block;
}

.rag-breakdown-item span {
  color: var(--app-muted);
  font-size: 12px;
}

.rag-breakdown-item strong {
  margin: 4px 0;
  font-size: 16px;
}

.rag-breakdown-item em {
  color: var(--app-muted);
  font-size: 11px;
  font-style: normal;
  line-height: 1.5;
}

.rag-risk-list {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rag-risk-label {
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 600;
  align-self: center;
}

.rag-risk-item {
  padding: 4px 8px;
  border-radius: var(--app-radius-xs, 8px);
  background: #fff5f2;
  color: var(--app-danger);
  font-size: 11px;
  border: 1px solid #fad5cc;
}

/* References */
.ref-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ref-doc-title {
  font-weight: 600;
  font-size: 13px;
}
.ref-chunks {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ref-chunk-item {
  padding: 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--el-fill-color-light);
}
.ref-chunk-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.ref-chunk-num {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-muted);
}

/* Loading state */
.inline-loading {
  text-align: center;
  padding: 40px 0;
  color: var(--app-muted);
}
.inline-loading p {
  margin: 8px 0 0;
}
</style>
