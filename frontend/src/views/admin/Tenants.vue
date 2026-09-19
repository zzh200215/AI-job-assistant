<template>
  <div class="page-shell">
    <section class="page-heading">
      <div>
        <p class="section-kicker">多租户运营</p>
        <h2>租户管理</h2>
        <p class="page-header-sub">
          可视化创建 / 停用租户、分配域名与管理员，配套套餐与品牌（T4-1）。
        </p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" @click="loadTenants"
          ><el-icon><Refresh /></el-icon>刷新</el-button
        >
        <el-button type="primary" @click="openCreate"
          ><el-icon><Plus /></el-icon>新建租户</el-button
        >
      </div>
    </section>

    <section class="summary-grid">
      <div>
        <span>租户总数</span><strong>{{ total }}</strong>
      </div>
      <div>
        <span>有效租户</span><strong>{{ activeCount }}</strong>
      </div>
      <div>
        <span>近 30 天到期</span><strong>{{ expiringCount }}</strong>
      </div>
    </section>

    <el-card shadow="never" class="panel">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          class="search-input"
          placeholder="搜索名称、标识"
          clearable
          :prefix-icon="Search"
          @keyup.enter="loadTenants"
          @clear="loadTenants"
        />
        <el-select v-model="statusFilter" class="status-select" @change="loadTenants">
          <el-option label="全部状态" value="all" />
          <el-option label="有效" value="active" />
          <el-option label="已暂停" value="suspended" />
          <el-option label="已过期" value="expired" />
        </el-select>
        <el-button :icon="Search" @click="loadTenants">查询</el-button>
      </div>
      <el-table
        v-loading="loading"
        :data="tenants"
        size="small"
        style="width: 100%"
        empty-text="未找到匹配的租户"
      >
        <el-table-column label="租户" min-width="220">
          <template #default="{ row }">
            <div class="tenant-cell">
              <span class="tenant-avatar">{{ initials(row.name) }}</span>
              <span>
                <strong>{{ row.name }}</strong>
                <small>{{ row.slug }} · #{{ row.id }}</small>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="套餐" width="104">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="planTagType(row.plan_tier)">{{
              planLabel(row.plan_tier)
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="管理员" min-width="110">
          <template #default="{ row }">{{ row.admin_user_id ? `用户 #${row.admin_user_id}` : '-' }}</template>
        </el-table-column>
        <el-table-column label="域名" width="86">
          <template #default="{ row }">
            <el-button v-if="domains[row.id]?.length" text type="primary" @click="openDomains(row)">
              {{ domains[row.id].length }} 个
            </el-button>
            <el-button v-else text type="primary" @click="openDomains(row)">绑定</el-button>
          </template>
        </el-table-column>
        <el-table-column label="到期时间" min-width="180">
          <template #default="{ row }">
            <div class="expiry-cell">
              <span>{{ formatTime(row.expires_at) }}</span>
              <el-tag v-if="expiryHint(row)" size="small" :type="expiryType(row)">{{
                expiryHint(row)
              }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button text type="primary" @click="openAdmin(row)">管理员</el-button>
            <el-button text type="warning" @click="openRenew(row)">续费</el-button>
            <el-button
              v-if="row.status !== 'expired'"
              text
              type="danger"
              @click="deactivate(row)"
              >停用</el-button
            >
            <el-button v-else text type="success" @click="activate(row)">启用</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer">
        <span>每页 {{ pageSize }} 条</span>
        <el-pagination
          v-if="total > pageSize"
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="loadTenants"
        />
      </div>
    </el-card>

    <!-- 创建租户 -->
    <el-dialog v-model="createVisible" title="新建租户" width="480px">
      <el-form label-width="86px" @submit.prevent>
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="客户公司名" />
        </el-form-item>
        <el-form-item label="标识" required>
          <el-input v-model="createForm.slug" placeholder="customer-a（小写字母/数字/中划线）" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="createForm.industry" placeholder="如 教育 / 互联网" />
        </el-form-item>
        <el-form-item label="套餐">
          <el-select v-model="createForm.plan_tier" style="width: 100%">
            <el-option label="免费 free" value="free" />
            <el-option label="专业 pro" value="pro" />
            <el-option label="企业 enterprise" value="enterprise" />
          </el-select>
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker
            v-model="createForm.expires_at"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空为永久"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="绑定域名">
          <el-input v-model="createForm.domain" placeholder="可选，如 customer-a.com" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑租户 -->
    <el-dialog v-model="editVisible" title="编辑租户" width="480px">
      <el-form label-width="86px" @submit.prevent>
        <el-form-item label="名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="editForm.industry" />
        </el-form-item>
        <el-form-item label="套餐">
          <el-select v-model="editForm.plan_tier" style="width: 100%">
            <el-option label="免费 free" value="free" />
            <el-option label="专业 pro" value="pro" />
            <el-option label="企业 enterprise" value="enterprise" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width: 100%">
            <el-option label="有效 active" value="active" />
            <el-option label="已暂停 suspended" value="suspended" />
            <el-option label="已过期 expired" value="expired" />
          </el-select>
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker
            v-model="editForm.expires_at"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空为永久"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分配管理员 -->
    <el-dialog v-model="adminVisible" title="分配租户管理员" width="400px">
      <p class="dialog-hint">输入系统用户 ID，该用户将成为此租户的管理员。</p>
      <el-input-number v-model="adminForm.user_id" :min="1" style="width: 100%" />
      <template #footer>
        <el-button @click="adminVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitAdmin">分配</el-button>
      </template>
    </el-dialog>

    <!-- 续费 -->
    <el-dialog v-model="renewVisible" title="租户续费" width="440px">
      <el-form label-width="86px" @submit.prevent>
        <el-form-item label="续费月数" required>
          <el-input-number v-model="renewForm.months" :min="1" :max="36" style="width: 100%" />
        </el-form-item>
        <el-form-item label="实付金额(分)">
          <el-input-number v-model="renewForm.amount" :min="0" :step="100" style="width: 100%" />
        </el-form-item>
      </el-form>
      <p class="dialog-hint">
        续费后立即生效：租户恢复 active、其下订阅重新开通，到期时间顺延
        {{ renewForm.months }} 个月。
      </p>
      <template #footer>
        <el-button @click="renewVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRenew">确认续费</el-button>
      </template>
    </el-dialog>

    <!-- 域名管理 -->
    <el-dialog v-model="domainsVisible" title="域名绑定" width="480px">
      <div class="domain-add">
        <el-input v-model="newDomain" placeholder="如 customer-a.com" @keyup.enter="bindDomain" />
        <el-button type="primary" :loading="saving" @click="bindDomain">绑定</el-button>
      </div>
      <el-empty v-if="!currentDomains.length" description="尚未绑定域名" :image-size="64" />
      <div v-for="d in currentDomains" :key="d.domain" class="domain-row">
        <span>
          <el-tag v-if="d.is_primary" size="small" type="success">主</el-tag>
          {{ d.domain }}
        </span>
        <el-button text type="danger" @click="unbindDomain(d)">解绑</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  assignTenantAdmin,
  bindTenantDomain,
  createTenant,
  listTenantDomains,
  listTenants,
  renewTenant,
  unbindTenantDomain,
  updateTenant,
} from '@/api/tenant'

