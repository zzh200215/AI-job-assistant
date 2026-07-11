<template>
  <div class="status-page">
    <el-card shadow="never" class="hero-card">
      <template #header>
        <span>System Status</span>
      </template>

      <div class="hero-top">
        <div>
          <p class="eyebrow">Runtime Overview</p>
          <h2>Project Runtime Dashboard</h2>
	          <div class="page-header-sub">
            Inspect environment mode, orchestration settings, request metrics, and embedding usage from one place.
          </div>
        </div>
        <div class="hero-badges">
          <el-tag :type="status.demo_mode ? 'warning' : 'success'">
            {{ status.demo_mode ? 'Demo Mode' : 'Live Mode' }}
          </el-tag>
          <el-tag type="info">
            {{ status.runtime_notes?.knowledge_seed_ready ? 'Knowledge Seeds Ready' : 'Knowledge Seeds Pending' }}
          </el-tag>
        </div>
      </div>

      <el-row v-if="canViewOverview" :gutter="16" class="metric-grid">
        <el-col v-for="item in overviewMetrics" :key="item.label" :xs="12" :sm="8" :md="6">
          <div class="metric-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </el-col>
      </el-row>
      <el-alert v-else class="mt" type="info" :closable="false" show-icon>
        <template #title>
          Global overview metrics are limited to recruiters and admins.
        </template>
      </el-alert>

      <el-descriptions :column="2" border class="mt">
        <el-descriptions-item label="Environment">{{ status.app_env || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Log Level">{{ status.log_level || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Orchestration Strategy">{{ status.orchestration_strategy || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Orchestration Engine">{{ status.orchestration_engine || '-' }}</el-descriptions-item>
        <el-descriptions-item label="LLM Mode">{{ status.runtime_notes?.llm_mode || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Embedding Mode">{{ status.runtime_notes?.embedding_mode || '-' }}</el-descriptions-item>
        <el-descriptions-item label="OCR Resume Parsing">
          {{ status.capabilities?.ocr_resume_parse ? 'Enabled' : 'Disabled' }}
        </el-descriptions-item>
        <el-descriptions-item label="Data Source API">
          {{ status.runtime_notes?.data_source_api_ready ? 'Ready' : 'Scaffolded' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-alert class="mt" type="info" :closable="false" show-icon>
        <template #title>
          {{ status.runtime_notes?.data_source_api_note || 'Current runtime notes are unavailable.' }}
        </template>
      </el-alert>
    </el-card>

    <el-row v-if="canViewOverview" :gutter="16">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <span>Request Metrics</span>
          </template>

          <el-row :gutter="12" class="mini-grid">
            <el-col v-for="item in runtimeMetrics" :key="item.label" :xs="12">
              <div class="mini-card">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </el-col>
          </el-row>

          <el-descriptions :column="1" border class="mt">
            <el-descriptions-item label="Methods">
              {{ formatPairs(overview.runtime_metrics?.method_totals) }}
            </el-descriptions-item>
            <el-descriptions-item label="Status Codes">
              {{ formatPairs(overview.runtime_metrics?.status_totals) }}
            </el-descriptions-item>
            <el-descriptions-item label="Last Request">
              {{ overview.runtime_metrics?.last_request_at || '-' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <span>Embedding Metrics</span>
          </template>

          <el-row :gutter="12" class="mini-grid">
            <el-col v-for="item in embeddingMetrics" :key="item.label" :xs="12">
              <div class="mini-card">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </el-col>
          </el-row>

          <el-descriptions :column="1" border class="mt">
            <el-descriptions-item label="Providers">
              {{ formatPairs(overview.embedding_metrics?.current?.provider_totals) }}
            </el-descriptions-item>
            <el-descriptions-item label="Models">
              {{ formatPairs(overview.embedding_metrics?.current?.model_totals) }}
            </el-descriptions-item>
            <el-descriptions-item label="Last Call">
              {{ overview.embedding_metrics?.current?.last_call_at || '-' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSystemOverview, getSystemStatus } from '@/api/system'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const status = ref({})
const overview = ref({})
const canViewOverview = computed(() => authStore.isRecruiter || !!authStore.user?.is_admin)

const overviewMetrics = computed(() => {
  const data = overview.value || {}
  return [
    { label: 'Users', value: data.users ?? 0 },
    { label: 'Resumes', value: data.resumes ?? 0 },
    { label: 'Job Descriptions', value: data.jds ?? 0 },
    { label: 'Analysis Records', value: data.analysis_records ?? 0 },
    { label: 'Interviews', value: data.interviews ?? 0 },
    { label: 'Screening Sessions', value: data.screening_sessions ?? 0 },
    { label: 'Knowledge Docs', value: data.knowledge_documents ?? 0 },
    { label: 'Data Sources', value: data.data_sources ?? 0 },
  ]
})

const runtimeMetrics = computed(() => {
  const data = overview.value?.runtime_metrics || {}
  return [
    { label: 'Total Requests', value: data.total_requests ?? 0 },
    { label: 'Error Requests', value: data.error_requests ?? 0 },
    { label: 'Slow Requests', value: data.slow_requests ?? 0 },
    { label: 'Avg Duration (ms)', value: data.avg_duration_ms ?? 0 },
    { label: 'Max Duration (ms)', value: data.max_duration_ms ?? 0 },
  ]
})

const embeddingMetrics = computed(() => {
  const data = overview.value?.embedding_metrics?.current || {}
  return [
    { label: 'Embedding Calls', value: data.total_calls ?? 0 },
    { label: 'Texts Embedded', value: data.total_texts ?? 0 },
    { label: 'Cache Hits', value: data.cache_hits ?? 0 },
    { label: 'Cache Misses', value: data.cache_misses ?? 0 },
    { label: 'Cache Hit Rate', value: data.cache_hit_rate ?? 0 },
  ]
})

function formatPairs(data) {
  if (!data || typeof data !== 'object' || !Object.keys(data).length) {
    return '-'
  }
  return Object.entries(data)
    .map(([key, value]) => `${key}: ${value}`)
    .join(' | ')
}

onMounted(async () => {
  const statusRes = await getSystemStatus()
  status.value = statusRes?.data || statusRes || {}

  if (!canViewOverview.value) {
    overview.value = {}
    return
  }

  const overviewRes = await getSystemOverview()
  overview.value = overviewRes?.data || overviewRes || {}
})
</script>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-card,
.panel-card {
  border-radius: var(--app-radius-md, 16px);
}

.hero-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-top h2 {
  margin: 8px 0 0;
}

.hero-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.metric-grid,
.mini-grid {
  margin-top: 8px;
}

.metric-card,
.mini-card {
  padding: 14px 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.metric-card span,
.mini-card span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}

.metric-card strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
}

.mini-card strong {
  display: block;
  margin-top: 8px;
  font-size: 20px;
}

.mt {
  margin-top: 16px;
}

@media (max-width: 768px) {
  .hero-top {
    flex-direction: column;
  }
}
</style>
