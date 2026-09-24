<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="eyebrow">Recommendation Tuning</p>
        <h2>推荐权重配置</h2>
        <div class="page-header-sub">
          调整向量/规则权重、规则子项占比和推荐阈值。保存后会直接作用于后续岗位推荐结果。
        </div>
      </div>
      <div class="hero-actions">
        <el-button @click="router.push('/jobs/recommend/evaluation')">返回推荐评测</el-button>
        <el-button :loading="loading.compare" type="success" plain @click="runCompare"
          >实验对比</el-button
        >
        <el-button :loading="loading.reset" @click="handleReset">恢复默认</el-button>
        <el-button type="primary" :loading="loading.save" @click="handleSave">保存配置</el-button>
      </div>
    </header>

    <div class="grid-two">
      <AppPanel>
        <template #title>主通道权重</template>
        <div class="slider-list">
          <div class="slider-item">
            <div class="slider-head">
              <strong>向量通道</strong>
              <span>{{ percentText(form.vector_weight) }}</span>
            </div>
            <el-slider v-model="vectorPercent" :min="0" :max="100" />
          </div>
          <div class="slider-item locked-item">
            <div class="slider-head">
              <strong>规则通道</strong>
              <span>{{ percentText(form.rule_weight) }}</span>
            </div>
            <el-progress :percentage="rulePercent" :show-text="false" />
          </div>
        </div>
      </AppPanel>

      <AppPanel>
        <template #title>推荐阈值</template>
        <div class="threshold-grid">
          <div class="threshold-item">
            <span>高度推荐</span>
            <el-input-number v-model="form.thresholds.high" :min="1" :max="100" />
          </div>
          <div class="threshold-item">
            <span>值得一试</span>
            <el-input-number v-model="form.thresholds.medium" :min="0" :max="99" />
          </div>
        </div>
        <div class="helper-text">要求 `高度推荐` 必须大于 `值得一试`。</div>
      </AppPanel>
    </div>

    <AppPanel>
      <template #title>规则子项权重</template>
      <template #badge>
        <span class="muted">四项总和需为 100%</span>
      </template>
      <div class="component-grid">
        <div class="slider-item">
          <div class="slider-head">
            <strong>技能匹配</strong>
            <span>{{ percentText(form.rule_components.skill) }}</span>
          </div>
          <el-slider v-model="skillPercent" :min="0" :max="100" />
        </div>
        <div class="slider-item">
          <div class="slider-head">
            <strong>经验匹配</strong>
            <span>{{ percentText(form.rule_components.experience) }}</span>
          </div>
          <el-slider v-model="experiencePercent" :min="0" :max="remainingAfterSkill" />
        </div>
        <div class="slider-item">
          <div class="slider-head">
            <strong>薪资匹配</strong>
            <span>{{ percentText(form.rule_components.salary) }}</span>
          </div>
          <el-slider v-model="salaryPercent" :min="0" :max="remainingAfterExperience" />
        </div>
        <div class="slider-item locked-item">
          <div class="slider-head">
            <strong>地点匹配</strong>
            <span>{{ percentText(form.rule_components.location) }}</span>
          </div>
          <el-progress :percentage="locationPercent" :show-text="false" />
        </div>
      </div>
    </AppPanel>

    <AppPanel>
      <template #title>当前配置摘要</template>
      <pre class="code-block">{{ configPreview }}</pre>
    </AppPanel>

    <AppPanel v-if="compareResult">
      <template #title>实验对比结果</template>
      <template #badge>
        <span class="muted">{{ compareResult.sample_total }} 条历史反馈样本</span>
      </template>
      <div class="compare-grid">
        <div class="compare-card">
          <span class="compare-label">{{ compareResult.variant_a.label }}</span>
          <strong>{{ percentText(compareResult.variant_a.summary.agreement_rate) }}</strong>
          <small>一致率</small>
          <p>
            高分点踩 {{ compareResult.variant_a.summary.high_score_dislike_count }} · 低分点赞
            {{ compareResult.variant_a.summary.low_score_like_count }}
          </p>
        </div>
        <div class="compare-card">
          <span class="compare-label">{{ compareResult.variant_b.label }}</span>
          <strong>{{ percentText(compareResult.variant_b.summary.agreement_rate) }}</strong>
          <small>一致率</small>
          <p>
            高分点踩 {{ compareResult.variant_b.summary.high_score_dislike_count }} · 低分点赞
            {{ compareResult.variant_b.summary.low_score_like_count }}
          </p>
        </div>
        <div class="compare-card delta-card">
          <span class="compare-label">变化</span>
          <strong>{{ signedPercent(compareResult.delta.agreement_rate) }}</strong>
          <small>一致率变化</small>
          <p>均分变化 {{ signedNumber(compareResult.delta.avg_combined_score) }}</p>
        </div>
      </div>

      <div class="mover-list" v-if="compareResult.delta.top_movers?.length">
        <div class="mover-title">变化最大的样本</div>
        <div class="mover-items">
          <div
            v-for="item in compareResult.delta.top_movers"
            :key="item.feedback_id"
            class="mover-item"
          >
            <strong>{{ item.jd_title }}</strong>
            <span>{{ item.resume_title }} · {{ item.feedback_type }}</span>
            <span
              >{{ item.score_a }} → {{ item.score_b }}（{{ signedNumber(item.score_delta) }}）</span
            >
            <span>{{ item.type_a }} → {{ item.type_b }}</span>
          </div>
        </div>
      </div>
    </AppPanel>
  </div>
