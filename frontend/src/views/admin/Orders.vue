<template>
  <div class="page-shell">
    <div class="page-header">
      <div><h2>订单管理</h2><div class="page-header-sub">共 {{ total }} 笔订单</div></div>
    </div>

    <div class="panel">
      <div class="panel-body">
        <el-table :data="orders" stripe border size="small" style="width:100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="user_id" label="用户ID" width="70" />
          <el-table-column label="套餐" width="80"><template #default="{ row }">{{ row.plan_tier }}</template></el-table-column>
          <el-table-column label="金额" width="80"><template #default="{ row }">¥{{ (row.amount / 100).toFixed(2) }}</template></el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'paid' ? 'success' : row.status === 'pending' ? 'warning' : 'info'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="payment_method" label="支付方式" width="100" />
          <el-table-column prop="transaction_id" label="交易号" width="160" />
          <el-table-column label="创建时间" width="160"><template #default="{ row }">{{ row.created_at }}</template></el-table-column>
          <el-table-column label="支付时间" width="160"><template #default="{ row }">{{ row.paid_at || '-' }}</template></el-table-column>
        </el-table>
        <div class="pagination-row" v-if="total > pageSize">
          <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="loadOrders" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'

const orders = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20

async function loadOrders() {
  try {
    const res = await request.get('/subscription/admin/orders', { params: { page: page.value, page_size: pageSize } })
    const data = res?.data || {}
    orders.value = data.items || []
    total.value = data.total || 0
  } catch {}
}

onMounted(loadOrders)
</script>

<style scoped>
.page-shell { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; padding: 18px 0; }
.panel { border-radius: 16px; border: 1px solid var(--app-line); background: #fff; box-shadow: var(--app-shadow-soft); }
.panel-body { padding: 16px; }
.pagination-row { margin-top: 16px; display: flex; justify-content: center; }
</style>
