<template>
  <div class="page-shell">
    <div class="hero">
      <h2>选择适合您的方案</h2>
      <p>AI 驱动的求职教练，从简历到 Offer 全程陪伴</p>
      <!-- §10.1：当前代码里唯一真正按套餐区分的行为是简历数量，其余能力对所有用户开放。
           这一句是"权益表里说不出来的标记"被摘掉之后，页面对现状的正面陈述。 -->
      <p class="hero-note">现在所有 AI 能力对各档套餐都开放，实际差别只有可管理的简历数量。</p>
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
            <div v-for="text in group.items" :key="text" class="feature-item">
              <el-icon class="feat-icon feat-yes"><CircleCheckFilled /></el-icon>
              <span>{{ text }}</span>
            </div>
          </div>
        </div>
      </div>
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
                <!-- 真门那一行报出各档的实际数字；其余行不再画 ✓/✗——除了简历数量，
                     两个符号里哪一个都在陈述一个不存在的事实 -->
                <span :class="row.enforced ? 'cmp-value' : 'cmp-same'">
                  {{ row.enforced ? row.values[p.id] : '各套餐一致' }}
                </span>
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
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { getSubscriptionPlans, getMySubscription } from '@/api/subscription'

const plans = ref([])
const comparisonRows = ref([])
const userSubscription = ref(null)

/* §10.1 他点"不做商业化 → 摘掉装饰那侧"。这份名单就是"装饰"与"能证"的分界：
   全仓 `check_quota` 只有两个调用方（`resume.py:198` 的 `resume_count`、以及通用端点
   `/subscription/check-quota`），所以**套餐在代码里真正造成的差别只有简历数量这一项**。
   `daily_*_limit` 与 `can_use_*` 在服务端都实现了（`subscription_service.py:258-259` 等），
   缺的是调用方——于是这一页此前正在对免费用户画 ✗ 说"你没有 AI 简历优化"，而那是一句没被证实的话。
   名单由 `backend/tests/test_plan_gating_inventory.py` 反向钉着：谁新接了一个额度门，那边就红，
   逼着两边一起改。 */
const ENFORCED_PLAN_KEYS = new Set(['resume_limit'])

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
  /* 只说能证的话：没有门在执行的额度不写数字，没有门在执行的权益不画 ✗（✗ 那一支连同
     `.feat-no` / `.feature-item.disabled` 样式一起删了——`ENFORCED_PLAN_KEYS` 只有
     `resume_limit` 一项，这一列今天不可能出现"没有"）。
     简历数量是唯一保留数字的一行，因为 `resume.py` 上传时真的按 `resume_limit` 判。 */
  return [
    {
      label: '简历',
      items: [
        `${features.resume_limit === -1 ? '不限' : features.resume_limit} 份简历`,
        '简历解析与评分',
        'AI 简历优化',
        'ATS 友好度检测',
      ],
    },
    {
      label: '面试',
      items: ['模拟面试', '面试报告与评估', '薄弱知识点训练', '自我介绍生成器'],
    },
    { label: '岗位', items: ['岗位推荐', '投递看板', 'Offer 决策助手', '谈薪资建议'] },
    { label: '其他', items: ['职业规划', '薪资洞察', 'AI 深度分析', '完整报告导出'] },
  ]
}

function buildComparisonRows(apiPlans) {
  /* 真门那一行的数字取自 API（`resume_limit`：-1 显示"不限"，否则显示份数），API 没给时退回
     featuresDisplay 的静态文案——它是 `TIER_FEATURES` 的镜像。其余行显示"各套餐一致"，
     因为没有任何门按它们判过。 */
  const tierValue = (key, meta, tier) => {
    const fromApi = apiPlans.find((p) => p.tier === tier)?.features?.[key]
    if (key === 'resume_limit' && fromApi !== undefined) {
      return fromApi === -1 ? '不限' : `${fromApi} 份`
    }
    return meta[tier]
  }
  return Object.entries(featuresDisplay).map(([key, meta]) => ({
    label: meta.label,
    enforced: ENFORCED_PLAN_KEYS.has(key),
    values: {
      free: tierValue(key, meta, 'free'),
      pro: tierValue(key, meta, 'pro'),
      enterprise: tierValue(key, meta, 'enterprise'),
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

/* §10.1 他点"抽掉购买入口、保留信息"：`mockPayOrder` 会真的把用户套餐改成 pro（于是 resume_limit
   从 1 变不限），而 Pro 与免费在代码里除了那一行没有任何行为差别——所以"升级到 Pro"这个按钮
   本身就是一个装饰。`createOrder` / `mockPayOrder` / 联系销售那几个函数一并撤下；
   后端 `app/api/subscription.py` 那几个端点没动（E19 的默认拒绝继续盖着它们），
   这一页也不再是它们的调用方。 */

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

.hero-note {
  font-size: 14px;
  color: var(--app-muted);
  border-left: 3px solid var(--app-line);
  padding-left: 10px;
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

.feat-icon {
  font-size: 16px;
  flex-shrink: 0;
}
.feat-yes {
  color: var(--app-success);
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

.cmp-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}
.cmp-same {
  font-size: 13px;
  color: var(--app-muted);
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
}
</style>
