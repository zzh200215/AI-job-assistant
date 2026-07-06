<template>
  <div class="home-page">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-grid">
        <div class="hero-main">
          <div class="badge-row">
            <span class="badge badge-mode" :class="{ recruiter: authStore.isRecruiter }">
              {{ authStore.isRecruiter ? 'Recruiter' : 'Candidate' }}
            </span>
          </div>
          <p class="eyebrow">{{ content.eyebrow }}</p>
          <h1>{{ content.title }}</h1>
          <p class="hero-desc">{{ content.description }}</p>

          <div class="pill-row">
            <span v-for="pill in content.pills" :key="pill">{{ pill }}</span>
          </div>

          <div class="hero-actions">
            <el-button type="primary" size="large" @click="go(content.primaryAction.path)">
              <el-icon><component :is="content.primaryAction.icon" /></el-icon>
              {{ content.primaryAction.label }}
            </el-button>
            <el-button size="large" @click="go(content.secondaryAction.path)">
              <el-icon><component :is="content.secondaryAction.icon" /></el-icon>
              {{ content.secondaryAction.label }}
            </el-button>
          </div>
        </div>

        <div class="hero-side">
          <div class="side-head">
            <span class="eyebrow">{{ content.journeyKicker }}</span>
            <strong>{{ content.journeyTitle }}</strong>
          </div>

          <div v-if="authStore.isRecruiter" class="side-notice">
            当前为招聘者工作台，围绕 JD 批量筛选候选人。
          </div>

          <div class="journey-strip">
            <div v-for="step in content.journey" :key="step.no" class="journey-step">
              <div class="step-indicator">{{ step.no }}</div>
              <div class="step-copy">
                <strong>{{ step.title }}</strong>
                <p>{{ step.desc }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Metrics -->
      <div class="metric-row">
        <div v-for="item in content.metrics" :key="item.label" class="metric-item" :class="item.tone">
          <span class="metric-label">{{ item.label }}</span>
          <strong class="data-value">{{ item.value }}</strong>
          <p>{{ item.desc }}</p>
        </div>
      </div>
    </section>

    <!-- Modules -->
    <section class="modules-section">
      <div class="section-head">
        <div>
          <p class="eyebrow">{{ content.modulesKicker }}</p>
          <h2>{{ content.modulesTitle }}</h2>
        </div>
        <el-button text @click="go('/about')">
          查看系统说明
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>

      <div class="module-grid">
        <article
          v-for="item in content.primaryModules"
          :key="item.path"
          class="module-card"
          @click="go(item.path)"
        >
          <div class="module-icon" :class="item.accent">
            <el-icon :size="20"><component :is="item.icon" /></el-icon>
          </div>
          <div class="module-body">
            <span class="module-tag">{{ item.tag }}</span>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </div>
          <div class="module-footer">
            <span>{{ item.meta }}</span>
            <el-icon><ArrowRight /></el-icon>
          </div>
        </article>
      </div>
    </section>

    <!-- Quick Links -->
    <section class="quick-section">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">Quick Access</p>
          <h2>补充入口</h2>
        </div>
      </div>

      <div class="quick-grid">
        <button
          v-for="item in content.quickLinks"
          :key="item.path"
          type="button"
          class="quick-btn"
          @click="go(item.path)"
        >
          <div class="quick-icon">
            <el-icon :size="16"><component :is="item.icon" /></el-icon>
          </div>
          <div class="quick-copy">
            <strong>{{ item.title }}</strong>
            <span>{{ item.desc }}</span>
          </div>
          <el-icon class="quick-arrow"><ArrowRight /></el-icon>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Clock,
  Collection,
  DataAnalysis,
  InfoFilled,
  MagicStick,
  Microphone,
  OfficeBuilding,
  Search,
  TrendCharts,
} from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const go = (path) => router.push(path)

