import { createRouter, createWebHistory } from 'vue-router'

import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { USER_ROLES, isRoleAllowed } from '@/constants/roles'
import { useAuthStore } from '@/stores/auth'

const BOTH_ROLES = [USER_ROLES.candidate, USER_ROLES.recruiter]

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/Register.vue'),
    meta: { title: '注册', public: true },
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('@/views/ResetPassword.vue'),
    meta: { title: '重置密码', public: true },
  },
  {
    path: '/enterprise/screening/preview',
    name: 'enterprise-screening-preview',
    component: () => import('@/views/EnterpriseScreeningPreview.vue'),
    meta: { title: '筛选报告预览', roles: [USER_ROLES.recruiter] },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '页面不存在', public: true },
  },
  {
    path: '/',
    component: DefaultLayout,
    redirect: '/home',
    children: [
      {
        path: 'home',
        name: 'home',
        component: () => import('@/views/Home.vue'),
        meta: { title: '首页', roles: BOTH_ROLES },
      },
      {
        path: 'smart-analysis',
        name: 'smart-analysis',
        component: () => import('@/views/SmartAnalysis.vue'),
        meta: { title: '智能分析', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'career-planning',
        name: 'career-planning',
        component: () => import('@/views/CareerPlanning.vue'),
        meta: { title: '职业规划', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'history',
        name: 'history',
        component: () => import('@/views/History.vue'),
        meta: { title: '历史记录', roles: BOTH_ROLES },
      },
      {
        path: 'tasks',
        name: 'task-center',
        component: () => import('@/views/TaskCenter.vue'),
        meta: { title: '任务中心', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'prompt-traces',
        name: 'prompt-traces',
        component: () => import('@/views/PromptTrace.vue'),
        meta: { title: 'Prompt 追踪', roles: BOTH_ROLES },
      },
      {
        path: 'eval-reports',
        name: 'eval-reports',
        component: () => import('@/views/EvalReport.vue'),
        meta: { title: '评测报表', roles: BOTH_ROLES },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: '个人中心', roles: BOTH_ROLES },
      },
      {
        path: 'knowledge',
        name: 'knowledge-base',
        component: () => import('@/views/KnowledgeBase.vue'),
        meta: { title: '知识库', roles: BOTH_ROLES },
      },
      {
        path: 'about',
        name: 'about',
        component: () => import('@/views/About.vue'),
        meta: { title: '关于系统', roles: BOTH_ROLES },
      },
      {
        path: 'system-status',
        name: 'system-status',
        component: () => import('@/views/SystemStatus.vue'),
        meta: { title: '系统状态', roles: BOTH_ROLES },
      },
      {
        path: 'delivery-guide',
        name: 'delivery-guide',
        component: () => import('@/views/DeliveryGuide.vue'),
        meta: { title: '交付说明', roles: BOTH_ROLES },
      },
      {
        path: 'resume',
        name: 'resume-upload',
        component: () => import('@/views/ResumeUpload.vue'),
        meta: { title: '简历上传', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'jd',
        redirect: { name: 'jd-input' },
        meta: { title: '岗位 JD', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'jd/input',
        name: 'jd-input',
        component: () => import('@/views/JDInput.vue'),
        meta: { title: '岗位 JD', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'analysis',
        name: 'analysis-result',
        component: () => import('@/views/AnalysisResult.vue'),
        meta: { title: '分析结果', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'analysis/:id',
        name: 'analysis-detail',
        component: () => import('@/views/AnalysisResult.vue'),
        meta: { title: '分析详情', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'interview',
        name: 'interview',
        component: () => import('@/views/Interview.vue'),
        meta: { title: '面试题', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'resume/compare/:id',
        name: 'resume-compare',
        component: () => import('@/views/ResumeCompare.vue'),
        meta: { title: '简历对比', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'agent',
        name: 'agent-analysis',
        component: () => import('@/views/AgentAnalysis.vue'),
        meta: { title: 'Agent 智能分析', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'multi-agent',
        name: 'multi-agent',
        component: () => import('@/views/MultiAgentAnalysis.vue'),
        meta: { title: '多智能体协作', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'jobs/search',
        name: 'job-search',
        component: () => import('@/views/JobSearch.vue'),
        meta: { title: '岗位市场', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'jobs/recommend',
        name: 'job-recommend',
        component: () => import('@/views/JobRecommend.vue'),
        meta: { title: '岗位推荐', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'jobs/recommend/evaluation',
        name: 'job-recommend-evaluation',
        component: () => import('@/views/RecommendationEval.vue'),
        meta: { title: '推荐评测', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'jobs/recommend/config',
        name: 'job-recommend-config',
        component: () => import('@/views/RecommendationConfig.vue'),
        meta: { title: '推荐权重配置', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'datasource',
        name: 'datasource',
        component: () => import('@/views/DataSource.vue'),
        meta: { title: '数据源管理', roles: [USER_ROLES.recruiter] },
      },
      {
        path: 'enterprise/screening',
        name: 'enterprise-screening',
        component: () => import('@/views/EnterpriseScreening.vue'),
        meta: { title: '企业筛选', roles: [USER_ROLES.recruiter] },
      },
      {
        path: 'query-rewrite-test',
        redirect: { name: 'knowledge-base', query: { tab: 'debug' } },
        meta: { title: '知识库', roles: BOTH_ROLES },
      },
      {
        path: 'explain-match',
        redirect: { name: 'smart-analysis' },
        meta: { title: '智能分析', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'interview/setup',
        name: 'interview-setup',
        component: () => import('@/views/InterviewSetup.vue'),
        meta: { title: 'AI 模拟面试', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'interview/room/:sessionId',
        name: 'interview-room',
        component: () => import('@/views/InterviewRoom.vue'),
        meta: { title: '面试进行中', roles: [USER_ROLES.candidate] },
      },
      {
        path: 'interview/report/:sessionId',
        name: 'interview-report',
        component: () => import('@/views/InterviewReport.vue'),
        meta: { title: '面试报告', roles: [USER_ROLES.candidate] },
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

  if (loggedIn && (to.name === 'login' || to.name === 'register')) {
    next(authStore.homeRoute)
    return
  }

  if (!to.meta?.public && !loggedIn) {
    next('/login')
    return
  }

  if (loggedIn && !isRoleAllowed(authStore.role, to.meta?.roles)) {
    next(authStore.homeRoute)
    return
  }

  next()
})

export default router
