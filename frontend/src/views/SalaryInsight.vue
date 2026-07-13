<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>薪资洞察</h2>
        <div class="page-header-sub">基于岗位库数据分析薪资分布，辅助Offer决策</div>
      </div>
    </div>

    <!-- 搜索栏 -->
    <div class="search-bar">
      <el-input
        v-model="searchPosition"
        placeholder="输入岗位关键词，如：前端、Java、产品经理"
        clearable
        style="max-width: 400px"
        @keyup.enter="doSearch"
      />
      <el-input
        v-model="searchCity"
        placeholder="城市（可选）"
        clearable
        style="max-width: 200px"
        @keyup.enter="doSearch"
      />
      <el-button type="primary" @click="doSearch">查询</el-button>
    </div>

    <div class="quick-searches">
      <span>常用岗位</span>
      <button
        v-for="item in quickPositions"
        :key="item"
        type="button"
        @click="applyQuickSearch(item)"
      >
        {{ item }}
      </button>
      <span class="quick-note">选择岗位后可按城市细化结果</span>
    </div>

    <!-- 薪资总览 -->
    <div v-if="overview" class="overview-section">
      <div class="stats-row">
        <div class="stat-card">
          <span class="stat-label">样本数</span>
          <strong class="data-value">{{ overview.sample_count || 0 }}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">薪资中位数</span>
          <strong class="data-value">{{ formatK(overview.median) }}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">P25</span>
          <strong class="data-value">{{ formatK(overview.p25) }}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">P75</span>
          <strong class="data-value">{{ formatK(overview.p75) }}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">平均</span>
          <strong class="data-value">{{ formatK(overview.avg) }}</strong>
        </div>
      </div>

      <!-- 薪资分布 -->
      <div v-if="overview.distribution?.length" class="panel">
        <div class="panel-header">
          <h3>薪资分布</h3>
        </div>
        <div class="panel-body">
          <div class="dist-chart">
            <div v-for="(bin, idx) in overview.distribution" :key="idx" class="dist-bar-col">
              <div class="dist-bar" :style="{ height: distHeight(bin.count) }" />
              <span class="dist-count">{{ bin.count }}</span>
              <span class="dist-label">{{ bin.range }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 城市对比 -->
      <div v-if="overview.city_breakdown?.length" class="panel">
        <div class="panel-header">
          <h3>城市薪资对比</h3>
        </div>
        <div class="panel-body">
          <el-table :data="overview.city_breakdown" stripe>
            <el-table-column prop="city" label="城市" width="120" />
            <el-table-column prop="sample_count" label="样本数" width="100" />
            <el-table-column prop="median" label="中位数(K)" width="120">
              <template #default="{ row }">{{ formatK(row.median) }}</template>
            </el-table-column>
            <el-table-column prop="p25" label="P25(K)" width="100">
              <template #default="{ row }">{{ formatK(row.p25) }}</template>
            </el-table-column>
            <el-table-column prop="p75" label="P75(K)" width="100">
              <template #default="{ row }">{{ formatK(row.p75) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!loading" class="empty-state">
      <div class="empty-layout">
        <div class="empty-copy">
          <el-icon :size="42" color="var(--app-primary)"><Coin /></el-icon>
          <h3>先定位你的市场薪资区间</h3>
          <p>输入岗位和城市后，将看到样本数量、薪资分布、分位区间与城市对比。</p>
        </div>
        <div class="insight-checklist">
          <div>
            <span class="check-icon blue">01</span>
            <p><strong>看中位数</strong><small>确认市场的常见薪资水平</small></p>
          </div>
          <div>
            <span class="check-icon violet">02</span>
            <p><strong>看 P25 - P75</strong><small>为谈薪预留合理区间</small></p>
          </div>
          <div>
            <span class="check-icon amber">03</span>
            <p><strong>评估期望薪资</strong><small>将个人期望和市场数据对照</small></p>
          </div>
        </div>
      </div>
    </div>

    <!-- 期望薪资评估 -->
    <div class="panel expectation-panel">
      <div class="panel-header">
        <h3>期望薪资合理性评估</h3>
      </div>
      <div class="panel-body">
        <div class="expect-form">
          <el-input v-model="expectPosition" placeholder="岗位关键词" style="max-width: 200px" />
          <el-input-number
            v-model="expectSalary"
            :min="1"
            placeholder="期望月薪(K)"
            style="max-width: 180px"
          />
          <el-input v-model="expectCity" placeholder="城市（可选）" style="max-width: 140px" />
          <el-button type="primary" @click="checkExpectation">评估</el-button>
        </div>
        <div v-if="expectResult" class="expect-result">
          <el-alert
            :title="
              expectResult.level === 'reasonable'
                ? '薪资期望合理'
                : expectResult.level === 'high'
                  ? '期望偏高'
                  : '期望偏低'
            "
            :type="
              expectResult.level === 'reasonable'
                ? 'success'
                : expectResult.level === 'high'
                  ? 'warning'
                  : 'info'
            "
            :description="expectResult.message || ''"
            show-icon
            :closable="false"
          />
          <div v-if="expectResult.market" class="expect-details">
            <span
              >市场中位数：<strong>{{ formatK(expectResult.market.median) }}</strong></span
            >
            <span
              >市场范围：<strong
                >{{ formatK(expectResult.market.p25) }} -
                {{ formatK(expectResult.market.p75) }}</strong
              ></span
            >
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Coin } from '@element-plus/icons-vue'
import { getSalaryOverview, checkSalaryExpectation } from '@/api/salary'

