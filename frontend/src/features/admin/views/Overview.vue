<template>
  <div class="page-shell">
    <section class="overview-heading">
      <div>
        <p class="section-kicker">运营概览</p>
        <h2>今天的系统运营信号</h2>
        <p class="page-header-sub">统一查看用户增长、订阅转化和需要跟进的订单。</p>
      </div>
      <div class="heading-actions">
        <el-select
          v-model="tenantId"
          class="tenant-select"
          clearable
          placeholder="全部租户"
          @change="loadAnalytics"
        >
          <el-option label="全部租户（平台级）" value="" />
          <el-option v-for="t in tenants" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-button :loading="loading" @click="loadOverview">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </div>
    </section>

    <section class="metrics-grid">
      <article v-for="item in metricCards" :key="item.label" class="metric-card" :class="item.tone">
        <div class="metric-icon">
          <el-icon><component :is="item.icon" /></el-icon>
        </div>
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </article>
    </section>

    <section class="work-grid">
      <el-card shadow="never" class="panel funnel-panel">
        <template #header>
          <div class="card-heading">
            <div>
              <h3>转化漏斗</h3>
              <span>近 30 天{{ tenantLabel }}注册 → 上传 → 分析 → 面试 → 订阅</span>
            </div>
          </div>
        </template>
        <div class="funnel-list">
          <div v-for="s in funnelSteps" :key="s.key" class="funnel-row">
            <span class="funnel-label">{{ s.label }}</span>
            <div class="funnel-track">
              <span :style="{ width: s.width }" />
            </div>
            <b>{{ s.count }}</b>
            <em>{{ s.rate }}%</em>
          </div>
        </div>
        <el-empty
          v-if="!funnelSteps.length && !loading"
          description="暂无漏斗数据"
          :image-size="72"
        />
      </el-card>

      <el-card shadow="never" class="panel action-panel">
        <template #header>
          <div class="card-heading">
            <div>
              <h3>订单状态</h3>
              <span>{{ tenantLabel }}最近订单</span>
            </div>
            <el-button text @click="router.push('/admin/orders')">查看订单</el-button>
          </div>
        </template>
        <div class="status-list">
          <div v-for="item in orderBreakdown" :key="item.label" class="status-row">
            <span class="status-label"><i :class="item.tone" />{{ item.label }}</span>
            <div class="status-track">
              <span :class="item.tone" :style="{ width: item.width }" />
            </div>
            <b>{{ item.value }}</b>
          </div>
        </div>
        <el-empty
          v-if="!filteredOrders.length && !loading"
          description="暂无订单数据"
          :image-size="72"
        />
      </el-card>
    </section>

    <el-card shadow="never" class="panel recent-panel">
      <template #header>
        <div class="card-heading">
          <div>
            <h3>最新订单</h3>
            <span>最近 6 笔{{ tenantLabel }}订阅记录</span>
          </div>
          <el-button type="primary" plain @click="router.push('/admin/orders')">管理订单</el-button>
        </div>
      </template>
      <el-table
        v-if="filteredOrders.length"
        :data="filteredOrders.slice(0, 6)"
        size="small"
        style="width: 100%"
      >
        <el-table-column prop="id" label="订单号" width="88"
          ><template #default="{ row }">#{{ row.id }}</template></el-table-column
        >
        <el-table-column label="套餐"
          ><template #default="{ row }">{{ planLabel(row.plan_tier) }}</template></el-table-column
        >
        <el-table-column label="金额" width="110"
          ><template #default="{ row }">{{ formatMoney(row.amount) }}</template></el-table-column
        >
        <el-table-column label="状态" width="110"
          ><template #default="{ row }"
            ><el-tag size="small" :type="statusType(row.status)">{{
              statusLabel(row.status)
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="创建时间" min-width="170"
          ><template #default="{ row }">{{
            dateTime(row.created_at, '-')
          }}</template></el-table-column
        >
      </el-table>
      <el-empty v-else-if="!loading" description="暂无可展示的订单" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CreditCard, Refresh, Tickets, User, UserFilled } from '@element-plus/icons-vue'
import request from '@/api/request'
import { listTenants } from '@/api/tenant'
import { dateTime } from '@/utils/format/date'

const router = useRouter()
const loading = ref(false)
const tenants = ref([])
const tenantId = ref('')
const summary = ref({})
const revenue = ref({})
const funnel = ref({})
const orders = ref([])

const tenantLabel = computed(() => {
  if (!tenantId.value) return '平台'
  const t = tenants.value.find((item) => String(item.id) === String(tenantId.value))
  return t ? `「${t.name}」` : '当前租户'
})
const filteredOrders = computed(() => {
  if (!tenantId.value) return orders.value
  const tid = Number(tenantId.value)
  return orders.value.filter((order) => Number(order.tenant_id) === tid)
})
const paidOrders = computed(() => filteredOrders.value.filter((order) => order.status === 'paid'))
const proUsers = computed(() => summary.value.pro_users || 0)
const totalUsers = computed(() => summary.value.total_users || 0)
const paidOrderCount = computed(() => summary.value.paid_orders || 0)

const metricCards = computed(() => [
  {
    label: '注册用户',
    value: totalUsers.value,
    hint: `${tenantLabel.value}用户口径`,
    icon: UserFilled,
    tone: 'blue',
  },
  {
    label: 'Pro 用户',
    value: proUsers.value,
    hint: '有效 pro 订阅用户',
    icon: User,
    tone: 'violet',
  },
  {
    label: '付费订单',
    value: paidOrderCount.value,
    hint: '已支付订单笔数',
    icon: Tickets,
    tone: 'amber',
  },
  {
    label: '已收款',
    value: formatMoney(revenue.value.total_amount),
    hint: '近 30 天已支付金额',
    icon: CreditCard,
    tone: 'green',
  },
])

