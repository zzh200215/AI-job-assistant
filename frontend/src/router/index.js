import { createRouter, createWebHistory } from 'vue-router'

import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { USER_ROLES } from '@/constants/roles'
import { getRouteRedirect } from './guard'
import { useAuthStore } from '@/stores/auth'

// 角色常量
const CANDIDATE = [USER_ROLES.candidate] // C 端求职者
const ADMIN = [USER_ROLES.admin] // 系统管理员

export const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/features/auth/views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/features/auth/views/Register.vue'),
    meta: { title: '注册', public: true },
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('@/features/auth/views/ResetPassword.vue'),
    meta: { title: '重置密码', public: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/features/auth/views/NotFound.vue'),
    meta: { title: '页面不存在', public: true },
  },
  /**
   * vue-router 的类型把记录分成"带 component 的单视图/多视图"与"带 redirect 的重定向"两种，
   * 不许同时出现；而运行时"布局 + 访问 `/` 跳 /home + children 仍渲染在 DefaultLayout 里"是成立的。
   * 所以只给这一条记录做一次断言，其余 42 条继续被检查。
   * @type {import('vue-router').RouteRecordRaw}
   */
  {
    path: '/',
    component: DefaultLayout,
    redirect: '/home',
    children: [
      // ===== C 端核心页面（8 个一级入口） =====
      {
        path: 'home',
        name: 'home',
        component: () => import('@/features/shell/views/Home.vue'),
        meta: { title: '首页', roles: CANDIDATE },
      },
      {
        path: 'resume-center',
        name: 'resume-center',
        component: () => import('@/features/resume/views/ResumeUpload.vue'),
        meta: { title: '简历中心', roles: CANDIDATE },
      },
      {
        path: 'smart-analysis',
        name: 'smart-analysis',
        component: () => import('@/features/analysis/views/SmartAnalysis.vue'),
        meta: { title: '智能分析', roles: CANDIDATE },
      },
      {
        path: 'jobs/recommend',
        name: 'job-recommend',
        component: () => import('@/features/jobs/views/JobRecommend.vue'),
        meta: { title: '岗位推荐', roles: CANDIDATE },
      },
      {
        path: 'interview/setup',
        name: 'interview-setup',
        component: () => import('@/features/interview/views/InterviewSetup.vue'),
        meta: { title: 'AI 模拟面试', roles: CANDIDATE },
      },
      {
        path: 'jobs/pipeline/kanban',
        name: 'pipeline-kanban',
        component: () => import('@/features/pipeline/views/PipelineKanban.vue'),
        meta: { title: '投递看板', roles: CANDIDATE },
      },
      {
        path: 'career-planning',
        name: 'career-planning',
        component: () => import('@/features/planning/views/CareerPlanning.vue'),
        meta: { title: '职业规划', roles: CANDIDATE },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/features/shell/views/Profile.vue'),
        meta: { title: '个人中心', roles: CANDIDATE },
      },
      {
        path: 'privacy',
        name: 'privacy',
        component: () => import('@/features/legal/views/Privacy.vue'),
        meta: { title: '隐私与数据', roles: CANDIDATE },
      },
      {
        path: 'organizations',
        name: 'organizations',
        component: () => import('@/features/billing/views/OrganizationWorkspace.vue'),
        meta: { title: '团队工作区', roles: CANDIDATE },
      },
      {
        path: 'subscription',
        name: 'subscription',
        component: () => import('@/features/billing/views/Subscription.vue'),
        meta: { title: '订阅方案', roles: CANDIDATE },
      },

      // ===== C 端次要页面（通过核心页面导航可达） =====
      {
        path: 'targets',
        name: 'job-targets',
        component: () => import('@/features/jobs/views/JobTargets.vue'),
        meta: { title: '求职目标', roles: CANDIDATE },
      },
      {
        path: 'offer',
        name: 'offer-compare',
        component: () => import('@/features/jobs/views/OfferCompare.vue'),
        meta: { title: 'Offer决策', roles: CANDIDATE },
      },
      {
        path: 'salary',
        name: 'salary-insight',
        component: () => import('@/features/jobs/views/SalaryInsight.vue'),
        meta: { title: '薪资洞察', roles: CANDIDATE },
      },
      {
        path: 'weekly-report',
        name: 'weekly-report',
        component: () => import('@/features/shell/views/WeeklyReport.vue'),
        meta: { title: '求职周报', roles: CANDIDATE },
      },
      {
        path: 'history',
        name: 'history',
        component: () => import('@/features/shell/views/History.vue'),
        meta: { title: '历史记录', roles: CANDIDATE },
      },
      {
        path: 'tasks',
        name: 'task-center',
        component: () => import('@/features/shell/views/TaskCenter.vue'),
        meta: { title: '任务中心', roles: CANDIDATE },
      },

      // 分析子页面
      {
        path: 'analysis',
        name: 'analysis-result',
        component: () => import('@/features/analysis/views/AnalysisResult.vue'),
        meta: { title: '分析结果', roles: CANDIDATE },
      },
      {
        path: 'analysis/:id',
        name: 'analysis-detail',
        component: () => import('@/features/analysis/views/AnalysisResult.vue'),
        meta: { title: '分析详情', roles: CANDIDATE },
      },

      // 岗位搜索（岗位推荐子页面）
      {
        path: 'jobs/search',
        name: 'job-search',
        component: () => import('@/features/jobs/views/JobSearch.vue'),
        meta: { title: '岗位搜索', roles: CANDIDATE },
      },

      // 面试子页面
      {
        path: 'interview',
        name: 'interview',
        component: () => import('@/features/interview/views/Interview.vue'),
        meta: { title: '面试练习', roles: CANDIDATE },
      },
      {
        path: 'interview/room/:sessionId',
        name: 'interview-room',
        component: () => import('@/features/interview/views/InterviewRoom.vue'),
        meta: { title: '面试进行中', roles: CANDIDATE },
      },
      {
        path: 'interview/report/:sessionId',
        name: 'interview-report',
        component: () => import('@/features/interview/views/InterviewReport.vue'),
        meta: { title: '面试报告', roles: CANDIDATE },
      },

      // 简历子页面
      {
        path: 'resume/compare/:id',
        name: 'resume-compare',
        component: () => import('@/features/resume/views/ResumeCompare.vue'),
        meta: { title: '简历对比', roles: CANDIDATE },
      },

      // ===== 管理员页面（普通用户不可见） =====
      {
        path: 'admin',
        name: 'admin-overview',
        component: () => import('@/features/admin/views/Overview.vue'),
        meta: { title: '管理后台', roles: ADMIN },
      },
      {
        path: 'admin/users',
        name: 'admin-users',
        component: () => import('@/features/admin/views/Users.vue'),
        meta: { title: '用户管理', roles: ADMIN },
      },
      {
        path: 'admin/orders',
        name: 'admin-orders',
        component: () => import('@/features/admin/views/Orders.vue'),
        meta: { title: '订单管理', roles: ADMIN },
      },
      {
        path: 'admin/tenants',
        name: 'admin-tenants',
        component: () => import('@/features/admin/views/Tenants.vue'),
        meta: { title: '租户管理', roles: ADMIN },
      },
      {
        path: 'prompt-traces',
        name: 'prompt-traces',
        component: () => import('@/features/admin/views/PromptTrace.vue'),
        meta: { title: 'Prompt 追踪', roles: ADMIN },
      },
      {
        path: 'eval-reports',
        name: 'eval-reports',
        component: () => import('@/features/eval/views/EvalReport.vue'),
        meta: { title: '评测报表', roles: ADMIN },
      },
      {
        path: 'system-status',
        name: 'system-status',
        component: () => import('@/features/admin/views/SystemStatus.vue'),
        meta: { title: '系统状态', roles: ADMIN },
      },
      {
        path: 'delivery-guide',
        name: 'delivery-guide',
        component: () => import('@/features/shell/views/DeliveryGuide.vue'),
        meta: { title: '交付说明', roles: ADMIN },
      },
      {
        path: 'about',
        name: 'about',
        component: () => import('@/features/shell/views/About.vue'),
        meta: { title: '关于系统', roles: ADMIN },
      },
      {
        path: 'knowledge',
        name: 'knowledge-base',
        component: () => import('@/features/knowledge/views/KnowledgeBase.vue'),
        meta: { title: '知识库', roles: ADMIN },
      },
      {
        path: 'agent',
        name: 'agent-analysis',
        component: () => import('@/features/analysis/views/AgentAnalysis.vue'),
        meta: { title: 'Agent 分析', roles: ADMIN },
      },
      {
        path: 'multi-agent',
        name: 'multi-agent',
        component: () => import('@/features/analysis/views/MultiAgentAnalysis.vue'),
        meta: { title: '多智能体', roles: ADMIN },
      },
      {
        path: 'jobs/recommend/evaluation',
        name: 'job-recommend-evaluation',
        component: () => import('@/features/eval/views/RecommendationEval.vue'),
        meta: { title: '推荐评测', roles: ADMIN },
      },
      {
        path: 'jobs/recommend/config',
        name: 'job-recommend-config',
        component: () => import('@/features/eval/views/RecommendationConfig.vue'),
        meta: { title: '推荐配置', roles: ADMIN },
      },

      // ===== 遗留重定向（兼容旧链接，指向新位置） =====
      {
        path: 'resume',
        redirect: { name: 'resume-center' },
        meta: { title: '简历中心', roles: CANDIDATE },
      },
      { path: 'jd', redirect: { name: 'jd-input' }, meta: { title: '岗位 JD', roles: CANDIDATE } },
      {
        path: 'jd/input',
        name: 'jd-input',
        component: () => import('@/features/resume/views/JDInput.vue'),
        meta: { title: '岗位 JD', roles: CANDIDATE },
      },
      {
        path: 'query-rewrite-test',
        redirect: { name: 'knowledge-base', query: { tab: 'debug' } },
        meta: { title: '知识库', roles: ADMIN },
      },
      {
        path: 'explain-match',
        redirect: { name: 'smart-analysis' },
        meta: { title: '智能分析', roles: CANDIDATE },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const loggedIn = authStore.isLoggedIn
  const redirect = getRouteRedirect({
    to,
    loggedIn,
    role: authStore.role,
    homeRoute: authStore.homeRoute,
  })

  if (redirect) {
    next(redirect)
    return
  }

  next()
})

export default router
