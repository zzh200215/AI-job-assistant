<template>
  <div class="page-shell">
    <div class="hero">
      <h2>选择适合您的方案</h2>
      <p>AI 驱动的求职教练，从简历到 Offer 全程陪伴</p>
    </div>

    <!-- 定价卡片 -->
    <div class="pricing-grid">
      <div
        v-for="plan in plans"
        :key="plan.id"
        class="pricing-card"
        :class="{ popular: plan.popular }"
      >
        <div v-if="plan.popular" class="popular-badge">最受欢迎</div>
        <div class="plan-header">
          <h3>{{ plan.name }}</h3>
          <div class="plan-price">
            <span class="price-num">{{ plan.price }}</span>
            <span class="price-unit">/月</span>
          </div>
          <p class="plan-desc">{{ plan.desc }}</p>
        </div>

        <div class="plan-features">
          <div v-for="(group, gIdx) in plan.features" :key="gIdx" class="feature-group">
            <div class="feature-group-title">{{ group.label }}</div>
            <div
              v-for="f in group.items"
              :key="f.text"
              class="feature-item"
              :class="{ disabled: !f.available }"
            >
              <el-icon v-if="f.available" class="feat-icon feat-yes"><CircleCheckFilled /></el-icon>
              <el-icon v-else class="feat-icon feat-no"><Close /></el-icon>
              <span>{{ f.text }}</span>
            </div>
          </div>
        </div>

        <div class="plan-action">
          <el-button
            :type="plan.popular ? 'primary' : ''"
            :plain="!plan.popular"
            size="large"
            class="plan-btn"
            :disabled="plan.id === 'free'"
            @click="selectPlan(plan)"
          >
            {{ plan.id === 'free' ? '当前使用中' : plan.id === 'pro' ? '升级到 Pro' : '联系销售' }}
          </el-button>
        </div>
      </div>
    </div>

    <!-- 企业版说明 -->
    <div class="enterprise-section">
      <el-card shadow="never" class="enterprise-card">
        <div class="enterprise-body">
          <div class="enterprise-info">
            <h3>企业版 — 为招聘团队量身定制</h3>
            <ul>
              <li>批量账号管理与权限控制</li>
              <li>定制化 AI 面试题库与评估模型</li>
              <li>招聘数据分析报表与人才看板</li>
              <li>专属客户成功经理与技术支持</li>
              <li>私有化部署选项（可选）</li>
            </ul>
          </div>
          <div class="enterprise-action">
            <el-button type="primary" size="large" @click="contactSales">联系销售团队</el-button>
            <span class="enterprise-note">2 个工作日内回复</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 功能对比表 -->
    <AppPanel>
      <template #title>完整功能对比</template>
      <div class="comparison-scroll">
        <table class="comparison-table">
          <thead>
            <tr>
              <th class="feat-col">功能</th>
              <th v-for="p in plans" :key="p.id">{{ p.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in comparisonRows" :key="row.label">
              <td class="feat-col">{{ row.label }}</td>
              <td v-for="p in plans" :key="p.id">
                <el-icon v-if="row.values[p.id]" class="cmp-yes"><CircleCheckFilled /></el-icon>
                <el-icon v-else class="cmp-no"><Close /></el-icon>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppPanel>
  </div>
</template>

<script setup>
import AppPanel from '@/components/ui/AppPanel.vue'
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import { CircleCheckFilled, Close } from '@element-plus/icons-vue'
import { getSubscriptionPlans, getMySubscription, createOrder } from '@/api/subscription'
import request from '@/api/request'

const plans = ref([])
const comparisonRows = ref([])
const userSubscription = ref(null)

const featuresDisplay = {
  resume_limit: { label: '简历数量', free: '1份', pro: '不限', enterprise: '不限' },
  daily_analysis_limit: { label: '每日分析', free: '3次', pro: '50次', enterprise: '不限' },
  daily_interview_limit: { label: '每日面试', free: '5次', pro: '100次', enterprise: '不限' },
  daily_recommendation_limit: { label: '每日推荐', free: '10次', pro: '200次', enterprise: '不限' },
  can_export_full_report: { label: '完整报告导出', free: false, pro: true, enterprise: true },
  can_use_deep_analysis: { label: 'AI 深度分析', free: false, pro: true, enterprise: true },
  can_use_ats_check: { label: 'ATS 友好度检测', free: false, pro: true, enterprise: true },
  can_use_offer_decision: { label: 'Offer 决策助手', free: false, pro: true, enterprise: true },
  can_use_salary_negotiation: { label: '谈薪资建议', free: false, pro: true, enterprise: true },
}

async function loadPlans() {
  try {
    const data = await getSubscriptionPlans()
    if (data?.items) {
      plans.value = data.items.map((p) => ({
        id: p.tier,
        name: p.name,
        price: formatPrice(p),
        desc:
          p.tier === 'free'
            ? '适合求职初期，体验核心功能'
            : p.tier === 'pro'
              ? '适合求职冲刺，全面发挥 AI 能力'
              : '适合招聘团队和企业 HR 部门',
        popular: p.tier === 'pro',
        features: buildFeatureGroups(p.features),
      }))
      comparisonRows.value = buildComparisonRows(data.items)
    }
  } catch {
    // fallback 到静态数据
  }
}

// T3-1：套餐价格取自后端（租户自定义价格优先），单位为分
function formatPrice(p) {
  const monthly = Number(p.price_monthly || 0)
  if (monthly <= 0) return p.tier === 'free' ? '¥0' : '定制'
  const yuan = monthly % 100 === 0 ? monthly / 100 : (monthly / 100).toFixed(2)
  return `¥${yuan}`
}

function buildFeatureGroups(features) {
  const groups = []
  // 简历
  const resumeItems = [
    {
      text: `${features.resume_limit === -1 ? '不限' : features.resume_limit} 份简历`,
      available: true,
    },
    { text: '简历解析与评分', available: true },
    { text: 'AI 简历优化', available: features.can_use_deep_analysis },
    { text: 'ATS 友好度检测', available: features.can_use_ats_check },
  ]
  groups.push({ label: '简历', items: resumeItems })

  // 面试
  const interviewLimit =
    features.daily_interview_limit === -1 ? '不限' : `${features.daily_interview_limit} 次/日`
  const interviewItems = [
    { text: `模拟面试 (${interviewLimit})`, available: true },
    { text: '面试报告与评估', available: true },
    { text: '薄弱知识点训练', available: features.can_use_deep_analysis },
    { text: '自我介绍生成器', available: features.can_use_deep_analysis },
  ]
  groups.push({ label: '面试', items: interviewItems })

  // 岗位
  const recLimit =
    features.daily_recommendation_limit === -1
      ? '不限'
      : `${features.daily_recommendation_limit} 次/日`
  const jobItems = [
    { text: `岗位推荐 (${recLimit})`, available: true },
    { text: '投递看板', available: true },
    { text: 'Offer 决策助手', available: features.can_use_offer_decision },
    { text: '谈薪资建议', available: features.can_use_salary_negotiation },
  ]
  groups.push({ label: '岗位', items: jobItems })

  // 其他
  const otherItems = [
    { text: '职业规划', available: true },
    { text: '薪资洞察', available: true },
    {
      text: `AI 深度分析 (${features.daily_analysis_limit === -1 ? '不限' : `${features.daily_analysis_limit} 次/日`})`,
      available: features.can_use_deep_analysis,
    },
    { text: '完整报告导出', available: features.can_export_full_report },
  ]
  groups.push({ label: '其他', items: otherItems })

  return groups
}

function buildComparisonRows(apiPlans) {
  return Object.entries(featuresDisplay).map(([key, meta]) => ({
    label: meta.label,
    values: {
      free: !!meta.free || apiPlans.find((p) => p.tier === 'free')?.features?.[key],
      pro: !!meta.pro || apiPlans.find((p) => p.tier === 'pro')?.features?.[key],
      enterprise:
        !!meta.enterprise || apiPlans.find((p) => p.tier === 'enterprise')?.features?.[key],
    },
  }))
}

async function loadUserSubscription() {
  try {
    const data = await getMySubscription()
    if (data) userSubscription.value = data
  } catch {
    // 订阅状态不可用时保持免费版默认展示。
  }
}

const paying = ref(false)
const payResult = ref(null) // {success, order_id, message}

async function selectPlan(plan) {
  if (plan.id === 'free') return

  if (plan.id === 'enterprise') {
    contactSales()
    return
  }

  // Pro 版：确认 → 创建订单 → 模拟支付
  try {
    await ElMessageBox.confirm(`确认升级到 ${plan.name} (${plan.price}/月)？`, '升级确认', {
      confirmButtonText: '确认升级',
      cancelButtonText: '取消',
      type: 'info',
    })
  } catch {
    return
  }

  paying.value = true
  try {
    const orderData = await createOrder('pro', 'monthly')
    if (!orderData?.order_id) {
      ElMessage.error('订单创建失败')
      return
    }

    // 调用模拟支付（生产环境替换为真实支付网关跳转）
    const res = await request.post('/subscription/mock-pay', { order_id: orderData.order_id })
    if (res?.message) {
      payResult.value = { success: true, order_id: orderData.order_id, message: res.message }
      ElMessage.success('🎉 升级成功！Pro 权益已生效')
      await loadUserSubscription()
    }
  } catch (e) {
    payResult.value = { success: false, order_id: null, message: e.message || '支付失败' }
    ElMessage.error('支付失败: ' + (e.message || '请稍后重试'))
  } finally {
    paying.value = false
  }
}

function contactSales() {
  ElMessage.success('已记录您的需求，销售团队将在 2 个工作日内联系您')
}

onMounted(() => {
  loadPlans()
  loadUserSubscription()
})
</script>

<style scoped>
.page-shell {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px 0;
}

.hero {
  text-align: center;
  padding: 40px 20px;
}

.hero h2 {
  font-size: 36px;
  font-weight: 800;
  margin: 0;
  color: var(--app-text);
}

.hero p {
  margin-top: 12px;
  font-size: 16px;
  color: var(--app-muted);
}

/* Pricing grid */
.pricing-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.pricing-card {
  position: relative;
  border-radius: 20px;
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition:
    transform 0.2s,
    box-shadow 0.2s;
}

.pricing-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--app-shadow-hover);
}

