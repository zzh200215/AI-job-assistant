<template>
  <div class="guide-page">
    <el-card shadow="never" class="hero-card">
      <p class="eyebrow">Delivery Guide</p>
      <h2>交付与验收说明</h2>
	      <div class="page-header-sub">
        这一页把项目当前可演示范围、生产边界、知识库维护方式和验收建议集中展示，避免信息分散在文档和代码里。
      </div>
	      <div class="hero-actions">
        <el-button type="primary" @click="router.push('/system-status')">查看系统状态</el-button>
        <el-button @click="router.push('/knowledge')">进入知识库</el-button>
        <el-button v-if="authStore.isRecruiter" @click="router.push('/datasource')">查看数据源</el-button>
      </div>
    </el-card>

    <section class="grid-two">
      <el-card shadow="never" class="panel-card">
        <template #header><span>当前交付范围</span></template>
        <ul class="bullet-list">
          <li v-for="item in deliveryScope" :key="item">{{ item }}</li>
        </ul>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header><span>演示与生产边界</span></template>
        <ul class="bullet-list">
          <li v-for="item in runtimeBoundaries" :key="item">{{ item }}</li>
        </ul>
      </el-card>
    </section>

    <section class="grid-two">
      <el-card shadow="never" class="panel-card">
        <template #header><span>知识库维护</span></template>
        <ul class="bullet-list">
          <li v-for="item in knowledgeOps" :key="item">{{ item }}</li>
        </ul>
      </el-card>

      <el-card shadow="never" class="panel-card">
        <template #header><span>验收建议</span></template>
        <ul class="bullet-list">
          <li v-for="item in acceptanceChecklist" :key="item">{{ item }}</li>
        </ul>
      </el-card>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const deliveryScope = [
  '简历解析、JD 解析、匹配分析、优化建议、面试题生成',
  '职业规划、岗位推荐、岗位搜索、企业筛选、知识库管理',
  '数据源管理、筛选导出、历史留痕、系统状态展示',
]

const runtimeBoundaries = [
  'LLM 或 Embedding 使用 mock 时，应视为演示模式。',
  'HTTP API 数据源目前是扩展框架，正式接入仍需补鉴权、分页和频控。',
  '系统结论依赖知识库质量、岗位池质量和模型输出，不等于真实招聘结论。',
]

const knowledgeOps = [
  '种子知识位于 docs/knowledge-seeds，可通过脚本或页面上传导入。',
  '知识库页面支持普通检索、高级调试、切片查看和重新处理。',
  '验收时应至少验证一条文档上传、一条检索命中和一条分析引用来源。',
]

const acceptanceChecklist = [
  '求职者主链路：分析 -> 规划 -> 岗位 -> 面试',
  '招聘者主链路：数据源 -> 企业筛选 -> 导出 -> 历史复盘',
  '系统状态可说明当前是否处于演示模式以及哪些能力是预留框架。',
]
</script>

<style scoped>
.page-shell {
  max-width: 1320px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-card,
.panel-card {
  border-radius: var(--app-radius-md, 16px);
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.grid-two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.bullet-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
}

@media (max-width: 960px) {
  .grid-two {
    grid-template-columns: 1fr;
  }
}
</style>
