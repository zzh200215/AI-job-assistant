<template>
  <div class="page-shell">
    <section class="page-heading">
      <div>
        <p class="section-kicker">账户运营</p>
        <h2>用户管理</h2>
        <p class="page-header-sub">{{ total }} 个账户，支持按当前加载数据搜索和筛选。</p>
      </div>
      <el-button :loading="loading" @click="loadUsers"
        ><el-icon><Refresh /></el-icon>刷新</el-button
      >
    </section>

    <section class="summary-grid">
      <div>
        <span>当前页用户</span><strong>{{ users.length }}</strong>
      </div>
      <div>
        <span>管理员</span><strong>{{ adminCount }}</strong>
      </div>
      <div>
        <span>近 7 天注册</span><strong>{{ recentCount }}</strong>
      </div>
    </section>

    <el-card shadow="never" class="panel">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          class="search-input"
          placeholder="搜索用户名、邮箱或 ID"
          clearable
          :prefix-icon="Search"
        />
        <el-select v-model="roleFilter" class="role-select">
          <el-option label="全部角色" value="all" /><el-option
            label="管理员"
            value="admin"
          /><el-option label="普通用户" value="user" />
        </el-select>
        <span class="result-count">显示 {{ filteredUsers.length }} / {{ users.length }} 条</span>
      </div>
      <el-table
        v-loading="loading"
        :data="filteredUsers"
        size="small"
        style="width: 100%"
        empty-text="未找到匹配的用户"
      >
        <el-table-column label="用户" min-width="210">
          <template #default="{ row }"
            ><div class="user-cell">
              <span class="avatar">{{ initials(row.username) }}</span
              ><span
                ><strong>{{ row.username || '未命名用户' }}</strong
                ><small>#{{ row.id }}</small></span
              >
            </div></template
          >
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="220" />
        <el-table-column label="角色" width="120"
          ><template #default="{ row }"
            ><el-tag size="small" :type="row.is_admin ? 'warning' : 'info'">{{
              row.is_admin ? '管理员' : '普通用户'
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="注册时间" min-width="180"
          ><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column
        >
        <el-table-column label="操作" width="84" fixed="right"
          ><template #default="{ row }"
            ><el-button text type="primary" @click="openDetail(row)">详情</el-button></template
          ></el-table-column
        >
      </el-table>
      <div class="table-footer">
        <span>每页 {{ pageSize }} 条</span
        ><el-pagination
          v-if="total > pageSize"
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="loadUsers"
        />
      </div>
    </el-card>

    <el-drawer v-model="drawerVisible" title="用户详情" size="420px">
      <template v-if="selectedUser"
        ><div class="drawer-profile">
          <span class="drawer-avatar">{{ initials(selectedUser.username) }}</span>
          <div>
            <h3>{{ selectedUser.username || '未命名用户' }}</h3>
            <el-tag size="small" :type="selectedUser.is_admin ? 'warning' : 'info'">{{
              selectedUser.is_admin ? '管理员' : '普通用户'
            }}</el-tag>
          </div>
        </div>
        <el-descriptions :column="1" border
          ><el-descriptions-item label="用户 ID">{{ selectedUser.id }}</el-descriptions-item
          ><el-descriptions-item label="邮箱">{{ selectedUser.email || '-' }}</el-descriptions-item
          ><el-descriptions-item label="注册时间">{{
            formatTime(selectedUser.created_at)
          }}</el-descriptions-item></el-descriptions
        ></template
      >
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import request from '@/api/request'

const users = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const keyword = ref('')
const roleFilter = ref('all')
const selectedUser = ref(null)
const drawerVisible = ref(false)
const pageSize = 20
const filteredUsers = computed(() =>
  users.value.filter((user) => {
    const term = keyword.value.trim().toLowerCase()
    const matchText =
      !term ||
      [user.id, user.username, user.email].some((item) =>
        String(item || '')
          .toLowerCase()
          .includes(term)
      )
    const matchRole =
      roleFilter.value === 'all' || (roleFilter.value === 'admin' ? user.is_admin : !user.is_admin)
    return matchText && matchRole
  })
)
const adminCount = computed(() => users.value.filter((user) => user.is_admin).length)
const recentCount = computed(
  () =>
    users.value.filter(
      (user) =>
        user.created_at &&
        Date.now() - new Date(user.created_at).getTime() <= 7 * 24 * 60 * 60 * 1000
    ).length
)
function initials(name) {
  return String(name || 'U')
    .slice(0, 1)
    .toUpperCase()
}
function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
}
function openDetail(user) {
  selectedUser.value = user
  drawerVisible.value = true
}
async function loadUsers() {
  loading.value = true
  try {
    const res = await request.get('/auth/admin/users', {
      params: { page: page.value, page_size: pageSize },
      notifyError: false,
    })
    const data = res?.data || res || {}
    users.value = data.items || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('用户列表加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(loadUsers)
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
  background: #fff;
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
  width: min(360px, 100%);
}
.role-select {
  width: 130px;
}
.result-count {
  margin-left: auto;
  color: var(--app-muted);
  font-size: 12px;
  white-space: nowrap;
}
.user-cell {
  display: flex;
  align-items: center;
  gap: 9px;
}
.avatar,
.drawer-avatar {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  color: var(--app-primary);
  font-weight: 700;
  background: var(--app-primary-light);
}
.avatar {
  width: 29px;
  height: 29px;
  border-radius: 7px;
  font-size: 12px;
}
.user-cell strong,
.user-cell small {
  display: block;
}
.user-cell strong {
  color: var(--app-text);
  font-size: 13px;
}
.user-cell small {
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
.drawer-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}
.drawer-avatar {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  font-size: 18px;
}
.drawer-profile h3 {
  margin: 0 0 6px;
  color: var(--app-text);
  font-size: 17px;
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
