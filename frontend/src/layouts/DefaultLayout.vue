<template>
  <el-container class="layout-shell" :class="{ 'workspace-theme': isAdminRoute }">
    <el-aside width="232px" class="aside-shell">
      <div class="brand" @click="router.push(authStore.homeRoute)">
        <div class="brand-mark">
          <svg
            width="20"
            height="20"
            viewBox="0 0 32 32"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <rect
              x="1"
              y="1"
              width="30"
              height="30"
              rx="8"
              stroke="currentColor"
              stroke-width="1.8"
            />
            <path d="M9 22V12l7-5 7 5v10H9z" fill="currentColor" opacity="0.88" />
            <path
              d="M13 22v-4a3 3 0 0 1 6 0v4"
              stroke="var(--el-color-white)"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
        </div>
        <div class="brand-copy">
          <strong>Career Signal</strong>
          <small>{{ isAdminRoute ? '管理后台' : '求职工作台' }}</small>
        </div>
      </div>

      <nav ref="navSection" class="nav-section" aria-label="主导航">
        <el-menu :default-active="route.path" router class="nav-menu">
          <el-menu-item
            v-for="item in candidateNav"
            :key="item.path"
            :index="item.path"
            class="nav-item"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>

          <el-sub-menu v-if="adminNav.length" index="admin-tools" class="nav-submenu">
            <template #title>
              <el-icon><Tools /></el-icon>
              <span>管理工具</span>
            </template>
            <el-menu-item
              v-for="item in adminNav"
              :key="item.path"
              :index="item.path"
              class="nav-item"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </nav>
    </el-aside>

    <el-container class="content-shell">
      <el-header class="topbar">
        <div class="topbar-main">
          <div class="topbar-left">
            <span class="topbar-product">Career Signal</span>
            <span class="topbar-sep" aria-hidden="true" />
            <span class="topbar-context">{{ isAdminRoute ? '运营工作台' : '求职工作台' }}</span>
          </div>
          <div class="topbar-right">
            <el-dropdown v-if="authStore.isLoggedIn" trigger="click" @command="handleCommand">
              <button class="user-chip" type="button">
                <span class="user-avatar">{{ userInitial }}</span>
                <span class="user-name">{{ authStore.user?.username || '用户' }}</span>
                <el-icon class="user-arrow"><ArrowDown /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                  <el-dropdown-item command="tasks">任务记录</el-dropdown-item>
                  <el-dropdown-item command="history">分析历史</el-dropdown-item>
                  <el-dropdown-item command="subscription">订阅方案</el-dropdown-item>
                  <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </el-header>

      <el-main class="main-shell">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  Clock,
  Coin,
  DataAnalysis,
  Document,
  Grid,
  HomeFilled,
  List,
  MagicStick,
  Microphone,
  Tools,
  TrendCharts,
  Trophy,
} from '@element-plus/icons-vue'

import { ElMessage } from '@/plugins/element-services'
import { USER_ROLES } from '@/constants/roles'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const candidateNavItems = [
  { path: '/home', icon: HomeFilled, label: '首页', matches: ['/home'] },
  {
    path: '/resume-center',
    icon: Document,
    label: '简历中心',
    matches: ['/resume-center', '/resume/compare'],
  },
  {
    path: '/smart-analysis',
    icon: MagicStick,
    label: '求职分析',
    matches: ['/smart-analysis', '/analysis'],
  },
  {
    path: '/jobs/recommend',
    icon: DataAnalysis,
    label: '岗位推荐',
    matches: ['/jobs/recommend', '/jobs/search'],
  },
  {
    path: '/interview/setup',
    icon: Microphone,
    label: 'AI 模拟面试',
    matches: ['/interview', '/interview/setup', '/interview/room', '/interview/report'],
  },
  {
    path: '/jobs/pipeline/kanban',
    icon: Grid,
    label: '投递看板',
    matches: ['/jobs/pipeline/kanban'],
  },
  {
    path: '/career-planning',
    icon: TrendCharts,
    label: '职业规划',
    matches: ['/career-planning'],
  },
  {
    path: '/profile',
    icon: List,
    label: '个人中心',
    matches: ['/profile', '/subscription'],
  },
]

const adminNavItems = [
  { path: '/admin', icon: Trophy, label: '管理后台', matches: ['/admin'] },
  { path: '/admin/users', icon: List, label: '用户管理', matches: ['/admin/users'] },
  { path: '/admin/orders', icon: Coin, label: '订单管理', matches: ['/admin/orders'] },
  { path: '/prompt-traces', icon: DataAnalysis, label: 'Prompt 追踪', matches: ['/prompt-traces'] },
  { path: '/eval-reports', icon: DataAnalysis, label: '评测报表', matches: ['/eval-reports'] },
  { path: '/system-status', icon: Trophy, label: '系统状态', matches: ['/system-status'] },
  { path: '/delivery-guide', icon: List, label: '交付说明', matches: ['/delivery-guide'] },
  { path: '/about', icon: Trophy, label: '关于系统', matches: ['/about'] },
  { path: '/knowledge', icon: Clock, label: '知识库', matches: ['/knowledge'] },
  { path: '/agent', icon: MagicStick, label: 'Agent 分析', matches: ['/agent'] },
  { path: '/multi-agent', icon: DataAnalysis, label: '多智能体', matches: ['/multi-agent'] },
  {
    path: '/jobs/recommend/evaluation',
    icon: TrendCharts,
    label: '推荐评测',
    matches: ['/jobs/recommend/evaluation'],
  },
  {
    path: '/jobs/recommend/config',
    icon: Coin,
    label: '推荐配置',
    matches: ['/jobs/recommend/config'],
  },
]

