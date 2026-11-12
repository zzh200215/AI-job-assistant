<template>
  <div class="page-shell">
    <section class="overview-heading">
      <div>
        <p class="section-kicker">运营概览</p>
        <h2>今天的系统运营信号</h2>
        <p class="page-header-sub">统一查看用户增长、订阅转化和需要跟进的订单。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" @click="loadOverview">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </div>
    </section>

    <!-- 指标卡的数据没取到时不能照常画：四张卡会变成"注册 0 / 付费 0"，比空着更像真数据 -->
    <AppLoadError
      v-if="analyticsError"
      title="运营指标加载失败"
      :message="analyticsError"
      @retry="loadAnalytics"
    />
    <section v-else class="metrics-grid">
      <article v-for="item in metricCards" :key="item.label" class="metric-card" :class="item.tone">
        <div class="metric-icon">
          <el-icon><component :is="item.icon" /></el-icon>
        </div>
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </article>
    </section>

    <section class="work-grid">
      <el-card shadow="never" class="panel funnel-panel">
        <template #header>
          <div class="card-heading">
            <div>
              <h3>转化漏斗</h3>
              <span>近 30 天注册 → 上传 → 分析 → 面试 → 订阅</span>
            </div>
          </div>
        </template>
        <AppLoadError
          v-if="analyticsError"
          title="转化漏斗加载失败"
          :message="analyticsError"
          @retry="loadAnalytics"
        />
        <template v-else>
          <div class="funnel-list">
            <div v-for="s in funnelSteps" :key="s.key" class="funnel-row">
              <span class="funnel-label">{{ s.label }}</span>
              <div class="funnel-track">
                <span :style="{ width: s.width }" />
              </div>
              <b>{{ s.count }}</b>
              <em>{{ s.rate }}%</em>
            </div>
          </div>
          <el-empty
            v-if="!funnelSteps.length && !loading"
            description="暂无漏斗数据"
            :image-size="72"
          />
        </template>
      </el-card>

      <el-card shadow="never" class="panel action-panel">
        <template #header>
          <div class="card-heading">
            <div>
              <h3>订单状态</h3>
              <span>最近订单</span>
            </div>
            <el-button text @click="router.push('/admin/orders')">查看订单</el-button>
          </div>
        </template>
        <AppLoadError
          v-if="ordersError"
          title="订单状态加载失败"
          :message="ordersError"
          @retry="loadOrders"
        />
        <template v-else>
          <div class="status-list">
            <div v-for="item in orderBreakdown" :key="item.label" class="status-row">
              <span class="status-label"><i :class="item.tone" />{{ item.label }}</span>
              <div class="status-track">
                <span :class="item.tone" :style="{ width: item.width }" />
              </div>
              <b>{{ item.value }}</b>
            </div>
          </div>
          <el-empty v-if="!orders.length && !loading" description="暂无订单数据" :image-size="72" />
        </template>
      </el-card>
    </section>

    <el-card shadow="never" class="panel recent-panel">
      <template #header>
        <div class="card-heading">
          <div>
            <h3>最新订单</h3>
            <span>最近 6 笔订阅记录</span>
          </div>
          <el-button type="primary" plain @click="router.push('/admin/orders')">管理订单</el-button>
        </div>
      </template>
      <AppLoadError
        v-if="ordersError"
        title="最新订单加载失败"
        :message="ordersError"
        @retry="loadOrders"
      />
      <el-table
        v-else-if="orders.length"
        :data="orders.slice(0, 6)"
        size="small"
        style="width: 100%"
      >
        <el-table-column prop="id" label="订单号" width="88"
          ><template #default="{ row }">#{{ row.id }}</template></el-table-column
        >
        <el-table-column label="套餐"
          ><template #default="{ row }">{{ planLabel(row.plan_tier) }}</template></el-table-column
        >
        <el-table-column label="金额" width="110"
          ><template #default="{ row }">{{ formatMoney(row.amount) }}</template></el-table-column
        >
        <el-table-column label="状态" width="110"
          ><template #default="{ row }"
            ><el-tag size="small" :type="statusType(row.status)">{{
              statusLabel(row.status)
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="创建时间" min-width="170"
          ><template #default="{ row }">{{
            dateTime(row.created_at, '-')
          }}</template></el-table-column
        >
      </el-table>
      <el-empty v-else-if="!loading" description="暂无可展示的订单" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CreditCard, Refresh, Tickets, User, UserFilled } from '@element-plus/icons-vue'
