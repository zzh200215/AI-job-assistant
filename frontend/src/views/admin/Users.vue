<template>
  <div class="page-shell">
    <div class="page-header">
      <div><h2>用户管理</h2><div class="page-header-sub">共 {{ total }} 个用户</div></div>
    </div>

    <div class="panel">
      <div class="panel-body">
        <el-table :data="users" stripe border size="small" style="width:100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="username" label="用户名" width="120" />
          <el-table-column prop="email" label="邮箱" width="180" />
          <el-table-column label="角色" width="80"><template #default="{ row }">{{ row.is_admin ? '管理员' : '用户' }}</template></el-table-column>
          <el-table-column label="注册时间" width="160"><template #default="{ row }">{{ row.created_at }}</template></el-table-column>
          <el-table-column label="操作" width="80"><template #default="{ row }">
            <el-button text size="small" @click="viewUser(row)">查看</el-button>
          </template></el-table-column>
        </el-table>
        <div class="pagination-row" v-if="total > pageSize">
          <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="loadUsers" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from '@/plugins/element-services'
import request from '@/api/request'

const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

async function loadUsers() {
  loading.value = true
  try {
    const res = await request.get('/auth/admin/users', { params: { page: page.value, page_size: pageSize } })
    const data = res?.data || {}
    users.value = data.items || []
    total.value = data.total || 0
  } catch { ElMessage.error('加载失败') } finally { loading.value = false }
}

function viewUser(row) {
  ElMessage.info(`用户 ${row.username}: ID=${row.id}, 邮箱=${row.email}, 角色=${row.is_admin ? '管理员' : '用户'}`)
}

onMounted(loadUsers)
</script>

<style scoped>
.page-shell { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; padding: 18px 0; }
.panel { border-radius: 16px; border: 1px solid var(--app-line); background: #fff; box-shadow: var(--app-shadow-soft); }
.panel-body { padding: 16px; }
.pagination-row { margin-top: 16px; display: flex; justify-content: center; }
</style>
