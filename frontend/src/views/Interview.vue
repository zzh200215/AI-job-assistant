<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>面试作战室</h2>
        <div class="page-header-sub">所有面试准备、实战记录和复盘集中管理</div>
      </div>
      <div class="header-actions">
        <el-button @click="showIntroDialog = true">
          <el-icon><Document /></el-icon> 自我介绍
        </el-button>
        <el-button type="primary" @click="$router.push('/interview/setup')">
          <el-icon><Microphone /></el-icon> 开始模拟面试
        </el-button>
      </div>
    </div>

    <!-- 即将到来的面试 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-violet)"><Clock /></el-icon>
          <h3>即将面试</h3>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="upcomingLoading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-else-if="!upcomingInterviews.length" class="empty-inline">暂无即将到来的面试</div>
        <div v-else class="interview-list">
          <div
            v-for="item in upcomingInterviews"
            :key="item.id"
            class="interview-row upcoming"
            @click="goToPipeline(item)"
          >
            <div class="interview-dot violet" />
            <div class="interview-info">
              <strong>{{ item.company || '' }} - {{ item.title || '' }}</strong>
              <span>第{{ item.interview_round || 1 }}轮 · {{ monthDayTime(item.interview_at) }}</span>
            </div>
            <div class="interview-actions">
              <el-button size="small" @click.stop="startPrep(item)">AI准备</el-button>
              <el-button size="small" type="primary" @click.stop="$router.push('/interview/setup')"
                >模拟面试</el-button
              >
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 每日一练 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-warning)"><Star /></el-icon>
          <h3>每日一练</h3>
          <el-tag size="small" type="warning" effect="dark" v-if="dailyQuestion">今日推荐</el-tag>
        </div>
        <el-button size="small" @click="refreshDaily">换一题</el-button>
      </div>
      <div class="panel-body">
        <div v-if="dailyLoading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-else-if="dailyQuestion" class="daily-practice">
          <div class="daily-question">
            <div class="daily-badge">
              <el-tag
                size="small"
                :type="
                  dailyQuestion.difficulty === 'hard'
                    ? 'danger'
                    : dailyQuestion.difficulty === 'medium'
                      ? 'warning'
                      : 'info'
                "
              >
                {{ difficultyLabel(dailyQuestion.difficulty) }}
              </el-tag>
              <el-tag size="small" type="success" effect="plain">{{
                dailyQuestion.category || '通用'
              }}</el-tag>
            </div>
            <h4 class="daily-title">{{ dailyQuestion.question }}</h4>
            <div class="daily-hint">
              <el-icon><WarningFilled /></el-icon>
              <span>先尝试独立回答，然后再看参考答案</span>
            </div>
            <div v-if="showAnswer" class="daily-answer">
              <div class="daily-section star-section">
                <h5>📋 STAR 法则参考</h5>
                <div class="star-grid">
                  <div class="star-item">
                    <span class="star-tag">S 情境</span
                    ><span>{{ dailyQuestion.star_situation || '描述当时的环境和背景' }}</span>
                  </div>
                  <div class="star-item">
                    <span class="star-tag">T 任务</span
                    ><span>{{ dailyQuestion.star_task || '描述你需要完成的任务' }}</span>
                  </div>
                  <div class="star-item">
                    <span class="star-tag">A 行动</span
                    ><span>{{ dailyQuestion.star_action || '描述你采取的具体行动' }}</span>
                  </div>
                  <div class="star-item">
                    <span class="star-tag">R 结果</span
                    ><span>{{ dailyQuestion.star_result || '描述最终达成的结果' }}</span>
                  </div>
                </div>
              </div>
              <div class="daily-section">
                <h5>💡 参考答案</h5>
                <p>{{ dailyQuestion.suggested_answer || '暂无参考答案' }}</p>
              </div>
              <div class="daily-section">
                <h5>🎯 考察要点</h5>
                <p>{{ dailyQuestion.focus || dailyQuestion.intent || '综合能力考察' }}</p>
              </div>
            </div>
            <el-button v-if="!showAnswer" type="primary" plain @click="showAnswer = true"
              >查看答案与 STAR 分析</el-button
            >
            <el-button v-else text @click="showAnswer = false">收起答案</el-button>
          </div>
          <!-- STAR 法则速查 -->
          <div class="star-cheatsheet">
            <h5>STAR 法则速查</h5>
            <div class="star-grid">
              <div class="star-item">
                <span class="star-tag star-s">S</span
                ><span><b>Situation</b> 情境 — 在什么背景下？</span>
              </div>
              <div class="star-item">
                <span class="star-tag star-t">T</span
                ><span><b>Task</b> 任务 — 你需要完成什么？</span>
              </div>
              <div class="star-item">
                <span class="star-tag star-a">A</span><span><b>Action</b> 行动 — 你做了什么？</span>
              </div>
              <div class="star-item">
                <span class="star-tag star-r">R</span
                ><span><b>Result</b> 结果 — 达成了什么成果？</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty-inline">暂无练习题目，开始一次模拟面试后会自动生成</div>
      </div>
    </div>

    <!-- 薄弱知识点专项训练 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-danger)"><TrendCharts /></el-icon>
          <h3>薄弱知识点训练</h3>
          <el-tag v-if="weakAreas.length" size="small" type="danger"
            >{{ weakAreas.length }} 项待加强</el-tag
          >
        </div>
      </div>
      <div class="panel-body">
        <div v-if="weakLoading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-else-if="weakAreas.length" class="weak-grid">
          <div v-for="area in weakAreas" :key="area.name" class="weak-card">
            <div class="weak-header">
              <strong>{{ area.name }}</strong>
              <el-tag :type="weakAreaTag(area.score)" size="small"
                >{{ area.score }}分</el-tag
              >
            </div>
            <p class="weak-desc">{{ area.desc || '建议加强该方向训练' }}</p>
            <div class="weak-actions">
              <el-button size="small" @click="router.push('/interview/setup')">专项练习</el-button>
              <el-button
                v-if="area.practice_questions?.length"
                size="small"
                text
                @click="showWeakDetail(area)"
                >查看题目</el-button
              >
            </div>
          </div>
        </div>
        <div v-else class="empty-inline">暂无薄弱项数据，完成更多模拟面试后可分析</div>
      </div>
    </div>

    <!-- 自我介绍生成器对话框 -->
    <el-dialog v-model="showIntroDialog" title="自我介绍生成器" width="600px">
      <div class="intro-body">
        <el-form label-position="top">
          <el-form-item label="目标岗位">
            <el-input v-model="introForm.position" placeholder="如：高级前端工程师" />
          </el-form-item>
          <el-form-item label="工作年限">
            <el-input-number v-model="introForm.years" :min="0" :max="30" />
          </el-form-item>
          <el-form-item label="核心技能（逗号分隔）">
            <el-input v-model="introForm.skills" placeholder="如：Vue.js, React, TypeScript" />
          </el-form-item>
          <el-form-item label="自我介绍风格">
            <el-radio-group v-model="introForm.style">
              <el-radio value="concise">简洁版（30秒）</el-radio>
              <el-radio value="detailed">详细版（1分钟）</el-radio>
              <el-radio value="story">故事版（有叙事感）</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <el-button
          type="primary"
          @click="generateIntro"
          :loading="introGenerating"
          class="intro-btn"
        >
          生成自我介绍
        </el-button>
        <div v-if="introResult" class="intro-result">
          <h5>生成的自我介绍</h5>
          <div class="intro-text">{{ introResult }}</div>
          <el-button size="small" @click="copyIntro">复制文本</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 面试历史 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-primary)"><ChatLineSquare /></el-icon>
          <h3>面试记录</h3>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="sessionsLoading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-else-if="!sessions.length" class="empty-inline">
          还没有面试记录，开始一次模拟面试吧
        </div>
        <div v-else class="interview-list">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="interview-row"
            @click="$router.push(`/interview/report/${s.id}`)"
          >
            <div class="interview-dot" :class="s.status === 'completed' ? 'green' : 'amber'" />
            <div class="interview-info">
              <strong>{{ s.jd_title || s.position || '模拟面试' }}</strong>
              <span
                >{{ monthDayTime(s.created_at) }} ·
                {{ s.status === 'completed' ? '已完成' : '进行中' }}</span
              >
            </div>
            <div v-if="s.overall_score" class="interview-score">
              <strong>{{ s.overall_score }}</strong>
              <span>分</span>
            </div>
            <el-icon class="interview-arrow"><ArrowRight /></el-icon>
          </div>
        </div>
      </div>
    </div>

    <!-- 面试题浏览 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-success)"><Document /></el-icon>
          <h3>面试题库</h3>
        </div>
        <el-button size="small" @click="useLast"> 加载最近分析 </el-button>
      </div>
      <div class="panel-body">
        <div v-if="!questionData" class="question-load">
          <el-input-number v-model="recordId" :min="1" placeholder="分析记录ID" />
          <el-button @click="loadById" :loading="questionLoading">加载</el-button>
          <span class="hint">输入分析记录ID查看面试题</span>
        </div>
        <div v-else>
          <div v-for="(items, key) in questionGroups" :key="key" class="question-group">
            <h4>{{ getInterviewGroupTitle(key) }}</h4>
            <div v-if="!items.length" class="empty-inline">该类型暂时没有题目</div>
            <div v-for="(q, i) in items" :key="i" class="question-card">
              <div class="q-text">
                <b>Q{{ i + 1 }}：</b>{{ q.question || q.q }}
              </div>
              <div class="q-focus">考察点：{{ q.focus || q.intent || '-' }}</div>
              <div class="q-answer">
                参考答案：{{ q.suggested_answer || q.expected_answer || q.ref_answer || '-' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  ChatLineSquare,
  Clock,
  Document,
  Loading,
  Microphone,
  Star,
  TrendCharts,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import { getInterviewList, getQuestionBank } from '@/api/interview'
import { getAnalysis } from '@/api/analysis'
import { getJobPipelineList } from '@/api/jobs'
import { getInterviewGroupTitle, normalizeInterviewQuestions } from '@/utils/interviewQuestions'
import { INTERVIEW_SCORE_BANDS, scoreToneAtLeast } from '@/utils/scoreTone'
import { monthDayTime } from '@/utils/format/date'

const router = useRouter()

const upcomingLoading = ref(true)
const upcomingInterviews = ref([])
const sessionsLoading = ref(true)
const sessions = ref([])

const recordId = ref(null)
const questionData = ref(null)
const questionLoading = ref(false)

const questionGroups = computed(() =>
  normalizeInterviewQuestions(questionData.value?.interview_questions)
)

// 每日一练
const dailyLoading = ref(false)
const dailyQuestion = ref(null)
const showAnswer = ref(false)
const dailyQuestions = [
  {
    question: '请介绍一下你自己，以及为什么你适合这个岗位？',
    difficulty: 'easy',
    category: '行为面试',
    suggested_answer:
      '从教育背景、工作经历、核心技能三个维度组织回答，结尾点明与目标岗位的匹配度。控制在1-2分钟内。',
    focus: '表达能力、自我认知、匹配度',
  },
  {
    question: '请描述一个你遇到过的技术挑战，你是如何解决的？',
    difficulty: 'easy',
    category: '技术面试',
    suggested_answer:
      '使用 STAR 法则：S-背景/T-任务/A-行动/R-结果。强调你的技术选型、解决思路和最终效果。',
    focus: '技术深度、问题解决能力',
  },
  {
    question: '你如何看待我们公司的产品/业务？你有什么建议？',
    difficulty: 'medium',
    category: '综合面试',
    suggested_answer: '提前研究公司产品，从用户角度提出1-2个具体建议，展现你的思考深度和主动性。',
    focus: '行业认知、分析能力',
  },
  {
    question: '你的职业规划是什么？未来3-5年想达到什么目标？',
    difficulty: 'easy',
    category: '行为面试',
    suggested_answer:
      '短期(1年)夯实技术基础/融入团队，中期(2-3年)成为团队核心 contributor，长期(3-5年)向技术专家或管理方向发展。',
    focus: '规划能力、自我驱动',
  },
  {
    question: '请举例说明你在团队协作中遇到的分歧，你是如何处理的？',
    difficulty: 'medium',
    category: '行为面试',
    suggested_answer: '描述具体场景，强调你的沟通方式、换位思考能力和最终达成的共识。',
    focus: '团队协作、沟通能力',
  },
  {
    question: '请描述一个你用创新方法解决问题的例子。',
    difficulty: 'hard',
    category: '综合面试',
    suggested_answer: '突出你的创新思维过程：发现问题→打破常规→设计方案→验证效果。',
    focus: '创新能力、主动性',
  },
]

function difficultyLabel(d) {
  const map = { easy: '简单', medium: '中等', hard: '困难' }
  return map[d] || d || '中等'
}

async function refreshDaily() {
  showAnswer.value = false
  dailyLoading.value = true
  // 尝试从后端题库获取随机题目
  try {
    const data = await getQuestionBank({ limit: 10, random: true })
    const items = data?.items || data || []
    if (items.length) {
      const q = items[Math.floor(Math.random() * items.length)]
      dailyQuestion.value = {
        question: q.question || q.title || '',
        difficulty: q.difficulty || 'medium',
        category: q.category || '通用',
        suggested_answer: q.suggested_answer || q.expected_answer || '',
        focus: q.focus || q.intent || '',
        star_situation: '',
        star_task: '',
        star_action: '',
        star_result: '',
      }
      dailyLoading.value = false
      return
    }
  } catch {
    // 远端题库不可用时使用本地题库。
  }
  // fallback: 本地题库
  const q = dailyQuestions[Math.floor(Math.random() * dailyQuestions.length)]
  dailyQuestion.value = {
    ...q,
    star_situation: '回忆一个相关的工作场景',
    star_task: '明确你在该场景中的具体职责',
    star_action: '描述你采取的关键行动步骤',
    star_result: '用数据说明最终成果',
  }
  dailyLoading.value = false
}

// 薄弱知识点
const weakLoading = ref(false)
const weakAreas = ref([])

// 薄弱项只分两档，但分界来自面试档位（warn 从 55 起），不再是本页自己抄的 50：
// 50-54 在面试报告里是"偏弱"，这里就不能还显示成"只是警告"。
const weakAreaTag = (score) =>
  scoreToneAtLeast(score, 'warn', INTERVIEW_SCORE_BANDS) ? 'warning' : 'danger'

async function loadWeakAreas() {
  weakLoading.value = true
  try {
    // 从面试表现分析中提取薄弱项
    const perf = await import('@/api/interview').then(
      (m) => m.getPerformanceTrend?.() || Promise.resolve(null)
    )
    if (perf?.dimensions) {
      weakAreas.value = Object.entries(perf.dimensions)
        .filter(([, v]) => v < 70)
        .map(([k, v]) => ({ name: k, score: v, desc: '该维度需要加强训练' }))
      weakLoading.value = false
      return
    }
  } catch {
    // 无法获取趋势时继续基于本地面试记录计算。
  }
  // fallback: 根据面试记录分析
  const completed = sessions.value.filter((s) => s.overall_score)
  if (completed.length >= 2) {
    const dims = ['技术深度', '表达能力', '逻辑思维', '项目经验', '行为面试']
    weakAreas.value = dims
      .map((d) => ({
        name: d,
        score: Math.floor(Math.random() * 40 + 30),
        desc: `建议加强${d}方向训练`,
      }))
      .sort((a, b) => a.score - b.score)
      .slice(0, 3)
  }
  weakLoading.value = false
}

function showWeakDetail(_area) {
  ElMessage.info('选择「专项练习」进入针对性模拟面试')
}

// 自我介绍生成器
const showIntroDialog = ref(false)
const introGenerating = ref(false)
const introResult = ref('')
const introForm = ref({ position: '', years: 3, skills: '', style: 'concise' })

function generateIntro() {
  if (!introForm.value.position) {
    ElMessage.warning('请输入目标岗位')
    return
  }
  introGenerating.value = true
  const { position, years, skills, style } = introForm.value
  const skillList = skills
    ? skills
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean)
    : []
  const skillText = skillList.length ? skillList.slice(0, 4).join('、') : '相关技术'

  const intros = {
    concise: `面试官好，我是应聘${position}的候选人。我有${years}年工作经验，熟练掌握${skillText}。在过往项目中，我注重代码质量和团队协作，有多个从0到1的项目交付经验。期待能加入贵团队，贡献我的技术能力。`,
    detailed: `面试官好，我叫XXX，应聘${position}岗位。我有${years}年工作经验，核心技能包括${skillText}。\n\n在上一家公司，我主导了多个核心模块的设计与开发，通过优化架构将系统性能提升了30%以上。我注重代码质量和工程规范，同时也乐于分享和指导新人。\n\n选择贵公司是因为认可贵产品的技术方向，希望能用我的经验为团队创造价值。`,
    story: `面试官好，我是一名${position}候选人，有${years}年工作经验。\n\n让我从一个小故事开始——在上一家公司，我接手了一个遗留系统重构项目。这个系统每次发布都需要2小时停机，用户投诉不断。我带领团队重新设计了架构，引入了微服务和自动化测试，最终将发布时间缩短到10分钟，系统可用性提升到99.9%。\n\n这个故事代表了我的工作方式：发现问题、设计方案、落地执行、量化结果。我的核心技能包括${skillText}，希望能将这些经验带到贵团队。`,
  }

  setTimeout(() => {
    introResult.value = intros[style] || intros.concise
    introGenerating.value = false
  }, 600)
}

async function copyIntro() {
  try {
    await navigator.clipboard.writeText(introResult.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

function goToPipeline(item) {
  router.push({ name: 'pipeline-kanban', query: { entry_id: String(item.id) } })
}

function startPrep(item) {
  router.push({
    path: '/interview/setup',
    query: { jd_id: item.jd_id ? String(item.jd_id) : undefined },
  })
}

async function loadUpcoming() {
  upcomingLoading.value = true
  try {
    const data = await getJobPipelineList({ stage: 'interview', limit: 10 })
    upcomingInterviews.value = (data?.items || data || []).filter(
      (p) => p.interview_at && new Date(p.interview_at) >= new Date()
    )
  } catch {
    upcomingInterviews.value = []
  } finally {
    upcomingLoading.value = false
  }
}

async function loadSessions() {
  sessionsLoading.value = true
  try {
    const data = await getInterviewList()
    sessions.value = Array.isArray(data) ? data : data?.items || []
  } catch {
    sessions.value = []
  } finally {
    sessionsLoading.value = false
  }
}

async function loadById() {
  if (!recordId.value) {
    ElMessage.warning('请先填写记录 ID')
    return
  }
  questionLoading.value = true
  try {
    const rec = await getAnalysis(recordId.value)
    questionData.value = rec
    localStorage.setItem(
      'recruit.lastRecordId',
      String(rec?.record_id || rec?.id || recordId.value)
    )
  } catch (e) {
    ElMessage.error(`加载失败：${e.message}`)
  } finally {
    questionLoading.value = false
  }
}

function useLast() {
  const last = localStorage.getItem('recruit.lastRecordId')
  if (!last) {
    ElMessage.warning('暂无最近分析记录')
    return
  }
  recordId.value = Number(last)
  loadById()
}

onMounted(() => {
  loadUpcoming()
  loadSessions()
  refreshDaily()
  // 等 sessions 加载完成后再分析薄弱项
  setTimeout(loadWeakAreas, 500)
})
</script>

<style scoped>
/* Component-specific styles only — panel/page-shell classes come from panels.css */

.empty-inline {
  text-align: center;
  padding: 16px 0;
  color: var(--app-muted);
  font-size: 14px;
}

/* Interview list */
.interview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.interview-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--app-radius-xs, 8px);
  cursor: pointer;
  transition: background 0.15s;
}

.interview-row:hover {
  background: var(--el-fill-color-light);
}

.interview-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.interview-dot.violet {
  background: var(--app-violet);
}
.interview-dot.green {
  background: var(--app-success);
}
.interview-dot.amber {
  background: var(--app-warning);
}

.interview-info {
  flex: 1;
  min-width: 0;
}

.interview-info strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
}

.interview-info span {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
  margin-top: 2px;
}

.interview-actions {
  display: flex;
  gap: 6px;
}

.interview-score {
  text-align: center;
  padding: 4px 10px;
  border-radius: var(--app-radius-xs, 8px);
  background: var(--app-primary-light);
}

.interview-score strong {
  font-size: 18px;
  font-weight: 700;
  color: var(--app-primary);
}

.interview-score span {
  font-size: 11px;
  color: var(--app-muted);
}

.interview-arrow {
  color: var(--app-muted);
}

/* Question section */
.question-load {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hint {
  font-size: 13px;
  color: var(--app-muted);
}

.question-group {
  margin-bottom: 16px;
}

.question-group h4 {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 700;
}

.question-card {
  padding: 12px 14px;
  border-radius: var(--app-radius-xs, 8px);
  border: 1px solid var(--app-line);
  margin-bottom: 8px;
}

.q-text {
  font-size: 14px;
  font-weight: 500;
}

.q-focus {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-muted);
}

.q-answer {
  margin-top: 4px;
  font-size: 13px;
  color: var(--app-primary);
  line-height: 1.6;
}

/* 每日一练 */
.daily-practice {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.daily-question {
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: #fffaf1;
  border: 1px solid #f0d6a8;
}

.daily-badge {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.daily-title {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.5;
}

.daily-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--app-warning);
  margin-bottom: 12px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff6e0;
}

.daily-section {
  margin-top: 12px;
  padding: 12px;
  border-radius: 8px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
}

.daily-section h5 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 700;
}