const funnelSteps = computed(() => {
  const steps = funnel.value.steps || []
  const max = Math.max(...steps.map((s) => s.count || 0), 1)
  return steps.map((s) => ({
    ...s,
    width: `${Math.max((s.count / max) * 100, s.count ? 8 : 0)}%`,
  }))
})

const orderBreakdown = computed(() => {
  const total = filteredOrders.value.length || 1
  const states = [
    { key: 'paid', label: '已支付', tone: 'green' },
    { key: 'pending', label: '待支付', tone: 'amber' },
    { key: 'cancelled', label: '已取消', tone: 'slate' },
  ]
  return states.map((state) => {
    const value = filteredOrders.value.filter((order) => order.status === state.key).length
    return {
      ...state,
      value,
      width: `${Math.max(value ? (value / total) * 100 : 0, value ? 8 : 0)}%`,
    }
  })
})

function formatMoney(amount) {
  return `￥${Number(amount || 0).toFixed(2)}`
}
function planLabel(plan) {
  return { free: '免费版', pro: 'Pro', enterprise: '企业版' }[plan] || plan || '-'
}
function statusLabel(status) {
  return { paid: '已支付', pending: '待支付', cancelled: '已取消' }[status] || status || '未知'
}
function statusType(status) {
  return { paid: 'success', pending: 'warning', cancelled: 'info' }[status] || 'info'
}

async function loadTenants() {
  try {
    const res = await listTenants({ page: 1, page_size: 100 }, { notifyError: false })
    const data = res?.data || res || {}
    tenants.value = data.items || []
  } catch {
    tenants.value = []
  }
}

async function loadAnalytics() {
  loading.value = true
  try {
    const params = {}
    if (tenantId.value) params.tenant_id = tenantId.value
    const [summaryRes, revenueRes, funnelRes] = await Promise.all([
      request.get('/analytics/summary', { params: { ...params }, notifyError: false }),
      request.get('/admin/analytics/revenue', { params: { ...params }, notifyError: false }),
      request.get('/analytics/funnel', { params: { ...params }, notifyError: false }),
    ])
    summary.value = summaryRes?.data || summaryRes || {}
    revenue.value = revenueRes?.data || revenueRes || {}
    funnel.value = funnelRes?.data || funnelRes || {}
  } catch {
    summary.value = {}
    revenue.value = {}
    funnel.value = {}
  } finally {
    loading.value = false
  }
}

async function loadOrders() {
  try {
    const res = await request.get('/subscription/admin/orders', {
      params: { page: 1, page_size: 100 },
      notifyError: false,
    })
    const data = res?.data || res || {}
    orders.value = data.items || []
  } catch {
    orders.value = []
  }
}

async function loadOverview() {
  loading.value = true
  try {
    await Promise.all([loadTenants(), loadOrders(), loadAnalytics()])
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<style scoped>
.page-shell {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 6px 0 18px;
}
.overview-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}
.heading-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.tenant-select {
  width: 200px;
}
.section-kicker {
  margin: 0 0 5px;
  color: var(--app-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.overview-heading h2 {
  margin: 0;
  color: var(--app-text);
  font-size: 24px;
  line-height: 1.25;
}
.page-header-sub {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 14px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.metric-card {
  position: relative;
  overflow: hidden;
  min-height: 138px;
  padding: 18px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
}
.metric-card::after {
  content: '';
  position: absolute;
  right: -18px;
  bottom: -28px;
  width: 92px;
  height: 92px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.055;
}
.metric-card.blue {
  color: var(--app-primary);
}
.metric-card.violet {
  color: var(--app-violet);
}
.metric-card.amber {
  color: var(--app-warning);
}
.metric-card.green {
  color: var(--app-success);
}
.metric-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  margin-bottom: 12px;
  border-radius: 7px;
  background: color-mix(in srgb, currentColor 12%, white);
  font-size: 17px;
}
.metric-card > span,
.metric-card small {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}
.metric-card strong {
  display: block;
  margin: 5px 0;
  color: var(--app-text);
  font-size: 25px;
  line-height: 1.1;
}
.metric-card small {
  font-size: 11px;
}
.work-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 18px;
}
.panel {
  border-radius: 8px;
  border-color: var(--app-line);
}
.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.card-heading h3 {
  margin: 0;
  color: var(--app-text);
  font-size: 15px;
}
.card-heading span {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}
.funnel-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 2px;
}
.funnel-row {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr) 34px 44px;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.funnel-label {
  color: var(--app-text);
}
.funnel-track {
  height: 7px;
  overflow: hidden;
  border-radius: 7px;
  background: var(--el-fill-color-light);
}
.funnel-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--app-primary);
}
.funnel-row b {
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.funnel-row em {
  color: var(--app-muted);
  font-size: 12px;
  font-style: normal;
  text-align: right;
}
.status-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 4px 2px;
}
.status-row {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr) 28px;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.status-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--app-text);
}
.status-label i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.status-track {
  height: 7px;
  overflow: hidden;
  border-radius: 7px;
  background: var(--el-fill-color-light);
}
.status-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
}
.green {
  background: var(--app-success);
}
.amber {
  background: var(--app-warning);
}
.slate {
  background: var(--app-muted);
}
.status-row b {
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.recent-panel :deep(.el-card__body) {
  padding-top: 8px;
}
@media (max-width: 1050px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .work-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .overview-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .heading-actions {
    width: 100%;
    flex-wrap: wrap;
  }
  .tenant-select {
    flex: 1;
    min-width: 160px;
  }
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  .metric-card {
    min-height: 118px;
  }
}
</style>
