<template>
  <div class="page">
    <el-card>
      <template #header>
        <span><el-icon><DataLine /></el-icon> 岗位数据源管理</span>
        <el-button size="small" type="primary" class="fr" @click="openCreate">
          <el-icon><Plus /></el-icon> 新建数据源
        </el-button>
      </template>

      <el-table :data="sources" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="source_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.source_type)">{{ row.source_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_sync_at" label="上次同步" width="160">
          <template #default="{ row }">
            {{ row.last_sync_at ? formatDate(row.last_sync_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="primary" plain @click="testConnect(row)">测试</el-button>
            <el-button size="small" type="success" plain @click="doSync(row)" :loading="syncingId === row.id">同步</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑数据源' : '新建数据源'" width="600px">
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：Boss直聘CSV" />
        </el-form-item>
        <el-form-item label="类型" prop="source_type">
          <el-select
            v-model="form.source_type"
            placement="bottom-start"
            :fallback-placements="['bottom-start']"
            style="width:100%"
            :disabled="isEdit"
          >
            <el-option label="CSV 文件" value="csv" />
            <el-option label="JSON 文件" value="json" />
            <el-option label="HTTP API" value="api" />
            <el-option label="Mock 演示" value="mock" />
            <el-option label="Arbeitnow 免费 API" value="arbeitnow" />
          </el-select>
        </el-form-item>

        <!-- CSV / JSON 配置 -->
        <template v-if="['csv','json'].includes(form.source_type)">
          <el-form-item label="文件路径">
            <el-input v-model="form.config.file_path" placeholder="如 /data/jobs.csv" />
          </el-form-item>
          <el-form-item label="编码">
            <el-input v-model="form.config.file_encoding" placeholder="utf-8" />
          </el-form-item>
          <el-form-item label="分隔符" v-if="form.source_type === 'csv'">
            <el-input v-model="form.config.delimiter" placeholder="," />
          </el-form-item>
          <el-form-item label="JSON路径" v-if="form.source_type === 'json'">
            <el-input v-model="form.config.json_path" placeholder="如 data.jobs" />
          </el-form-item>
        </template>

        <template v-if="form.source_type === 'arbeitnow'">
          <el-form-item label="搜索关键词">
            <el-input v-model="form.config.search_query" placeholder="如 python / frontend / remote" />
          </el-form-item>
        </template>

        <!-- API 配置 -->
        <template v-if="form.source_type === 'api'">
          <el-form-item label="请求URL">
            <el-input v-model="form.config.api_url" placeholder="https://api.example.com/jobs" />
          </el-form-item>
          <el-form-item label="请求方法">
            <el-select
              v-model="form.config.api_method"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              style="width:100%"
            >
              <el-option label="GET" value="GET" />
              <el-option label="POST" value="POST" />
            </el-select>
          </el-form-item>
          <el-form-item label="鉴权方式">
            <el-select
              v-model="form.config.auth_type"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              style="width:100%"
            >
              <el-option label="无" value="none" />
              <el-option label="Bearer Token" value="bearer" />
              <el-option label="API Key" value="api_key" />
            </el-select>
          </el-form-item>
          <el-form-item label="Bearer Token" v-if="form.config.auth_type === 'bearer'">
            <el-input v-model="form.config.auth_token" placeholder="sk-xxx 或 access token" show-password />
          </el-form-item>
          <template v-if="form.config.auth_type === 'api_key'">
            <el-form-item label="Key 名称">
              <el-input v-model="form.config.auth_key_name" placeholder="如 Authorization / api_key" />
            </el-form-item>
            <el-form-item label="Key 值">
              <el-input v-model="form.config.auth_key_value" placeholder="鉴权值" show-password />
            </el-form-item>
            <el-form-item label="放置位置">
              <el-select
                v-model="form.config.auth_in"
                placement="bottom-start"
                :fallback-placements="['bottom-start']"
                style="width:100%"
              >
                <el-option label="Header" value="header" />
                <el-option label="Query" value="query" />
              </el-select>
            </el-form-item>
          </template>
          <el-form-item label="Headers">
            <el-input type="textarea" v-model="headerJson" :rows="2" placeholder='{"Authorization":"Bearer xxx"}' />
          </el-form-item>
          <el-form-item label="Query 参数">
            <el-input type="textarea" v-model="queryJson" :rows="2" placeholder='{"keyword":"python","city":"beijing"}' />
          </el-form-item>
          <el-form-item label="Body" v-if="form.config.api_method === 'POST'">
            <el-input type="textarea" v-model="bodyJson" :rows="3" placeholder='{"page":1,"page_size":20}' />
          </el-form-item>
          <el-form-item label="列表路径">
            <el-input v-model="form.config.json_path" placeholder="如 data.jobs / result.items" />
          </el-form-item>
          <el-form-item label="分页开关">
            <el-switch v-model="form.config.pagination_enabled" />
          </el-form-item>
          <template v-if="form.config.pagination_enabled">
            <el-form-item label="页码参数">
              <el-input v-model="form.config.page_param" placeholder="page" />
            </el-form-item>
            <el-form-item label="每页参数">
              <el-input v-model="form.config.page_size_param" placeholder="page_size" />
            </el-form-item>
            <el-form-item label="起始页码">
              <el-input-number v-model="form.config.page_start" :min="0" :step="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="每页条数">
              <el-input-number v-model="form.config.page_size" :min="1" :max="200" :step="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="最大页数">
              <el-input-number v-model="form.config.max_pages" :min="1" :max="100" :step="1" style="width:100%" />
            </el-form-item>
            <el-form-item label="更多路径">
              <el-input v-model="form.config.has_more_path" placeholder="可选，如 data.has_more" />
            </el-form-item>
          </template>
          <el-form-item label="限流(ms)">
            <el-input-number v-model="form.config.rate_limit_ms" :min="0" :max="10000" :step="100" style="width:100%" />
          </el-form-item>
          <el-form-item label="重试次数">
            <el-input-number v-model="form.config.retry_max_attempts" :min="1" :max="10" :step="1" style="width:100%" />
          </el-form-item>
          <el-form-item label="退避(ms)">
            <el-input-number v-model="form.config.retry_backoff_ms" :min="0" :max="10000" :step="100" style="width:100%" />
          </el-form-item>
          <el-divider content-position="left">Token 刷新</el-divider>
          <el-form-item label="刷新地址">
            <el-input v-model="form.config.auth_refresh_url" placeholder="https://api.example.com/refresh" />
          </el-form-item>
          <el-form-item label="刷新方法">
            <el-select
              v-model="form.config.auth_refresh_method"
              placement="bottom-start"
              :fallback-placements="['bottom-start']"
              style="width:100%"
            >
              <el-option label="POST" value="POST" />
              <el-option label="GET" value="GET" />
            </el-select>
          </el-form-item>
          <el-form-item label="刷新返回 token 路径">
            <el-input v-model="form.config.auth_refresh_token_path" placeholder="access_token / data.token" />
          </el-form-item>
        </template>

        <el-form-item label="字段映射">
          <el-input type="textarea" v-model="mappingJson" :rows="4" placeholder='标准字段:原始字段' />
        </el-form-item>

        <el-form-item label="状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 测试结果弹窗 -->
    <el-dialog v-model="testVisible" title="连接测试结果" width="600px">
      <el-alert :type="testResult.connectable ? 'success' : 'error'" :closable="false">
        {{ testResult.message }}
      </el-alert>
      <el-table v-if="testResult.sample && testResult.sample.length" :data="testResult.sample" border class="mt-2">
        <el-table-column type="expand">
          <template #default="{ row }">
            <pre style="margin:0;padding:8px;background:#f5f7fa;border-radius:4px;">{{ JSON.stringify(row, null, 2) }}</pre>
          </template>
        </el-table-column>
        <el-table-column v-for="key in sampleKeys" :key="key" :prop="key" :label="key" />
      </el-table>
    </el-dialog>

    <!-- 同步结果弹窗 -->
    <el-dialog v-model="syncVisible" title="同步结果" width="500px">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="状态">
          <el-tag :type="syncResult.status === 'success' ? 'success' : (syncResult.status === 'partial' ? 'warning' : 'danger')">
            {{ syncResult.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="总条数">{{ syncResult.total_count }}</el-descriptions-item>
        <el-descriptions-item label="成功">{{ syncResult.success_count }}</el-descriptions-item>
        <el-descriptions-item label="失败">{{ syncResult.fail_count }}</el-descriptions-item>
        <el-descriptions-item label="去重跳过">{{ syncResult.duplicate_count }}</el-descriptions-item>
        <el-descriptions-item label="向量数">{{ syncResult.embed_count }}</el-descriptions-item>
        <el-descriptions-item label="耗时(ms)">{{ syncResult.duration_ms }}</el-descriptions-item>
      </el-descriptions>
      <p class="mt-2" style="color:#666;">{{ syncResult.message }}</p>
    </el-dialog>

    <!-- 同步日志 -->
    <el-card class="mt-3">
      <template #header>
        <span><el-icon><List /></el-icon> 最近同步日志</span>
      </template>
      <el-table :data="logs" v-loading="logLoading" border stripe size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="source_id" label="数据源" width="80" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="logTag(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_count" label="读取" width="70" />
        <el-table-column prop="success_count" label="成功" width="70" />
        <el-table-column prop="fail_count" label="失败" width="70" />
        <el-table-column prop="duplicate_count" label="去重" width="70" />
        <el-table-column prop="embed_count" label="向量" width="70" />
        <el-table-column prop="duration_ms" label="耗时(ms)" width="90" />
        <el-table-column prop="started_at" label="开始时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误信息" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  listDataSources, createDataSource, updateDataSource,
  deleteDataSource, testDataSource, syncDataSource, listSyncLogs
} from '@/api/datasource.js'

const loading = ref(false)
const sources = ref([])
const logs = ref([])
const logLoading = ref(false)

const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const submitting = ref(false)

const defaultConfig = () => ({
  file_path: '',
  file_encoding: 'utf-8',
  search_query: '',
  delimiter: ',',
  json_path: '',
  api_url: '',
  api_method: 'GET',
  api_query: {},
  api_headers: {},
  api_body: {},
  auth_type: 'none',
  auth_token: '',
  auth_key_name: '',
  auth_key_value: '',
  auth_in: 'header',
  auth_refresh_url: '',
  auth_refresh_method: 'POST',
  auth_refresh_query: {},
  auth_refresh_headers: {},
  auth_refresh_body: {},
  auth_refresh_token_path: 'access_token',
  pagination_enabled: false,
  page_param: 'page',
  page_start: 1,
  page_size_param: 'page_size',
  page_size: 20,
  max_pages: 5,
  rate_limit_ms: 0,
  retry_max_attempts: 3,
  retry_backoff_ms: 500,
  has_more_path: '',
  field_mapping: {
    title: 'title',
    company: 'company',
    location: 'location',
    salary_range: 'salary',
    experience_requirement: 'experience',
    education_requirement: 'education',
    raw_text: 'description',
    skill_tags: 'skills',
    industry: 'industry',
    external_url: 'url',
  }
})

const form = reactive({
  id: null,
  name: '',
  source_type: 'csv',
  config: defaultConfig(),
  status: 1,
})

const headerJson = ref('{}')
const queryJson = ref('{}')
const bodyJson = ref('{}')
const mappingJson = ref('')

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  source_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
}

const syncingId = ref(null)
const syncVisible = ref(false)
const syncResult = reactive({ status: '', total_count: 0, success_count: 0, fail_count: 0, duplicate_count: 0, embed_count: 0, duration_ms: 0, message: '' })

const testVisible = ref(false)
const testResult = reactive({ connectable: false, sample: [], message: '' })

const sampleKeys = computed(() => {
  if (!testResult.sample.length) return []
  return Object.keys(testResult.sample[0]).slice(0, 6)
})

function typeTag(t) {
  const map = { csv: 'primary', json: 'success', api: 'warning', mock: 'info', arbeitnow: 'danger' }
  return map[t] || ''
}
function logTag(s) {
  const map = { success: 'success', partial: 'warning', failed: 'danger', running: 'primary' }
  return map[s] || 'info'
}
function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString()
}

async function fetchSources() {
  loading.value = true
  try {
    const res = await listDataSources()
    sources.value = Array.isArray(res) ? res : (res?.items || [])
  } finally {
    loading.value = false
  }
}

async function fetchLogs() {
  logLoading.value = true
  try {
    const ids = sources.value.map(s => s.id)
    if (!ids.length) {
      logs.value = []
      return
    }

    const results = await Promise.allSettled(
      ids.map(id => listSyncLogs(id, { page: 1, page_size: 20 })),
    )

    const merged = results
      .filter(result => result.status === 'fulfilled')
      .flatMap(result => result.value?.items || [])
      .sort((a, b) => new Date(b.started_at || 0).getTime() - new Date(a.started_at || 0).getTime())

    const seen = new Set()
    logs.value = merged.filter((item) => {
      if (!item?.id || seen.has(item.id)) {
        return false
      }
      seen.add(item.id)
      return true
    }).slice(0, 20)
  } finally {
    logLoading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  form.id = null
  form.name = ''
  form.source_type = 'csv'
  form.config = defaultConfig()
  form.status = 1
  headerJson.value = '{}'
  queryJson.value = '{}'
  bodyJson.value = '{}'
  mappingJson.value = JSON.stringify(defaultConfig().field_mapping, null, 2)
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.id = row.id
  form.name = row.name
  form.source_type = row.source_type
  form.config = Object.assign(defaultConfig(), row.config || {})
  form.status = row.status
  headerJson.value = JSON.stringify(form.config.api_headers || {}, null, 2)
  queryJson.value = JSON.stringify(form.config.api_query || {}, null, 2)
  bodyJson.value = JSON.stringify(form.config.api_body || {}, null, 2)
  mappingJson.value = JSON.stringify(form.config.field_mapping || {}, null, 2)
  dialogVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  // 解析 JSON 字段
  try {
    if (form.source_type === 'api') {
      form.config.api_headers = JSON.parse(headerJson.value || '{}')
      form.config.api_query = JSON.parse(queryJson.value || '{}')
      form.config.api_body = JSON.parse(bodyJson.value || '{}')
    }
    form.config.field_mapping = JSON.parse(mappingJson.value || '{}')
  } catch {
    ElMessage.error('JSON 格式错误，请检查字段映射或 Headers')
    return
  }

  submitting.value = true
  try {
    const payload = {
      name: form.name,
      source_type: form.source_type,
      config: form.config,
      sync_interval: 0,
    }
    if (isEdit.value) {
      await updateDataSource(form.id, { name: form.name, config: form.config, status: form.status })
      ElMessage.success('更新成功')
    } else {
      await createDataSource(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await fetchSources()
    await fetchLogs()
  } finally {
    submitting.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除数据源 "${row.name}" 吗？`, '提示', { type: 'warning' })
  await deleteDataSource(row.id)
  ElMessage.success('删除成功')
  await fetchSources()
  await fetchLogs()
}

async function testConnect(row) {
  const res = await testDataSource(row.id)
  Object.assign(testResult, res || {})
  testVisible.value = true
}

async function doSync(row) {
  syncingId.value = row.id
  try {
    const res = await syncDataSource(row.id, { dry_run: false, limit: 0 })
    Object.assign(syncResult, res || {})
    syncVisible.value = true
    await fetchSources()
    await fetchLogs()
  } finally {
    syncingId.value = null
  }
}

onMounted(() => {
  fetchSources().then(fetchLogs)
})
</script>

<style scoped>
.page { padding: 20px; }
.fr { float: right; }
.mt-2 { margin-top: 12px; }
.mt-3 { margin-top: 20px; }
</style>
