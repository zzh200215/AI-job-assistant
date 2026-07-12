<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>管理后台</h2>
        <div class="page-header-sub">系统运营数据总览</div>
      </div>
    </div>

    <div class="stats-row">
      <div class="stat-card">
        <span class="stat-label">用户总数</span>
        <strong class="stat-value">{{ stats.total_users }}</strong>
      </div>
      <div class="stat-card">
        <span class="stat-label">Pro 用户</span>
        <strong class="stat-value stat-pro">{{ stats.pro_users }}</strong>
      </div>
      <div class="stat-card">
        <span class="stat-label">今日订单</span>
        <strong class="stat-value stat-order">{{ stats.today_orders }}</strong>
      </div>
      <div class="stat-card">
        <span class="stat-label">订单总额</span>
        <strong class="stat-value stat-revenue">¥{{ stats.total_revenue }}</strong>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>快捷入口</h3></div>
      <div class="panel-body">
        <div class="quick-links">
          <el-button @click="$router.push('/admin/users')" size="large"><el-icon><User /></el-icon> 用户管理</el-button>
          <el-button @click="$router.push('/admin/orders')" size="large"><el-icon><Coin /></el-icon> 订单管理</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Coin, User } from '@element-plus/icons-vue'
import request from '@/api/request'

const stats = ref({
  total_users: 0,
  pro_users: 0,
  today_orders: 0,
  total_revenue: 0,
})

onMounted(async () => {
  try {
    const usersData = await request.get('/auth/admin/users', { params: { page: 1, page_size: 1 } })
    const ordersData = await request.get('/subscription/admin/orders', { params: { page: 1, page_size: 50 } })
    const users = usersData?.data || {}
    const orders = ordersData?.data || {}
    stats.value.total_users = users.total || 0
    const today = new Date().toDateString()
    const allOrders = orders.items || []
    stats.value.today_orders = allOrders.filter(o => o.created_at && new Date(o.created_at).toDateString() === today).length
    stats.value.total_revenue = allOrders.filter(o => o.status === 'paid').reduce((s, o) => s + (o.amount || 0), 0) / 100
    stats.value.pro_users = 0 // 需要单独查询
  } catch {}
})
</script>

<style scoped>
.page-shell { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; padding: 18px 0; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.stat-card { padding: 20px; border-radius: 16px; background: #fff; border: 1px solid var(--app-line); text-align: center; box-shadow: var(--app-shadow-soft); }
.stat-label { display: block; font-size: 12px; color: var(--app-muted); }
.stat-value { display: block; font-size: 32px; font-weight: 800; color: var(--app-primary); margin-top: 8px; }
.stat-pro { color: var(--app-violet) !important; }
.stat-order { color: var(--app-warning) !important; }
.stat-revenue { color: var(--app-success) !important; }
.quick-links { display: flex; gap: 12px; }
.panel { border-radius: 16px; border: 1px solid var(--app-line); background: #fff; box-shadow: var(--app-shadow-soft); }
.panel-header { padding: 16px 20px; border-bottom: 1px solid var(--app-line); }
.panel-header h3 { margin: 0; font-size: 16px; font-weight: 700; }
.panel-body { padding: 20px; }
</style>