import AppLoadError from '@/components/ui/AppLoadError.vue'
import { getAnalyticsSummary, getAdminRevenue, getAnalyticsFunnel } from '@/api/analytics'
import { getAdminOrders } from '@/api/subscription'
import { dateTime } from '@/utils/format/date'
import { userErrorCopy } from '@/utils/requestTracing'

const router = useRouter()
const loading = ref(false)
/* 两个数据源各留一个错误位：概览指标（指标卡 + 漏斗）和订单来自两个接口，
   共用一个布尔位会让"订单挂了"把漏斗一起判死，重试按钮也说不清该重调哪个加载函数。 */
const analyticsError = ref('')
const ordersError = ref('')
const summary = ref(/** @type {import('@/api/analytics').AnalyticsSummaryPayload} */ ({}))
const revenue = ref(/** @type {import('@/api/analytics').AnalyticsRevenuePayload} */ ({}))
const funnel = ref(/** @type {import('@/api/analytics').AnalyticsFunnelPayload} */ ({}))
const orders = ref([])

const paidOrders = computed(() => orders.value.filter((order) => order.status === 'paid'))
const proUsers = computed(() => summary.value.pro_users || 0)
const totalUsers = computed(() => summary.value.total_users || 0)
const paidOrderCount = computed(() => summary.value.paid_orders || 0)

const metricCards = computed(() => [
  {
    label: '注册用户',
    value: totalUsers.value,
    hint: '全量用户口径',
    icon: UserFilled,
    tone: 'blue',
  },
  {
    label: 'Pro 用户',
    value: proUsers.value,
    hint: '有效 pro 订阅用户',
    icon: User,
    tone: 'violet',
  },
  {
    label: '付费订单',
    value: paidOrderCount.value,
    hint: '已支付订单笔数',
    icon: Tickets,
    tone: 'amber',
  },
  {
    label: '已收款',
    value: formatMoney(revenue.value.total_amount),
    hint: '近 30 天已支付金额',
    icon: CreditCard,
    tone: 'green',
  },
])

const funnelSteps = computed(() => {
  const steps = funnel.value.steps || []
  const max = Math.max(...steps.map((s) => s.count || 0), 1)
  return steps.map((s) => ({
    ...s,
    width: `${Math.max((s.count / max) * 100, s.count ? 8 : 0)}%`,
  }))
})

const orderBreakdown = computed(() => {
  const total = orders.value.length || 1
  const states = [
    { key: 'paid', label: '已支付', tone: 'green' },
    { key: 'pending', label: '待支付', tone: 'amber' },
    { key: 'cancelled', label: '已取消', tone: 'slate' },
  ]
  return states.map((state) => {
    const value = orders.value.filter((order) => order.status === state.key).length
    return {
      ...state,
      value,
      width: `${Math.max(value ? (value / total) * 100 : 0, value ? 8 : 0)}%`,
    }
  })
})

function formatMoney(amount) {
  return `￥${Number(amount || 0).toFixed(2)}`
}
function planLabel(plan) {
  return { free: '免费版', pro: 'Pro', enterprise: '企业版' }[plan] || plan || '-'
}
function statusLabel(status) {
  return { paid: '已支付', pending: '待支付', cancelled: '已取消' }[status] || status || '未知'
}
function statusType(status) {
  return { paid: 'success', pending: 'warning', cancelled: 'info' }[status] || 'info'
}

