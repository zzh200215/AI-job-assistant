<template>
  <div class="page-shell">
    <section class="hero-card">
      <p class="eyebrow">System Positioning</p>
      <h2>智能招聘与职业规划平台</h2>
	      <div class="page-header-sub">
        当前这一版系统的重点，已经从单点的简历处理工具，转成一套围绕“分析、规划、筛岗、面试准备”展开的求职工作台。
        它的价值不只是给一个分数，而是把后续动作也串起来。
      </div>

	      <div class="hero-tags">
        <el-tag>Agentic RAG</el-tag>
        <el-tag type="success">多智能体协作</el-tag>
        <el-tag type="warning">职业规划</el-tag>
        <el-tag type="info">FastAPI + Vue 3</el-tag>
      </div>
    </section>

    <section class="grid-two">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><Compass /></el-icon>
            <span>当前定位</span>
          </div>
        </template>
        <div class="info-list">
          <article v-for="item in positioning" :key="item.title" class="info-item">
            <strong>{{ item.title }}</strong>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><DataAnalysis /></el-icon>
            <span>当前主链路</span>
          </div>
        </template>
        <div class="pipeline">
          <div v-for="step in pipeline" :key="step.no" class="pipeline-item">
            <div class="pipeline-no">{{ step.no }}</div>
            <div>
              <strong>{{ step.title }}</strong>
              <p>{{ step.desc }}</p>
            </div>
          </div>
        </div>
      </el-card>
    </section>

    <section>
      <div class="section-head">
        <p class="eyebrow">Core Workspaces</p>
        <h2>当前面向用户开放的主要工作区</h2>
      </div>

      <div class="workspace-grid">
        <article v-for="item in workspaces" :key="item.title" class="workspace-card">
          <div class="workspace-top">
            <el-icon :size="22"><component :is="item.icon" /></el-icon>
            <span>{{ item.tag }}</span>
          </div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.desc }}</p>
          <div class="workspace-features">
            <el-tag v-for="feature in item.features" :key="feature" size="small" effect="plain">
              {{ feature }}
            </el-tag>
          </div>
        </article>
      </div>
    </section>

    <section class="grid-two">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><Cpu /></el-icon>
            <span>系统结构</span>
          </div>
        </template>
        <div class="stack-flow">
          <div v-for="layer in architecture" :key="layer.name" class="stack-layer">
            <strong>{{ layer.name }}</strong>
            <p>{{ layer.desc }}</p>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><Setting /></el-icon>
            <span>技术栈</span>
          </div>
        </template>
        <div class="tech-list">
          <div v-for="item in techStack" :key="item.label" class="tech-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
      </el-card>
    </section>

    <section class="grid-two">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><CircleCheck /></el-icon>
            <span>这一版系统更擅长什么</span>
          </div>
        </template>
        <div class="bullet-list">
          <div v-for="item in strengths" :key="item" class="bullet-item">{{ item }}</div>
        </div>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><Warning /></el-icon>
            <span>边界与注意点</span>
          </div>
        </template>
        <div class="bullet-list">
          <div v-for="item in boundaries" :key="item" class="bullet-item">{{ item }}</div>
        </div>
      </el-card>
    </section>

    <section class="grid-two">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><InfoFilled /></el-icon>
            <span>运行状态入口</span>
          </div>
        </template>
        <div class="bullet-list">
          <div class="bullet-item">系统状态页可查看当前是否处于演示模式、OCR 能力和运行边界。</div>
          <div class="bullet-item">适合答辩时说明“哪些能力已落地，哪些仍是预留扩展”。</div>
        </div>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-title">
            <el-icon><InfoFilled /></el-icon>
            <span>交付说明入口</span>
          </div>
        </template>
        <div class="bullet-list">
          <div class="bullet-item">交付说明页集中展示项目范围、知识库维护方式和验收建议。</div>
          <div class="bullet-item">适合把零散文档内容收拢成一页交付视图。</div>
        </div>
      </el-card>
    </section>
  </div>
</template>