const candidateContent = {
  eyebrow: 'Candidate Workspace',
  title: '面向求职者的分析与求职工作台',
  description: '把简历分析、职业规划、岗位搜索和模拟面试整理成一条连续链路，避免求职流程在多个页面之间割裂。',
  pills: ['Agentic RAG', '简历分析', '职业规划', '岗位市场', '模拟面试'],
  primaryAction: { path: '/smart-analysis', label: '从智能分析开始', icon: MagicStick },
  secondaryAction: { path: '/career-planning', label: '查看职业规划', icon: TrendCharts },
  journeyKicker: '推荐路径',
  journeyTitle: '先判断方向，再进入投递和面试准备',
  modulesKicker: 'Core Workspaces',
  modulesTitle: '求职者最常用的四个入口',
  metrics: [
    { label: '核心模块', value: '5', desc: '分析、规划、岗位、面试、知识库', tone: 'tone-blue' },
    { label: '主流程', value: '1', desc: '从简历判断到投递准备', tone: 'tone-amber' },
    { label: '分析引擎', value: 'RAG', desc: '多阶段检索与解释输出', tone: 'tone-violet' },
    { label: '沉淀方式', value: '留痕', desc: '分析与面试结果可回看', tone: 'tone-green' },
  ],
  journey: [
    { no: '01', title: '智能分析', desc: '先评估当前简历与目标岗位的匹配度、差距和理由。' },
    { no: '02', title: '职业规划', desc: '把差距转成能力补齐计划和阶段目标。' },
    { no: '03', title: '岗位市场', desc: '对照市场机会调整目标岗位和投递节奏。' },
    { no: '04', title: '模拟面试', desc: '围绕当前岗位做针对性演练和复盘。' },
  ],
  primaryModules: [
    {
      path: '/smart-analysis',
      icon: MagicStick,
      title: '智能分析',
      desc: '统一查看岗位匹配度、差距解释、简历优化建议和引用来源。',
      meta: '适合作为求职流程起点',
      tag: 'Analysis',
      accent: 'accent-blue',
    },
    {
      path: '/career-planning',
      icon: TrendCharts,
      title: '职业规划',
      desc: '围绕当前能力与目标岗位，生成成长路径和阶段行动建议。',
      meta: '把分析结论转成长期动作',
      tag: 'Career',
      accent: 'accent-green',
    },
    {
      path: '/jobs/search',
      icon: Search,
      title: '岗位市场',
      desc: '搜索岗位、比较机会，再把值得投递的岗位带回分析链路。',
      meta: '连接市场机会与个人判断',
      tag: 'Market',
      accent: 'accent-amber',
    },
    {
      path: '/interview/setup',
      icon: Microphone,
      title: 'AI 模拟面试',
      desc: '按简历、目标岗位和面试类型生成完整演练，不只是题库。',
      meta: '适合投递前做针对性准备',
      tag: 'Interview',
      accent: 'accent-violet',
    },
  ],
  quickLinks: [
    { path: '/knowledge', icon: Collection, title: '知识库', desc: '查看资料和检索结果' },
    { path: '/history', icon: Clock, title: '历史记录', desc: '回看分析和面试结果，减少重复上传与判断。' },
    { path: '/system-status', icon: InfoFilled, title: '系统状态', desc: '查看当前运行模式与能力边界。' },
    { path: '/delivery-guide', icon: InfoFilled, title: '交付说明', desc: '查看可演示范围与验收建议。' },
    { path: '/about', icon: InfoFilled, title: '关于系统', desc: '查看系统边界与技术栈说明。' },
  ],
}