async function loadAnalytics() {
  loading.value = true
  try {
    const [summaryRes, revenueRes, funnelRes] = await Promise.all([
      getAnalyticsSummary({}, { notifyError: false }),
      getAdminRevenue({}, { notifyError: false }),
      getAnalyticsFunnel({}, { notifyError: false }),
    ])
    summary.value = summaryRes || {}
    revenue.value = revenueRes || {}
    funnel.value = funnelRes || {}
    // 成功一次就把横幅撤掉，否则重试成功后那条"加载失败"会一直挂在页面上
    analyticsError.value = ''
  } catch (e) {
    /* 失败时把旧值清掉：错误面只负责"这一次失败了"，不能让上一次的数字留在下面被当成这一次的结果。
       上屏那句只认 userErrorCopy——axios 自带的是英文技术串（Network Error / status code 500），
       用户读不懂，也不该由视图翻译。 */
    summary.value = {}
    revenue.value = {}
    funnel.value = {}
    analyticsError.value = userErrorCopy(e, '暂时取不到运营数据，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function loadOrders() {
  try {
    const res = await getAdminOrders({ page: 1, page_size: 100 }, { notifyError: false })
    const data = res?.data || res || {}
    orders.value = data.items || []
    ordersError.value = ''
  } catch (e) {
    /* 这里原来是 `catch { orders.value = [] }`：GET 失败不弹提示，页面于是画出"暂无订单数据"，
       把服务端的 500 说成"你今天没有订单"。失败必须留下自己的状态位，由模板画出错误面。 */
    orders.value = []
    ordersError.value = userErrorCopy(e, '暂时取不到订单数据，请稍后重试')
  }
}

async function loadOverview() {
  loading.value = true
  try {
    await Promise.all([loadOrders(), loadAnalytics()])
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<style scoped>
.page-shell {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 6px 0 18px;
}
.overview-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}
.heading-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.section-kicker {
  margin: 0 0 5px;
  color: var(--app-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.overview-heading h2 {
  margin: 0;
  color: var(--app-text);
  font-size: 24px;
  line-height: 1.25;
}
.page-header-sub {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 14px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.metric-card {
  position: relative;
  overflow: hidden;
  min-height: 138px;
  padding: 18px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
}
.metric-card::after {
  content: '';
  position: absolute;
  right: -18px;
  bottom: -28px;
  width: 92px;
  height: 92px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.055;
}
.metric-card.blue {
  color: var(--app-primary);
}
.metric-card.violet {
  color: var(--app-violet);
}
.metric-card.amber {
  color: var(--app-warning);
}
.metric-card.green {
  color: var(--app-success);
}
.metric-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  margin-bottom: 12px;
  border-radius: 7px;
  background: color-mix(in srgb, currentColor 12%, white);
  font-size: 17px;
}
.metric-card > span,
.metric-card small {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
}
.metric-card strong {
  display: block;
  margin: 5px 0;
  color: var(--app-text);
  font-size: 25px;
  line-height: 1.1;
}
.metric-card small {
  font-size: 11px;
}
.work-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 18px;
}
.panel {
  border-radius: 8px;
  border-color: var(--app-line);
}
.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.card-heading h3 {
  margin: 0;
  color: var(--app-text);
  font-size: 15px;
}
.card-heading span {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}
.funnel-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 2px;
}
.funnel-row {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr) 34px 44px;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.funnel-label {
  color: var(--app-text);
}
.funnel-track {
  height: 7px;
  overflow: hidden;
  border-radius: 7px;
  background: var(--el-fill-color-light);
}
.funnel-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--app-primary);
}
.funnel-row b {
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.funnel-row em {
  color: var(--app-muted);
  font-size: 12px;
  font-style: normal;
  text-align: right;
}
.status-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 4px 2px;
}
.status-row {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr) 28px;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.status-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--app-text);
}
.status-label i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.status-track {
  height: 7px;
  overflow: hidden;
  border-radius: 7px;
  background: var(--el-fill-color-light);
}
.status-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
}
.green {
  background: var(--app-success);
}
.amber {
  background: var(--app-warning);
}
.slate {
  background: var(--app-muted);
}
.status-row b {
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.recent-panel :deep(.el-card__body) {
  padding-top: 8px;
}
@media (max-width: 1050px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .work-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .overview-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .heading-actions {
    width: 100%;
    flex-wrap: wrap;
  }
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  .metric-card {
    min-height: 118px;
  }
}
</style>