.pricing-card.popular {
  border-color: var(--app-primary);
  box-shadow: 0 8px 32px rgba(25, 107, 219, 0.15);
  transform: scale(1.04);
  z-index: 1;
}

.pricing-card.popular:hover {
  transform: scale(1.04) translateY(-4px);
}

.popular-badge {
  position: absolute;
  top: 14px;
  right: 14px;
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--app-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.plan-header {
  padding: 28px 24px 20px;
  text-align: center;
  border-bottom: 1px solid var(--app-line);
}

.plan-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.plan-price {
  margin: 16px 0;
}

.price-num {
  font-size: 42px;
  font-weight: 800;
  color: var(--app-primary);
}

.price-unit {
  font-size: 16px;
  color: var(--app-muted);
}

.plan-desc {
  margin: 0;
  font-size: 14px;
  color: var(--app-muted);
}

.plan-features {
  padding: 20px 24px;
  flex: 1;
}

.feature-group {
  margin-bottom: 16px;
}

.feature-group-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--app-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 14px;
}

.feature-item.disabled {
  color: var(--app-muted);
  opacity: 0.6;
}

.feat-icon {
  font-size: 16px;
  flex-shrink: 0;
}
.feat-yes {
  color: var(--app-success);
}
.feat-no {
  color: var(--app-muted);
}