const recruiterContent = {
  eyebrow: 'Recruiter Workspace',
  title: '面向招聘者的筛选与数据工作台',
  description: '把候选人筛选、数据源维护和知识沉淀拆成明确入口，招聘端登录后不再混入求职者页面。',
  pills: ['Recruiter Mode', '候选人筛选', '数据源管理', '知识沉淀', '流程留痕'],
  primaryAction: { path: '/enterprise/screening', label: '进入企业筛选', icon: OfficeBuilding },
  secondaryAction: { path: '/datasource', label: '管理数据源', icon: DataAnalysis },
  journeyKicker: '推荐路径',
  journeyTitle: '先准备数据，再进入批量筛选和复盘',
  modulesKicker: 'Recruiting Workspaces',
  modulesTitle: '招聘者最常用的四个入口',
  metrics: [
    { label: '核心模块', value: '4', desc: '筛选、数据源、知识库、历史', tone: 'tone-blue' },
    { label: '主流程', value: '1', desc: '从数据准备到候选人排序', tone: 'tone-amber' },
    { label: '工作重点', value: '批量', desc: '围绕单个 JD 比较候选人', tone: 'tone-violet' },
    { label: '沉淀方式', value: '留痕', desc: '筛选记录可持续追踪', tone: 'tone-green' },
  ],
  journey: [
    { no: '01', title: '配置数据源', desc: '先接入简历、职位或外部渠道数据，保证筛选输入稳定。' },
    { no: '02', title: '企业筛选', desc: '围绕 JD 批量比较候选人，输出排序、风险与缺口。' },
    { no: '03', title: '知识支撑', desc: '通过知识库沉淀标准、标签与评估依据。' },
    { no: '04', title: '历史复盘', desc: '回看筛选记录和同步日志，持续校准策略。' },
  ],
  primaryModules: [
    {
      path: '/enterprise/screening',
      icon: OfficeBuilding,
      title: '企业筛选',
      desc: '围绕单个 JD 批量比较候选人，直接输出排序、风险点和关键差距。',
      meta: '招聘端的主工作区',
      tag: 'Recruiting',
      accent: 'accent-blue',
    },
    {
      path: '/datasource',
      icon: DataAnalysis,
      title: '数据源管理',
      desc: '配置和测试招聘数据源，跟踪同步任务与采集质量。',
      meta: '保证筛选输入持续可用',
      tag: 'Data',
      accent: 'accent-green',
    },
    {
      path: '/knowledge',
      icon: Collection,
      title: '知识库',
      desc: '沉淀招聘标准、岗位资料和检索能力，支撑判断一致性。',
      meta: '把经验沉淀成可复用材料',
      tag: 'Knowledge',
      accent: 'accent-amber',
    },
    {
      path: '/history',
      icon: Clock,
      title: '历史记录',
      desc: '追踪既往筛选结论和任务执行过程，便于复盘和审计。',
      meta: '减少重复筛选与判断',
      tag: 'History',
      accent: 'accent-violet',
    },
  ],
  quickLinks: [
    { path: '/knowledge', icon: Collection, title: '知识库', desc: '沉淀招聘标准与岗位资料' },
    { path: '/history', icon: Clock, title: '历史记录', desc: '查看过往筛选记录与处理痕迹。' },
    { path: '/system-status', icon: InfoFilled, title: '系统状态', desc: '确认当前运行模式与能力边界。' },
    { path: '/delivery-guide', icon: InfoFilled, title: '交付说明', desc: '查看交付范围与验收建议。' },
    { path: '/about', icon: InfoFilled, title: '关于系统', desc: '查看平台边界与技术栈说明。' },
  ],
}

const content = computed(() => (authStore.isRecruiter ? recruiterContent : candidateContent))
</script>

<style scoped>
.home-page {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  color: var(--app-text);
}

/* ===== Hero ===== */
.hero {
  padding: 24px;
  border-radius: 20px;
  border: 1px solid var(--app-line);
  background: #fff;
  box-shadow: var(--app-shadow);
}

.hero-grid {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 16px;
}

.hero-main { padding: 4px 0; }
.hero-side {
  padding: 16px 18px;
  background: var(--el-fill-color-light);
  border-radius: 14px;
}

/* Badge */
.badge-row { margin-bottom: 10px; }

.badge-mode {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  background: var(--app-primary-light);
  color: var(--app-primary);
}

.badge-mode.recruiter {
  background: var(--app-violet-light);
  color: var(--app-violet);
}

/* Typography */
.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-main h1 {
  margin: 8px 0 0;
  font-size: 34px;
  line-height: 1.1;
  max-width: 14ch;
  font-weight: 800;
}