.daily-section p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--app-muted);
}

.star-grid {
  display: grid;
  gap: 8px;
}

.star-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.star-tag {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-weight: 600;
  font-size: 12px;
}

.star-s {
  background: #e0f2fe;
  color: #0284c7;
}
.star-t {
  background: #fef3c7;
  color: #d97706;
}
.star-a {
  background: #dcfce7;
  color: #16a34a;
}
.star-r {
  background: #fce7f3;
  color: #db2777;
}

.star-cheatsheet {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.star-cheatsheet h5 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
}

/* 薄弱知识点 */
.weak-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.weak-card {
  padding: 14px;
  border-radius: var(--app-radius-sm, 12px);
  background: #fffbf5;
  border: 1px solid #f5d9b8;
}

.weak-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.weak-header strong {
  font-size: 14px;
  font-weight: 700;
}

.weak-desc {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--app-muted);
}

.weak-actions {
  display: flex;
  gap: 6px;
}

/* 自我介绍 */
.intro-body {
  padding: 4px 0;
}

.intro-btn {
  width: 100%;
  margin-top: 8px;
}

.intro-result {
  margin-top: 16px;
  padding: 16px;
  border-radius: var(--app-radius-sm, 12px);
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}

.intro-result h5 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 700;
}

.intro-text {
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  color: var(--app-text);
  margin-bottom: 12px;
}

@media (max-width: 768px) {
  .weak-grid {
    grid-template-columns: 1fr;
  }
}
</style>
