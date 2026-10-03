<template>
  <div v-if="careerData" class="career-content">
    <el-row :gutter="16" class="career-section">
      <el-col :span="8">
        <div class="status-card">
          <div class="status-value data-value">
            {{ careerData.current_status?.career_stage || '-' }}
          </div>
          <div class="status-label">当前阶段</div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="status-card">
          <div class="status-value data-value">
            {{ careerData.current_status?.level || '-' }}
          </div>
          <div class="status-label">当前职级</div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="status-card">
          <div class="status-value data-value" style="color: var(--app-warning)">
            {{ (careerData.skill_gaps || []).length }}
          </div>
          <div class="status-label">技能缺口</div>
        </div>
      </el-col>
    </el-row>

    <div v-if="careerData.skill_radar?.dimensions?.length" class="panel career-section">
      <div class="panel-header"><span>📊 技能雷达</span></div>
      <div class="panel-body">
        <div class="radar-chart">
          <div v-for="dim in careerData.skill_radar.dimensions" :key="dim.name" class="radar-row">
            <span class="radar-label">{{ dim.name }}</span>
            <div class="radar-track">
              <div class="radar-bar current" :style="{ width: dim.current_score + '%' }">
                <span class="radar-val">{{ dim.current_score }}</span>
              </div>
              <div
                class="radar-bar target"
                :style="{
                  width: dim.target_score - dim.current_score + '%',
                  left: dim.current_score + '%',
                }"
              >
                <span class="radar-val-target">→{{ dim.target_score }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="careerData.skill_gaps?.length" class="panel career-section">
      <div class="panel-header">
        <span>⚠️ 技能提升建议（{{ careerData.skill_gaps.length }} 项）</span>
      </div>
      <div class="panel-body">
        <template v-if="hasStructuredSkillGaps">
          <el-collapse>
            <el-collapse-item v-for="(gap, i) in careerData.skill_gaps" :key="i" :name="i">
              <template #title>
                <div class="gap-title">
                  <el-tag :type="levelTagType(gap.priority)" size="small">{{
                    gap.priority
                  }}</el-tag>
                  <span class="gap-skill">{{ gap.skill }}</span>
                  <span class="gap-level">{{ gap.current_level }} → {{ gap.target_level }}</span>
                </div>
              </template>
              <div class="gap-detail">
                <p v-if="gap.importance"><b>为什么重要：</b>{{ gap.importance }}</p>
                <p v-if="gap.acquisition_method"><b>获取途径：</b>{{ gap.acquisition_method }}</p>
                <div v-if="gap.resources?.length" class="gap-resources">
                  <b>推荐资源：</b>
                  <el-tag
                    v-for="r in gap.resources"
                    :key="r.name"
                    size="small"
                    type="info"
                    effect="plain"
                    style="margin: 2px"
                    >{{ r.name }}{{ r.estimated_hours ? ` (${r.estimated_hours}h)` : '' }}</el-tag
                  >
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </template>
        <template v-else
          ><ul>
            <li v-for="(g, i) in careerData.skill_gaps" :key="i">📌 {{ g }}</li>
          </ul></template
        >
      </div>
    </div>

    <div v-if="visualPhases.length" class="panel career-section">
      <div class="panel-header">
        <span
          >🛤️ 成长路线图（{{ careerData.visual_roadmap?.total_duration_months || '-' }}个月）</span
        >
      </div>
      <div class="panel-body">
        <div class="roadmap">
          <div v-for="phase in visualPhases" :key="phase.id" class="roadmap-phase">
            <div class="phase-connector" :style="{ borderColor: phase.color }">
              <div class="phase-dot" :style="{ background: phase.color }">
                {{ phase.order }}
              </div>
            </div>
            <div class="phase-card" :style="{ borderLeftColor: phase.color }">
              <div class="phase-header">
                <span class="phase-name">{{ phase.name }}</span>
                <el-tag size="small" effect="plain">{{ phase.duration_months }}个月</el-tag>
              </div>
              <div class="phase-skills">
                <el-tag
                  v-for="s in phase.skills"
                  :key="s"
                  size="small"
                  type="success"
                  effect="plain"
                  style="margin: 2px"
                  >{{ s }}</el-tag
                >
              </div>
              <div v-if="phase.milestones?.length" class="phase-milestones">
                <div v-for="m in phase.milestones" :key="m.name" class="milestone-item">
                  <span class="ms-icon">{{ milestoneIcon(m.type) }}</span>
                  <span>{{ m.name }}</span>
                </div>
              </div>
              <div v-if="phase.projects?.length" class="phase-projects">
                <div v-for="p in phase.projects" :key="p.name" class="phase-project-item">
                  <el-icon><Folder /></el-icon>
                  <b>{{ p.name }}</b
                  >：<span class="project-desc">{{ p.description }}</span>
                  <el-tag v-for="t in p.tech_stack" :key="t" size="small" style="margin: 1px">{{
                    t
                  }}</el-tag>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="roadmap-dir" v-if="careerData.visual_roadmap?.career_direction">
          🏁 最终方向：<strong>{{ careerData.visual_roadmap.career_direction }}</strong>
        </div>
      </div>
    </div>

    <div v-if="careerData.project_recommendations?.length" class="panel career-section">
      <div class="panel-header"><span>🔨 推荐项目实践</span></div>
      <div class="panel-body">
        <el-row :gutter="16">
          <el-col
            :span="12"
            v-for="proj in careerData.project_recommendations"
            :key="proj.project"
            style="margin-bottom: 16px"
          >
            <div class="panel proj-card">
              <div class="panel-body">
                <div class="proj-header">
                  <h4 class="proj-name">{{ proj.project }}</h4>
                  <el-tag :type="complexityType(proj.complexity)" size="small" effect="dark">{{
                    proj.complexity
                  }}</el-tag>
                </div>
                <p class="proj-reason">{{ proj.reason }}</p>
                <p v-if="proj.description" class="proj-desc">{{ proj.description }}</p>
                <div class="proj-techs">
                  <el-tag
                    v-for="t in proj.tech_stack"
                    :key="t"
                    size="small"
                    type="info"
                    effect="plain"
                    >{{ t }}</el-tag
                  >
                </div>
                <div v-if="proj.learning_outcomes?.length" class="proj-outcomes">
                  <span class="outcome-label">学到的技能：</span>
                  <span v-for="o in proj.learning_outcomes" :key="o" class="outcome-item">{{
                    o
                  }}</span>
                </div>
                <div v-if="proj.estimated_time" class="proj-time">
                  ⏱ 预估：{{ proj.estimated_time }}
                </div>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>
    </div>

    <div v-if="careerData.industry_insight" class="panel career-section">
      <div class="panel-header"><span>📈 行业洞察</span></div>
      <div class="panel-body">
        <el-row :gutter="16">
          <el-col :span="12">
            <h5>当前趋势</h5>
            <ul>
              <li v-for="t in careerData.industry_insight.current_trends || []" :key="t">
                {{ t }}
              </li>
            </ul>
          </el-col>
          <el-col :span="12">
            <h5>热门技能</h5>
            <el-tag
              v-for="s in careerData.industry_insight.demanded_skills || []"
              :key="s"
              type="warning"
              style="margin: 2px"
              >{{ s }}</el-tag
            >
          </el-col>
        </el-row>
        <div v-if="careerData.industry_insight.career_alternatives?.length" class="mt">
          <h5>可考虑的其他方向</h5>
          <el-tag
            v-for="alt in careerData.industry_insight.career_alternatives"
            :key="alt"
            type="info"
            style="margin: 2px"
            >{{ alt }}</el-tag
          >
        </div>
        <div v-if="careerData.industry_insight.salary_range" class="mt salary-ref">
          💰 薪资参考：<strong>{{ careerData.industry_insight.salary_range }}</strong>
        </div>
      </div>
    </div>

    <div class="panel career-section">
      <div class="panel-header"><span>📋 阶段计划</span></div>
      <div class="panel-body">
        <el-row :gutter="16">
          <el-col :span="8">
            <div class="plan-card plan-short">
              <h4>短期计划</h4>
              <div class="plan-tl">
                {{ careerData.short_term_plan?.timeline || '1-3月' }}
              </div>
              <ul>
                <li v-for="g in careerData.short_term_plan?.goals || []" :key="g">
                  {{ g }}
                </li>
              </ul>
              <div v-if="careerData.short_term_plan?.daily_routine" class="plan-routine">
                <b>每日安排：</b>{{ careerData.short_term_plan.daily_routine }}
              </div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="plan-card plan-mid">
              <h4>中期计划</h4>
              <div class="plan-tl">
                {{ careerData.mid_term_plan?.timeline || '3-12月' }}
              </div>
              <ul>
                <li v-for="g in careerData.mid_term_plan?.goals || []" :key="g">
                  {{ g }}
                </li>
              </ul>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="plan-card plan-long">
              <h4>长期计划</h4>
              <div class="plan-tl">
                {{ careerData.long_term_plan?.timeline || '1-3年' }}
              </div>
              <ul>
                <li v-for="g in careerData.long_term_plan?.goals || []" :key="g">
                  {{ g }}
                </li>
              </ul>
              <div v-if="careerData.long_term_plan?.target_companies" class="plan-targets">
                🏢
                <span v-for="c in careerData.long_term_plan.target_companies" :key="c"
                  >{{ c }}
                </span>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>
    </div>

    <div v-if="careerData.recommended_certifications?.length" class="panel career-section">
      <div class="panel-header"><span>🎓 推荐证书</span></div>
      <div class="panel-body">
        <el-table :data="careerData.recommended_certifications" size="small">
          <el-table-column prop="name" label="证书" />
          <el-table-column prop="level" label="难度" width="80" />
          <el-table-column prop="relevance" label="岗位关联度" width="200" />
        </el-table>
      </div>
    </div>

    <el-alert
      v-if="careerData.overall_advice"
      :title="careerData.overall_advice"
      type="success"
      :closable="false"
      show-icon
    />
  </div>
  <el-empty v-else description="暂无职业规划数据" />
</template>

<script setup>
import { Folder } from '@element-plus/icons-vue'

import { complexityType, milestoneIcon } from '@/features/analysis/lib/analysisModel'
import { levelTagType } from '@/utils/statusTone'

/* 职业规划面板：D51 从 SmartAnalysis.vue 搬出来（这一页最大的一个标签页）。
   纯展示：只吃三个值，不发请求、不发事件。后两个之所以是 prop 而不是在这里重算，是因为
   "结构化缺口"的判据住在 lib（`hasStructuredCareerGaps`）、"阶段列表"的取法住在页面的链上，
   面板自己再推一遍就是两份真相。
   样式是**复制**过来的、父页面那 1092 行一行没删：scoped 样式不跨组件，而静态切分看不见动态类名（D44）。
   复制的是页面样式里 "Career content / Radar / Plan cards / Roadmap" 那四段。另有一批类
   （gap-title、proj-card、milestone-item、outcome-item、roadmap-dir、salary-ref…）在全仓**没有任何规则**，
   它们只是 markup 里的钩子，所以既不在复制范围里，也不在页面样式里。 */
defineProps({
  careerData: { type: Object, default: null },
  visualPhases: {
    type: /** @type {import('vue').PropType<import('../lib/analysisModel').RoadmapPhase[]>} */ (
      Array
    ),
    default: () => [],
  },
  hasStructuredSkillGaps: { type: Boolean, default: false },
})
</script>

<style scoped>
/* Career content */
.career-content {
}
.status-card {
  padding: 18px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--el-fill-color-light);
  text-align: center;
}
.status-value {
  font-size: 28px;
  line-height: 1.1;
  margin-bottom: 6px;
}
.status-label {
  font-size: 12px;
  color: var(--app-muted);
}
.career-section {
  margin-bottom: 16px;
}

