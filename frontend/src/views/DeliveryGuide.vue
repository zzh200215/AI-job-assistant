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

const router = useRouter()

const deliveryScope = [
  '简历解析、JD 解析、匹配分析、优化建议、面试题生成',
  '职业规划、岗位推荐、岗位搜索、AI 模拟面试、知识库管理',
  '投递看板、Offer 决策、薪资洞察、求职周报、历史留痕',
]

const runtimeBoundaries = [
  'LLM 或 Embedding 使用 mock 时，应视为演示模式。',
  '外部岗位搜索基于爬虫源，站点结构变化可能导致命中率下降。',
  '系统结论依赖知识库质量、岗位池质量和模型输出，不等于真实求职建议。',
]

const knowledgeOps = [
  '种子知识位于 docs/knowledge-seeds，可通过脚本或页面上传导入。',
  '知识库页面支持普通检索、高级调试、切片查看和重新处理。',
  '验收时应至少验证一条文档上传、一条检索命中和一条分析引用来源。',
]

const acceptanceChecklist = [
  '求职主链路：分析 → 岗位推荐 → 投递看板 → 模拟面试 → Offer 决策',
  '辅助链路：求职目标 → 职业规划 → 薪资洞察 → 求职周报',
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