</template>

<script setup>
import AppPanel from '@/components/ui/AppPanel.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ElMessage } from '@/plugins/element-services'
import {
  compareJobRecommendConfig,
  getJobRecommendConfig,
  resetJobRecommendConfig,
  updateJobRecommendConfig,
} from '@/api/jobs'

const router = useRouter()

const loading = reactive({
  compare: false,
  save: false,
  reset: false,
})
const savedConfig = ref(null)
const compareResult = ref(null)

const form = reactive({
  vector_weight: 0.6,
  rule_weight: 0.4,
  rule_components: {
    skill: 0.5,
    experience: 0.2,
    salary: 0.15,
    location: 0.15,
  },
  thresholds: {
    high: 80,
    medium: 60,
  },
})

const vectorPercent = computed({
  get: () => Math.round(form.vector_weight * 100),
  set: (value) => {
    form.vector_weight = round4(value / 100)
    form.rule_weight = round4(1 - form.vector_weight)
  },
})

const rulePercent = computed(() => Math.round(form.rule_weight * 100))

const skillPercent = computed({
  get: () => Math.round(form.rule_components.skill * 100),
  set: (value) => {
    form.rule_components.skill = round4(value / 100)
    rebalanceRuleComponents()
  },
})

const remainingAfterSkill = computed(() => Math.max(100 - skillPercent.value, 0))

const experiencePercent = computed({
  get: () => Math.round(form.rule_components.experience * 100),
  set: (value) => {
    form.rule_components.experience = round4(value / 100)
    rebalanceRuleComponents('experience')
  },
})

const remainingAfterExperience = computed(() =>
  Math.max(100 - skillPercent.value - experiencePercent.value, 0)
)

const salaryPercent = computed({
  get: () => Math.round(form.rule_components.salary * 100),
  set: (value) => {
    form.rule_components.salary = round4(value / 100)
    rebalanceRuleComponents('salary')
  },
})

const locationPercent = computed(() => Math.round(form.rule_components.location * 100))

const configPreview = computed(() =>
  JSON.stringify(
    {
      vector_weight: form.vector_weight,
      rule_weight: form.rule_weight,
      rule_components: form.rule_components,
      thresholds: form.thresholds,
    },
    null,
    2
  )
)

onMounted(() => {
  loadConfig()
})

async function loadConfig() {
  const data = await getJobRecommendConfig()
  savedConfig.value = structuredCloneSafe(data)
  applyConfig(data)
}

async function handleSave() {
  if (form.thresholds.high <= form.thresholds.medium) {
    ElMessage.warning('高度推荐阈值必须大于值得一试阈值')
    return
  }
  loading.save = true
  try {
    const data = await updateJobRecommendConfig(toPayload())
    savedConfig.value = structuredCloneSafe(data)
    applyConfig(data)
    ElMessage.success('推荐权重配置已保存')
  } finally {
    loading.save = false
  }
}

