<template>
  <div v-if="loading" class="inline-loading">
    <el-icon class="is-loading" size="22"><Loading /></el-icon>
    <p>正在生成匹配度解释...</p>
  </div>
  <template v-else-if="explainResult">
    <div class="explain-hero">
      <div class="explain-score-ring">
        <el-progress
          type="circle"
          :percentage="explainResult.overall_score"
          :stroke-width="8"
          :size="120"
          :color="scoreToneColor(explainResult.overall_score)"
        >
          <template #default>
            <div class="big-score data-value">{{ explainResult.overall_score }}</div>
            <div class="score-lbl">总分</div>
          </template>
        </el-progress>
      </div>
      <div class="explain-score-info">
        <el-tag :type="explainRecTag" size="large" effect="dark" class="mb">
          {{ localizedRecommendation }}
        </el-tag>
        <p class="explain-reason">{{ localizedOverallReason }}</p>
        <p class="explain-weights">
          权重: skill{{ explainResult.weights_used.skill }} / project{{
            explainResult.weights_used.project
          }}
          / exp{{ explainResult.weights_used.experience }} / edu{{
            explainResult.weights_used.education
          }}
          / keyword{{ explainResult.weights_used.keyword }} / bonus{{
            explainResult.weights_used.bonus
          }}
        </p>
      </div>
    </div>

    <h4 class="mt">六维评分详情</h4>
    <div v-for="dim in explainResult.dimensions" :key="dim.name" class="dim-block">
      <div class="dim-header">
        <span class="dim-name">{{ dim.name }}</span>
        <span class="dim-w">权重 {{ (dim.weight * 100).toFixed(0) }}%</span>
        <span class="dim-score data-value" :style="{ color: scoreToneTextColor(dim.score) }">{{
          dim.score.toFixed(1)
        }}</span>
      </div>
      <div class="dim-bar">
        <div
          class="dim-fill"
          :style="{ width: `${dim.score}%`, background: scoreToneColor(dim.score) }"
        />
      </div>
      <p class="dim-reason">{{ localizeSentence(dim.reason) }}</p>
      <div v-if="dim.details?.length" class="dim-details">
        <el-tag
          v-for="detail in dim.details"
          :key="detail"
          size="small"
          type="info"
          effect="plain"
          style="margin: 1px"
          >{{ localizeSentence(detail) }}</el-tag
        >
      </div>
    </div>

    <el-row :gutter="16" class="mt">
      <el-col :span="12">
        <h4>已匹配技能</h4>
        <el-tag v-for="s in matchedSkills" :key="s" type="success" style="margin: 2px">{{
          s
        }}</el-tag>
        <el-empty v-if="!matchedSkills.length" description="暂无" :image-size="40" />
      </el-col>
      <el-col :span="12">
        <h4>缺失技能</h4>
        <el-tag v-for="s in missingSkills" :key="s" type="danger" style="margin: 2px">{{
          s
        }}</el-tag>
        <el-empty v-if="!missingSkills.length" description="暂无" :image-size="40" />
      </el-col>
    </el-row>
  </template>
  <el-empty v-else description="完成智能分析后可在这里查看匹配度解释" />
</template>

<script setup>
import { computed } from 'vue'

import { Loading } from '@element-plus/icons-vue'

import { explainRecommendationTag, mergeMissingSkills } from '@/features/analysis/lib/analysisModel'
import { localizeRecommendationText, localizeSentence } from '@/utils/analysisLocalization'
/* 填色与描边（进度条、条形）吃 tone 本体——那是非文字，门槛 3:1；分数当文字读的那一处吃
   抬过一档的文字版，否则蓝档压在深色面板上是 3.06。 */
import { scoreToneColor, scoreToneTextColor } from '@/utils/scoreTone'

/* 匹配度解释面板：D52 从 SmartAnalysis.vue 搬出来。
   显示形状（推荐标签、两列缺口合并、句子本地化）在面板里自己推，因为它们只服务这一块，而
   规则本身住在 lib / utils 里，没有第二份；`explainResult` 这个值仍由页面的链持有，面板不改它。
   样式是从页面**复制**的（"Explain tab / Dimension bars / Loading state" 三段），页面那 1092 行没删。
   `weights_used` 直接读嵌套字段这件事是原样搬过来的：后端 `schemas/analysis.py:23` 把它声明成
   必填 dict，六个键都在，所以这一路在生产里到不了"字段缺失"。 */
const props = defineProps({
  loading: { type: Boolean, default: false },
  explainResult: { type: Object, default: null },
})

const localizedRecommendation = computed(() =>
  localizeRecommendationText(props.explainResult?.recommendation || '')
)
const explainRecTag = computed(() => explainRecommendationTag(localizedRecommendation.value))
const localizedOverallReason = computed(() =>
  localizeSentence(props.explainResult?.overall_reason || '')
)
const matchedSkills = computed(() => props.explainResult?.skill_match?.matched || [])
const missingSkills = computed(() => mergeMissingSkills(props.explainResult?.skill_match))
</script>

<style scoped>
/* Explain tab */
.explain-hero {
  display: flex;
  gap: 20px;
  align-items: center;
  padding: 20px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--el-fill-color-light);
  margin-bottom: 16px;
}

.big-score {
  font-size: 28px;
}
.score-lbl {
  font-size: 12px;
  color: var(--app-muted);
}

.explain-score-info {
  flex: 1;
}
.explain-reason {
  margin: 8px 0 0;
  color: var(--app-muted);
  line-height: 1.7;
}
.explain-weights {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  font-family: var(--app-font-mono);
}

/* Dimension bars */
.dim-block {
  margin-bottom: 16px;
  padding: 14px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--el-border-color);
}

.dim-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.dim-name {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}
.dim-w {
  color: var(--app-muted);
  font-size: 12px;
}
.dim-score {
  font-size: 18px;
  font-weight: 700;
}

.dim-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--el-border-color-light);
  overflow: hidden;
}

.dim-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease;
}

.dim-reason {
  margin: 6px 0 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
}
.dim-details {
  margin-top: 6px;
}

/* Loading state */
.inline-loading {
  text-align: center;
  padding: 40px 0;
  color: var(--app-muted);
}
.inline-loading p {
  margin: 8px 0 0;
}
</style>
