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
      <el-input v-model="searchPosition" placeholder="输入岗位关键词，如：前端、Java、产品经理" clearable style="max-width:400px" @keyup.enter="doSearch" />
      <el-input v-model="searchCity" placeholder="城市（可选）" clearable style="max-width:200px" @keyup.enter="doSearch" />
      <el-button type="primary" @click="doSearch">查询</el-button>
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
      <el-icon :size="48" color="var(--app-muted)"><Coin /></el-icon>
      <h3>输入岗位关键词查询薪资数据</h3>
      <p>系统将基于岗位库分析薪资分布和城市对比</p>
    </div>

    <!-- 期望薪资评估 -->
    <div class="panel expectation-panel">
      <div class="panel-header">
        <h3>期望薪资合理性评估</h3>
      </div>
      <div class="panel-body">
        <div class="expect-form">
          <el-input v-model="expectPosition" placeholder="岗位关键词" style="max-width:200px" />
          <el-input-number v-model="expectSalary" :min="1" placeholder="期望月薪(K)" style="max-width:180px" />
          <el-input v-model="expectCity" placeholder="城市（可选）" style="max-width:140px" />
          <el-button type="primary" @click="checkExpectation">评估</el-button>
        </div>
        <div v-if="expectResult" class="expect-result">
          <el-alert
            :title="expectResult.level === 'reasonable' ? '薪资期望合理' : expectResult.level === 'high' ? '期望偏高' : '期望偏低'"
            :type="expectResult.level === 'reasonable' ? 'success' : expectResult.level === 'high' ? 'warning' : 'info'"
            :description="expectResult.message || ''"
            show-icon
            :closable="false"
          />
          <div v-if="expectResult.market" class="expect-details">
            <span>市场中位数：<strong>{{ formatK(expectResult.market.median) }}</strong></span>
            <span>市场范围：<strong>{{ formatK(expectResult.market.p25) }} - {{ formatK(expectResult.market.p75) }}</strong></span>
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

const maxDist = computed(() => {
  if (!overview.value?.distribution) return 1
  return Math.max(1, ...overview.value.distribution.map(d => d.count))
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
  } catch {} finally {
    loading.value = false
  }
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
  } catch {}
}
</script>

<style scoped>
.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
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
  text-align: center;
  padding: 60px 0;
}

.empty-state h3 {
  margin: 16px 0 8px;
  font-size: 18px;
}

.empty-state p {
  color: var(--app-muted);
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
  .stats-row { flex-wrap: wrap; }
  .stat-card { flex: 1 1 calc(50% - 6px); }
  .search-bar { flex-direction: column; }
  .expect-form { flex-direction: column; }
}
</style>
