<template>
  <div class="smart-page">
    <!-- Hero -->
    <section class="analysis-hero">
      <div class="hero-title-area">
        <div class="hero-title-main">
          <div class="hero-badge">
            <span class="badge-dot" />
            Agentic RAG
          </div>
          <h1>智能分析</h1>
          <p>把简历、岗位 JD、知识召回与分析结论整合成一个更完整的决策工作台。</p>
          <div class="hero-tags">
            <span>多智能体协作</span>
            <span>匹配分析</span>
            <span>引用溯源</span>
          </div>
        </div>
        <!-- Decorative pipeline node -->
        <div class="hero-node" aria-hidden="true">
          <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
            <circle cx="40" cy="40" r="38" stroke="var(--app-primary)" stroke-width="1" opacity="0.15" />
            <circle cx="40" cy="40" r="28" stroke="var(--app-primary)" stroke-width="1" opacity="0.2" />
            <circle cx="40" cy="40" r="8" fill="var(--app-primary)" opacity="0.3" />
            <path d="M4 40 Q 20 16 40 12 Q 60 8 76 40" stroke="var(--app-primary)" stroke-width="1" opacity="0.12" fill="none" stroke-dasharray="3 3" />
            <path d="M4 40 Q 20 64 40 68 Q 60 72 76 40" stroke="var(--app-primary)" stroke-width="1" opacity="0.12" fill="none" stroke-dasharray="3 3" />
          </svg>
        </div>
      </div>

      <div class="hero-metrics">
        <div class="hm-item" :class="{ ready: !!resumeInfo }">
          <span class="hm-label">简历状态</span>
          <strong class="data-value">{{ resumeInfo ? '已上传' : '待上传' }}</strong>
          <small>{{ resumeInfo?.file_name || '等待候选人简历' }}</small>
        </div>
        <div class="hm-item" :class="{ ready: !!(jdInfo || jdForm.title || jdForm.raw_text) }">
          <span class="hm-label">JD 状态</span>
          <strong class="data-value">{{ jdInfo || jdForm.title || jdForm.raw_text ? '已就绪' : '待填写' }}</strong>
          <small>{{ jdInfo?.title || jdForm.title || '等待目标岗位 JD' }}</small>
        </div>
        <div class="hm-item" :class="{ ready: loading || !!result }">
          <span class="hm-label">分析流程</span>
          <strong class="data-value">{{ analysisFlowLabel }}</strong>
          <small>{{ analysisFlowHint }}</small>
        </div>
        <div class="hm-item" :class="{ ready: !!result }">
          <span class="hm-label">结果总览</span>
          <strong class="data-value">{{ result ? result.match_score : '--' }}</strong>
          <small>{{ analysisConfidence?.label || '等待生成匹配报告' }}</small>
        </div>
      </div>
    </section>

    <!-- Input Card -->
    <section class="card-section">
      <div class="card-head">
        <div class="card-head-left">
          <el-icon><MagicStick /></el-icon>
          <span>一键智能分析</span>
        </div>
        <el-tag size="small">Agentic RAG + 多智能体协作</el-tag>
      </div>

      <div class="card-body">
        <div class="input-split">
          <!-- Resume Upload -->
          <div class="input-col">
            <div class="input-col-label">上传简历</div>
            <el-upload
              drag
              action="#"
              :http-request="customUploadResume"
              :show-file-list="false"
              :before-upload="beforeUploadResume"
              accept=".pdf,.docx,.doc"
              :disabled="loading"
              class="resume-upload"
            >
              <div v-if="!resumeInfo" class="upload-blank">
                <el-icon class="upload-icon"><UploadFilled /></el-icon>
                <div class="upload-title">拖拽简历到此处，或<em>点击上传</em></div>
                <div class="upload-hint">支持 PDF / DOCX，不超过 10MB</div>
              </div>
              <div v-else class="upload-ready">
                <el-icon class="done-icon"><SuccessFilled /></el-icon>
                <div class="upload-ready-copy">
                  <strong>{{ resumeInfo.file_name }}</strong>
                  <span>ID: {{ resumeInfo.id }}</span>
                </div>
                <el-button text type="danger" size="small" @click.stop="clearResume">移除</el-button>
              </div>
            </el-upload>
          </div>

          <!-- JD Input -->
          <div class="input-col">
            <div class="input-col-label">输入岗位 JD</div>
            <el-form :model="jdForm" label-position="top" :disabled="loading" class="jd-form">
              <el-form-item label="岗位名称" required>
                <el-input v-model="jdForm.title" placeholder="如：Python 后端开发工程师" />
              </el-form-item>
              <el-form-item label="公司（可选）">
                <el-input v-model="jdForm.company" placeholder="如：示例科技" />
              </el-form-item>
              <el-form-item label="JD 内容" required>
                <el-input v-model="jdForm.raw_text" type="textarea" :rows="4" placeholder="粘贴岗位 JD 完整内容…" />
              </el-form-item>
            </el-form>
            <div v-if="jdInfo" class="jd-ready">
              <el-tag size="small" type="success">JD 已创建，ID: {{ jdInfo.id }}</el-tag>
              <el-button text type="danger" size="small" @click="clearJD">移除</el-button>
            </div>
          </div>
        </div>

        <!-- Action -->
        <div class="action-bar">
          <div class="action-copy">
            <strong>输出包括</strong>
            <span>匹配度、差距、职业方向、面试题与引用来源</span>
          </div>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            :disabled="!canAnalyze"
            @click="onStartAnalysis"
          >
            <el-icon><Promotion /></el-icon>
            {{ loading ? '智能分析中…' : '一键智能分析' }}
          </el-button>
        </div>
      </div>
    </section>

    <!-- Agent Pipeline Progress -->
    <section v-if="loading && agentSteps.length" class="card-section">
      <div class="card-head">
        <div class="card-head-left">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>Agent Pipeline</span>
        </div>
        <el-tag type="warning" size="small">{{ completedStepCount }} / {{ agentSteps.length }} 步</el-tag>
      </div>

      <div class="card-body">
        <!-- Progress snapshot -->
        <div class="pipeline-status">
          <div class="ps-item">
            <span>当前阶段</span>
            <strong class="data-value">{{ currentStepName }}</strong>
          </div>
          <div class="ps-item">
            <span>已完成</span>
            <strong class="data-value">{{ completedStepCount }}</strong>
          </div>
          <div class="ps-item">
            <span>总步骤</span>
            <strong class="data-value">{{ agentSteps.length }}</strong>
          </div>
        </div>

        <!-- Pipeline visual timeline -->
        <div class="pipeline-timeline">
          <div
            v-for="(s, i) in agentSteps"
            :key="i"
            class="pipeline-node"
            :class="`node-${s.status}`"
          >
            <div class="pipeline-connector" />
            <div class="pipeline-dot">
              <el-icon v-if="s.status === 'completed'" :size="14"><SuccessFilled /></el-icon>
              <el-icon v-else-if="s.status === 'failed'" :size="14"><CircleCloseFilled /></el-icon>
              <el-icon v-else-if="s.status === 'running'" :size="14" class="is-loading"><Loading /></el-icon>
              <span v-else class="dot-empty" />
            </div>
            <div class="pipeline-content">
              <div class="pl-head">
                <strong>{{ stepLabel(s.step_name) }}</strong>
                <span class="pl-meta">
                  {{ statusText(s.status) }}
                  <span v-if="s.duration_ms"> · {{ s.duration_ms }}ms</span>
                </span>
              </div>
              <div v-if="s.status === 'completed' && s.output_data" class="pl-preview">
                <span v-if="s.step_name === 'intent_recognition'">
                  意图: <b>{{ s.output_data.intent || '-' }}</b>
                </span>
                <span v-else-if="s.step_name === 'match_analysis'">
                  匹配度: <b>{{ s.output_data.match_score ?? '-' }}</b>
                </span>
                <span v-else-if="s.step_name === 'resume_optimization'">
                  优化建议: <b>{{ (s.output_data.sections || []).length }} 项</b>
                </span>
                <span v-else-if="s.step_name === 'interview_questions'">
                  面试题: <b>{{ s.output_data.total_questions ?? '-' }} 题</b>
                </span>
                <span v-else-if="s.step_name === 'summary_report'">汇总完成</span>
              </div>
              <el-tag v-if="s.error_msg" size="small" type="danger">{{ s.error_msg }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Terminal state -->
    <section v-if="!loading && !result && agentSteps.length" class="card-section">
      <div class="card-head">
        <div class="card-head-left">
          <el-icon><InfoFilled /></el-icon>
          <span>任务提示</span>
        </div>
        <el-tag :type="taskOutcomeTag" size="small">{{ analysisFlowLabel }}</el-tag>
      </div>
      <div class="card-body">
        <el-alert
          :type="taskOutcomeTag === 'danger' ? 'error' : taskOutcomeTag"
          :closable="false"
          show-icon
          :title="terminalHint"
        />
      </div>
    </section>

    <!-- Results -->
    <div v-if="result" class="results-section">
      <!-- Score -->
      <section class="card-section score-section">
        <div class="card-body score-body">
          <div class="score-center">
            <el-progress
              type="dashboard"
              :percentage="result.match_score"
              :color="scoreColor(result.match_score)"
              :width="140"
              :stroke-width="10"
            >
              <template #default="{ percentage }">
                <div class="score-value data-value">{{ percentage }}</div>
                <div class="score-label">匹配度</div>
              </template>
            </el-progress>
            <div class="score-meta">
              <div class="score-rec">{{ localizedMatchRecommendation }}</div>
              <div class="score-sum">{{ localizedMatchSummary }}</div>
              <div class="score-chips">
                <span class="chip chip-match">已匹配 {{ matchedSkills.length }} 项</span>
                <span class="chip chip-gap">待补足 {{ missingSkills.length }} 项</span>
                <span class="chip chip-ref">
                  置信度 {{ analysisConfidence ? (analysisConfidence.score ?? 0) : '--' }}
                </span>
              </div>
            </div>
          </div>

          <el-descriptions :column="4" border size="small" class="dim-table">
            <el-descriptions-item label="技能">
              <span class="data-value dim-val">{{ dimensionScore('skills') }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="经验">
              <span class="data-value dim-val">{{ dimensionScore('experience') }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="学历">
              <span class="data-value dim-val">{{ dimensionScore('education') }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="行业">
              <span class="data-value dim-val">{{ dimensionScore('industry') }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <!-- RAG Confidence -->
          <div v-if="analysisConfidence" class="rag-confidence">
            <div class="rag-confidence-main">
              <div class="rag-badge" :class="`badge-${analysisConfidence.level || 'low'}`">
                {{ analysisConfidence.score ?? 0 }}
              </div>
              <div class="rag-confidence-copy">
                <div class="rag-confidence-title">
                  分析可信度
                  <el-tag size="small" :type="confidenceTagType(analysisConfidence.level)">
                    {{ analysisConfidence.label || '-' }}
                  </el-tag>
                </div>
                <div class="rag-confidence-summary">{{ analysisConfidence.summary || '暂无可信度说明' }}</div>
              </div>
            </div>
            <div class="rag-confidence-metrics">
              <div class="rag-metric">
                <span>召回片段</span>
                <strong class="data-value">{{ analysisConfidence.signals?.total_chunks ?? 0 }}</strong>
              </div>
              <div class="rag-metric">
                <span>覆盖文档</span>
                <strong class="data-value">{{ analysisConfidence.signals?.unique_docs ?? 0 }}</strong>
              </div>
              <div class="rag-metric">
                <span>平均相关度</span>
                <strong class="data-value">{{ analysisConfidence.signals?.avg_similarity ?? 0 }}</strong>
              </div>
              <div class="rag-metric">
                <span>命中能力模型</span>
                <strong class="data-value">{{ analysisConfidence.signals?.has_skill_model ? '是' : '否' }}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Tabs -->
      <section class="card-section">
        <div class="card-body tab-body">
          <el-tabs v-model="reportTab" @tab-click="onTabClick">
            <!-- 技能匹配 -->
            <el-tab-pane label="技能匹配" name="skills">
              <el-row :gutter="16">
                <el-col :span="12">
                  <div class="skill-group">
                    <h4>已匹配技能</h4>
                    <el-tag v-for="s in matchedSkills" :key="s" type="success" style="margin:2px;">{{ s }}</el-tag>
                    <el-empty v-if="!matchedSkills.length" description="暂无" :image-size="40" />
                  </div>
                </el-col>
                <el-col :span="12">
                  <div class="skill-group">
                    <h4>缺失技能</h4>
                    <el-tag v-for="s in missingSkills" :key="s" type="danger" style="margin:2px;">{{ s }}</el-tag>
                    <el-empty v-if="!missingSkills.length" description="暂无" :image-size="40" />
                  </div>
                </el-col>
              </el-row>
              <el-row :gutter="16" class="mt">
                <el-col :span="8">
                  <h4>优势</h4>
                  <ul>
                    <li v-for="(x, i) in localizedStrengths" :key="i">
                      <b>{{ x.item || x }}</b>
                      <span v-if="x.impact">：{{ x.impact }}</span>
                      <span v-if="x.evidence" class="muted">（{{ x.evidence }}）</span>
                    </li>
                  </ul>
                </el-col>
                <el-col :span="8">
                  <h4>差距</h4>
                  <ul>
                    <li v-for="(x, i) in localizedGaps" :key="i">
                      <b>{{ x.item || x }}</b>
                      <span v-if="x.action">：{{ x.action }}</span>
                      <span v-if="x.impact && !x.action">：{{ x.impact }}</span>
                      <el-tag v-if="x.severity" size="small" :type="x.severity === '高' ? 'danger' : x.severity === '中' ? 'warning' : 'info'" style="margin-left:4px;">{{ x.severity }}</el-tag>
                    </li>
                  </ul>
                </el-col>
                <el-col :span="8">
                  <h4>风险</h4>
                  <ul><li v-for="(x, i) in localizedRiskPoints" :key="i">{{ x }}</li></ul>
                </el-col>
              </el-row>
            </el-tab-pane>

            <!-- 匹配度解释 -->
            <el-tab-pane label="匹配度解释" name="explain">
              <div v-if="explainLoading" class="inline-loading">
                <el-icon class="is-loading" size="22"><Loading /></el-icon>
                <p>正在生成匹配度解释...</p>
              </div>
              <template v-else-if="explainResult">
                <div class="explain-hero">
                  <div class="explain-score-ring">
                    <el-progress type="circle" :percentage="explainResult.overall_score" :stroke-width="8" :size="120" :color="explainScoreColor(explainResult.overall_score)">
                      <template #default>
                        <div class="big-score data-value">{{ explainResult.overall_score }}</div>
                        <div class="score-lbl">总分</div>
                      </template>
                    </el-progress>
                  </div>
                  <div class="explain-score-info">
                    <el-tag :type="explainRecTag" size="large" effect="dark" class="mb">
                      {{ localizedExplainRecommendation }}
                    </el-tag>
                    <p class="explain-reason">{{ localizedExplainOverallReason }}</p>
                    <p class="explain-weights">
                      权重: skill{{ explainResult.weights_used.skill }} / project{{ explainResult.weights_used.project }}
                      / exp{{ explainResult.weights_used.experience }} / edu{{ explainResult.weights_used.education }}
                      / keyword{{ explainResult.weights_used.keyword }} / bonus{{ explainResult.weights_used.bonus }}
                    </p>
                  </div>
                </div>

                <h4 class="mt">六维评分详情</h4>
                <div v-for="dim in explainResult.dimensions" :key="dim.name" class="dim-block">
                  <div class="dim-header">
                    <span class="dim-name">{{ dim.name }}</span>
                    <span class="dim-w">权重 {{ (dim.weight * 100).toFixed(0) }}%</span>
                    <span class="dim-score data-value" :style="{ color: explainScoreColor(dim.score) }">{{ dim.score.toFixed(1) }}</span>
                  </div>
                  <div class="dim-bar"><div class="dim-fill" :style="{ width: `${dim.score}%`, background: explainScoreColor(dim.score) }" /></div>
                  <p class="dim-reason">{{ localizeSentence(dim.reason) }}</p>
                  <div v-if="dim.details?.length" class="dim-details">
                    <el-tag v-for="detail in dim.details" :key="detail" size="small" type="info" effect="plain" style="margin:1px;">{{ localizeSentence(detail) }}</el-tag>
                  </div>
                </div>

                <el-row :gutter="16" class="mt">
                  <el-col :span="12">
                    <h4>已匹配技能</h4>
                    <el-tag v-for="s in explainMatchedSkills" :key="s" type="success" style="margin:2px;">{{ s }}</el-tag>
                    <el-empty v-if="!explainMatchedSkills.length" description="暂无" :image-size="40" />
                  </el-col>
                  <el-col :span="12">
                    <h4>缺失技能</h4>
                    <el-tag v-for="s in explainMissingSkills" :key="s" type="danger" style="margin:2px;">{{ s }}</el-tag>
                    <el-empty v-if="!explainMissingSkills.length" description="暂无" :image-size="40" />
                  </el-col>
                </el-row>
              </template>
              <el-empty v-else description="完成智能分析后可在这里查看匹配度解释" />
            </el-tab-pane>

            <!-- 职业方向 -->
            <el-tab-pane label="🎯 职业方向" name="career-paths">
              <div v-if="careerPathsLoading" class="inline-loading">
                <el-icon class="is-loading" size="22"><Loading /></el-icon>
                <p>正在分析适合您的岗位方向...</p>
              </div>
              <template v-else-if="careerPaths.length > 0">
                <el-alert :title="careerPathSummary || `根据您的技能和经验，推荐以下 ${careerPaths.length} 个岗位方向`" type="success" :closable="false" show-icon style="margin-bottom:16px;" />
                <div class="career-path-grid">
                  <el-card v-for="(cp, i) in careerPaths" :key="i" shadow="hover" class="cp-card" :class="'cp-' + (cp.category === '高度匹配' ? 'high' : 'trans')">
                    <div class="cp-header">
                      <span class="cp-score data-value" :class="scoreClass(cp.match_score)">{{ cp.match_score }}</span>
                      <div class="cp-info">
                        <h4 class="cp-title">{{ cp.title }}</h4>
                        <el-tag size="small" :type="cp.category === '高度匹配' ? 'success' : 'warning'" effect="dark">{{ cp.category }}</el-tag>
                        <span class="cp-seniority">{{ cp.seniority }}</span>
                      </div>
                    </div>
                    <p class="cp-reason">{{ cp.reason }}</p>
                    <div v-if="cp.matched_skills?.length" class="cp-skills">
                      <span class="cp-skill-label">已具备：</span>
                      <el-tag v-for="s in cp.matched_skills" :key="s" size="small" type="success" effect="plain" style="margin:1px;">{{ s }}</el-tag>
                    </div>
                    <div v-if="cp.gap_skills?.length" class="cp-skills">
                      <span class="cp-skill-label">需提升：</span>
                      <el-tag v-for="s in cp.gap_skills" :key="s" size="small" type="danger" effect="plain" style="margin:1px;">{{ s }}</el-tag>
                    </div>
                    <div v-if="cp.salary_range" class="cp-salary">💰 {{ cp.salary_range }}</div>
                  </el-card>
                </div>
              </template>
              <el-empty v-else description="暂无职业方向推荐（请先完成一键智能分析）" />
            </el-tab-pane>

            <!-- 简历优化 -->
            <el-tab-pane label="简历优化建议" name="optimize">
              <el-alert :title="result.optimize_suggestions?.overall || ''" type="success" :closable="false" />
              <el-collapse class="mt">
                <el-collapse-item v-for="(s, i) in result.optimize_suggestions?.sections || []" :key="i" :title="`【${s.section}】`">
                  <ul><li v-for="(x, j) in s.suggestions" :key="j">{{ x }}</li></ul>
                </el-collapse-item>
              </el-collapse>
              <el-row :gutter="16" class="mt">
                <el-col :span="12">
                  <h4>建议补充关键词</h4>
                  <el-tag v-for="k in result.optimize_suggestions?.keywords_to_add || []" :key="k" type="success" style="margin:2px;">{{ k }}</el-tag>
                </el-col>
                <el-col :span="12">
                  <h4>建议删除</h4>
                  <el-tag v-for="k in result.optimize_suggestions?.keywords_to_remove || []" :key="k" type="danger" style="margin:2px;">{{ k }}</el-tag>
                </el-col>
              </el-row>
              <h4 class="mt">排版建议</h4>
              <ul><li v-for="(x, i) in result.optimize_suggestions?.format_tips || []" :key="i">{{ x }}</li></ul>
              <el-divider />
              <div class="generate-area">
                <p class="generate-desc">基于以上优化建议，AI 可自动生成一份完整的优化版简历</p>
                <el-button type="primary" size="large" :loading="genOptimizing" @click="onGenerateOptimized">
                  <el-icon><EditPen /></el-icon> {{ genOptimizing ? '生成中…' : '🚀 生成优化版简历' }}
                </el-button>
              </div>
            </el-tab-pane>

            <!-- 面试题 -->
            <el-tab-pane label="个性化面试题" name="interview">
              <el-empty v-if="!hasInterview" description="暂无面试题" />
              <template v-else>
                <div v-for="(items, key) in interviewGroups" :key="key">
                  <h4>{{ groupTitle(key) }}</h4>
                  <div v-for="(q, i) in items" :key="i" class="q-card">
                    <div class="q"><b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}</div>
                    <div class="q-intent">考察点：{{ q.focus || q.intent }}</div>
                    <div class="q-answer">参考答案：{{ q.suggested_answer || q.expected_answer || q.ref_answer }}</div>
                    <div v-if="q.preparation_tips" class="q-tip">备考建议：{{ q.preparation_tips }}</div>
                  </div>
                </div>
              </template>
            </el-tab-pane>

            <!-- 职业规划 -->
            <el-tab-pane label="🎯 职业规划" name="career">
              <div v-if="careerData" class="career-content">
                <el-row :gutter="16" class="career-section">
                  <el-col :span="8">
                    <div class="status-card">
                      <div class="status-value data-value">{{ careerData.current_status?.career_stage || '-' }}</div>
                      <div class="status-label">当前阶段</div>
                    </div>
                  </el-col>
                  <el-col :span="8">
                    <div class="status-card">
                      <div class="status-value data-value">{{ careerData.current_status?.level || '-' }}</div>
                      <div class="status-label">当前职级</div>
                    </div>
                  </el-col>
                  <el-col :span="8">
                    <div class="status-card">
                      <div class="status-value data-value" style="color:var(--app-warning)">{{ (careerData.skill_gaps || []).length }}</div>
                      <div class="status-label">技能缺口</div>
                    </div>
                  </el-col>
                </el-row>

                <el-card v-if="careerData.skill_radar?.dimensions?.length" shadow="never" class="career-section">
                  <template #header><span>📊 技能雷达</span></template>
                  <div class="radar-chart">
                    <div v-for="dim in careerData.skill_radar.dimensions" :key="dim.name" class="radar-row">
                      <span class="radar-label">{{ dim.name }}</span>
                      <div class="radar-track">
                        <div class="radar-bar current" :style="{ width: dim.current_score + '%' }"><span class="radar-val">{{ dim.current_score }}</span></div>
                        <div class="radar-bar target" :style="{ width: (dim.target_score - dim.current_score) + '%', left: dim.current_score + '%' }"><span class="radar-val-target">→{{ dim.target_score }}</span></div>
                      </div>
                    </div>
                  </div>
                </el-card>

                <el-card v-if="careerData.skill_gaps?.length" shadow="never" class="career-section">
                  <template #header><span>⚠️ 技能提升建议（{{ careerData.skill_gaps.length }} 项）</span></template>
                  <template v-if="hasStructuredSkillGaps">
                    <el-collapse>
                      <el-collapse-item v-for="(gap, i) in careerData.skill_gaps" :key="i" :name="i">
                        <template #title>
                          <div class="gap-title">
                            <el-tag :type="gap.priority === '高' ? 'danger' : gap.priority === '中' ? 'warning' : 'info'" size="small">{{ gap.priority }}</el-tag>
                            <span class="gap-skill">{{ gap.skill }}</span>
                            <span class="gap-level">{{ gap.current_level }} → {{ gap.target_level }}</span>
                          </div>
                        </template>
                        <div class="gap-detail">
                          <p v-if="gap.importance"><b>为什么重要：</b>{{ gap.importance }}</p>
                          <p v-if="gap.acquisition_method"><b>获取途径：</b>{{ gap.acquisition_method }}</p>
                          <div v-if="gap.resources?.length" class="gap-resources">
                            <b>推荐资源：</b>
                            <el-tag v-for="r in gap.resources" :key="r.name" size="small" type="info" effect="plain" style="margin:2px;">{{ r.name }}{{ r.estimated_hours ? ` (${r.estimated_hours}h)` : '' }}</el-tag>
                          </div>
                        </div>
                      </el-collapse-item>
                    </el-collapse>
                  </template>
                  <template v-else><ul><li v-for="(g, i) in careerData.skill_gaps" :key="i">📌 {{ g }}</li></ul></template>
                </el-card>

                <el-card v-if="visualPhases.length" shadow="never" class="career-section">
                  <template #header><span>🛤️ 成长路线图（{{ careerData.visual_roadmap?.total_duration_months || '-' }}个月）</span></template>
                  <div class="roadmap">
                    <div v-for="(phase, i) in visualPhases" :key="phase.id" class="roadmap-phase">
                      <div class="phase-connector" :style="{ borderColor: phase.color }">
                        <div class="phase-dot" :style="{ background: phase.color }">{{ phase.order }}</div>
                      </div>
                      <div class="phase-card" :style="{ borderLeftColor: phase.color }">
                        <div class="phase-header">
                          <span class="phase-name">{{ phase.name }}</span>
                          <el-tag size="small" effect="plain">{{ phase.duration_months }}个月</el-tag>
                        </div>
                        <div class="phase-skills"><el-tag v-for="s in phase.skills" :key="s" size="small" type="success" effect="plain" style="margin:2px;">{{ s }}</el-tag></div>
                        <div v-if="phase.milestones?.length" class="phase-milestones">
                          <div v-for="m in phase.milestones" :key="m.name" class="milestone-item">
                            <span class="ms-icon">{{ milestoneIcon(m.type) }}</span>
                            <span>{{ m.name }}</span>
                          </div>
                        </div>
                        <div v-if="phase.projects?.length" class="phase-projects">
                          <div v-for="p in phase.projects" :key="p.name" class="phase-project-item">
                            <el-icon><Folder /></el-icon>
                            <b>{{ p.name }}</b>：<span class="project-desc">{{ p.description }}</span>
                            <el-tag v-for="t in p.tech_stack" :key="t" size="small" style="margin:1px;">{{ t }}</el-tag>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="roadmap-dir" v-if="careerData.visual_roadmap?.career_direction">🏁 最终方向：<strong>{{ careerData.visual_roadmap.career_direction }}</strong></div>
                </el-card>

                <el-card v-if="careerData.project_recommendations?.length" shadow="never" class="career-section">
                  <template #header><span>🔨 推荐项目实践</span></template>
                  <el-row :gutter="16">
                    <el-col :span="12" v-for="proj in careerData.project_recommendations" :key="proj.project" style="margin-bottom:16px;">
                      <el-card shadow="hover" class="proj-card">
                        <div class="proj-header">
                          <h4 class="proj-name">{{ proj.project }}</h4>
                          <el-tag :type="complexityType(proj.complexity)" size="small" effect="dark">{{ proj.complexity }}</el-tag>
                        </div>
                        <p class="proj-reason">{{ proj.reason }}</p>
                        <p v-if="proj.description" class="proj-desc">{{ proj.description }}</p>
                        <div class="proj-techs"><el-tag v-for="t in proj.tech_stack" :key="t" size="small" type="info" effect="plain">{{ t }}</el-tag></div>
                        <div v-if="proj.learning_outcomes?.length" class="proj-outcomes">
                          <span class="outcome-label">学到的技能：</span>
                          <span v-for="o in proj.learning_outcomes" :key="o" class="outcome-item">{{ o }}</span>
                        </div>
                        <div v-if="proj.estimated_time" class="proj-time">⏱ 预估：{{ proj.estimated_time }}</div>
                      </el-card>
                    </el-col>
                  </el-row>
                </el-card>

                <el-card v-if="careerData.industry_insight" shadow="never" class="career-section">
                  <template #header><span>📈 行业洞察</span></template>
                  <el-row :gutter="16">
                    <el-col :span="12">
                      <h5>当前趋势</h5>
                      <ul><li v-for="t in (careerData.industry_insight.current_trends || [])" :key="t">{{ t }}</li></ul>
                    </el-col>
                    <el-col :span="12">
                      <h5>热门技能</h5>
                      <el-tag v-for="s in (careerData.industry_insight.demanded_skills || [])" :key="s" type="warning" style="margin:2px;">{{ s }}</el-tag>
                    </el-col>
                  </el-row>
                  <div v-if="careerData.industry_insight.career_alternatives?.length" class="mt">
                    <h5>可考虑的其他方向</h5>
                    <el-tag v-for="alt in careerData.industry_insight.career_alternatives" :key="alt" type="info" style="margin:2px;">{{ alt }}</el-tag>
                  </div>
                  <div v-if="careerData.industry_insight.salary_range" class="mt salary-ref">💰 薪资参考：<strong>{{ careerData.industry_insight.salary_range }}</strong></div>
                </el-card>

                <el-card shadow="never" class="career-section">
                  <template #header><span>📋 阶段计划</span></template>
                  <el-row :gutter="16">
                    <el-col :span="8">
                      <div class="plan-card plan-short">
                        <h4>短期计划</h4>
                        <div class="plan-tl">{{ careerData.short_term_plan?.timeline || '1-3月' }}</div>
                        <ul><li v-for="g in (careerData.short_term_plan?.goals || [])" :key="g">{{ g }}</li></ul>
                        <div v-if="careerData.short_term_plan?.daily_routine" class="plan-routine"><b>每日安排：</b>{{ careerData.short_term_plan.daily_routine }}</div>
                      </div>
                    </el-col>
                    <el-col :span="8">
                      <div class="plan-card plan-mid">
                        <h4>中期计划</h4>
                        <div class="plan-tl">{{ careerData.mid_term_plan?.timeline || '3-12月' }}</div>
                        <ul><li v-for="g in (careerData.mid_term_plan?.goals || [])" :key="g">{{ g }}</li></ul>
                      </div>
                    </el-col>
                    <el-col :span="8">
                      <div class="plan-card plan-long">
                        <h4>长期计划</h4>
                        <div class="plan-tl">{{ careerData.long_term_plan?.timeline || '1-3年' }}</div>
                        <ul><li v-for="g in (careerData.long_term_plan?.goals || [])" :key="g">{{ g }}</li></ul>
                        <div v-if="careerData.long_term_plan?.target_companies" class="plan-targets">🏢 <span v-for="c in careerData.long_term_plan.target_companies" :key="c">{{ c }} </span></div>
                      </div>
                    </el-col>
                  </el-row>
                </el-card>

                <el-card v-if="careerData.recommended_certifications?.length" shadow="never" class="career-section">
                  <template #header><span>🎓 推荐证书</span></template>
                  <el-table :data="careerData.recommended_certifications" size="small">
                    <el-table-column prop="name" label="证书" />
                    <el-table-column prop="level" label="难度" width="80" />
                    <el-table-column prop="relevance" label="岗位关联度" width="200" />
                  </el-table>
                </el-card>

                <el-alert v-if="careerData.overall_advice" :title="careerData.overall_advice" type="success" :closable="false" show-icon />
              </div>
              <el-empty v-else description="暂无职业规划数据" />
            </el-tab-pane>

            <!-- 综合评价 -->
            <el-tab-pane label="综合评价" name="summary">
              <div v-if="finalReport">
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item label="候选人">{{ finalReport.summary?.candidate_name || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="目标岗位">{{ finalReport.summary?.target_position || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="推荐建议">{{ localizedSummaryRecommendation }}</el-descriptions-item>
                  <el-descriptions-item label="综合评价" :span="2">{{ localizedOverallEvaluation }}</el-descriptions-item>
                </el-descriptions>
                <h4 class="mt">投递建议</h4>
                <el-table :data="finalReport.action_items || []" size="small" class="mt">
                  <el-table-column prop="priority" label="优先级" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.priority === '高' ? 'danger' : row.priority === '中' ? 'warning' : 'info'" size="small">{{ row.priority }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="action" label="行动" />
                  <el-table-column prop="reason" label="原因" show-overflow-tooltip />
                </el-table>
                <h4 class="mt">发展建议</h4>
                <el-row :gutter="16">
                  <el-col :span="12">
                    <div class="dev-card">
                      <h5>短期</h5>
                      <ul><li v-for="(s, i) in finalReport.development_advice?.short_term || []" :key="i">{{ s }}</li></ul>
                    </div>
                  </el-col>
                  <el-col :span="12">
                    <div class="dev-card">
                      <h5>长期</h5>
                      <ul><li v-for="(s, i) in finalReport.development_advice?.long_term || []" :key="i">{{ s }}</li></ul>
                    </div>
                  </el-col>
                </el-row>
              </div>
              <el-empty v-else description="暂无综合评价" />
            </el-tab-pane>

            <!-- 引用来源 -->
            <el-tab-pane label="📚 引用来源" name="references">
              <div v-if="referencesLoading" class="inline-loading">
                <el-icon class="is-loading" size="22"><Loading /></el-icon>
                <p>正在检索引用来源…</p>
              </div>
              <template v-else-if="references.length > 0 || analysisConfidence">
                <div v-if="analysisConfidence" class="rag-confidence">
                  <div class="rag-confidence-main">
                    <div class="rag-badge" :class="`badge-${analysisConfidence.level || 'low'}`">
                      {{ analysisConfidence.score ?? 0 }}
                    </div>
                    <div class="rag-confidence-copy">
                      <div class="rag-confidence-title">
                        本次检索可信度
                        <el-tag size="small" :type="confidenceTagType(analysisConfidence.level)">{{ analysisConfidence.label || '-' }}</el-tag>
                      </div>
                      <div class="rag-confidence-summary">{{ analysisConfidence.summary || '暂无可信度说明' }}</div>
                      <div v-if="referenceQuery" class="rag-confidence-query">检索查询：{{ referenceQuery }}</div>
                    </div>
                  </div>
                  <div v-if="analysisConfidence.breakdown?.length" class="rag-breakdown">
                    <div v-for="item in analysisConfidence.breakdown" :key="item.name" class="rag-breakdown-item">
                      <span>{{ item.name }}</span>
                      <strong class="data-value">{{ item.score }}</strong>
                      <em>{{ item.detail }}</em>
                    </div>
                  </div>
                  <div v-if="analysisConfidence.risks?.length" class="rag-risk-list">
                    <span class="rag-risk-label">风险提示</span>
                    <span v-for="risk in analysisConfidence.risks" :key="risk" class="rag-risk-item">{{ risk }}</span>
                  </div>
                </div>
                <el-alert v-if="references.length > 0" title="本次分析参考了以下知识库文档" type="info" :closable="false" show-icon style="margin-bottom:16px;" />
                <el-collapse v-if="references.length > 0" v-model="refOpenDocs">
                  <el-collapse-item v-for="(doc, i) in references" :key="i" :title="`${doc.doc_title}  (${typeLabel(doc.doc_type)})`" :name="i">
                    <template #title>
                      <div class="ref-title">
                        <el-icon><Document /></el-icon>
                        <span class="ref-doc-title">{{ doc.doc_title }}</span>
                        <el-tag size="small" type="info" effect="plain">{{ typeLabel(doc.doc_type) }}</el-tag>
                      </div>
                    </template>
                    <div class="ref-chunks">
                      <div v-for="(chunk, j) in doc.chunks" :key="j" class="ref-chunk-item">
                        <div class="ref-chunk-header">
                          <span class="ref-chunk-num">片段 #{{ j + 1 }}</span>
                          <el-tag size="small" :type="scoreTagType(chunk.score)" effect="plain">相似度 {{ (chunk.score * 100).toFixed(1) }}%</el-tag>
                        </div>
                        <el-input :model-value="chunk.text" type="textarea" :rows="2" readonly class="ref-chunk-text" />
                      </div>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </template>
              <el-empty v-else description="暂无引用知识（知识库为空或未检索到相关文档）" />
            </el-tab-pane>
          </el-tabs>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from '@/plugins/element-services'
import {
  UploadFilled, SuccessFilled, MagicStick, Promotion, Loading,
  SuccessFilled as SuccessIcon, WarningFilled, CircleCloseFilled, Document,
  InfoFilled, EditPen, Folder
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { uploadResume, parseResume } from '@/api/resume'
import { createJD, parseJD } from '@/api/jd'
import { runFullAnalysis, getAnalysis, getAnalysisReferences, explainMatch } from '@/api/analysis'
import { generateOptimized } from '@/api/resume'
import { useAgentTaskPolling } from '@/composables/useAgentTaskPolling'
import {
  localizeRecommendationText,
  localizeSentence,
  localizeSeverity,
  normalizeLocalizedObjectList,
  normalizeLocalizedTextList,
} from '@/utils/analysisLocalization'

const authStore = useAuthStore()
const uid = computed(() => authStore.user?.id || 'guest')
const storageKey = (k) => `recruit.${k}.${uid.value}`

const loading = ref(false)
const resumeInfo = ref(null)
const jdInfo = ref(null)
const result = ref(null)
const reportTab = ref('skills')
const agentSteps = ref([])
const genOptimizing = ref(false)
const genRedirecting = ref(false)
const explainLoading = ref(false)
const explainResult = ref(null)
const { pollTask: pollAgentTask } = useAgentTaskPolling()
const taskOutcome = ref('idle')

const references = ref([])
const referencesLoading = ref(false)
const refOpenDocs = ref([0])
const referenceQuery = ref('')
const referenceConfidence = ref(null)

const jdForm = reactive({ title: '', company: '', raw_text: '' })

const canAnalyze = computed(() => {
  const hasJD = jdInfo.value || (jdForm.title.trim() && jdForm.raw_text.trim())
  return resumeInfo.value && hasJD
})

const completedStepCount = computed(() =>
  agentSteps.value.filter(s => s.status === 'completed').length
)

const analysisFlowLabel = computed(() => {
  if (loading.value) return '分析中'
  if (result.value) return '已完成'
  if (taskOutcome.value === 'partial') return '部分完成'
  if (taskOutcome.value === 'failed') return '失败'
  if (taskOutcome.value === 'cancelled') return '已取消'
  if (taskOutcome.value === 'timeout') return '已超时'
  return '待开始'
})

const analysisFlowHint = computed(() => {
  if (loading.value || agentSteps.value.length) {
    return `${completedStepCount.value} / ${agentSteps.value.length || 0} 步`
  }
  if (taskOutcome.value === 'failed') return '分析失败，请检查输入或稍后重试'
  if (taskOutcome.value === 'cancelled') return '任务已取消'
  if (taskOutcome.value === 'timeout') return '轮询超时，请稍后查看历史记录'
  return '尚未启动分析任务'
})

const taskOutcomeTag = computed(() => ({
  partial: 'warning',
  failed: 'danger',
  cancelled: 'info',
  timeout: 'warning',
}[taskOutcome.value] || 'info'))

const terminalHint = computed(() => {
  if (taskOutcome.value === 'partial') return '任务部分完成，但没有生成完整分析结果。可以稍后去历史记录查看，或直接重试。'
  if (taskOutcome.value === 'failed') return '任务执行失败，当前没有可展示的分析结果。'
  if (taskOutcome.value === 'cancelled') return '任务已取消，当前没有可展示的分析结果。'
  if (taskOutcome.value === 'timeout') return '前端轮询已超时，后台任务可能仍在继续。你可以稍后去历史记录查看结果。'
  return '当前没有可展示的分析结果。'
})

const activeStep = computed(() => {
  const idx = agentSteps.value.findIndex(s => s.status === 'running')
  if (idx >= 0) return idx
  return completedStepCount.value
})

const currentStepName = computed(() => {
  const running = agentSteps.value.find(s => s.status === 'running')
  if (running) return stepLabel(running.step_name)
  const pending = agentSteps.value.find(s => s.status === 'pending')
  if (pending) return stepLabel(pending.step_name)
  const lastCompleted = [...agentSteps.value].reverse().find(s => s.status === 'completed')
  if (lastCompleted) return stepLabel(lastCompleted.step_name)
  return '准备中'
})

const getDimension = (key) => {
  const value = result.value?.match_report?.dimension_scores?.[key]
  if (value && typeof value === 'object') return value
  if (typeof value === 'number') return { score: value }
  return { score: 0 }
}

const dimensionScore = (key) => getDimension(key).score ?? 0

const pickNonEmptyArray = (...candidates) => {
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) return candidate
  }
  return []
}

const matchedSkills = computed(() => pickNonEmptyArray(getDimension('skills').matched, result.value?.matched_skills))
const missingSkills = computed(() => pickNonEmptyArray(getDimension('skills').missing, result.value?.missing_skills))
const finalReport = computed(() => result.value?.final_report || null)
const rawMatchRecommendation = computed(() => result.value?.match_report?.recommendation || '')
const rawMatchSummary = computed(() => result.value?.match_report?.summary || '')
const localizedMatchRecommendation = computed(() => localizeRecommendationText(rawMatchRecommendation.value))
const localizedMatchSummary = computed(() => localizeSentence(rawMatchSummary.value))
const localizedStrengths = computed(() => normalizeLocalizedObjectList(result.value?.match_report?.strengths))
const localizedGaps = computed(() => normalizeLocalizedObjectList(result.value?.match_report?.gaps))
const localizedRiskPoints = computed(() => normalizeLocalizedTextList(result.value?.match_report?.risk_points))
const rawSummaryRecommendation = computed(() => finalReport.value?.summary?.recommendation || '')
const rawOverallEvaluation = computed(() => finalReport.value?.summary?.overall_evaluation || '')
const localizedSummaryRecommendation = computed(() => localizeRecommendationText(rawSummaryRecommendation.value))
const localizedOverallEvaluation = computed(() => localizeSentence(rawOverallEvaluation.value))

const normalizeConfidence = (value) => {
  if (!value || typeof value !== 'object') return null
  if (typeof value.score === 'number') return value
  if (value.summary) return value
  return null
}

const analysisConfidence = computed(() => (
  normalizeConfidence(result.value?.rag_confidence) || normalizeConfidence(referenceConfidence.value)
))

const localizedExplainRecommendation = computed(() => localizeRecommendationText(explainResult.value?.recommendation || ''))
const localizedExplainOverallReason = computed(() => localizeSentence(explainResult.value?.overall_reason || ''))
const localizedExplainRiskPoints = computed(() => normalizeLocalizedTextList(explainResult.value?.risk_points))
const localizedExplainSuggestions = computed(() => normalizeLocalizedTextList(explainResult.value?.optimization_suggestions))

const explainRecTag = computed(() => ({
  '强烈推荐': 'success',
  '可以投递': 'primary',
  '谨慎投递': 'warning',
  '不建议投递': 'danger',
}[localizedExplainRecommendation.value] || 'info'))

const explainMatchedSkills = computed(() => explainResult.value?.skill_match?.matched || [])
const explainMissingSkills = computed(() => {
  const skillMatch = explainResult.value?.skill_match || {}
  const required = Array.isArray(skillMatch.missing_required) ? skillMatch.missing_required : []
  const nice = Array.isArray(skillMatch.missing_nice) ? skillMatch.missing_nice : []
  return [...required, ...nice.filter(item => !required.includes(item))]
})

const careerData = computed(() => result.value?.career_planning || null)
const visualPhases = computed(() => careerData.value?.visual_roadmap?.phases || [])
const hasStructuredSkillGaps = computed(() => {
  const gaps = careerData.value?.skill_gaps || []
  return gaps.length > 0 && typeof gaps[0] === 'object' && gaps[0] !== null
})

const milestoneIcon = (type) => ({ skill: '📚', cert: '🎓', project: '🔨', job: '💼' }[type] || '📍')

const complexityType = (level) => ({ '简单': 'success', '中等': 'warning', '困难': 'danger' }[level] || 'info')

const INTERVIEW_GROUP_DEFS = [
  { key: 'hr_questions', legacy: 'basic', title: 'HR 题' },
  { key: 'tech_questions', legacy: 'tech', title: '技术题' },
  { key: 'project_questions', legacy: 'project', title: '项目题' },
  { key: 'scenario_questions', legacy: 'scenario', title: '场景题' },
]

const hasInterview = computed(() => Object.keys(interviewGroups.value).length > 0)

const interviewGroups = computed(() => {
  const iq = result.value?.interview_questions || {}
  const groups = {}
  INTERVIEW_GROUP_DEFS.forEach(({ key, legacy }) => {
    const items = Array.isArray(iq[key]) && iq[key].length
      ? iq[key]
      : (Array.isArray(iq[legacy]) ? iq[legacy] : [])
    if (items.length) groups[key] = items
  })
  return groups
})

const groupTitle = (k) => INTERVIEW_GROUP_DEFS.find(item => item.key === k)?.title || k

// ---- Resume upload ----
const beforeUploadResume = (file) => {
  const ext = file.name.split('.').pop().toLowerCase()
  if (!['pdf', 'docx', 'doc'].includes(ext)) {
    ElMessage.error('仅支持 PDF / DOCX / DOC 格式')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('文件超过 10MB')
    return false
  }
  return true
}

const customUploadResume = async ({ file }) => {
  try {
    const data = await uploadResume(file)
    ElMessage.success('简历上传成功，正在解析…')
    const parsed = await parseResume(data.id)
    resumeInfo.value = { id: data.id, file_name: file.name, parsed: parsed.parsed }
    localStorage.setItem(storageKey('lastResumeId'), data.id)
    ElMessage.success('简历解析完成')
  } catch (e) { /* request.js 已提示 */ }
}

const clearResume = () => { resumeInfo.value = null; explainResult.value = null }
const clearJD = () => {
  jdInfo.value = null; jdForm.title = ''; jdForm.company = ''; jdForm.raw_text = ''; explainResult.value = null
}

// ---- Analysis ----
const onStartAnalysis = async () => {
  if (!canAnalyze.value) return
  if (!jdInfo.value) {
    if (!jdForm.title.trim() || !jdForm.raw_text.trim()) {
      ElMessage.warning('请填写岗位名称和 JD 内容'); return
    }
    try {
      const jd = await createJD({ title: jdForm.title, company: jdForm.company || '', raw_text: jdForm.raw_text })
      await parseJD(jd.id)
      jdInfo.value = { id: jd.id, title: jdForm.title }
      localStorage.setItem(storageKey('lastJDId'), jd.id)
    } catch (e) { return }
  }

  loading.value = true
  taskOutcome.value = 'idle'
  result.value = null
  explainResult.value = null
  agentSteps.value = []
  references.value = []
  referenceQuery.value = ''
  referenceConfidence.value = null
  careerPaths.value = []
  careerPathSummary.value = ''

  try {
    const startRes = await runFullAnalysis({ resume_id: resumeInfo.value.id, jd_id: jdInfo.value.id })
    const taskId = startRes?.task_id
    if (!taskId) { ElMessage.error('启动智能分析失败'); return }
    await pollAgentTask(taskId, {
      onProgress(taskData, steps) {
        agentSteps.value = steps
        taskOutcome.value = taskData?.status || 'running'
      },
      async onCompleted(taskData) {
        taskOutcome.value = taskData?.status || 'completed'
        const recordId = taskData?.analysis_record_id
        if (!recordId) { ElMessage.error('任务完成但未生成分析记录'); return }
        const data = await getAnalysis(recordId)
        result.value = data
        localStorage.setItem(storageKey('lastRecordId'), String(data.record_id || data.id || recordId))
        await loadExplainMatch(true)
        await loadReferences(true)
        ElMessage.success(`智能分析完成，匹配度 ${data.match_score}`)
        reportTab.value = 'skills'
      },
      onFailed(error) {
        taskOutcome.value = 'failed'
        ElMessage.error(`智能分析失败: ${error.message || '未知错误'}`)
      },
      onCancelled(error) {
        taskOutcome.value = 'cancelled'
        ElMessage.warning(error.message || 'Agent task was cancelled')
      },
      onTimeout() {
        taskOutcome.value = 'timeout'
        ElMessage.warning('分析超时，请稍后查看历史记录')
      },
    })
  } catch (e) { /* request.js 已提示 */ }
  finally { loading.value = false }
}

const onTabClick = (tab) => {
  if (tab.paneName === 'references') loadReferences()
  else if (tab.paneName === 'explain') loadExplainMatch()
  else if (tab.paneName === 'career-paths') loadCareerPaths()
}

const loadExplainMatch = async (force = false) => {
  const resumeId = result.value?.resume_id || resumeInfo.value?.id
  const jdId = result.value?.jd_id || jdInfo.value?.id
  if (!resumeId || !jdId) return
  if (explainResult.value && !force) return
  explainLoading.value = true
  try {
    const data = await explainMatch({ resume_id: resumeId, jd_id: jdId })
    explainResult.value = data
  } catch (e) { console.error('加载匹配度解释失败:', e) }
  finally { explainLoading.value = false }
}

const careerPaths = ref([])
const careerPathsLoading = ref(false)
const careerPathSummary = ref('')

const loadCareerPaths = async () => {
  const rid = result.value?.resume_id || resumeInfo.value?.id
  if (!rid) return
  careerPathsLoading.value = true
  try {
    const { recommendCareerPaths } = await import('@/api/jobs')
    const data = await recommendCareerPaths(rid)
    careerPaths.value = data?.career_paths || []
    careerPathSummary.value = data?.summary || ''
  } catch (e) { console.error('加载职业方向失败:', e) }
  finally { careerPathsLoading.value = false }
}

const scoreClass = (s) => s >= 80 ? 'sc-high' : s >= 60 ? 'sc-mid' : 'sc-low'

const loadReferences = async (force = false) => {
  if ((!force && references.value.length > 0) || !result.value?.id) return
  referencesLoading.value = true
  try {
    const data = await getAnalysisReferences(result.value.id)
    references.value = data?.references || []
    referenceQuery.value = data?.query || ''
    if (!result.value?.rag_confidence && data?.rag_confidence) {
      referenceConfidence.value = data.rag_confidence
    }
  } catch (e) { console.error('加载引用来源失败:', e) }
  finally { referencesLoading.value = false }
}

const typeLabel = (t) => ({
  resume_template: '简历模板', jd_lib: '岗位描述库', interview_q: '面试题库',
  skill_model: '能力模型', industry_report: '行业报告', general: '通用',
}[t] || t || '通用')

const scoreTagType = (score) => score >= 0.8 ? 'success' : score >= 0.6 ? 'warning' : 'info'
const confidenceTagType = (level) => level === 'high' ? 'success' : level === 'medium' ? 'warning' : 'danger'

const STEP_LABELS = {
  IntentAgent: '意图识别', ResumeParseAgent: '简历解析', JDParseAgent: 'JD 解析',
  MatchAnalysisAgent: '匹配分析', ResumeOptimizeAgent: '简历优化',
  InterviewQuestionAgent: '面试题生成', SummaryAgent: '汇总报告',
  intent_recognition: '意图识别', resume_parse: '简历解析', jd_parse: 'JD 解析',
  knowledge_retrieval: '知识检索', matching_analysis: '匹配分析',
  resume_optimization: '简历优化', interview_question_generation: '面试题生成',
  self_check: '自我校验', final_report: '汇总报告',
}

const CANONICAL_STEP_LABELS = {
  intent_recognition: '意图识别', resume_parse: '简历解析', jd_parse: 'JD 解析',
  knowledge_retrieval: '知识检索', match_analysis: '匹配分析',
  resume_optimization: '简历优化', interview_questions: '面试题生成',
  career_planning: '职业规划', self_check: '自我校验', summary_report: '汇总报告',
}

function stepLabel(name) { return CANONICAL_STEP_LABELS[name] || STEP_LABELS[name] || name }
function stepStatus(status) { return { completed: 'finish', running: 'process', failed: 'error', skipped: 'wait' }[status] || 'wait' }
function stepType(status) { return { completed: 'success', running: 'primary', failed: 'danger', skipped: 'info' }[status] || 'info' }
function stepIcon(status) { return { completed: SuccessIcon, failed: CircleCloseFilled, running: Loading }[status] || WarningFilled }
function statusText(status) { return { pending: '等待中', running: '执行中', completed: '已完成', failed: '失败' }[status] || status }
function stepDesc(s) {
  if (s.status === 'completed') return `${s.duration_ms || 0}ms`
  if (s.status === 'failed') return '失败'
  if (s.status === 'running') return '执行中…'
  return ''
}

function scoreColor(s) {
  if (s >= 80) return [{ color: '#1DB954', percentage: 100 }]
  if (s >= 60) return [{ color: '#F5A623', percentage: 100 }]
  return [{ color: '#D4442F', percentage: 100 }]
}

function explainScoreColor(s) {
  if (s >= 80) return '#1DB954'
  if (s >= 60) return '#196BDB'
  if (s >= 40) return '#F5A623'
  return '#D4442F'
}

const onGenerateOptimized = async () => {
  const resumeId = resumeInfo.value?.id
  if (!resumeId) { ElMessage.warning('请先上传简历'); return }
  genOptimizing.value = true
  try {
    await generateOptimized(resumeId, jdInfo.value?.id || null)
    ElMessage.success('优化版简历生成成功')
    window.location.href = `/resume/compare/${resumeId}`
  } catch (e) { /* request.js 已提示 */ }
  finally { genOptimizing.value = false; genRedirecting.value = false }
}

onMounted(() => {
  const rid = localStorage.getItem(storageKey('lastResumeId'))
  const jid = localStorage.getItem(storageKey('lastJDId'))
  if (rid) resumeInfo.value = { id: Number(rid), file_name: `简历 #${rid}` }
  if (jid) jdInfo.value = { id: Number(jid), title: `JD #${jid}` }

  const pending = localStorage.getItem('recruit.pendingAnalysis')
  if (pending) {
    try {
      const ctx = JSON.parse(pending)
      if (ctx.title) jdForm.title = ctx.title
      if (ctx.company) jdForm.company = ctx.company
      if (ctx.jd_text) jdForm.raw_text = ctx.jd_text
      if (ctx.jdId) {
        jdInfo.value = { id: Number(ctx.jdId), title: ctx.title || `JD #${ctx.jdId}` }
        localStorage.setItem(storageKey('lastJDId'), String(ctx.jdId))
      }
    } catch (e) { console.warn('解析 pendingAnalysis 失败', e) }
    finally { localStorage.removeItem('recruit.pendingAnalysis') }
  }
})
</script>

<style scoped>
.smart-page {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Hero ===== */
.analysis-hero {
  padding: 24px;
  border-radius: 20px;
  border: 1px solid var(--app-line);
  background: #fff;
  box-shadow: var(--app-shadow);
}

.hero-title-area {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-size: 11px;
  font-weight: 600;
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--app-primary);
}

.hero-title-main h1 {
  margin: 6px 0 0;
  font-size: 30px;
  font-weight: 800;
  line-height: 1.1;
}

.hero-title-main p {
  margin: 10px 0 0;
  max-width: 540px;
  color: var(--app-muted);
  line-height: 1.7;
  font-size: 14px;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.hero-tags span {
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--app-line);
  font-size: 11px;
  color: var(--app-muted);
}

.hero-node {
  flex-shrink: 0;
  opacity: 0.6;
  display: none;
}

@media (min-width: 1024px) {
  .hero-node { display: block; }
}

/* Hero metrics */
.hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.hm-item {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--app-line);
  background: #fff;
  transition: background 0.2s ease;
}

.hm-item.ready {
  background: var(--el-fill-color-light);
}

.hm-label {
  display: block;
  font-size: 11px;
  color: var(--app-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hm-item strong {
  display: block;
  margin-top: 8px;
  font-size: 20px;
  line-height: 1.1;
}

.hm-item small {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}

/* ===== Card sections ===== */
.card-section {
  border-radius: 16px;
  border: 1px solid var(--app-line);
  background: #fff;
  box-shadow: var(--app-shadow);
  overflow: hidden;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);
}

.card-head-left {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
}

.card-body {
  padding: 20px;
}

/* ===== Input split ===== */
.input-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.input-col-label {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--app-text);
}

/* Upload */
.resume-upload :deep(.el-upload),
.resume-upload :deep(.el-upload-dragger) {
  width: 100%;
}

.resume-upload :deep(.el-upload-dragger) {
  min-height: 220px;
  border-radius: 14px;
  border: 1px dashed var(--app-line);
  background: var(--el-fill-color-light);
  transition: border-color 0.2s ease, background 0.2s ease;
}

.resume-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--app-primary);
  background: var(--app-primary-light);
}

.upload-blank {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.upload-icon {
  font-size: 36px;
  color: var(--app-muted);
}

.upload-title {
  font-size: 14px;
  color: var(--app-muted);
}

.upload-title em {
  font-style: normal;
  color: var(--app-primary);
  font-weight: 600;
}

.upload-hint {
  font-size: 12px;
  color: var(--app-muted);
}

.upload-ready {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}

.done-icon {
  font-size: 32px;
  color: var(--app-success);
}

.upload-ready-copy strong {
  display: block;
  font-size: 14px;
}

.upload-ready-copy span {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-muted);
}

/* JD */
.jd-form { width: 100%; }
.jd-form :deep(.el-form-item) { margin-bottom: 14px; }
.jd-ready { display: flex; align-items: center; gap: 8px; margin-top: 8px; }

/* Action bar */
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.action-copy strong {
  display: block;
  color: var(--app-text);
  font-size: 14px;
}

.action-copy span {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
}

/* ===== Pipeline ===== */
.pipeline-status {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}

.ps-item {
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
}

.ps-item span {
  display: block;
  color: var(--app-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ps-item strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

/* Pipeline timeline */
.pipeline-timeline {
  position: relative;
  padding-left: 28px;
}

.pipeline-node {
  position: relative;
  display: flex;
  gap: 14px;
  padding-bottom: 18px;
}

.pipeline-node:last-child {
  padding-bottom: 0;
}

.pipeline-connector {
  position: absolute;
  left: -8px;
  top: 20px;
  bottom: 0;
  width: 2px;
  background: var(--el-border-color);
}

.pipeline-node:last-child .pipeline-connector {
  display: none;
}

.pipeline-dot {
  position: relative;
  z-index: 1;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.node-completed .pipeline-dot {
  background: var(--app-success);
  color: #fff;
}

.node-running .pipeline-dot {
  background: var(--app-primary);
  color: #fff;
  box-shadow: 0 0 0 4px rgba(25, 107, 219, 0.15);
}

.node-failed .pipeline-dot {
  background: var(--app-danger);
  color: #fff;
}

.node-pending .pipeline-dot {
  background: var(--el-border-color);
}

.dot-empty {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-border-color);
}

.pipeline-content {
  flex: 1;
  min-width: 0;
}

.pl-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.pl-head strong {
  font-size: 14px;
}

.pl-meta {
  font-size: 12px;
  color: var(--app-muted);
}

.pl-preview {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  color: var(--app-primary-dark);
}

/* ===== Results ===== */
.results-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.score-body {
  padding: 24px;
}

.score-center {
  display: flex;
  gap: 24px;
  align-items: center;
  padding-bottom: 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.score-value {
  font-size: 36px;
  line-height: 1;
}

.score-label {
  font-size: 12px;
  color: var(--app-muted);
}

.score-meta { flex: 1; }

.score-rec {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}

.score-sum {
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.7;
}

.score-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.chip {
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid transparent;
}

.chip-match {
  background: #e8f8ee;
  color: var(--app-success);
  border-color: #ccecd7;
}

.chip-gap {
  background: var(--app-violet-light);
  color: var(--app-violet);
  border-color: #d9cef0;
}

.chip-ref {
  background: var(--app-primary-light);
  color: var(--app-primary);
  border-color: #c1d6f0;
}

.dim-table { margin-top: 0; }
.dim-val { color: var(--app-primary); }

/* RAG Confidence */
.rag-confidence {
  margin-top: 16px;
  padding: 16px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
}

.rag-confidence-main {
  display: flex;
  gap: 14px;
  align-items: center;
}

.rag-badge {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.badge-high { background: linear-gradient(135deg, #1DB954, #48c978); }
.badge-medium { background: linear-gradient(135deg, #F5A623, #f7b94d); }
.badge-low { background: linear-gradient(135deg, #D4442F, #dc6b5a); }

.rag-confidence-copy { flex: 1; min-width: 0; }

.rag-confidence-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
}

.rag-confidence-summary {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
}

.rag-confidence-query {
  margin-top: 6px;
  color: var(--app-muted);
  font-size: 12px;
  word-break: break-all;
}

.rag-confidence-metrics {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.rag-metric {
  padding: 10px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--el-border-color);
}

.rag-metric span {
  display: block;
  color: var(--app-muted);
  font-size: 11px;
  margin-bottom: 4px;
}

.rag-metric strong {
  font-size: 16px;
}

.rag-breakdown {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.rag-breakdown-item {
  padding: 10px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--el-border-color);
}

.rag-breakdown-item span,
.rag-breakdown-item strong,
.rag-breakdown-item em {
  display: block;
}

.rag-breakdown-item span {
  color: var(--app-muted);
  font-size: 12px;
}

.rag-breakdown-item strong {
  margin: 4px 0;
  font-size: 16px;
}

.rag-breakdown-item em {
  color: var(--app-muted);
  font-size: 11px;
  font-style: normal;
  line-height: 1.5;
}

.rag-risk-list {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rag-risk-label {
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 600;
  align-self: center;
}

.rag-risk-item {
  padding: 4px 8px;
  border-radius: 6px;
  background: #fff5f2;
  color: var(--app-danger);
  font-size: 11px;
  border: 1px solid #fad5cc;
}

/* Explain tab */
.explain-hero {
  display: flex;
  gap: 20px;
  align-items: center;
  padding: 20px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  margin-bottom: 16px;
}

.big-score { font-size: 28px; }
.score-lbl { font-size: 12px; color: var(--app-muted); }

.explain-score-info { flex: 1; }
.explain-reason { margin: 8px 0 0; color: var(--app-muted); line-height: 1.7; }
.explain-weights { margin: 8px 0 0; color: var(--app-muted); font-size: 12px; font-family: var(--app-font-mono); }

/* Dimension bars */
.dim-block {
  margin-bottom: 16px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--el-border-color);
}

.dim-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.dim-name { font-weight: 600; font-size: 14px; flex: 1; }
.dim-w { color: var(--app-muted); font-size: 12px; }
.dim-score { font-size: 18px; font-weight: 700; }

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

.dim-reason { margin: 6px 0 0; color: var(--app-muted); font-size: 13px; line-height: 1.6; }
.dim-details { margin-top: 6px; }

/* Query card */
.q-card {
  padding: 14px;
  margin: 8px 0;
  border-radius: 10px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
}

.q { font-size: 14px; }
.q-intent { color: var(--app-muted); font-size: 12px; margin: 4px 0; }
.q-answer { color: var(--app-success); font-size: 13px; }
.q-tip { margin-top: 4px; font-size: 12px; color: var(--app-warning); }

/* Career paths */
.career-path-grid { display: flex; flex-direction: column; gap: 10px; }
.cp-card { border-radius: 12px; }
.cp-high { border-left: 3px solid var(--app-success); }
.cp-trans { border-left: 3px solid var(--app-warning); }
.cp-header { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.cp-score { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; color: #fff; flex-shrink: 0; }
.sc-high { background: linear-gradient(135deg, #1DB954, #48c978); }
.sc-mid { background: linear-gradient(135deg, #F5A623, #f7b94d); }
.sc-low { background: linear-gradient(135deg, #D4442F, #dc6b5a); }
.cp-info { flex: 1; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cp-title { margin: 0; font-size: 15px; font-weight: 600; }
.cp-seniority { font-size: 12px; color: var(--app-muted); }
.cp-reason { font-size: 13px; color: var(--app-muted); margin: 4px 0; }
.cp-skills { margin: 4px 0; }
.cp-skill-label { font-size: 12px; color: var(--app-muted); margin-right: 4px; }
.cp-salary { font-size: 13px; color: var(--app-warning); margin-top: 4px; font-weight: 600; }

/* Career content */
.career-content { }
.status-card { padding: 18px; border-radius: 12px; background: var(--el-fill-color-light); text-align: center; }
.status-value { font-size: 28px; line-height: 1.1; margin-bottom: 6px; }
.status-label { font-size: 12px; color: var(--app-muted); }
.career-section { margin-bottom: 16px; }

/* Radar */
.radar-chart { display: flex; flex-direction: column; gap: 10px; }
.radar-row { display: flex; align-items: center; gap: 10px; }
.radar-label { width: 80px; font-size: 13px; font-weight: 500; flex-shrink: 0; }
.radar-track { flex: 1; height: 10px; border-radius: 999px; background: var(--el-border-color-light); position: relative; overflow: hidden; }
.radar-bar { position: absolute; top: 0; left: 0; height: 100%; border-radius: 999px; display: flex; align-items: center; }
.radar-bar.current { background: var(--app-primary); z-index: 1; }
.radar-bar.target { background: rgba(25, 107, 219, 0.2); }
.radar-val, .radar-val-target { font-size: 10px; font-weight: 600; padding: 0 6px; color: #fff; font-family: var(--app-font-mono); }
.radar-val-target { color: var(--app-primary); }

/* Plan cards */
.plan-card { padding: 16px; border-radius: 12px; border: 1px solid var(--el-border-color); }
.plan-short { border-left: 3px solid var(--app-primary); }
.plan-mid { border-left: 3px solid var(--app-warning); }
.plan-long { border-left: 3px solid var(--app-violet); }
.plan-tl { font-size: 12px; color: var(--app-muted); font-family: var(--app-font-mono); margin-bottom: 8px; }

/* Roadmap */
.roadmap { display: flex; flex-direction: column; gap: 0; }
.roadmap-phase { display: flex; gap: 14px; }
.phase-connector { position: relative; width: 32px; display: flex; flex-direction: column; align-items: center; border-left: 2px solid; padding-bottom: 16px; }
.phase-dot { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; font-weight: 700; margin-left: -15px; }
.phase-card { flex: 1; padding: 14px; border-radius: 10px; border: 1px solid var(--el-border-color); border-left: 3px solid; margin-bottom: 12px; }
.phase-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.phase-name { font-weight: 600; font-size: 14px; }

/* Generate area */
.generate-area { text-align: center; padding: 16px 0; }
.generate-desc { color: var(--app-muted); font-size: 13px; margin-bottom: 12px; }

/* Dev card */
.dev-card { padding: 14px; border-radius: 10px; border: 1px solid var(--el-border-color); }

/* References */
.ref-title { display: flex; align-items: center; gap: 8px; }
.ref-doc-title { font-weight: 600; font-size: 13px; }
.ref-chunks { display: flex; flex-direction: column; gap: 10px; }
.ref-chunk-item { padding: 10px; border-radius: 8px; background: var(--el-fill-color-light); }
.ref-chunk-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.ref-chunk-num { font-size: 12px; font-weight: 600; color: var(--app-muted); }

/* Loading state */
.inline-loading { text-align: center; padding: 40px 0; color: var(--app-muted); }
.inline-loading p { margin: 8px 0 0; }

/* Tab body */
.tab-body { padding: 0; }
.tab-body :deep(.el-tabs__header) { margin: 0 20px; }
.tab-body :deep(.el-tabs__content) { padding: 16px 20px 20px; }

/* List */
ul { padding-left: 16px; margin: 4px 0; }
h4 { margin: 12px 0 6px; }
h5 { margin: 0 0 8px; }

.mt { margin-top: 16px; }
.mb { margin-bottom: 8px; }

/* ===== Responsive ===== */
@media (max-width: 1024px) {
  .hero-metrics { grid-template-columns: 1fr 1fr; }
  .input-split { grid-template-columns: 1fr; }
  .rag-confidence-metrics { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 768px) {
  .analysis-hero { padding: 18px; }
  .hero-metrics { grid-template-columns: 1fr; }
  .score-center { flex-direction: column; text-align: center; }
  .action-bar { flex-direction: column; align-items: flex-start; }
  .pipeline-status { grid-template-columns: 1fr; }
  .rag-confidence-metrics { grid-template-columns: 1fr; }
  .rag-breakdown { grid-template-columns: 1fr; }
}

@media (max-width: 560px) {
  .card-body { padding: 16px; }
  .hero-metrics { grid-template-columns: 1fr; }
  .hero-title-main h1 { font-size: 26px; }
}
</style>