.hero-desc {
  max-width: 600px;
  margin: 14px 0 0;
  color: var(--app-muted);
  line-height: 1.7;
  font-size: 14px;
}

/* Pills */
.pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 14px;
}

.pill-row span {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--app-line);
  font-size: 11px;
  color: var(--app-muted);
}

/* Hero actions */
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

/* Side panel */
.side-head span {
  display: block;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.side-head strong {
  display: block;
  margin-top: 6px;
  font-size: 16px;
  font-weight: 700;
}

.side-notice {
  margin: 14px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  color: var(--app-muted);
  line-height: 1.6;
}

/* Journey steps */
.journey-strip {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.journey-step {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--app-line);
}

.step-indicator {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-size: 12px;
  font-weight: 700;
}

.journey-step strong {
  display: block;
  font-size: 13px;
}

.journey-step p {
  margin: 3px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.6;
}

/* ===== Metrics ===== */
.metric-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.metric-item {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--app-line);
  background: #fff;
}

.metric-label {
  display: block;
  font-size: 11px;
  color: var(--app-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.metric-item strong {
  display: block;
  margin-top: 8px;
  font-size: 22px;
  line-height: 1.1;
}

.metric-item p {
  margin: 4px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.6;
}

.tone-blue strong { color: var(--app-primary); }
.tone-amber strong { color: var(--app-warning); }
.tone-violet strong { color: var(--app-violet); }
.tone-green strong { color: var(--app-success); }

/* ===== Modules ===== */
.modules-section { margin-top: 0; }

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 14px;
}

.section-head.compact { margin-bottom: 10px; }

.section-head h2 {
  margin: 6px 0 0;
  font-size: 22px;
  font-weight: 700;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.module-card {
  padding: 20px;
  border-radius: 16px;
  border: 1px solid var(--app-line);
  background: #fff;
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
  display: flex;
  flex-direction: column;
}

.module-card:hover {
  box-shadow: var(--app-shadow-lg);
  transform: translateY(-2px);
}

.module-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.module-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  background: var(--el-fill-color-light);
  color: var(--app-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.module-body h3 {
  margin: 8px 0 6px;
  font-size: 17px;
  font-weight: 700;
}

.module-body p {
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.7;
  flex: 1;
}

.module-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  font-weight: 500;
  color: var(--app-muted);
}

.module-footer .el-icon {
  color: var(--app-muted);
}

/* Module icon accents */
.accent-blue .module-icon { background: var(--app-primary-light); color: var(--app-primary); }
.accent-green .module-icon { background: #e8f8ee; color: var(--app-success); }
.accent-amber .module-icon { background: #fef5e7; color: var(--app-warning); }
.accent-violet .module-icon { background: var(--app-violet-light); color: var(--app-violet); }

/* ===== Quick Links ===== */
.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.quick-btn {
  display: grid;
  grid-template-columns: 34px 1fr 16px;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--app-line);
  background: #fff;
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
  text-align: left;
}

.quick-btn:hover {
  box-shadow: var(--app-shadow);
  transform: translateY(-1px);
}

.quick-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
  color: var(--app-muted);
}

.quick-copy strong,
.quick-copy span {
  display: block;
}

.quick-copy strong {
  font-size: 13px;
  color: var(--app-text);
}

.quick-copy span {
  margin-top: 2px;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-arrow {
  color: var(--app-muted);
  font-size: 14px;
}

/* ===== Responsive ===== */
@media (max-width: 1200px) {
  .module-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 1024px) {
  .hero-grid { grid-template-columns: 1fr; }
  .metric-row { grid-template-columns: 1fr 1fr; }
  .quick-grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 768px) {
  .hero { padding: 18px; }
  .hero-main h1 { font-size: 28px; }
  .hero-actions { flex-direction: column; }
  .hero-actions .el-button { width: 100%; }
  .module-grid { grid-template-columns: 1fr 1fr; }
  .metric-row,
  .quick-grid { grid-template-columns: 1fr; }
}

@media (max-width: 560px) {
  .module-grid { grid-template-columns: 1fr; }
}
</style>