const tenants = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const statusFilter = ref('all')
const domains = ref({}) // tenant_id -> [domain rows]

const createVisible = ref(false)
const createForm = reactive({ name: '', slug: '', industry: '', plan_tier: 'free', expires_at: '', domain: '' })
const editVisible = ref(false)
const editForm = reactive({ id: null, name: '', industry: '', plan_tier: 'free', status: 'active', expires_at: '' })
const adminVisible = ref(false)
const adminForm = reactive({ tenant_id: null, user_id: null })
const renewVisible = ref(false)
const renewForm = reactive({ tenant_id: null, months: 1, amount: 0 })
const domainsVisible = ref(false)
const currentTenant = ref(null)
const newDomain = ref('')

const activeCount = computed(() => tenants.value.filter((t) => t.status === 'active').length)
const expiringCount = computed(() => {
  const soon = Date.now() + 30 * 24 * 60 * 60 * 1000
  return tenants.value.filter((t) => t.expires_at && new Date(t.expires_at).getTime() <= soon).length
})
const currentDomains = computed(() => domains.value[currentTenant.value?.id] || [])

function initials(name) {
  return String(name || 'T').slice(0, 1).toUpperCase()
}
function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
}
function statusLabel(s) {
  return { active: '有效', suspended: '已暂停', expired: '已过期' }[s] || s || '-'
}
function statusTagType(s) {
  return { active: 'success', suspended: 'warning', expired: 'danger' }[s] || 'info'
}
function planLabel(p) {
  return { free: '免费', pro: '专业', enterprise: '企业' }[p] || p || '-'
}
function planTagType(p) {
  return { free: 'info', pro: 'primary', enterprise: 'warning' }[p] || 'info'
}