const isAdminRole = computed(() => authStore.role === USER_ROLES.admin)
const candidateNav = computed(() => candidateNavItems)
const adminNav = computed(() => (isAdminRole.value ? adminNavItems : []))

const isAdminRoute = computed(() =>
  adminNavItems.some((item) => route.path === item.path || route.path.startsWith(`${item.path}/`))
)

const userInitial = computed(() =>
  (authStore.user?.nickname || authStore.user?.username || 'U').slice(0, 1).toUpperCase()
)

const navSection = ref(null)

/* 窄屏导航是横向滚动条：进入某一页时把当前项滚到可见区域，
   否则从侧栏折叠过来的第一屏看不到高亮项。 */
watch(
  () => route.path,
  async () => {
    await nextTick()
    // Element Plus 在下一拍才给菜单项挂 is-active，延后一拍再量。
    setTimeout(() => {
      const scroller = navSection.value
      if (!scroller || scroller.scrollWidth <= scroller.clientWidth) return
      const active = scroller.querySelector('.el-menu-item.is-active')
      if (active) scroller.scrollTo({ left: Math.max(0, active.offsetLeft - 16), behavior: 'auto' })
    }, 80)
  },
  { immediate: true }
)

function handleCommand(cmd) {
  if (cmd === 'profile') {
    router.push('/profile')
    return
  }
  if (cmd === 'tasks') {
    router.push('/tasks')
    return
  }
  if (cmd === 'history') {
    router.push('/history')
    return
  }
  if (cmd === 'subscription') {
    router.push('/subscription')
    return
  }
  if (cmd !== 'logout') return
  authStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}

/* 管理后台仍用深色作用域：EP 的浮层 teleport 到 body，所以根节点要跟着切。 */
watch(
  isAdminRoute,
  (dark) => {
    document.documentElement.classList.toggle('workspace-theme', dark)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  document.documentElement.classList.remove('workspace-theme')
})
</script>

<style scoped>
.layout-shell {
  min-height: 100vh;
  background: var(--app-bg);
}

/* ===== Sidebar ===== */
.aside-shell {
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  background: var(--app-surface-strong);
  border-right: 1px solid var(--app-line);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 20px;
  cursor: pointer;
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: var(--app-radius-sm);
  background: var(--app-primary);
  color: var(--el-color-white);
}

.brand-copy strong {
  display: block;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.brand-copy small {
  display: block;
  margin-top: 2px;
  color: var(--app-muted);
  font-size: 11px;
}

.nav-section {
  flex: 1;
  min-height: 0;
}

.nav-menu {
  border-right: none;
  background: transparent;
}

.nav-menu :deep(.el-menu-item),
.nav-menu :deep(.el-sub-menu__title) {
  height: 38px;
  margin-bottom: 2px;
  padding: 0 10px;
  border-radius: var(--app-radius-sm);
  color: var(--app-muted);
  font-size: 13px;
  font-weight: 500;
}

.nav-menu :deep(.el-menu-item:hover),
.nav-menu :deep(.el-sub-menu__title:hover) {
  background: var(--app-surface-muted);
  color: var(--app-text);
}

.nav-menu :deep(.el-menu-item.is-active) {
  background: var(--app-primary-light);
  color: var(--app-primary-dark);
  font-weight: 600;
}

.nav-menu :deep(.el-menu--inline) {
  background: transparent;
}

.nav-menu :deep(.el-menu-item .el-icon),
.nav-menu :deep(.el-sub-menu__title .el-icon) {
  margin-right: 9px;
  font-size: 16px;
}

/* ===== Content ===== */
.content-shell {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.topbar {
  height: 60px;
  padding: 0;
  background: var(--app-surface-strong);
  border-bottom: 1px solid var(--app-line);
}

.topbar-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 100%;
  padding: 0 var(--app-shell-gutter);
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.topbar-product {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 600;
}

.topbar-sep {
  width: 1px;
  height: 14px;
  background: var(--app-line);
}

.topbar-context {
  color: var(--app-muted);
  font-size: 12px;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px 4px 4px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--app-text);
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;
}

.user-chip:hover {
  border-color: var(--app-line);
  background: var(--app-surface-muted);
}

.user-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--app-primary-light);
  color: var(--app-primary-dark);
  font-size: 12px;
  font-weight: 700;
}

.user-name {
  max-width: 120px;
  overflow: hidden;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-arrow {
  color: var(--app-muted);
  font-size: 12px;
}

.main-shell {
  padding: 0;
  background: var(--app-bg);
}

/* ===== Route transition ===== */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.16s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ===== Responsive ===== */
@media (max-width: 1080px) {
  .layout-shell {
    flex-direction: column;
  }

  .aside-shell {
    width: 100% !important;
    padding: 10px 16px 0;
    border-right: none;
    border-bottom: 1px solid var(--app-line);
  }

  .brand {
    padding: 2px 0 8px;
  }

  .nav-section {
    display: block;
    overflow-x: auto;
  }

  .nav-menu {
    display: flex;
    padding-bottom: 8px;
  }

  .nav-menu :deep(.el-menu-item) {
    height: 34px;
    margin: 0 4px 0 0;
    padding: 0 10px;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .nav-menu :deep(.el-sub-menu) {
    display: none;
  }

  .topbar-main {
    padding: 0 16px;
  }

  .main-shell {
    padding: 0;
  }
}

@media (max-width: 768px) {
  .topbar {
    height: 54px;
  }

  .topbar-context,
  .topbar-sep {
    display: none;
  }

  .user-name {
    display: none;
  }

  .topbar-product {
    font-size: 13px;
  }
}
</style>
