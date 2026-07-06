<template>
  <el-container class="layout-shell">
    <!-- Sidebar -->
    <el-aside width="220px" class="aside-shell">
      <div class="brand" @click="router.push(authStore.homeRoute)">
        <div class="brand-mark">
          <svg width="22" height="22" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="1" y="1" width="30" height="30" rx="8" stroke="currentColor" stroke-width="1.8" />
            <path d="M9 22V12l7-5 7 5v10H9z" fill="currentColor" opacity="0.88" />
            <path d="M13 22v-4a3 3 0 0 1 6 0v4" stroke="#fff" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </div>
        <div class="brand-copy">
          <strong>Career Signal</strong>
          <small>{{ authStore.roleLabel }}</small>
        </div>
      </div>

      <nav class="nav-section">
        <el-menu
          :default-active="route.path"
          router
          class="nav-menu"
          background-color="transparent"
          text-color="#4b5563"
          active-text-color="#196bdb"
        >
          <el-menu-item
            v-for="item in visibleNav"
            :key="item.path"
            :index="item.path"
            class="nav-item"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu>
      </nav>

      <div class="aside-footer">
        <div class="aside-chip">
          <span class="aside-chip-dot" :class="runtime.demoMode ? 'dot-amber' : 'dot-green'" />
          <div class="aside-chip-copy">
            <strong>{{ currentNav?.label || '工作台' }}</strong>
            <span>{{ runtime.demoMode ? '演示模式' : authStore.roleLabel }}</span>
          </div>
        </div>
      </div>
    </el-aside>

    <!-- Main content area -->
    <el-container class="content-shell">
      <!-- Topbar -->
      <el-header class="topbar">
        <div class="topbar-main">
          <div class="topbar-left">
            <div class="topbar-kicker">{{ currentNav?.tag || 'Workspace' }}</div>
            <h1 class="page-title">{{ route.meta?.title || currentNav?.label || '' }}</h1>
          </div>
          <div class="topbar-right">
            <div class="topbar-badges">
              <span class="badge">
                <span class="badge-dot" :class="authStore.isRecruiter ? 'dot-violet' : 'dot-blue'" />
                {{ authStore.roleLabel }}
              </span>
              <span class="badge badge-outline">Agentic RAG</span>
            </div>
            <el-dropdown v-if="authStore.isLoggedIn" @command="handleCommand">
              <span class="user-chip">
                <span class="user-avatar">{{ (authStore.user?.username || 'U')[0].toUpperCase() }}</span>
                <span class="user-name">{{ authStore.user?.username || '用户' }}</span>
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">个人中心</el-dropdown-item>
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
import { computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  Clock,
  Collection,
  DataAnalysis,
  HomeFilled,
  InfoFilled,
  MagicStick,
  Microphone,
  OfficeBuilding,
  TrendCharts,
} from '@element-plus/icons-vue'

import { ElMessage } from '@/plugins/element-services'
import { getSystemStatus } from '@/api/system'
import { USER_ROLES } from '@/constants/roles'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const runtime = reactive({ demoMode: false })

const allNav = [
  {
    path: '/home',
    icon: HomeFilled,
    label: '首页',
    tag: 'Overview',
    desc: '核心入口与推荐流程。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/home'],
  },
  {
    path: '/smart-analysis',
    icon: MagicStick,
    label: '智能分析',
    tag: 'Analysis',
    desc: '简历与岗位匹配分析。',
    roles: [USER_ROLES.candidate],
    matches: ['/smart-analysis', '/analysis', '/resume', '/jd', '/agent', '/multi-agent', '/explain-match'],
  },
  {
    path: '/career-planning',
    icon: TrendCharts,
    label: '职业规划',
    tag: 'Career',
    desc: '阶段目标与能力提升路径。',
    roles: [USER_ROLES.candidate],
    matches: ['/career-planning'],
  },
  {
    path: '/jobs/search',
    icon: DataAnalysis,
    label: '岗位市场',
    tag: 'Market',
    desc: '搜索岗位、比较机会。',
    roles: [USER_ROLES.candidate],
    matches: ['/jobs/search', '/jobs/recommend', '/jobs/recommend/evaluation', '/jobs/recommend/config'],
  },
  {
    path: '/interview/setup',
    icon: Microphone,
    label: 'AI 模拟面试',
    tag: 'Interview',
    desc: '基于简历和岗位进行面试演练。',
    roles: [USER_ROLES.candidate],
    matches: ['/interview', '/interview/setup', '/interview/room', '/interview/report'],
  },
  {
    path: '/enterprise/screening',
    icon: OfficeBuilding,
    label: '企业筛选',
    tag: 'Recruiting',
    desc: '围绕 JD 批量筛选候选人。',
    roles: [USER_ROLES.recruiter],
    matches: ['/enterprise/screening'],
  },
  {
    path: '/datasource',
    icon: DataAnalysis,
    label: '数据源管理',
    tag: 'Data',
    desc: '配置招聘数据源与同步。',
    roles: [USER_ROLES.recruiter],
    matches: ['/datasource'],
  },
  {
    path: '/knowledge',
    icon: Collection,
    label: '知识库',
    tag: 'Knowledge',
    desc: '文档管理与检索调试。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/knowledge', '/query-rewrite-test'],
  },
  {
    path: '/history',
    icon: Clock,
    label: '历史记录',
    tag: 'History',
    desc: '回看分析、筛选或面试记录。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/history'],
  },
  {
    path: '/tasks',
    icon: Clock,
    label: '任务中心',
    tag: 'Tasks',
    desc: '异步分析任务状态追踪。',
    roles: [USER_ROLES.candidate],
    matches: ['/tasks'],
  },
  {
    path: '/prompt-traces',
    icon: DataAnalysis,
    label: 'Prompt 追踪',
    tag: 'LLMOps',
    desc: '版本对比、实验分组和结果回放。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/prompt-traces'],
  },
  {
    path: '/eval-reports',
    icon: DataAnalysis,
    label: '评测报表',
    tag: 'Eval',
    desc: '离线评测结果、历史快照与版本对比。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/eval-reports'],
  },
  {
    path: '/about',
    icon: InfoFilled,
    label: '关于系统',
    tag: 'About',
    desc: '系统边界与产品定位。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/about'],
  },
  {
    path: '/system-status',
    icon: InfoFilled,
    label: '系统状态',
    tag: 'Status',
    desc: '运行模式与能力开关。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/system-status'],
  },
  {
    path: '/delivery-guide',
    icon: InfoFilled,
    label: '交付说明',
    tag: 'Delivery',
    desc: '交付范围与验收建议。',
    roles: [USER_ROLES.candidate, USER_ROLES.recruiter],
    matches: ['/delivery-guide'],
  },
]