async function loadTenants() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    const res = await listTenants(params, { notifyError: false })
    const data = res?.data || res || {}
    tenants.value = data.items || []
    total.value = data.total || 0
    await Promise.all(tenants.value.map((t) => loadDomains(t.id)))
  } catch {
    ElMessage.error('租户列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadDomains(tenantId) {
  try {
    const res = await listTenantDomains(tenantId, { notifyError: false })
    domains.value[tenantId] = res?.data || res || []
  } catch {
    domains.value[tenantId] = []
  }
}

function openCreate() {
  Object.assign(createForm, { name: '', slug: '', industry: '', plan_tier: 'free', expires_at: '', domain: '' })
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.name.trim()) return ElMessage.warning('请填写租户名称')
  saving.value = true
  try {
    const payload = { ...createForm }
    const org = await createTenant(payload)
    if (payload.domain) {
      await bindTenantDomain(org.id, { domain: payload.domain, is_primary: true }).catch(() => {})
    }
    ElMessage.success('租户已创建')
    createVisible.value = false
    await loadTenants()
  } catch (err) {
    ElMessage.error(err?.userMessage || '创建失败')
  } finally {
    saving.value = false
  }
}

function openEdit(row) {
  Object.assign(editForm, {
    id: row.id,
    name: row.name,
    industry: row.industry || '',
    plan_tier: row.plan_tier || 'free',
    status: row.status || 'active',
    expires_at: row.expires_at ? String(row.expires_at).slice(0, 19) : '',
  })
  editVisible.value = true
}

async function submitEdit() {
  if (!editForm.name.trim()) return ElMessage.warning('请填写租户名称')
  saving.value = true
  try {
    await updateTenant(editForm.id, {
      name: editForm.name,
      industry: editForm.industry,
      plan_tier: editForm.plan_tier,
      status: editForm.status,
      expires_at: editForm.expires_at || null,
    })
    ElMessage.success('租户已更新')
    editVisible.value = false
    await loadTenants()
  } catch (err) {
    ElMessage.error(err?.userMessage || '保存失败')
  } finally {
    saving.value = false
  }
}

function openAdmin(row) {
  adminForm.tenant_id = row.id
  adminForm.user_id = null
  adminVisible.value = true
}

function expiryHint(row) {
  if (!row.expires_at) return ''
  const days = Math.ceil((new Date(row.expires_at) - Date.now()) / (24 * 60 * 60 * 1000))
  if (days < 0) return '已过期'
  if (days <= 30) return `剩余 ${days} 天`
  return ''
}
function expiryType(row) {
  if (!row.expires_at) return 'info'
  return new Date(row.expires_at) < Date.now() ? 'danger' : 'warning'
}

function openRenew(row) {
  renewForm.tenant_id = row.id
  renewForm.months = 1
  renewForm.amount = 0
  renewVisible.value = true
}

async function submitRenew() {
  saving.value = true
  try {
    await renewTenant(renewForm.tenant_id, {
      months: renewForm.months,
      amount: renewForm.amount,
    })
    ElMessage.success('租户已续费，订阅已恢复')
    renewVisible.value = false
    await loadTenants()
  } catch (err) {
    ElMessage.error(err?.userMessage || '续费失败')
  } finally {
    saving.value = false
  }
}

async function submitAdmin() {
  if (!adminForm.user_id) return ElMessage.warning('请输入用户 ID')
  saving.value = true
  try {
    await assignTenantAdmin(adminForm.tenant_id, { user_id: adminForm.user_id })
    ElMessage.success('管理员已分配')
    adminVisible.value = false
    await loadTenants()
  } catch (err) {
    ElMessage.error(err?.userMessage || '分配失败')
  } finally {
    saving.value = false
  }
}