async function handleReset() {
  loading.reset = true
  try {
    const data = await resetJobRecommendConfig()
    savedConfig.value = structuredCloneSafe(data)
    applyConfig(data)
    ElMessage.success('已恢复默认配置')
  } finally {
    loading.reset = false
  }
}

async function runCompare() {
  loading.compare = true
  try {
    compareResult.value = await compareJobRecommendConfig({
      label_a: '已保存配置',
      label_b: '候选配置',
      config_a: savedConfig.value || toPayload(),
      config_b: toPayload(),
    })
  } finally {
    loading.compare = false
  }
}

function applyConfig(data) {
  form.vector_weight = Number(data?.vector_weight ?? 0.6)
  form.rule_weight = Number(data?.rule_weight ?? 0.4)
  form.rule_components.skill = Number(data?.rule_components?.skill ?? 0.5)
  form.rule_components.experience = Number(data?.rule_components?.experience ?? 0.2)
  form.rule_components.salary = Number(data?.rule_components?.salary ?? 0.15)
  form.rule_components.location = Number(data?.rule_components?.location ?? 0.15)
  form.thresholds.high = Number(data?.thresholds?.high ?? 80)
  form.thresholds.medium = Number(data?.thresholds?.medium ?? 60)
}

function toPayload() {
  return {
    vector_weight: round4(form.vector_weight),
    rule_weight: round4(form.rule_weight),
    rule_components: {
      skill: round4(form.rule_components.skill),
      experience: round4(form.rule_components.experience),
      salary: round4(form.rule_components.salary),
      location: round4(form.rule_components.location),
    },
    thresholds: {
      high: Number(form.thresholds.high),
      medium: Number(form.thresholds.medium),
    },
  }
}

function rebalanceRuleComponents(lastChanged = 'skill') {
  const components = form.rule_components
  const totalWithoutLocation = components.skill + components.experience + components.salary
  components.location = round4(Math.max(1 - totalWithoutLocation, 0))

  if (lastChanged === 'salary' && components.location < 0) {
    components.salary = round4(1 - components.skill - components.experience)
    components.location = 0
  }
}

function percentText(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function round4(value) {
  return Number(Number(value).toFixed(4))
}

function signedPercent(value) {
  const num = Number(value || 0)
  return `${num >= 0 ? '+' : ''}${Math.round(num * 100)}%`
}

function signedNumber(value) {
  const num = Number(value || 0)
  return `${num >= 0 ? '+' : ''}${Number(num.toFixed(2))}`
}

function structuredCloneSafe(value) {
  return JSON.parse(JSON.stringify(value || {}))
}
</script>

<style scoped>
.page-shell {
  max-width: 1040px;
  margin: 0 auto;
  padding: 12px 0 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

.helper-text,
.muted {
  color: var(--app-muted);
}

.grid-two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.compare-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.slider-list,
.component-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.slider-item,
.threshold-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.slider-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.slider-head strong,
.threshold-item span {
  color: var(--app-text);
}

.locked-item :deep(.el-progress-bar__outer) {
  background: #edf2ee;
}

.threshold-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.threshold-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.code-block {
  margin: 0;
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: #0f1720;
  color: #dde7f2;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.compare-card,
.mover-item {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.compare-card strong,
.compare-card span,
.compare-card small,
.compare-card p,
.mover-item strong,
.mover-item span {
  display: block;
}

.compare-label {
  font-size: 12px;
  color: var(--app-muted);
}

.compare-card strong {
  margin-top: 8px;
  font-size: 24px;
  color: var(--app-text);
}

.compare-card p,
.mover-item span {
  margin: 6px 0 0;
  color: var(--app-muted);
  font-size: 12px;
}

.delta-card {
  background: linear-gradient(180deg, #f6faf7, #fdfefe);
}

.mover-list {
  margin-top: 16px;
}

.mover-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text);
}

.mover-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mover-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

@media (max-width: 960px) {
  .grid-two,
  .threshold-grid,
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>