const visibleNav = computed(() => allNav.filter(item => item.roles.includes(authStore.role)))

const currentNav = computed(() => {
  if (route.path === '/profile') return { label: '个人中心', tag: 'Profile', desc: '账号信息与系统模式。' }
  const active = visibleNav.value.find(item =>
    item.matches.some(prefix => route.path === prefix || route.path.startsWith(`${prefix}/`)),
  )
  return active || visibleNav.value[0] || null
})

function handleCommand(cmd) {
  if (cmd === 'profile') { router.push('/profile'); return }
  if (cmd !== 'logout') return
  authStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}

onMounted(async () => {
  try {
    const data = await getSystemStatus()
    runtime.demoMode = !!data?.demo_mode
  } catch {
    runtime.demoMode = false
  }
})
</script>

<style scoped>
/* ===== Shell ===== */
.layout-shell {
  min-height: 100vh;
  background: var(--app-bg);
}

/* ===== Sidebar ===== */
.aside-shell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px 12px;
  background: #fff;
  border-right: 1px solid var(--app-line);
}

/* Brand */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 12px 20px;
  cursor: pointer;
  transition: opacity 0.18s ease;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 8px;
}

.brand:hover { opacity: 0.8; }

.brand-mark {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--app-primary);
  background: var(--app-primary-light);
  flex-shrink: 0;
}

.brand-copy strong {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text);
  letter-spacing: -0.02em;
}

.brand-copy small {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--app-muted);
}

/* Navigation */
.nav-section { flex: 1; }

.nav-menu,
.nav-menu :deep(.el-menu) {
  border-right: none;
}

.nav-menu :deep(.el-menu-item) {
  height: 42px;
  margin-bottom: 2px;
  border-radius: 10px;
  font-size: 14px;
  transition: background 0.15s ease;
}

.nav-menu :deep(.el-menu-item:hover) {
  background: var(--el-fill-color-light) !important;
}

.nav-menu :deep(.el-menu-item.is-active) {
  background: var(--app-primary-light) !important;
  color: var(--app-primary) !important;
  font-weight: 600;
}

.nav-menu :deep(.el-menu-item .el-icon) {
  margin-right: 8px;
}

/* Aside footer */
.aside-footer {
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.aside-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
}

.aside-chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-green { background: var(--app-success); }
.dot-amber { background: var(--app-warning); }

.aside-chip-copy strong,
.aside-chip-copy span {
  display: block;
  line-height: 1.3;
}

.aside-chip-copy strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}

.aside-chip-copy span {
  font-size: 11px;
  color: var(--app-muted);
}

/* ===== Content area ===== */
.content-shell {
  display: flex;
  flex-direction: column;
}

/* ===== Topbar ===== */
.topbar {
  height: auto;
  padding: 0;
  background: #fff;
  border-bottom: 1px solid var(--app-line);
}

.topbar-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 24px;
}

.topbar-left { min-width: 0; }

.topbar-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--app-muted);
  margin-bottom: 2px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--app-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.topbar-badges {
  display: flex;
  gap: 6px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  background: var(--el-fill-color-light);
  color: var(--app-muted);
}

.badge-outline {
  background: transparent;
  border: 1px solid var(--app-line);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.dot-blue { background: var(--app-primary); }
.dot-violet { background: var(--app-violet); }

/* User chip */
.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 6px 6px;
  border-radius: 10px;
  cursor: pointer;
  background: var(--el-fill-color-light);
  transition: background 0.15s ease;
}

.user-chip:hover { background: var(--el-border-color-lighter); }

.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text);
}

/* ===== Main content ===== */
.main-shell {
  padding: 20px 24px 24px;
  background: transparent;
}

/* ===== Route transition ===== */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
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
    border-right: none;
    border-bottom: 1px solid var(--app-line);
    flex-direction: row;
    flex-wrap: wrap;
    padding: 12px 16px;
    gap: 0;
  }

  .aside-shell .brand {
    border-bottom: none;
    padding: 4px 0;
    margin-bottom: 0;
    flex-shrink: 0;
  }

  .aside-shell .nav-section {
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    margin-left: 12px;
  }

  .aside-shell .aside-footer { display: none; }

  .nav-menu :deep(.el-menu-item) {
    height: 36px;
    white-space: nowrap;
  }
}

@media (max-width: 768px) {
  .topbar-main {
    padding: 12px 16px;
    flex-direction: column;
    align-items: flex-start;
  }

  .topbar-right {
    width: 100%;
    justify-content: space-between;
  }

  .main-shell {
    padding: 12px 16px;
  }

  .page-title {
    font-size: 18px;
  }

  .topbar-badges .badge:nth-child(2) { display: none; }
}
</style>
