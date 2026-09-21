<template>
  <div class="page-shell">
    <section class="page-heading">
      <div>
        <p class="section-kicker">订阅运营</p>
        <h2>订单管理</h2>
        <p class="page-header-sub">跟进订阅状态和近期收款记录。</p>
      </div>
      <el-button :loading="loading" @click="loadOrders"
        ><el-icon><Refresh /></el-icon>刷新</el-button
      >
    </section>
    <section class="summary-grid">
      <div>
        <span>当前页订单</span><strong>{{ orders.length }}</strong>
      </div>
      <div>
        <span>已支付</span><strong class="is-green">{{ paidCount }}</strong>
      </div>
      <div>
        <span>待支付</span><strong class="is-amber">{{ pendingCount }}</strong>
      </div>
      <div>
        <span>当前页已收款</span><strong>{{ formatMoney(paidRevenue) }}</strong>
      </div>
    </section>
    <el-card shadow="never" class="panel">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          class="search-input"
          placeholder="搜索订单号、用户 ID 或交易号"
          clearable
          :prefix-icon="Search"
        /><el-select v-model="statusFilter" class="status-select"
          ><el-option label="全部状态" value="all" /><el-option
            label="已支付"
            value="paid" /><el-option label="待支付" value="pending" /><el-option
            label="已取消"
            value="cancelled" /></el-select
        ><span class="result-count">显示 {{ filteredOrders.length }} / {{ orders.length }} 条</span>
      </div>
      <el-table
        v-loading="loading"
        :data="filteredOrders"
        size="small"
        style="width: 100%"
        empty-text="未找到匹配的订单"
        ><el-table-column label="订单" min-width="100"
          ><template #default="{ row }"
            ><strong class="order-id">#{{ row.id }}</strong></template
          ></el-table-column
        ><el-table-column label="用户" width="100"
          ><template #default="{ row }">用户 {{ row.user_id }}</template></el-table-column
        ><el-table-column label="套餐" width="110"
          ><template #default="{ row }">{{ planLabel(row.plan_tier) }}</template></el-table-column
        ><el-table-column label="金额" width="110"
          ><template #default="{ row }">{{ formatMoney(row.amount) }}</template></el-table-column
        ><el-table-column label="状态" width="110"
          ><template #default="{ row }"
            ><el-tag :type="statusType(row.status)" size="small">{{
              statusLabel(row.status)
            }}</el-tag></template
          ></el-table-column
        ><el-table-column label="创建时间" min-width="170"
          ><template #default="{ row }">{{
            dateTime(row.created_at, '-')
          }}</template></el-table-column
        ><el-table-column label="操作" width="84" fixed="right"
          ><template #default="{ row }"
            ><el-button text type="primary" @click="openDetail(row)">详情</el-button></template
          ></el-table-column
        ></el-table
      >
      <div class="table-footer">
        <span>每页 {{ pageSize }} 条</span
        ><el-pagination
          v-if="total > pageSize"
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="loadOrders"
        />
      </div>
    </el-card>
    <el-drawer v-model="drawerVisible" title="订单详情" size="420px"
      ><template v-if="selectedOrder"
        ><div class="drawer-order">
          <span>订单 #{{ selectedOrder.id }}</span
          ><el-tag :type="statusType(selectedOrder.status)">{{
            statusLabel(selectedOrder.status)
          }}</el-tag>
        </div>
        <el-descriptions :column="1" border
          ><el-descriptions-item label="用户 ID">{{ selectedOrder.user_id }}</el-descriptions-item
          ><el-descriptions-item label="套餐">{{
            planLabel(selectedOrder.plan_tier)
          }}</el-descriptions-item
          ><el-descriptions-item label="金额">{{
            formatMoney(selectedOrder.amount)
          }}</el-descriptions-item
          ><el-descriptions-item label="支付方式">{{
            selectedOrder.payment_method || '-'
          }}</el-descriptions-item
          ><el-descriptions-item label="交易号">{{
            selectedOrder.transaction_id || '-'
          }}</el-descriptions-item
          ><el-descriptions-item label="创建时间">{{
            dateTime(selectedOrder.created_at, '-')
          }}</el-descriptions-item
          ><el-descriptions-item label="支付时间">{{
            dateTime(selectedOrder.paid_at, '-')
          }}</el-descriptions-item></el-descriptions
        ></template
      ></el-drawer
    >
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import request from '@/api/request'
import { dateTime } from '@/utils/format/date'

const orders = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const keyword = ref('')
const statusFilter = ref('all')
const selectedOrder = ref(null)
const drawerVisible = ref(false)
const pageSize = 20
const filteredOrders = computed(() =>
  orders.value.filter((order) => {
    const term = keyword.value.trim().toLowerCase()
    const matchText =
      !term ||
      [order.id, order.user_id, order.transaction_id].some((item) =>
        String(item || '')
          .toLowerCase()
          .includes(term)
      )
    return matchText && (statusFilter.value === 'all' || order.status === statusFilter.value)
  })
)
const paidCount = computed(() => orders.value.filter((order) => order.status === 'paid').length)
const pendingCount = computed(
  () => orders.value.filter((order) => order.status === 'pending').length
)
const paidRevenue = computed(() =>
  orders.value
    .filter((order) => order.status === 'paid')
    .reduce((sum, order) => sum + Number(order.amount || 0), 0)
)
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
function openDetail(order) {
  selectedOrder.value = order
  drawerVisible.value = true
}
async function loadOrders() {
  loading.value = true
  try {
    const res = await request.get('/subscription/admin/orders', {
      params: { page: page.value, page_size: pageSize },
      notifyError: false,
    })
    const data = res?.data || res || {}
    orders.value = data.items || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('订单列表加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(loadOrders)
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
.section-kicker {
  margin: 0 0 5px;
  color: var(--app-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.page-heading h2 {
  margin: 0;
  color: var(--app-text);
  font-size: 24px;
}
.page-header-sub {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 14px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
.is-green {
  color: var(--app-success) !important;
}
.is-amber {
  color: var(--app-warning) !important;
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
  width: min(360px, 100%);
}
.status-select {
  width: 130px;
}
.result-count {
  margin-left: auto;
  color: var(--app-muted);
  font-size: 12px;
  white-space: nowrap;
}
.order-id {
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
}
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 15px;
  color: var(--app-muted);
  font-size: 12px;
}
.drawer-order {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  padding: 14px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  color: var(--app-text);
  font-size: 16px;
  font-weight: 700;
}
@media (max-width: 760px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .summary-grid div:nth-child(2) {
    border-right: 0;
  }
  .summary-grid div:nth-child(-n + 2) {
    border-bottom: 1px solid var(--app-line);
  }
  .toolbar {
    align-items: stretch;
    flex-wrap: wrap;
  }
  .search-input {
    width: 100%;
  }
  .result-count {
    width: 100%;
    margin-left: 0;
  }
  .table-footer {
    align-items: flex-start;
    gap: 10px;
    flex-direction: column;
  }
}
</style>