const searchPosition = ref('')
const searchCity = ref('')
const loading = ref(false)
const overview = ref(null)

const expectPosition = ref('')
const expectSalary = ref(null)
const expectCity = ref('')
const expectResult = ref(null)
const quickPositions = ['前端开发', 'Java 开发', '产品经理', '数据分析师', '算法工程师']

const maxDist = computed(() => {
  if (!overview.value?.distribution) return 1
  return Math.max(1, ...overview.value.distribution.map((d) => d.count))
})

function formatK(val) {
  if (val == null) return '--'
  return Math.round(val) + 'K'
}

function distHeight(count) {
  return Math.max(4, (count / maxDist.value) * 100) + '%'
}

async function doSearch() {
  if (!searchPosition.value.trim()) return
  loading.value = true
  overview.value = null
  try {
    const data = await getSalaryOverview({ position: searchPosition.value, city: searchCity.value })
    overview.value = data
  } catch {
    // 请求层已反馈错误，保留上一次查询结果。
  } finally {
    loading.value = false
  }
}

function applyQuickSearch(position) {
  searchPosition.value = position
  expectPosition.value = position
  doSearch()
}

async function checkExpectation() {
  if (!expectPosition.value.trim() || !expectSalary.value) return
  try {
    const data = await checkSalaryExpectation({
      position: expectPosition.value,
      salary: expectSalary.value,
      city: expectCity.value,
    })
    expectResult.value = data
  } catch {
    // 请求层已反馈错误，保留上一次评估结果。
  }
}
</script>

<style scoped>
.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.quick-searches {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: -8px 0 20px;
  color: var(--app-muted);
  font-size: 12px;
}
.quick-searches > span:first-child {
  margin-right: 2px;
}
.quick-searches button {
  padding: 4px 9px;
  border: 1px solid var(--app-line);
  border-radius: 6px;
  background: #fff;
  color: var(--app-text);
  cursor: pointer;
  font-size: 12px;
}
.quick-searches button:hover {
  border-color: var(--app-primary);
  color: var(--app-primary);
}
.quick-note {
  margin-left: auto;
  color: var(--app-muted);
}

.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  flex: 1;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--app-line);
  background: #fff;
  text-align: center;
}

.stat-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
  margin-bottom: 6px;
}

.stat-card strong {
  font-size: 20px;
}

.panel + .panel {
  margin-top: 16px;
}

.empty-state {
  padding: 10px 0 20px;
}

.empty-layout {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(300px, 1.1fr);
  overflow: hidden;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: #fff;
  box-shadow: var(--app-shadow-soft);
  text-align: left;
}
.empty-copy {
  padding: 34px;
  background: var(--app-primary-light);
}
.empty-copy h3 {
  margin: 14px 0 7px;
  color: var(--app-text);
  font-size: 20px;
}
.empty-copy p {
  max-width: 340px;
  margin: 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.75;
}
.insight-checklist {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 20px 28px;
}
.insight-checklist > div {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.insight-checklist > div:last-child {
  border-bottom: 0;
}
.check-icon {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
}
.check-icon.blue {
  background: var(--app-primary-light);
  color: var(--app-primary);
}
.check-icon.violet {
  background: var(--app-violet-light);
  color: var(--app-violet);
}
.check-icon.amber {
  background: #fff4d8;
  color: #996000;
}
.insight-checklist p {
  margin: 0;
}
.insight-checklist strong,
.insight-checklist small {
  display: block;
}
.insight-checklist strong {
  color: var(--app-text);
  font-size: 13px;
}
.insight-checklist small {
  margin-top: 2px;
  color: var(--app-muted);
  font-size: 12px;
}

/* Distribution chart */
.dist-chart {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 160px;
}

.dist-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  position: relative;
}

.dist-bar {
  width: 100%;
  max-width: 48px;
  border-radius: 6px 6px 0 0;
  background: linear-gradient(180deg, var(--app-primary) 0%, #7db0ee 100%);
  transition: height 0.4s ease;
}

.dist-count {
  position: absolute;
  top: -18px;
  font-size: 11px;
  font-weight: 600;
}

.dist-label {
  margin-top: 6px;
  font-size: 10px;
  color: var(--app-muted);
  white-space: nowrap;
}

/* Expectation */
.expectation-panel {
  margin-top: 20px;
}

.expect-form {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.expect-result {
  margin-top: 12px;
}

.expect-details {
  display: flex;
  gap: 20px;
  margin-top: 12px;
  font-size: 14px;
}

.expect-details strong {
  color: var(--app-primary);
}

@media (max-width: 768px) {
  .stats-row {
    flex-wrap: wrap;
  }
  .stat-card {
    flex: 1 1 calc(50% - 6px);
  }
  .search-bar {
    flex-direction: column;
  }
  .expect-form {
    flex-direction: column;
  }
  .quick-note {
    width: 100%;
    margin-left: 0;
  }
  .empty-layout {
    grid-template-columns: 1fr;
  }
  .empty-copy {
    padding: 26px 22px;
  }
  .insight-checklist {
    padding: 14px 22px;
  }
}
</style>