<script setup>
import {
  CircleCheck,
  Collection,
  Compass,
  Cpu,
  DataAnalysis,
  InfoFilled,
  MagicStick,
  Microphone,
  Search,
  Setting,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue'

const positioning = [
  {
    title: '不是单点工具',
    desc: '它不再只负责简历解析或岗位匹配，而是把分析结果继续延伸到职业规划、筛岗和面试准备。',
  },
  {
    title: '更像工作台',
    desc: '首页、导航和各模块的关系，已经更偏向一个连续流程，而不是一组互相独立的功能页面。',
  },
  {
    title: '强调可行动结果',
    desc: '系统输出的不只是结论，还包括下一步该做什么、去哪里做，以及如何复盘。',
  },
]

const pipeline = [
  { no: '01', title: '输入简历与目标岗位', desc: '从用户现状和目标岗位开始，建立统一上下文。' },
  { no: '02', title: '智能分析', desc: '做岗位理解、知识检索、匹配解释和简历建议。' },
  { no: '03', title: '职业规划', desc: '把分析结果延伸成技能差距、路线建议和阶段动作。' },
  { no: '04', title: '职位筛选', desc: '结合市场机会，重新判断哪些岗位值得投递。' },
  { no: '05', title: '模拟面试', desc: '围绕当前简历和岗位做针对性演练。' },
  { no: '06', title: '历史复盘', desc: '把分析、检索和面试结果持续沉淀下来。' },
]

const workspaces = [
  {
    icon: MagicStick,
    tag: 'Analysis',
    title: '智能分析',
    desc: '统一输出岗位匹配度、差距解释、简历优化建议、面试题和引用来源。',
    features: ['匹配解释', '简历建议', '引用来源'],
  },
  {
    icon: TrendCharts,
    tag: 'Career',
    title: '职业规划',
    desc: '根据简历和目标岗位生成技能缺口、成长路线和阶段性行动建议。',
    features: ['能力差距', '成长路线', '行动建议'],
  },
  {
    icon: Search,
    tag: 'Market',
    title: '岗位市场',
    desc: '搜索岗位、对比机会，把外部职位信息重新接回分析链路。',
    features: ['职位检索', '机会比较', '目标回带'],
  },
  {
    icon: Microphone,
    tag: 'Interview',
    title: 'AI 模拟面试',
    desc: '围绕当前简历和岗位生成更接近真实流程的面试演练与报告。',
    features: ['面试演练', '过程评估', '结果报告'],
  },
  {
    icon: Collection,
    tag: 'Knowledge',
    title: '知识库',
    desc: '管理文档、做普通检索和高级调试，支撑整条 RAG 分析链。',
    features: ['文档管理', '检索调试', 'RAG 支撑'],
  },
]

const architecture = [
  {
    name: '前端工作台',
    desc: 'Vue 3 + Element Plus 负责工作区组织、状态切换和结果展示。',
  },
  {
    name: 'API 与鉴权层',
    desc: 'FastAPI 提供统一接口，JWT + bcrypt 负责登录注册与会话身份。',
  },
  {
    name: '编排与智能层',
    desc: '分析链路由 Agentic RAG 驱动，原生编排和 LangGraph 策略并存。',
  },
  {
    name: '数据与知识层',
    desc: 'MySQL 管结构化数据，Chroma 管向量检索，上传文档和历史结果沉淀在系统内。',
  },
]

const techStack = [
  { label: '前端', value: 'Vue 3 + Vite + Element Plus + Pinia' },
  { label: '后端', value: 'FastAPI + SQLAlchemy + Pydantic' },
  { label: '鉴权', value: 'JWT + bcrypt' },
  { label: '知识检索', value: 'Chroma + Embedding 封装' },
  { label: '模型接入', value: 'Mock / OpenAI / Qwen / Local' },
  { label: '文件解析', value: 'pdfplumber + python-docx' },
]

const strengths = [
  '把分析结果延伸成职业规划和面试准备，而不是停留在“看一份报告”。',
  '允许岗位市场、知识库和智能分析互相回流，形成连续工作流。',
  '适合做课程项目、毕业设计或求职产品方向的完整演示。',
]

const boundaries = [
  '系统输出依然依赖模型和知识库质量，不等于真实招聘决策。',
  '岗位数据、知识文档和提示词配置会直接影响结果可靠性。',
  '如果后续模块继续增加，首页和关于页也需要继续保持同步收敛。',
]
</script>

<style scoped>
.page-shell {
  max-width: 1360px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-card,
.panel-card,
.workspace-card {
  border: 1px solid var(--app-line);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--app-shadow-soft);
}

.hero-card {
  padding: 28px;
  border-radius: var(--app-radius-md, 16px);
  background: var(--app-bg);
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-card h2,
.section-head h2 {
  margin: 10px 0 0;
}

.hero-card h2 {
  font-size: 38px;
  line-height: 1.08;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}

.grid-two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel-card {
  border-radius: var(--app-radius-md, 16px);
}

.panel-title,
.workspace-top {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  color: var(--app-text);
}

.info-list,
.pipeline,
.stack-flow,
.bullet-list {
  display: grid;
  gap: 12px;
}

.info-item,
.stack-layer,
.bullet-item {
  padding: 14px 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.info-item strong,
.pipeline-item strong,
.stack-layer strong {
  display: block;
  color: var(--app-text);
}

.info-item p,
.pipeline-item p,
.stack-layer p,
.workspace-card p {
  margin: 6px 0 0;
  color: var(--app-muted);
  line-height: 1.75;
}

.pipeline-item {
  display: grid;
  grid-template-columns: 50px 1fr;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: var(--app-bg);
}

.pipeline-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  border-radius: var(--app-radius-sm, 12px);
  background: linear-gradient(135deg, var(--app-primary), var(--app-warning));
  color: #fff;
  font-weight: 700;
}

.section-head {
  margin-bottom: 14px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.workspace-card {
  padding: 20px;
  border-radius: var(--app-radius-md, 16px);
  background: var(--app-bg);
}

.workspace-top span {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--app-bg);
  border: 1px solid var(--app-line);
  font-size: 12px;
  color: var(--app-muted);
}

.workspace-card h3 {
  margin: 16px 0 8px;
  font-size: 22px;
}

.workspace-features {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.tech-list {
  display: grid;
  gap: 10px;
}

.tech-item {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: var(--app-bg);
}

.tech-item span {
  color: var(--app-muted);
}

.tech-item strong {
  text-align: right;
  color: var(--app-text);
}

@media (max-width: 1280px) {
  .workspace-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .grid-two,
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .hero-card {
    padding: 20px;
  }

  .hero-card h2 {
    font-size: 30px;
  }

  .pipeline-item {
    grid-template-columns: 1fr;
  }
}
</style>