/* Radar */
.radar-chart {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.radar-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.radar-label {
  width: 80px;
  font-size: 13px;
  font-weight: 500;
  flex-shrink: 0;
}
.radar-track {
  flex: 1;
  height: 10px;
  border-radius: 999px;
  background: var(--el-border-color-light);
  position: relative;
  overflow: hidden;
}
.radar-bar {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: 999px;
  display: flex;
  align-items: center;
}
.radar-bar.current {
  background: var(--app-primary);
  z-index: 1;
}
.radar-bar.target {
  background: rgba(25, 107, 219, 0.2);
}
.radar-val,
.radar-val-target {
  font-size: 10px;
  font-weight: 600;
  padding: 0 6px;
  color: #fff;
  font-family: var(--app-font-mono);
}
.radar-val-target {
  color: var(--app-primary);
}

/* Plan cards */
.plan-card {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  border: 1px solid var(--el-border-color);
}
.plan-short {
  border-left: 3px solid var(--app-primary);
}
.plan-mid {
  border-left: 3px solid var(--app-warning);
}
.plan-long {
  border-left: 3px solid var(--app-violet);
}
.plan-tl {
  font-size: 12px;
  color: var(--app-muted);
  font-family: var(--app-font-mono);
  margin-bottom: 8px;
}

/* Roadmap */
.roadmap {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.roadmap-phase {
  display: flex;
  gap: 14px;
}
.phase-connector {
  position: relative;
  width: 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  border-left: 2px solid;
  padding-bottom: 16px;
}
.phase-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  margin-left: -15px;
}
.phase-card {
  flex: 1;
  padding: 14px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--el-border-color);
  border-left: 3px solid;
  margin-bottom: 12px;
}
.phase-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.phase-name {
  font-weight: 600;
  font-size: 14px;
}
</style>
