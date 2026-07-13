<template>
  <div class="page-shell">
    <section class="overview-heading">
      <div>
        <p class="section-kicker">运营概览</p>
        <h2>今天的系统运营信号</h2>
        <p class="page-header-sub">统一查看用户增长、订阅转化和需要跟进的订单。</p>
      </div>
      <el-button :loading="loading" @click="loadOverview">
        <el-icon><Refresh /></el-icon>
        刷新数据
      </el-button>
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
      <el-card shadow="never" class="panel trend-panel">
        <template #header>
          <div class="card-heading">
            <div>
              <h3>订单状态</h3>
              <span>当前已加载的最近订单</span>
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
        <el-empty v-if="!orders.length && !loading" description="暂无订单数据" :image-size="72" />
      </el-card>

      <el-card shadow="never" class="panel action-panel">
        <template #header
          ><div class="card-heading">
            <div>
              <h3>待处理事项</h3>
              <span>按优先级快速进入工作区</span>
            </div>
          </div></template
        >
        <div class="action-list">
          <button class="action-item" type="button" @click="router.push('/admin/orders')">
            <span class="action-icon amber"
              ><el-icon><Tickets /></el-icon
            ></span>
            <span
              ><strong>待支付订单</strong
              ><small>{{ pendingOrders }} 笔订单等待处理或确认</small></span
            >
            <el-icon class="action-arrow"><ArrowRight /></el-icon>
          </button>
          <button class="action-item" type="button" @click="router.push('/admin/users')">
            <span class="action-icon blue"
              ><el-icon><User /></el-icon
            ></span>
            <span><strong>最新注册用户</strong><small>查看最近加入的平台用户</small></span>
            <el-icon class="action-arrow"><ArrowRight /></el-icon>
          </button>
          <button class="action-item" type="button" @click="router.push('/system-status')">
            <span class="action-icon green"
              ><el-icon><Monitor /></el-icon
            ></span>
            <span><strong>运行状态检查</strong><small>确认服务模式与功能开关</small></span>
            <el-icon class="action-arrow"><ArrowRight /></el-icon>
          </button>
        </div>
      </el-card>
    </section>

    <el-card shadow="never" class="panel recent-panel">
      <template #header>
        <div class="card-heading">
          <div>
            <h3>最新订单</h3>
            <span>最近 6 笔订阅记录</span>
          </div>
          <el-button type="primary" plain @click="router.push('/admin/orders')">管理订单</el-button>
        </div>
      </template>
      <el-table v-if="orders.length" :data="orders.slice(0, 6)" size="small" style="width: 100%">
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
          ><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column
        >
      </el-table>
      <el-empty v-else-if="!loading" description="暂无可展示的订单" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  CreditCard,
  Monitor,
  Refresh,
  Tickets,
  User,
  UserFilled,
} from '@element-plus/icons-vue'
import request from '@/api/request'

const router = useRouter()
const loading = ref(false)
const totalUsers = ref(0)
const orders = ref([])

const paidOrders = computed(() => orders.value.filter((order) => order.status === 'paid'))
const pendingOrders = computed(
  () => orders.value.filter((order) => order.status === 'pending').length
)
const totalRevenue = computed(() =>
  paidOrders.value.reduce((sum, order) => sum + Number(order.amount || 0), 0)
)
const proUsers = computed(
  () =>
    new Set(
      paidOrders.value.filter((order) => order.plan_tier === 'pro').map((order) => order.user_id)
    ).size
)

const metricCards = computed(() => [
  {
    label: '注册用户',
    value: totalUsers.value,
    hint: '平台累计账户数',
    icon: UserFilled,
    tone: 'blue',
  },
  {
    label: 'Pro 用户',
    value: proUsers.value,
    hint: '按已支付 Pro 订单估算',
    icon: User,
    tone: 'violet',
  },
  {
    label: '待处理订单',
    value: pendingOrders.value,
    hint: '需要继续跟进',
    icon: Tickets,
    tone: 'amber',
  },
  {
    label: '已收款',
    value: formatMoney(totalRevenue.value),
    hint: '当前订单列表中的已支付金额',
    icon: CreditCard,
    tone: 'green',
  },
])

const orderBreakdown = computed(() => {
  const total = orders.value.length || 1
  const states = [
    { key: 'paid', label: '已支付', tone: 'green' },
    { key: 'pending', label: '待支付', tone: 'amber' },
    { key: 'cancelled', label: '已取消', tone: 'slate' },
  ]
  return states.map((state) => {
    const value = orders.value.filter((order) => order.status === state.key).length
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
function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
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

async function loadOverview() {
  loading.value = true
  try {
    const [usersData, ordersData] = await Promise.all([
      request.get('/auth/admin/users', { params: { page: 1, page_size: 1 }, notifyError: false }),
      request.get('/subscription/admin/orders', {
        params: { page: 1, page_size: 100 },
        notifyError: false,
      }),
    ])
    totalUsers.value = usersData?.data?.total || usersData?.total || 0
    const data = ordersData?.data || ordersData || {}
    orders.value = data.items || []
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
  background: #fff;
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
.action-list {
  display: flex;
  flex-direction: column;
}
.action-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 18px;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 11px 0;
  border: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}
.action-item:last-child {
  border-bottom: 0;
}
.action-item:hover strong {
  color: var(--app-primary);
}
.action-item span:not(.action-icon) {
  min-width: 0;
}
.action-item strong,
.action-item small {
  display: block;
}
.action-item strong {
  color: var(--app-text);
  font-size: 13px;
}
.action-item small {
  overflow: hidden;
  margin-top: 3px;
  color: var(--app-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.action-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 7px;
}
.action-icon.amber {
  color: #9a6200;
  background: #fff4d8;
}
.action-icon.blue {
  color: var(--app-primary);
  background: var(--app-primary-light);
}
.action-icon.green {
  color: #137a4a;
  background: #e7f7ef;
}
.action-arrow {
  color: var(--app-muted);
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
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  .metric-card {
    min-height: 118px;
  }
}
</style>