async function openDomains(row) {
  currentTenant.value = row
  newDomain.value = ''
  await loadDomains(row.id)
  domainsVisible.value = true
}

async function bindDomain() {
  const domain = newDomain.value.trim()
  if (!domain) return ElMessage.warning('请输入域名')
  saving.value = true
  try {
    await bindTenantDomain(currentTenant.value.id, { domain })
    ElMessage.success('域名已绑定')
    newDomain.value = ''
    await loadDomains(currentTenant.value.id)
    await loadTenants()
  } catch (err) {
    ElMessage.error(err?.userMessage || '绑定失败')
  } finally {
    saving.value = false
  }
}

async function unbindDomain(d) {
  try {
    await ElMessageBox.confirm(`确定解绑域名「${d.domain}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  saving.value = true
  try {
    await unbindTenantDomain(currentTenant.value.id, d.domain)
    ElMessage.success('域名已解绑')
    await loadDomains(currentTenant.value.id)
  } catch (err) {
    ElMessage.error(err?.userMessage || '解绑失败')
  } finally {
    saving.value = false
  }
}

async function deactivate(row) {
  try {
    await ElMessageBox.confirm(
      `确定停用租户「${row.name}」？停用后该租户域名下所有请求将返回 403。`,
      '停用确认',
      { type: 'warning', confirmButtonText: '停用' }
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await updateTenant(row.id, { status: 'expired' })
    ElMessage.success('租户已停用')
    await loadTenants()
  } catch (err) {
    ElMessage.error(err?.userMessage || '停用失败')
  } finally {
    saving.value = false
  }
}

async function activate(row) {
  saving.value = true
  try {
    await updateTenant(row.id, { status: 'active' })
    ElMessage.success('租户已启用')
    await loadTenants()
  } catch (err) {
    ElMessage.error(err?.userMessage || '启用失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadTenants)
</script>

<style scoped>
.page-shell {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 6px 0 18px;
}
.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}
.heading-actions {
  display: flex;
  gap: 10px;
}
.section-kicker {
  margin: 0 0 5px;
  color: var(--app-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.page-heading h2 {
  margin: 0;
  font-size: 24px;
  color: var(--app-text);
}
.page-header-sub {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 14px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
}
.summary-grid div {
  padding: 13px 18px;
  border-right: 1px solid var(--app-line);
}
.summary-grid div:last-child {
  border: 0;
}
.summary-grid span,
.summary-grid strong {
  display: block;
}
.summary-grid span {
  color: var(--app-muted);
  font-size: 12px;
}
.summary-grid strong {
  margin-top: 3px;
  color: var(--app-text);
  font-size: 20px;
}
.panel {
  border-radius: 8px;
  border-color: var(--app-line);
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0 16px;
}
.search-input {
  width: min(300px, 100%);
}
.status-select {
  width: 130px;
}
.tenant-cell {
  display: flex;
  align-items: center;
  gap: 9px;
}
.tenant-avatar {
  width: 29px;
  height: 29px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 7px;
  color: var(--app-primary);
  font-weight: 700;
  background: var(--app-primary-light);
  font-size: 12px;
}
.tenant-cell strong,
.tenant-cell small {
  display: block;
}
.tenant-cell strong {
  color: var(--app-text);
  font-size: 13px;
}
.tenant-cell small {
  margin-top: 1px;
  color: var(--app-muted);
  font-size: 11px;
}
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 15px;
  color: var(--app-muted);
  font-size: 12px;
}
.expiry-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.dialog-hint {
  margin: 0 0 12px;
  color: var(--app-muted);
  font-size: 13px;
}
.domain-add {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.domain-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border: 1px solid var(--app-line);
  border-radius: 7px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--app-text);
}
@media (max-width: 680px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .summary-grid {
    grid-template-columns: 1fr;
  }
  .summary-grid div {
    border-right: 0;
    border-bottom: 1px solid var(--app-line);
  }
  .toolbar {
    align-items: stretch;
    flex-wrap: wrap;
  }
  .search-input {
    width: 100%;
  }
}
</style>