.plan-action {
  padding: 16px 24px 24px;
}

.plan-btn {
  width: 100%;
  height: 48px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
}

/* Enterprise */
.enterprise-card {
  border-radius: 20px;
  border: 1px solid var(--app-line);
  background: linear-gradient(135deg, #f0f9ff, #e8f4fd);
}

.enterprise-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 8px;
}

.enterprise-info h3 {
  margin: 0 0 12px;
  font-size: 20px;
  font-weight: 700;
}

.enterprise-info ul {
  margin: 0;
  padding-left: 18px;
}

.enterprise-info li {
  margin-bottom: 6px;
  font-size: 14px;
  line-height: 1.6;
}

.enterprise-action {
  text-align: center;
  flex-shrink: 0;
}

.enterprise-note {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-muted);
}

/* Comparison table */
.comparison-scroll {
  overflow-x: auto;
}

.comparison-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.comparison-table th,
.comparison-table td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--app-line);
  text-align: center;
}

.comparison-table th {
  font-weight: 700;
  background: var(--app-bg);
}

.feat-col {
  text-align: left !important;
  font-weight: 500;
  min-width: 160px;
}

.cmp-yes {
  color: var(--app-success);
  font-size: 18px;
}
.cmp-no {
  color: #d1d5db;
  font-size: 18px;
}

@media (max-width: 900px) {
  .pricing-grid {
    grid-template-columns: 1fr;
  }
  .pricing-card.popular {
    transform: none;
  }
  .pricing-card.popular:hover {
    transform: translateY(-4px);
  }
  .enterprise-body {
    flex-direction: column;
    text-align: center;
  }
}
</style>
