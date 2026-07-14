<template>
  <div class="em-page">
    <el-card class="em-card" shadow="never">
      <template #header><span>📊 匹配度深度解释器</span></template>

      <el-form :inline="true" :model="form">
        <el-form-item label="简历 ID">
          <el-input-number v-model="form.resume_id" :min="1" />
        </el-form-item>
        <el-form-item label="JD ID">
          <el-input-number v-model="form.jd_id" :min="1" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="doExplain">
            <el-icon><DataAnalysis /></el-icon> 解释匹配度
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div v-if="loading" class="loading-hint">
      <el-icon class="is-loading" size="24"><Loading /></el-icon>
      <p>规则计算 6 维分数 → LLM 生成解释...</p>
    </div>

    <template v-if="result && !loading">
      <!-- 总分 -->
      <el-card class="score-card" shadow="never">
        <div class="score-hero">
          <div class="score-ring">
            <el-progress
              type="circle"
              :percentage="result.overall_score"
              :stroke-width="8"
              :size="140"
              :color="scoreColor(result.overall_score)"
            >
              <template #default>
                <div class="big-score">{{ result.overall_score }}</div>
                <div class="score-lbl">总分</div>
              </template>
            </el-progress>
          </div>
          <div class="score-info">
            <el-tag :type="recTag" size="large" effect="dark">{{ result.recommendation }}</el-tag>
            <p class="overall-reason">{{ result.overall_reason }}</p>
            <p class="weight-info">
              权重配置: skill{{ result.weights_used.skill }} / project{{
                result.weights_used.project
              }}
              / exp{{ result.weights_used.experience }} / edu{{ result.weights_used.education }} /
              keyword{{ result.weights_used.keyword }} / bonus{{ result.weights_used.bonus }}
            </p>
          </div>
        </div>
      </el-card>

      <!-- 维度分 -->
      <el-card shadow="never">
        <template #header><span>🎯 六维评分详情</span></template>
        <div v-for="dim in result.dimensions" :key="dim.name" class="dim-block">
          <div class="dim-header">
            <span class="dim-name">{{ dim.name }}</span>
            <span class="dim-w">权重 {{ (dim.weight * 100).toFixed(0) }}%</span>
            <span class="dim-score" :style="{ color: scoreColor(dim.score) }">{{
              dim.score.toFixed(1)
            }}</span>
          </div>
          <div class="dim-bar">
            <div
              class="dim-fill"
              :style="{ width: dim.score + '%', background: scoreColor(dim.score) }"
            />
          </div>
          <p class="dim-reason">{{ dim.reason }}</p>
          <div v-if="dim.details?.length" class="dim-details">
            <el-tag
              v-for="d in dim.details"
              :key="d"
              size="small"
              type="info"
              effect="plain"
              style="margin: 1px"
              >{{ d }}</el-tag
            >
          </div>
        </div>
      </el-card>

      <!-- 技能命中 -->
      <el-card v-if="result.skill_match" shadow="never">
        <template #header><span>🔧 技能命中详情</span></template>
        <el-row :gutter="16">
          <el-col :span="12">
            <h5>✅ 已匹配 ({{ result.skill_match.matched?.length || 0 }})</h5>
            <el-tag
              v-for="s in result.skill_match.matched || []"
              :key="s"
              type="success"
              style="margin: 2px"
              >{{ s }}</el-tag
            >
            <el-empty
              v-if="!result.skill_match.matched?.length"
              description="无"
              :image-size="40"
            />
          </el-col>
          <el-col :span="12">
            <h5>❌ 缺失核心 ({{ result.skill_match.missing_required?.length || 0 }})</h5>
            <el-tag
              v-for="s in result.skill_match.missing_required || []"
              :key="s"
              type="danger"
              style="margin: 2px"
              >{{ s }}</el-tag
            >
            <el-empty
              v-if="!result.skill_match.missing_required?.length"
              description="无"
              :image-size="40"
            />
          </el-col>
        </el-row>
      </el-card>

      <!-- 风险 + 建议 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never">
            <template #header><span style="color: #e6a23c">⚠️ 风险点</span></template>
            <ul v-if="result.risk_points?.length">
              <li v-for="r in result.risk_points" :key="r">{{ r }}</li>
            </ul>
            <el-empty v-else description="无明显风险" :image-size="40" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header><span style="color: #409eff">💡 改进建议</span></template>
            <ul v-if="result.optimization_suggestions?.length">
              <li v-for="s in result.optimization_suggestions" :key="s">{{ s }}</li>
            </ul>
            <el-empty v-else description="暂无建议" :image-size="40" />
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from '@/plugins/element-services'
import { explainMatch } from '@/api/analysis'
import { DataAnalysis, Loading } from '@element-plus/icons-vue'

const form = reactive({ resume_id: null, jd_id: null })
const loading = ref(false)
const result = ref(null)

async function doExplain() {
  if (!form.resume_id || !form.jd_id) {
    ElMessage.warning('请填写简历 ID 和 JD ID')
    return
  }
  loading.value = true
  result.value = null
  try {
    const data = await explainMatch({ resume_id: form.resume_id, jd_id: form.jd_id })
    result.value = data
  } catch (e) {
    ElMessage.error(e.message || '解释失败')
  } finally {
    loading.value = false
  }
}

function scoreColor(s) {
  if (s >= 80) return '#67C23A'
  if (s >= 60) return '#409EFF'
  if (s >= 40) return '#E6A23C'
  return '#F56C6C'
}

const recTag = computed(
  () =>
    ({
      强烈推荐: 'success',
      可以投递: 'primary',
      谨慎投递: 'warning',
      不建议投递: 'danger',
    })[result.value?.recommendation] || 'info'
)
</script>

<style scoped>
.em-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.em-card {
  border-radius: 12px;
}
.loading-hint {
  text-align: center;
  padding: 40px;
  color: #909399;
}
.score-card {
  border-radius: 12px;
}
.score-hero {
  display: flex;
  align-items: center;
  gap: 32px;
}
.big-score {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
}
.score-lbl {
  font-size: 12px;
  color: #909399;
}
.score-info {
  flex: 1;
}
.overall-reason {
  font-size: 14px;
  color: #606266;
  margin: 8px 0;
}
.weight-info {
  font-size: 11px;
  color: #909399;
}
.dim-block {
  margin-bottom: 16px;
}
.dim-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dim-name {
  font-weight: 600;
  width: 80px;
}
.dim-w {
  font-size: 11px;
  color: #909399;
}
.dim-score {
  font-size: 18px;
  font-weight: 700;
}
.dim-bar {
  height: 10px;
  background: #f0f2f5;
  border-radius: 5px;
  margin: 4px 0;
  overflow: hidden;
}
.dim-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.6s;
}
.dim-reason {
  font-size: 12px;
  color: #606266;
}
.dim-details {
  margin-top: 2px;
}
h5 {
  margin: 8px 0 4px;
}
ul {
  padding-left: 18px;
}
li {
  margin: 4px 0;
  font-size: 13px;
  color: #606266;
}
</style>
