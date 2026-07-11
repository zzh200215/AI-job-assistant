<template>
  <div class="knowledge-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero-head">
        <div>
          <p class="eyebrow">Knowledge Workspace</p>
          <h2>知识库管理</h2>
	          <div class="page-header-sub">
            支持增量上传、批量维护、检索验证和 Query Rewrite 调试，覆盖岗位、能力模型、职业路径与薪资资料。
          </div>
        </div>
        <div class="hero-actions">
          <el-button type="primary" @click="showUpload = true">
            <el-icon><UploadFilled /></el-icon>
            上传文档
          </el-button>
          <el-button @click="toggleDebugTab">
            <el-icon><MagicStick /></el-icon>
            {{ activeTab === 'debug' ? '回到文档管理' : '进入检索调试' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <section class="stats-grid">
      <div v-for="item in stats" :key="item.label" class="stat-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.count }}</strong>
      </div>
    </section>

    <el-card v-if="isAdmin" shadow="never" class="panel-card">
      <template #header>
        <div class="panel-header">
          <div>
            <h2>Embedding 用量</h2>
            <p>查看当前后端进程内的向量化请求规模、缓存命中和模型分布。</p>
          </div>
          <div class="panel-actions">
            <el-button @click="loadEmbeddingStats" :loading="embeddingLoading">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="embed-stats-grid" v-loading="embeddingLoading">
        <div class="embed-stat-card">
          <span>总调用次数</span>
          <strong>{{ embeddingStats.total_calls ?? 0 }}</strong>
        </div>
        <div class="embed-stat-card">
          <span>总文本条数</span>
          <strong>{{ embeddingStats.total_texts ?? 0 }}</strong>
        </div>
        <div class="embed-stat-card">
          <span>缓存命中率</span>
          <strong>{{ formatPercent(embeddingStats.cache_hit_rate) }}</strong>
        </div>
        <div class="embed-stat-card">
          <span>网络批次数</span>
          <strong>{{ embeddingStats.network_batches ?? 0 }}</strong>
        </div>
      </div>

      <div class="embed-detail-grid">
        <el-card shadow="never" class="inner-card embed-detail-card">
          <template #header>
            <span>按 Provider</span>
          </template>
          <el-empty v-if="!providerStats.length" description="暂无调用数据" />
          <div v-else class="metric-list">
            <div v-for="item in providerStats" :key="item.label" class="metric-row">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="inner-card embed-detail-card">
          <template #header>
            <span>按 Model</span>
          </template>
          <el-empty v-if="!modelStats.length" description="暂无调用数据" />
          <div v-else class="metric-list">
            <div v-for="item in modelStats" :key="item.label" class="metric-row">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </el-card>
      </div>

      <el-card shadow="never" class="inner-card embed-trend-card">
        <template #header>
          <span>最近 7 天趋势</span>
        </template>
        <el-empty v-if="!dailyTrend.length" description="暂无历史趋势数据" />
        <el-table v-else :data="dailyTrend" size="small" stripe>
          <el-table-column prop="stat_date" label="日期" width="120" />
          <el-table-column prop="provider" label="Provider" width="120" />
          <el-table-column prop="model" label="Model" min-width="180" show-overflow-tooltip />
          <el-table-column prop="total_calls" label="调用次数" width="100" />
          <el-table-column prop="total_texts" label="文本条数" width="100" />
          <el-table-column label="缓存命中率" width="110">
            <template #default="{ row }">{{ formatPercent(row.cache_hit_rate) }}</template>
          </el-table-column>
          <el-table-column prop="network_batches" label="批次数" width="90" />
        </el-table>
      </el-card>

      <p class="embed-footnote">最近调用时间：{{ embeddingStats.last_call_at || '-' }}</p>
    </el-card>

    <el-card shadow="never" class="workspace-card">
      <div class="workspace-header">
        <div>
          <h2>统一工作台</h2>
          <p>文档管理、普通检索和高级调试放在同一页，便于快速闭环。</p>
        </div>
        <el-tabs v-model="activeTab" class="workspace-tabs">
          <el-tab-pane label="文档管理" name="docs" />
          <el-tab-pane label="普通检索" name="search" />
          <el-tab-pane label="高级调试" name="debug" />
        </el-tabs>
      </div>
    </el-card>

    <el-card v-show="activeTab === 'docs'" shadow="never" class="panel-card">
      <template #header>
        <div class="panel-header">
          <div>
            <h2>文档列表</h2>
            <p>支持按类型、状态和归属筛选，并查看切片详情或重新处理失败文档。</p>
          </div>
          <div class="panel-actions">
            <el-button @click="loadList" :loading="loading">刷新</el-button>
            <el-button type="danger" plain @click="onRebuild">重建索引</el-button>
          </div>
        </div>
      </template>

      <el-form :inline="true" size="small" class="filter-row">
        <el-form-item label="文档类型">
          <el-select
            v-model="filterType"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            clearable
            placeholder="全部类型"
            style="width: 190px"
          >
            <el-option
              v-for="item in DOC_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filterStatus"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            clearable
            placeholder="全部状态"
            style="width: 140px"
          >
            <el-option label="处理中" value="processing" />
            <el-option label="就绪" value="ready" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="范围">
          <el-switch
            v-model="myOnly"
            inline-prompt
            active-text="我的"
            inactive-text="全部"
          />
        </el-form-item>
      </el-form>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="160">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.doc_type)" size="small">{{ typeLabel(row.doc_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file_name" label="文件名" min-width="180" show-overflow-tooltip />
        <el-table-column prop="chunk_count" label="切片数" width="90" align="center" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误信息" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_msg" class="err">{{ row.error_msg }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="上传时间" width="180" />
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button size="small" @click="openDetail(row)">详情</el-button>
              <el-button
                size="small"
                type="warning"
                plain
                @click="onReprocess(row)"
                :disabled="reprocessingId === row.id"
                :loading="reprocessingId === row.id"
              >
                重处理
              </el-button>
              <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @current-change="loadList"
        @size-change="loadList"
      />
    </el-card>

    <el-card v-show="activeTab === 'search'" shadow="never" class="panel-card">
      <template #header>
        <div class="panel-header">
          <div>
            <h2>知识检索测试</h2>
            <p>验证文档是否可召回，查看不同类型数据源的命中情况。</p>
          </div>
          <el-button text @click="prefillRewriteFromSearch">把当前搜索词带入高级调试</el-button>
        </div>
      </template>

      <el-form :inline="true" class="search-form">
        <el-form-item label="关键词">
          <el-input v-model="searchQuery" placeholder="例如：Python 后端 / AI 工程 / 转行路线" style="width: 320px" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select
            v-model="searchDocType"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            clearable
            placeholder="不限"
            style="width: 180px"
          >
            <el-option
              v-for="item in DOC_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="searchLoading" @click="onSearch">检索</el-button>
        </el-form-item>
      </el-form>

      <div v-if="searchResults.length">
        <el-timeline>
          <el-timeline-item
            v-for="(item, index) in searchResults"
            :key="index"
            :timestamp="`${item.doc_title} 路 ${typeLabel(item.doc_type)} 路 鐩镐技搴?${formatScore(item.score)}`"
          >
            <div class="search-text">
              {{ item.text?.slice(0, 320) }}{{ item.text?.length > 320 ? '...' : '' }}
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
      <el-empty v-else-if="searched" description="未找到匹配内容" />
    </el-card>

    <el-card v-show="activeTab === 'debug'" shadow="never" class="panel-card">
      <template #header>
        <div class="panel-header">
          <div>
            <h2>高级检索调试</h2>
            <p>观察 Query Rewrite、召回结果、RAG 置信度和最终上下文拼装。</p>
          </div>
          <el-button text @click="activeTab = 'docs'">回到文档管理</el-button>
        </div>
      </template>

      <el-form :model="rewriteForm" label-width="110px" class="rewrite-form">
        <el-form-item label="原始问题">
          <el-input
            v-model="rewriteForm.original_query"
            type="textarea"
            :rows="2"
            placeholder="输入你要测试的检索问题"
          />
        </el-form-item>
        <el-form-item label="简历摘要">
          <el-input
            v-model="rewriteForm.resume_summary"
            type="textarea"
            :rows="3"
            placeholder="可选，用于模拟带候选人上下文的检索"
          />
        </el-form-item>
        <el-form-item label="JD 摘要">
          <el-input
            v-model="rewriteForm.jd_summary"
            type="textarea"
            :rows="3"
            placeholder="可选，用于模拟带岗位上下文的检索"
          />
        </el-form-item>
        <el-form-item label="文档类型">
          <el-select
            v-model="rewriteForm.doc_type"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            clearable
            placeholder="不限"
            style="width: 220px"
          >
            <el-option
              v-for="item in DOC_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="每路召回">
          <el-slider
            v-model="rewriteForm.top_k_per_query"
            :min="1"
            :max="20"
            show-stops
            style="width: 320px"
          />
          <span class="inline-tip">{{ rewriteForm.top_k_per_query }} 条</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="rewriteLoading" @click="runRewriteDebug">
            执行改写与检索
          </el-button>
        </el-form-item>
      </el-form>

      <el-card v-if="rewriteResult.rewritten_queries.length" shadow="never" class="inner-card">
        <template #header>
          <span>改写后的查询（{{ rewriteResult.rewritten_queries.length }}）</span>
        </template>
        <el-timeline>
          <el-timeline-item
            v-for="(item, index) in rewriteResult.rewritten_queries"
            :key="index"
            :type="item.query_type === 'original' ? 'info' : 'primary'"
            :hollow="item.query_type === 'original'"
          >
            <div class="rewrite-item-title">{{ item.query_text }}</div>
            <div class="rewrite-item-meta">
              <el-tag size="small">{{ item.query_type }}</el-tag>
              <span>{{ item.purpose }}</span>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <el-card v-if="rewriteResult.rag_confidence" shadow="never" class="inner-card">
        <template #header>
          <span>RAG 置信度</span>
        </template>
        <div class="confidence-grid">
          <div class="confidence-main">
            <div class="confidence-score" :class="`confidence-${rewriteResult.rag_confidence.level || 'low'}`">
              {{ rewriteResult.rag_confidence.score ?? 0 }}
            </div>
            <div>
              <strong>{{ rewriteResult.rag_confidence.label || '-' }}</strong>
              <p>{{ rewriteResult.rag_confidence.summary || '' }}</p>
            </div>
          </div>
          <div class="confidence-signals">
            <div class="signal-item">
              <span>召回片段</span>
              <strong>{{ rewriteResult.rag_confidence.signals?.total_chunks ?? 0 }}</strong>
            </div>
            <div class="signal-item">
              <span>覆盖文档</span>
              <strong>{{ rewriteResult.rag_confidence.signals?.unique_docs ?? 0 }}</strong>
            </div>
            <div class="signal-item">
              <span>平均相关度</span>
              <strong>{{ rewriteResult.rag_confidence.signals?.avg_similarity ?? 0 }}</strong>
            </div>
            <div class="signal-item">
              <span>命中能力模型</span>
              <strong>{{ rewriteResult.rag_confidence.signals?.has_skill_model ? '是' : '否' }}</strong>
            </div>
          </div>
        </div>
      </el-card>

      <el-card v-if="rewriteResult.retrieved_chunks.length" shadow="never" class="inner-card">
        <template #header>
          <span>召回切片（{{ rewriteResult.total_chunks }}）</span>
        </template>
        <el-table :data="rewriteResult.retrieved_chunks" border stripe size="small">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="expand-block">
                <p class="expand-label">完整文本</p>
                <p class="expand-text">{{ row.text }}</p>
                <p class="expand-label">命中的查询</p>
                <el-tag
                  v-for="(query, idx) in row.queries"
                  :key="idx"
                  size="small"
                  class="expand-tag"
                >
                  {{ query.type }}: {{ query.text }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="doc_title" label="来源文档" width="180" show-overflow-tooltip />
          <el-table-column prop="doc_type" label="类型" width="130">
            <template #default="{ row }">
              <el-tag size="small">{{ typeLabel(row.doc_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="score" label="相似度" width="100">
            <template #default="{ row }">{{ formatScore(row.score) }}</template>
          </el-table-column>
          <el-table-column prop="final_score" label="最终分" width="100">
            <template #default="{ row }">{{ formatScore(row.final_score) }}</template>
          </el-table-column>
          <el-table-column prop="rerank_source" label="重排源" width="120" />
          <el-table-column prop="query_type" label="召回类型" width="120" />
          <el-table-column prop="query_used" label="召回 Query" show-overflow-tooltip />
          <el-table-column prop="text" label="文本摘要" show-overflow-tooltip />
        </el-table>
      </el-card>

      <el-card v-if="rewriteResult.rag_context" shadow="never" class="inner-card">
        <template #header>
          <span>RAG 上下文</span>
        </template>
        <pre class="rag-context">{{ rewriteResult.rag_context }}</pre>
      </el-card>
    </el-card>

    <el-dialog v-model="showUpload" title="上传知识库文档" width="560px">
      <el-form :model="uploadForm" label-width="90px">
        <el-form-item label="文档标题">
          <el-input v-model="uploadForm.title" placeholder="输入文档标题" />
        </el-form-item>
        <el-form-item label="文档类型">
          <el-select
            v-model="uploadForm.doc_type"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            style="width: 100%"
          >
            <el-option
              v-for="item in DOC_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="上传文件">
          <el-upload
            drag
            action="#"
            :http-request="doUpload"
            :show-file-list="false"
            :before-upload="beforeUpload"
            accept=".txt,.md,.pdf,.docx,.doc"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽文件到这里，或点击上传</div>
            <template #tip>
              <div class="el-upload__tip">支持 txt / md / pdf / docx / doc，大小不超过 20MB</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <div v-if="uploading" class="upload-progress">
        <div class="progress-info">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ uploadStatus }}</span>
        </div>
        <el-progress :percentage="uploadProgress" :stroke-width="12" :text-inside="true" />
        <div class="progress-sub" v-if="uploadProgress < 100">
          {{ formatSize(uploadedBytes) }} / {{ formatSize(totalBytes) }}
        </div>
      </div>

      <el-alert
        v-if="uploadError"
        class="upload-alert"
        :title="uploadError"
        type="error"
        :closable="false"
        show-icon
      >
        <template #append>
          <el-button size="small" type="danger" :loading="retrying" @click="retryUpload">
            閲嶆柊涓婁紶
          </el-button>
        </template>
      </el-alert>
    </el-dialog>

    <el-drawer v-model="showDetail" size="56%" :title="detailDoc?.title || '文档详情'">
      <div v-if="detailDoc" class="detail-stack">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="文档 ID">{{ detailDoc.id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(detailDoc.status)" size="small">{{ statusLabel(detailDoc.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="类型">{{ typeLabel(detailDoc.doc_type) }}</el-descriptions-item>
          <el-descriptions-item label="切片数">{{ detailDoc.chunk_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="文件名" :span="2">{{ detailDoc.file_name }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ formatSize(detailDoc.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ detailDoc.update_time || '-' }}</el-descriptions-item>
          <el-descriptions-item v-if="detailDoc.error_msg" label="错误信息" :span="2">
            <span class="err">{{ detailDoc.error_msg }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="drawer-actions">
          <el-button @click="refreshDetail" :loading="detailLoading">刷新详情</el-button>
          <el-button
            type="warning"
            plain
            @click="onReprocess(detailDoc)"
            :loading="reprocessingId === detailDoc.id"
          >
            重新处理文档
          </el-button>
        </div>

        <el-card shadow="never" class="inner-card">
          <template #header>
            <span>切片预览（{{ detailChunks.length }}）</span>
          </template>

          <el-empty v-if="!detailChunks.length && !detailLoading" description="当前文档暂无切片，或尚未完成向量化" />
          <div v-else class="chunk-list">
            <article v-for="chunk in detailChunks" :key="chunk.chunk_id" class="chunk-card">
              <div class="chunk-head">
                <strong>Chunk {{ chunk.chunk_index }}</strong>
                <el-tag size="small">{{ chunk.chunk_id }}</el-tag>
              </div>
              <p>{{ chunk.text }}</p>
            </article>
          </div>
        </el-card>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { Loading, MagicStick, UploadFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import {
  deleteKnowledgeDoc,
  getEmbeddingStats,
  getKnowledgeChunks,
  listKnowledge,
  queryRewriteTest,
  rebuildKnowledge,
  reprocessKnowledgeDoc,
  searchKnowledge,
  uploadKnowledge,
} from '@/api/knowledge'

const DOC_TYPE_OPTIONS = [
  { value: 'jd_lib', label: '岗位 JD 库' },
  { value: 'skill_model', label: '行业岗位能力模型' },
  { value: 'resume_template', label: '简历模板 / 案例' },
  { value: 'interview_q', label: '面试题库' },
  { value: 'career_path', label: '职业发展路径资料' },
  { value: 'salary_market', label: '企业招聘信息 / 薪资' },
  { value: 'transition_guide', label: '校招 / 社招 / 转行资料' },
  { value: 'industry_report', label: '行业报告' },
  { value: 'general', label: '通用文档' },
]

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const filterType = ref(null)
const filterStatus = ref(null)
const myOnly = ref(false)
const reprocessingId = ref(null)

const showUpload = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadedBytes = ref(0)
const totalBytes = ref(0)
const uploadStatus = ref('')
const uploadError = ref('')
const retrying = ref(false)
const uploadForm = reactive({
  title: '',
  doc_type: 'general',
})
let pendingFile = null

const searchQuery = ref('')
const searchDocType = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
const searched = ref(false)

const normalizeTab = (value) => ['docs', 'search', 'debug'].includes(value) ? value : 'docs'
const activeTab = ref(normalizeTab(route.query.tab))
const rewriteLoading = ref(false)
const rewriteForm = reactive({
  original_query: '',
  resume_summary: '',
  jd_summary: '',
  doc_type: '',
  top_k_per_query: 5,
  max_queries: 5,
})
const rewriteResult = reactive({
  original_query: '',
  rewritten_queries: [],
  retrieved_chunks: [],
  total_chunks: 0,
  rag_confidence: null,
  rag_context: '',
  references: [],
})

const showDetail = ref(false)
const detailLoading = ref(false)
const detailDoc = ref(null)
const detailChunks = ref([])
const embeddingLoading = ref(false)
const embeddingStats = reactive({
  total_calls: 0,
  total_texts: 0,
  cache_hits: 0,
  cache_misses: 0,
  network_batches: 0,
  cache_hit_rate: 0,
  provider_totals: {},
  model_totals: {},
  last_call_at: null,
})

const stats = computed(() => [
  { label: '文档总数', count: total.value },
  { label: '就绪', count: list.value.filter(item => item.status === 'ready').length },
  { label: '处理中', count: list.value.filter(item => item.status === 'processing').length },
  { label: '失败', count: list.value.filter(item => item.status === 'failed').length },
])
const isAdmin = computed(() => !!authStore.user?.is_admin)
const providerStats = computed(() =>
  Object.entries(embeddingStats.provider_totals || {}).map(([label, value]) => ({ label, value }))
)
const modelStats = computed(() =>
  Object.entries(embeddingStats.model_totals || {}).map(([label, value]) => ({ label, value }))
)
const dailyTrend = computed(() => embeddingStats.daily_trend || [])

async function loadList() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      my_only: myOnly.value,
    }
    if (filterType.value) params.doc_type = filterType.value
    if (filterStatus.value) params.status = filterStatus.value
    const data = await listKnowledge(params)
    list.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadEmbeddingStats() {
  if (!isAdmin.value) return
  embeddingLoading.value = true
  try {
    const data = await getEmbeddingStats()
    Object.assign(embeddingStats, {
      total_calls: data.total_calls ?? 0,
      total_texts: data.total_texts ?? 0,
      cache_hits: data.cache_hits ?? 0,
      cache_misses: data.cache_misses ?? 0,
      network_batches: data.network_batches ?? 0,
      cache_hit_rate: data.cache_hit_rate ?? 0,
      provider_totals: data.provider_totals || {},
      model_totals: data.model_totals || {},
      daily_trend: data.daily_trend || [],
      last_call_at: data.last_call_at || null,
    })
  } finally {
    embeddingLoading.value = false
  }
}

function beforeUpload(file) {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['txt', 'md', 'pdf', 'docx', 'doc'].includes(ext)) {
    ElMessage.error('仅支持 txt / md / pdf / docx / doc 格式')
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error(`文件超过 20MB（当前 ${(file.size / 1024 / 1024).toFixed(1)}MB）`)
    return false
  }
  return true
}

async function doUpload({ file }) {
  if (!uploadForm.title.trim()) {
    ElMessage.warning('请先填写文档标题')
    return
  }

  pendingFile = file
  uploading.value = true
  uploadError.value = ''
  uploadProgress.value = 0
  uploadedBytes.value = 0
  totalBytes.value = file.size
  uploadStatus.value = '正在上传...'

  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', uploadForm.title.trim())
    formData.append('doc_type', uploadForm.doc_type)
    await uploadKnowledge(formData, (event) => {
      const loaded = Number(event?.loaded || 0)
      const total = Number(event?.total || file.size || 0)
      const ratio = total > 0 ? loaded / total : 0
      uploadProgress.value = Math.max(0, Math.min(100, Math.round(ratio * 100)))
      uploadedBytes.value = loaded
    })

    uploadStatus.value = '正在处理：解析 -> 切片 -> 向量化'
    uploadProgress.value = 100
    showUpload.value = false
    uploadForm.title = ''
    uploadForm.doc_type = 'general'
    pendingFile = null
    ElMessage.success('上传完成')
    await loadList()
  } catch (error) {
    uploadError.value = error.message || '上传失败'
    uploadProgress.value = 0
  } finally {
    uploading.value = false
  }
}

async function retryUpload() {
  if (!pendingFile) {
    ElMessage.warning('没有可重试的文件')
    return
  }
  retrying.value = true
  try {
    await doUpload({ file: pendingFile })
  } finally {
    retrying.value = false
  }
}

async function openDetail(row) {
  showDetail.value = true
  detailDoc.value = row
  await refreshDetail(row.id)
}

async function refreshDetail(id = detailDoc.value?.id) {
  if (!id) return
  detailLoading.value = true
  try {
    const data = await getKnowledgeChunks(id)
    detailDoc.value = data.document || detailDoc.value
    detailChunks.value = data.chunks || []
  } finally {
    detailLoading.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除《${row.title}》吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await deleteKnowledgeDoc(row.id)
  ElMessage.success('已删除')
  if (detailDoc.value?.id === row.id) {
    showDetail.value = false
  }
  await loadList()
}

async function onReprocess(row) {
  reprocessingId.value = row.id
  try {
    await reprocessKnowledgeDoc(row.id)
    ElMessage.success('宸叉彁浜ら噸澶勭悊')
    await loadList()
    if (detailDoc.value?.id === row.id) {
      await refreshDetail(row.id)
    }
  } finally {
    reprocessingId.value = null
  }
}

async function onRebuild() {
  try {
    await ElMessageBox.confirm('重建会重新处理全部知识库文档，确认继续吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await rebuildKnowledge()
  ElMessage.success('重建完成')
  await loadList()
}

async function onSearch() {
  if (!searchQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  searchLoading.value = true
  searched.value = true
  try {
    const data = await searchKnowledge({
      query: searchQuery.value.trim(),
      doc_type: searchDocType.value || null,
      top_k: 10,
    })
    searchResults.value = data.results || []
  } finally {
    searchLoading.value = false
  }
}

function toggleDebugTab() {
  activeTab.value = activeTab.value === 'debug' ? 'docs' : 'debug'
}

function prefillRewriteFromSearch() {
  activeTab.value = 'debug'
  rewriteForm.original_query = searchQuery.value.trim()
  rewriteForm.doc_type = searchDocType.value || ''
}

async function runRewriteDebug() {
  if (!rewriteForm.original_query.trim()) {
    ElMessage.warning('请输入原始问题')
    return
  }
  rewriteLoading.value = true
  try {
    const data = await queryRewriteTest({
      original_query: rewriteForm.original_query.trim(),
      resume_summary: rewriteForm.resume_summary,
      jd_summary: rewriteForm.jd_summary,
      doc_type: rewriteForm.doc_type || null,
      top_k_per_query: rewriteForm.top_k_per_query,
      max_queries: rewriteForm.max_queries,
    })
    Object.assign(rewriteResult, {
      original_query: data.original_query || '',
      rewritten_queries: data.rewritten_queries || [],
      retrieved_chunks: data.retrieved_chunks || [],
      total_chunks: data.total_chunks || 0,
      rag_confidence: data.rag_confidence || null,
      rag_context: data.rag_context || '',
      references: data.references || [],
    })
    ElMessage.success(`调试完成，共召回 ${rewriteResult.total_chunks} 条切片`)
  } finally {
    rewriteLoading.value = false
  }
}

function typeLabel(value) {
  return DOC_TYPE_OPTIONS.find(item => item.value === value)?.label || value
}

function typeTag(value) {
  return {
    jd_lib: 'primary',
    skill_model: 'success',
    resume_template: 'info',
    interview_q: 'warning',
    career_path: 'success',
    salary_market: 'danger',
    transition_guide: 'warning',
    industry_report: 'info',
    general: '',
  }[value] || ''
}

function statusLabel(value) {
  return {
    processing: '处理中',
    ready: '就绪',
    failed: '失败',
  }[value] || value
}

function statusTag(value) {
  return {
    processing: 'warning',
    ready: 'success',
    failed: 'danger',
  }[value] || ''
}

function formatSize(size) {
  if (!size) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function formatScore(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(4)
}

function formatPercent(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(1)}%`
}

watch([filterType, filterStatus, myOnly], () => {
  page.value = 1
  loadList()
})

watch(activeTab, (value) => {
  router.replace({ query: { ...route.query, tab: value } })
})

watch(() => route.query.tab, (value) => {
  const next = normalizeTab(value)
  if (next !== activeTab.value) activeTab.value = next
})

onMounted(() => {
  loadList()
  loadEmbeddingStats()
})
</script>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card,
.workspace-card,
.panel-card {
  border: none;
  border-radius: var(--app-radius-md, 16px);
}

.hero-head,
.workspace-header,
.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--app-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.hero-head h2,
.panel-header h2,
.workspace-header h2 {
  margin: 0;
  color: var(--app-text);
}

.workspace-header p,
.panel-header p {
  margin: 8px 0 0;
  color: var(--app-muted);
  line-height: 1.7;
}

.workspace-tabs {
  flex-shrink: 0;
}

.hero-actions,
.panel-actions,
.table-actions,
.drawer-actions {
  display: flex;
  gap: 10px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.embed-stats-grid,
.embed-detail-grid {
  display: grid;
  gap: 12px;
}

.embed-stats-grid {
  grid-template-columns: repeat(4, 1fr);
  margin-bottom: 12px;
}

.embed-detail-grid {
  grid-template-columns: 1fr 1fr;
}

.embed-stat-card {
  padding: 18px;
  border-radius: var(--app-radius-sm, 12px);
  background: #fff;
}

.embed-stat-card span,
.metric-row span,
.embed-footnote {
  color: var(--app-muted);
  font-size: 12px;
}

.embed-stat-card strong {
  display: block;
  margin-top: 10px;
  color: var(--app-text);
  font-size: 28px;
}

.metric-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.metric-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--app-line);
}

.metric-row:last-child {
  border-bottom: none;
}

.metric-row strong {
  color: var(--app-primary);
}

.embed-footnote {
  margin: 12px 0 0;
}

.stat-card {
  padding: 18px;
  border-radius: var(--app-radius-sm, 12px);
  background: #fff;
}

.stat-card span {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}

.stat-card strong {
  display: block;
  margin-top: 10px;
  color: var(--app-primary);
  font-size: 28px;
}

.filter-row,
.search-form {
  margin-bottom: 16px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.err {
  color: var(--app-danger);
  font-size: 12px;
}

.search-text {
  color: var(--app-text);
  font-size: 13px;
  line-height: 1.7;
}

.upload-progress,
.upload-alert {
  margin-top: 12px;
}

.progress-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.progress-sub {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
  text-align: right;
}

.rewrite-form {
  margin-bottom: 16px;
}

.inline-tip {
  margin-left: 12px;
  color: var(--app-muted);
  font-size: 13px;
}

.inner-card + .inner-card {
  margin-top: 16px;
}

.rewrite-item-title {
  font-weight: 600;
  color: var(--app-text);
}

.rewrite-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  color: var(--app-muted);
  font-size: 13px;
}

.expand-block {
  padding: 8px 16px;
}

.expand-label {
  margin: 0 0 6px;
  color: var(--app-muted);
  font-size: 12px;
}

.expand-text {
  margin: 0;
  padding: 8px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
  white-space: pre-wrap;
}

.expand-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}

.confidence-grid {
  display: grid;
  gap: 14px;
}

.confidence-main {
  display: flex;
  align-items: center;
  gap: 14px;
}

.confidence-score {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 68px;
  height: 68px;
  border-radius: var(--app-radius-sm, 12px);
  font-size: 24px;
  font-weight: 700;
  color: #fff;
}

.confidence-high {
  background: linear-gradient(135deg, var(--app-success), #57c77a);
}

.confidence-medium {
  background: linear-gradient(135deg, var(--app-primary), #5f97f0);
}

.confidence-low {
  background: linear-gradient(135deg, var(--app-danger), #ef7c66);
}

.confidence-main p {
  margin: 6px 0 0;
  color: var(--app-muted);
  line-height: 1.7;
}

.confidence-signals {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.signal-item {
  padding: 12px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
}

.signal-item span {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}

.signal-item strong {
  display: block;
  margin-top: 6px;
  color: var(--app-text);
}

.rag-context {
  margin: 0;
  padding: 12px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-bg);
  font-size: 13px;
  white-space: pre-wrap;
}

.detail-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chunk-card {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
}

.chunk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.chunk-card p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.7;
  color: var(--app-text);
}

@media (max-width: 900px) {
  .hero-head,
  .workspace-header,
  .panel-header {
    flex-direction: column;
  }

  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .embed-stats-grid,
  .embed-detail-grid {
    grid-template-columns: 1fr 1fr;
  }

  .confidence-signals {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .embed-stats-grid,
  .embed-detail-grid {
    grid-template-columns: 1fr;
  }

  .hero-actions,
  .panel-actions,
  .table-actions,
  .drawer-actions {
    flex-direction: column;
    width: 100%;
  }
}
</style>

