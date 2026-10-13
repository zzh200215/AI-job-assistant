<template>
  <div class="page-shell rr-page">
    <div class="page-header">
      <div>
        <h2>简历评估报告</h2>
        <div class="page-header-sub">
          {{
            report ? headerName : '六个模块：小结、评分概览、竞争分析、修改建议、面试预演、投递策略'
          }}
        </div>
      </div>
      <div class="rr-header-actions">
        <el-button @click="backToCenter">返回简历中心</el-button>
        <el-button type="primary" :loading="downloading" :disabled="!report" @click="doDownload">
          <el-icon><Download /></el-icon> 下载独立 HTML
        </el-button>
      </div>
    </div>

    <el-alert v-if="pageError" :title="pageError" type="error" show-icon :closable="false" />

    <!-- 还没有报告：作业入口与状态屏 -->
    <section v-if="!report" class="rr-card">
      <h3 class="rr-h3">开始生成报告</h3>
      <p class="rr-lead">
        挑一份简历，可选一个目标岗位。报告会分几节依次生成，通常需要几分钟——这一页会自己刷新结果，
        中途离开也不会重复生成。
      </p>
      <div class="rr-form">
        <label class="rr-field">
          <span class="rr-field-label">简历</span>
          <el-select v-model="form.resumeId" placeholder="选择一份简历" :loading="optionsLoading">
            <el-option v-for="r in resumes" :key="r.id" :label="resumeLabel(r)" :value="r.id" />
          </el-select>
        </label>
        <label class="rr-field">
          <span class="rr-field-label">目标岗位（可选）</span>
          <el-select v-model="form.jdId" clearable placeholder="不选则按简历关键词判断方向">
            <el-option
              v-for="j in jdOptions"
              :key="j.id"
              :label="j.title || '未命名岗位'"
              :value="j.id"
            />
          </el-select>
        </label>
        <label class="rr-field rr-field-wide">
          <span class="rr-field-label">目标岗位名称（可选）</span>
          <el-input
            v-model="form.targetPosition"
            placeholder="例如：RAG 应用开发工程师"
            maxlength="80"
          />
        </label>
      </div>
      <div class="rr-start-row">
        <el-button
          type="primary"
          :loading="job.loading"
          :disabled="!form.resumeId"
          @click="startReport"
        >
          {{ job.id ? '重新生成报告' : '开始生成报告' }}
        </el-button>
        <span v-if="job.loading" class="rr-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          正在逐节生成，请稍候
        </span>
        <span v-else-if="job.status === 'failed'" class="rr-loading"
          >这一份报告没能生成，可以再点一次</span
        >
      </div>
    </section>

    <template v-if="report">
      <nav class="rr-nav" aria-label="报告模块快速导航">
        <a
          v-for="m in MODULES"
          :key="m.anchor"
          :href="`#${m.anchor}`"
          :class="['rr-nav-link', activeAnchor === m.anchor ? 'is-active' : '']"
          @click.prevent="jumpTo(m.anchor)"
          >{{ m.label }}</a
        >
      </nav>

      <!-- 模块一：小结（不设小标题，一段话） -->
      <section id="m-summary" class="rr-card">
        <p class="rr-verdict">
          <span>方向定位：{{ textOr(report.verdict.direction, '未定') }}</span>
          <span class="rr-sep">｜</span>
          <span
            >目标等级：{{ textOr(report.verdict.target_level, '未定')
            }}<template v-if="report.verdict.level_basis"
              >（{{ report.verdict.level_basis }}）</template
            ></span
          >
          <span class="rr-sep">｜</span>
          <span
            >评级：<strong :style="{ color: scoreToneTextColor(report.total_score) }">{{
              gradeText
            }}</strong></span
          >
          <span class="rr-sep">｜</span>
          <span>日期：{{ textOr(report.report_date, '—') }}</span>
        </p>
      </section>

      <!-- 模块二：一、评分概览 -->
      <section id="m-score" class="rr-card">
        <h3 class="rr-h3">
          一、评分概览（七维 100 分）
          <span class="rr-hint">每维满分不同，下面的进度条画的是「拿到该维满分的几成」</span>
        </h3>
        <table class="rr-table">
          <thead>
            <tr>
              <th>维度</th>
              <th class="rr-th-num">得分 / 满分</th>
              <th>待优化点</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="dim in report.dimensions" :key="dim.key" class="rr-dim-row">
              <td class="rr-dim-name">{{ dim.label }}</td>
              <td class="rr-dim-score">
                <strong :style="{ color: scoreToneTextColor(dimRate(dim)) }">
                  {{ dim.score === null ? '未评分' : `${dim.score} / ${dim.full}` }}
                </strong>
                <el-progress
                  v-if="dim.score !== null"
                  class="rr-dim-bar"
                  :percentage="dimRate(dim)"
                  :color="scoreToneColor(dimRate(dim))"
                  :stroke-width="6"
                  :show-text="false"
                />
                <p v-else class="rr-dim-none">本次分析未给出该维度评分</p>
              </td>
              <td class="rr-dim-note">
                <span v-if="!dim.note" class="rr-muted">本次分析没有为这一维写出待优化点</span>
                <template v-else>
                  <el-tag
                    v-if="!scoreToneAtLeast(dimRate(dim), 'good')"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    这维拖后腿
                  </el-tag>
                  {{ dim.note }}
                </template>
                <p v-if="dim.missing_keywords?.length" class="rr-dim-missing">
                  没看到的词：{{ dim.missing_keywords.join('、') }}
                </p>
              </td>
            </tr>
            <tr class="rr-total-row">
              <td>合计</td>
              <td class="rr-dim-score">
                <strong :style="{ color: scoreToneTextColor(report.total_score) }">
                  {{ report.total_score === null ? '未评分' : `${report.total_score} / 100` }}
                </strong>
              </td>
              <td class="rr-dim-note">{{ gradeText }}</td>
            </tr>
          </tbody>
        </table>
        <p class="rr-grade">
          {{ textOr(report.grade_scale, '等级：A 85 以上 / B 75–84 / C 65–74 / D 64 及以下') }}。
          分数代表的是现在这份简历的竞争力，不是你的能力上限。<template
            v-if="report.grade && report.grade_desc"
          >
            {{ report.grade }}：{{ report.grade_desc }}</template
          >
        </p>
        <div v-if="report.to_next_grade.length" class="rr-next-grade">
          <strong>距上一档还差：</strong>
          <ul class="rr-list">
            <li v-for="(item, i) in report.to_next_grade" :key="i">{{ item }}</li>
          </ul>
        </div>
        <div v-if="report.missing_keywords.length" class="rr-missing-keywords">
          <strong>岗位词表里没看到的词：</strong>
          <span class="rr-kw-row">
            <el-tag
              v-for="kw in report.missing_keywords"
              :key="kw"
              size="small"
              type="info"
              effect="plain"
            >
              {{ kw }}
            </el-tag>
          </span>
        </div>
      </section>

      <!-- 模块三：二、竞争分析 -->
      <section id="m-fit" class="rr-card">
        <h3 class="rr-h3">二、竞争分析</h3>
        <p class="rr-fit-line">
          <strong>方向定位</strong>：{{ textOr(report.verdict.direction, '未定') }}
          <template v-if="report.verdict.direction_basis"
            >——{{ report.verdict.direction_basis }}</template
          >
        </p>
        <p class="rr-fit-line">
          <strong>竞争力档位</strong>：
          <span class="rr-badge">{{ textOr(competition.positioning_badge, '未给出档位') }}</span>
          ——{{ textOr(competition.positioning_note, '本次分析未给出定位说明') }}
          <span class="rr-muted">
            （这一档评的是背景在同类人里站哪，与上面那一格的「这份简历做得好不好」不是一回事）
          </span>
        </p>
        <ul class="rr-bul">
          <li v-for="(item, i) in competition.cards" :key="`c${i}`">
            <strong>能打的牌</strong>：{{ item }}
          </li>
          <li v-for="(item, i) in competition.gaps" :key="`g${i}`">
            <strong>要补的短板</strong>：{{ item }}
          </li>
          <li v-for="(item, i) in competition.advice" :key="`a${i}`">
            <strong>针对性建议</strong>：{{ item }}
          </li>
          <li v-if="competition.salary_note">
            <strong>{{ competition.salary_provided ? '期望薪资' : '薪资参考' }}</strong
            >：{{ competition.salary_note }}
            <span v-if="!competition.salary_provided" class="rr-muted">
              （你没填期望薪资，这一段是按目标等级给的参考区间）
            </span>
          </li>
        </ul>
        <p v-if="!competitionRows" class="rr-muted">本次分析未给出可打的牌与要补的短板</p>
      </section>

      <!-- 模块四：三、修改建议（Word 审阅式批改稿） -->
      <section id="m-resume" class="rr-card">
        <h3 class="rr-h3">
          三、修改建议
          <span class="rr-hint">
            在你原简历上直接批改：删除线是建议改掉的原话，下划线是建议改成的内容，右栏批注说明每处为什么这么改
          </span>
        </h3>
        <template v-if="redline">
          <div class="rr-rvbar">
            <span class="rr-stat">{{ redline.stat }}</span>
            <div class="rr-rv-actions">
              <el-switch v-model="cleanOnly" active-text="仅看改后净稿" />
              <el-button size="small" @click="copyCleanDraft">复制净稿</el-button>
            </div>
          </div>
          <div class="rr-cols">
            <div class="rr-paper">
              <div v-for="block in paperBlocks" :key="block.block_id" class="rr-block">
                <div class="rr-block-head">
                  <span class="rr-block-label">{{ block.label }}</span>
                  <span v-if="!block.editable && !cleanOnly" class="rr-manual-hint">
                    这栏请自己在简历文件里改
                  </span>
                </div>
                <p class="rr-block-text">
                  <template v-for="(part, i) in block.parts" :key="i">
                    <span v-if="part.kind === 'text'" class="rr-plain">{{ part.value }}</span>
                    <del v-else-if="part.kind === 'del'" class="rr-del">{{ part.value }}</del>
                    <ins v-else-if="part.kind === 'ins'" class="rr-ins">{{ part.value }}</ins>
                    <sup v-else class="rr-mark">{{ part.value }}</sup>
                  </template>
                </p>
              </div>
            </div>
            <aside v-if="!cleanOnly" class="rr-side">
              <p class="rr-side-tip">勾上想采纳的编号，下面的按钮才会写回简历</p>
              <div
                v-for="note in redlineNotes"
                :key="note.mark"
                :class="['rr-note', note.key ? 'rr-note-key' : '']"
              >
                <div class="rr-note-head">
                  <el-checkbox
                    :model-value="pickedMarks.includes(note.mark)"
                    :disabled="!note.editable"
                    @change="togglePicked(note)"
                  >
                    {{ note.mark }}
                  </el-checkbox>
                  <el-tag v-if="note.key" size="small" type="danger" effect="dark">关键</el-tag>
                  <span v-if="!note.editable" class="rr-manual-hint">这栏请自己在简历文件里改</span>
                </div>
                <p class="rr-note-body">{{ note.note }}</p>
                <p class="rr-note-where">{{ note.label }}</p>
              </div>
              <p v-if="redline.free_note" class="rr-note-free">{{ redline.free_note }}</p>
            </aside>
          </div>

          <div v-if="!cleanOnly" class="rr-apply">
            <el-button
              type="primary"
              :loading="applying"
              :disabled="!pickedMarks.length"
              @click="applyMarks"
            >
              应用已采纳的 {{ pickedMarks.length }} 条
            </el-button>
            <span v-if="applyScoreLine" class="rr-apply-score">{{ applyScoreLine }}</span>
            <span v-else-if="applyResult && applyResult.changed" class="rr-apply-score">
              未指定目标岗位，本次不显示匹配分变化
            </span>
            <span class="rr-apply-hint">只写回你勾选的那几处，其余原文一个字都不动</span>
          </div>

          <el-alert
            v-if="applyError"
            :title="applyError"
            type="error"
            show-icon
            :closable="false"
          />

          <div v-if="applyResult" class="rr-apply-result">
            <p v-if="applyResult.changed" class="rr-apply-ok">
              已写回 {{ appliedLabels.length }} 处：{{
                appliedLabels.join('、') || '（本次没有可写回的段落）'
              }}
            </p>
            <p v-else class="rr-apply-ok">这几处这次没有改动被写回，原简历保持不动</p>
            <p v-if="applyResult.rejected.length" class="rr-apply-rejected">
              另有 {{ applyResult.rejected.length }} 处这次没能写进去，可以重新生成报告再看这一处
            </p>
          </div>
          <p v-if="resumeChanged" class="rr-muted">
            简历内容已更新，上面的批改稿仍是改写前的结果；重新生成一次报告可以拿到新的批改。
          </p>
        </template>
        <p v-else class="rr-missing">
          这一节这次没能生成，其余各节不受影响。可以先照着第二节的待优化点自己过一遍，稍后重跑这一节。
        </p>
      </section>

      <!-- 模块五：四、面试预演 -->
      <section id="m-interview" class="rr-card">
        <h3 class="rr-h3">
          四、面试预演<template v-if="interview && !interview.deferred"
            >（含追问与标准答案）</template
          >
          <span v-if="!interview" class="rr-hint">这一节这次没能生成</span>
          <span v-else-if="interview.deferred" class="rr-hint">这一节现在做价值不大</span>
          <span v-else class="rr-hint">{{ interviewDistributionText }}</span>
        </h3>
        <template v-if="interview">
          <p v-if="interview.deferred" class="rr-deferred">{{ interview.note }}</p>
          <template v-else>
            <div v-for="q in interviewQuestions" :key="q.no" class="rr-question">
              <p class="rr-question-title">
                <span class="rr-question-no">Q{{ q.no }}</span
                >{{ q.question }}
              </p>
              <span class="rr-label">【标准答案】</span>
              <p class="rr-answer">{{ q.answer }}</p>
              <template v-for="(follow, i) in q.followups" :key="i">
                <span class="rr-label rr-label-follow"
                  >【追问 {{ i + 1 }}】（{{ follow.kind }}）</span
                >
                <p class="rr-answer">{{ follow.text }}</p>
              </template>
              <p :class="['rr-status', q.status === '需补强' ? 'rr-status-warn' : '']">
                状态：<template v-if="q.status === '需补强'"
                  >⚠️ 需补强（缺：{{ q.missing.join('、') || '未点名' }}）</template
                ><template v-else>✅ 可答</template>
              </p>
            </div>
            <p v-if="!interviewQuestions.length" class="rr-muted">这次没有给出可用的题目</p>
          </template>
        </template>
        <p v-else class="rr-missing">
          这一节这次没能生成，其余各节不受影响。把第三节改完再重跑这一节，性价比更高。
        </p>
      </section>

      <!-- 模块六：五、投递策略 -->
      <section id="m-boss" class="rr-card">
        <h3 class="rr-h3">
          五、投递策略
          <span class="rr-hint">BOSS 直聘 · 通用投递建议</span>
        </h3>
        <template v-if="strategy">
          <div v-for="(chapter, i) in strategyChapters" :key="i" class="rr-chapter">
            <h4 class="rr-h4">{{ chapter.title }}</h4>
            <template v-for="(blk, j) in chapter.blocks" :key="j">
              <table v-if="blk.kind === 'table'" class="rr-table">
                <thead>
                  <tr>
                    <th v-for="(cell, k) in blk.head" :key="k">{{ cell }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, r) in blk.rows" :key="r">
                    <td v-for="(cell, c) in row" :key="c">
                      <template v-for="(part, p) in inlineParts(cell)" :key="p">
                        <strong v-if="part.kind === 'strong'">{{ part.value }}</strong>
                        <span v-else>{{ part.value }}</span>
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
              <p v-else class="rr-paragraph">
                <template v-for="(part, p) in blk.parts" :key="p">
                  <strong v-if="part.kind === 'strong'">{{ part.value }}</strong>
                  <span v-else>{{ part.value }}</span>
                </template>
              </p>
            </template>
          </div>
          <div v-if="fillins.label || fillins.opener" class="rr-chapter">
            <h4 class="rr-h4">本报告的两处填空</h4>
            <template v-if="fillins.label">
              <p class="rr-paragraph">
                <strong>在线简历一句话标签</strong>（引第三节你写下的那句，别另起一句）：
              </p>
              <p class="rr-quote">{{ fillins.label }}</p>
            </template>
            <p v-if="fillins.opener" class="rr-paragraph">
              <strong>打招呼第一句里的项目亮点</strong>：开场就说这句 ——
              <span class="rr-quote">{{ fillins.opener }}</span>
              。话术模板里那几处【】保持原样不要填死，投递时按每条 JD 改 2–3 个词。
            </p>
          </div>
        </template>
        <p v-else class="rr-missing">这一节的定稿文本没能读出来，报告里没有替代内容。</p>
      </section>

      <el-button v-if="showBackTop" class="rr-back-top" circle @click="backToTop">
        <el-icon><ArrowUp /></el-icon>
      </el-button>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUp, Download, Loading } from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import { createAgentTaskPoller } from '@/utils/agentTaskPolling'
import { userErrorCopy } from '@/utils/requestTracing'
import {
  applyReportRedline,
  createReportJob,
  downloadReportHtml,
  getReportJob,
  getResumeList,
} from '@/api/resume'
import { getJDList } from '@/api/jd'
import { scoreToneAtLeast, scoreToneColor, scoreToneTextColor } from '@/utils/scoreTone'

/* 锚点与文案由 `docs/resume-report-spec.md` §1 钉住，与后端 `report_html_lint.MODULES` 同一张表：
   两份交付物（应用内这一页、可下载的独立 HTML）必须指向同一批 id，导航才不会各跳各处。 */
const MODULES = [
  { anchor: 'm-summary', label: '小结' },
  { anchor: 'm-score', label: '一、评分概览' },
  { anchor: 'm-fit', label: '二、竞争分析' },
  { anchor: 'm-resume', label: '三、修改建议' },
  { anchor: 'm-interview', label: '四、面试预演' },
  { anchor: 'm-boss', label: '五、投递策略' },
]

/* 一次报告最多三发模型调用，所以预算 = 改写那一族的 150 秒 × 3。
   与改写作业相同的纪律：每一趟请求都是毫秒级返回，这里**不带** per-request 超时。 */
const REPORT_POLL_INTERVAL_MS = 2000
const REPORT_POLL_MAX_ATTEMPTS = 225
// 高亮当前模块的判定线：导航条贴在顶上，模块标题滚到这条线以下才算"正在看它"
const NAV_OFFSET_PX = 160

const route = useRoute()
const router = useRouter()

const resumes = ref([])
const jdOptions = ref([])
const optionsLoading = ref(false)
const form = reactive({ resumeId: null, jdId: null, targetPosition: '' })

const job = reactive({ id: null, status: '', loading: false })
const report = ref(null)
const pageError = ref('')
const activeAnchor = ref(MODULES[0].anchor)
const showBackTop = ref(false)
const downloading = ref(false)
const cleanOnly = ref(false)
const pickedMarks = ref([])
const applying = ref(false)
const applyError = ref('')
const applyResult = ref(null)
const resumeChanged = ref(false)

// 卸载之后轮询器落地的那一发（rejectOnStop）不许再弹提示，也不许再写这几个状态
let alive = true

const textOr = (value, fallback) =>
  value === null || value === undefined || value === '' ? fallback : value

const competition = computed(() => report.value?.competition || {})
const redline = computed(() => report.value?.redline || null)
const interview = computed(() => report.value?.interview || null)
const strategy = computed(() => report.value?.strategy || null)

// §7 那两处填空由后端算（`build_personalization`），这里只引用不重算：
// 应用内这一页与下载的那份 HTML 必须给同一句话。
const fillins = computed(() => {
  const p = report.value?.personalization || {}
  return { label: p.one_line_label || '', opener: p.opener || '' }
})

const headerName = computed(() => {
  const name = report.value?.verdict?.candidate_name
  return name ? `${name} · 六模块评估报告` : '六模块评估报告'
})

const candidateName = computed(
  () => report.value?.verdict?.candidate_name || currentResumeName.value || '简历'
)

const currentResumeName = computed(() => {
  const hit = resumes.value.find((r) => r.id === form.resumeId)
  return hit?.name || hit?.file_name || ''
})

const gradeText = computed(() => {
  const total = report.value?.total_score
  const grade = report.value?.grade
  if (total === null || total === undefined) return grade ? `${grade}（未评分）` : '未知（未评分）'
  return `${grade || '未知'}（${total}/100）`
})

/* 七维满分各不相同（5 到 20），所以色调与进度条都按"拿到该维满分的几成"算：
   直接拿原始分上色，个人优势那一档最高也只有 5 分，会被读成一个大红项。
   未评分不是 0 分，所以那一行既不画条也不上色（`dimRate` 只在 `score` 是数字时被用到）。 */
function dimRate(dim) {
  if (typeof dim?.score !== 'number' || !dim?.full) return 0
  return Math.round((dim.score / dim.full) * 100)
}

const competitionRows = computed(() => {
  const c = competition.value
  return (
    (c.cards?.length || 0) +
    (c.gaps?.length || 0) +
    (c.advice?.length || 0) +
    (c.salary_note ? 1 : 0)
  )
})

const interviewDistributionText = computed(() => {
  const dist = interview.value?.distribution || {}
  const kind = Object.entries(dist.by_kind || {})
    .map(([name, count]) => `${name} ${count}`)
    .join(' / ')
  const project = Object.entries(dist.by_project || {})
    .map(([name, count]) => `${name} ${count} 题`)
    .join('、')
  return `共 ${dist.total ?? 0} 题；题型分布：${kind || '未分类'}；${project || '未分组'}；需补强 ${
    dist.weak ?? 0
  } 题`
})

const redlineBlocksById = computed(() => {
  const map = {}
  for (const block of redline.value?.blocks || []) map[block.block_id] = block
  return map
})

/**
 * 左栏按 `sections` 顺序把原简历全部铺开，命中的地方就地标记（§4：一段都不许省）。
 * 「仅看改后净稿」摘掉 `del` 与上标编号、把 `ins` 退回正文——句子还是那句句子，只是不再带记号。
 */
const paperBlocks = computed(() => {
  const byId = redlineBlocksById.value
  const sections = report.value?.sections?.length
    ? report.value.sections
    : (redline.value?.blocks || []).map((block) => ({ ...block }))
  return sections.map((section) => {
    const block = byId[section.block_id]
    const marked = markParts(section.text || block?.text || '', block?.edits || [])
    // 净稿 = 原文摘掉 `del` 与编号、把 `ins` 当成正文留下；与「仅看改后净稿」那个开关看到的是同一份
    const cleanText = marked
      .filter((part) => part.kind === 'text' || part.kind === 'ins')
      .map((part) => part.value)
      .join('')
    return {
      block_id: section.block_id,
      label: section.label || block?.label || '原文',
      editable: block ? block.editable !== false : section.editable !== false,
      parts: cleanOnly.value ? [{ kind: 'text', value: cleanText }] : marked,
      cleanText,
    }
  })
})

const cleanDraft = computed(() =>
  paperBlocks.value.map((block) => `${block.label}\n${block.cleanText}`).join('\n\n')
)

/** §8：这一页要能拿走一份干净、可直接投递的文本。拼装逻辑只有这一份，与左栏同源。 */
async function copyCleanDraft() {
  try {
    await navigator.clipboard.writeText(cleanDraft.value)
    ElMessage.success('净稿已复制，可以直接贴进简历文件')
  } catch {
    ElMessage.warning('复制没成功，请切到「仅看改后净稿」后手动选中复制')
  }
}

/**
 * 把 `del`/`ins`/编号插回原文的那几个位置。
 * 与渲染器同一套规则：按编号顺序找 `del` 的第一处命中，找不到就不标（宁可少标，不猜位置）。
 */
function markParts(text, edits) {
  if (!edits.length) return [{ kind: 'text', value: text }]
  const parts = []
  let cursor = 0
  for (const edit of [...edits].sort((a, b) => a.mark - b.mark)) {
    const at = text.indexOf(edit.del || '', cursor)
    if (at < 0) continue
    if (at > cursor) parts.push({ kind: 'text', value: text.slice(cursor, at) })
    parts.push({ kind: 'del', value: edit.del })
    if (edit.ins) parts.push({ kind: 'ins', value: edit.ins })
    parts.push({ kind: 'mark', value: edit.mark })
    cursor = at + edit.del.length
  }
  parts.push({ kind: 'text', value: text.slice(cursor) })
  return parts
}

const interviewQuestions = computed(() =>
  (interview.value?.questions || []).map((q) => ({
    no: q.no,
    question: q.question || '',
    answer: q.answer || '',
    status: q.status || '',
    missing: Array.isArray(q.missing) ? q.missing : [],
    followups: Array.isArray(q.followups) ? q.followups : [],
  }))
)

const strategyChapters = computed(() =>
  (strategy.value?.chapters || []).map((chapter) => ({
    title: chapter.title || '',
    blocks: chapterBlocks(chapter),
  }))
)

const redlineNotes = computed(() => {
  const notes = []
  for (const block of redline.value?.blocks || []) {
    for (const edit of block.edits || []) {
      notes.push({
        mark: edit.mark,
        note: edit.note,
        key: !!edit.key,
        block_id: block.block_id,
        label: block.label,
        editable: block.editable !== false,
      })
    }
  }
  return notes
})

/** 非 `editable` 的块（基本信息、经历抬头、技术栈、教育背景）只能在简历文件里自己改，所以点不进勾选。 */
function togglePicked(note) {
  if (!note.editable) return
  const at = pickedMarks.value.indexOf(note.mark)
  if (at >= 0) pickedMarks.value.splice(at, 1)
  else pickedMarks.value.push(note.mark)
}

const appliedLabels = computed(() => {
  const labels = []
  for (const row of applyResult.value?.applied || []) {
    const hit = paperBlocks.value.find((b) => b.block_id === row.block_id)
    labels.push(hit?.label || row.block_id)
  }
  return labels
})

const applyScoreLine = computed(() => {
  const score = applyResult.value?.score
  const before = score?.before?.score
  const after = score?.after?.score
  if (typeof before !== 'number' || typeof after !== 'number') return ''
  const delta =
    typeof score.delta === 'number' ? `（${score.delta >= 0 ? '+' : ''}${score.delta}）` : ''
  return `匹配分 ${before} → ${after}${delta}`
})

/* 轮询：**复用**既有的 `createAgentTaskPoller`，与改写作业同一族纪律——
   卸载即落地（`rejectOnStop`）、在途不建第二个作业、失败与超时只说我们自己的那句。
   载荷里**没有**服务端的失败原因，所以屏幕上出现的只可能是下面这两句措辞。 */
const poller = createAgentTaskPoller(
  {
    getAgentTask: (jobId) => getReportJob(jobId),
    getAgentSteps: async () => ({ steps: [] }),
  },
  {
    rejectOnStop: true,
    setPollingState(value) {
      job.loading = value
    },
  }
)

onUnmounted(() => {
  alive = false
  poller.stopPolling()
  window.removeEventListener('scroll', onScroll)
})

onMounted(async () => {
  window.addEventListener('scroll', onScroll, { passive: true })
  await loadOptions()
  const resumed = restoreFromQuery()
  if (!resumed) onScroll()
})

/** 刷新或从别处带 `job_id` 进来时接住已有的作业，不再建第二个。 */
async function restoreFromQuery() {
  const jobId = Number(route.query.job_id || 0)
  if (!jobId) return false
  await runJob(jobId)
  return true
}

async function loadOptions() {
  optionsLoading.value = true
  const resumeId = Number(route.query.resume_id || 0) || null
  try {
    const data = await getResumeList({ page: 1, page_size: 50 })
    resumes.value = data?.items || []
  } catch {
    resumes.value = []
    pageError.value = '暂时读不到简历列表，请检查网络后回到这一页重试'
  }
  try {
    const jdData = await getJDList({ page: 1, page_size: 100 })
    jdOptions.value = jdData?.items || []
  } catch {
    // 岗位列表读不出来只是少一个可选项：这一发不是这一页的主数据，下拉留着空、目标岗位名称仍可填
  }
  form.resumeId = resumes.value.some((r) => r.id === resumeId)
    ? resumeId
    : resumes.value[0]?.id || null
  optionsLoading.value = false
}

function resumeLabel(r) {
  return r.name || r.file_name || `简历 #${r.id}`
}

function startReport() {
  if (job.loading || !form.resumeId) return
  pageError.value = ''
  applyResult.value = null
  applyError.value = ''
  runCreate()
}

async function runCreate() {
  job.loading = true
  job.status = 'pending'
  try {
    const created = await createReportJob(form.resumeId, {
      jd_id: form.jdId || null,
      target_position: form.targetPosition || '',
    })
    job.id = created?.job_id ?? null
    if (job.id) rememberJobInQuery(job.id)
    await runJob(job.id, created?.status)
  } catch (err) {
    if (!alive) return
    job.status = 'failed'
    pageError.value = userErrorCopy(err, '这一份报告没能生成，稍后再试')
  } finally {
    if (alive) job.loading = false
  }
}

async function runJob(jobId, knownStatus = '') {
  if (!jobId) return
  job.id = jobId
  job.status = knownStatus || 'pending'
  try {
    const data = await poller.pollTask(jobId, {
      maxPollCount: REPORT_POLL_MAX_ATTEMPTS,
      intervalMs: REPORT_POLL_INTERVAL_MS,
      timeoutMessage: '这一份报告这次没跑完，稍后再试',
      failedMessage: '这一份报告没能生成，稍后再试',
    })
    if (!alive) return
    job.status = data?.status || 'completed'
    report.value = normalizeReport(data?.report)
    pickedMarks.value = defaultPicked(report.value)
    pageError.value = ''
  } catch (err) {
    // 卸载打断了轮询：人不在这屏了，这句给谁看都没有意义
    if (!alive || err?.code === 'polling_stopped') return
    job.status = 'failed'
    pageError.value = userErrorCopy(err, '这一份报告没能生成，稍后再试')
  } finally {
    if (alive) job.loading = false
  }
}

/** 默认把标了「关键」的几条勾上：这一档是必改项，先做这几处的顺序不该靠人再点一遍。 */
function defaultPicked(normalized) {
  const notes = []
  for (const block of normalized?.redline?.blocks || []) {
    for (const edit of block.edits || []) {
      if (edit.key && block.editable !== false) notes.push(edit.mark)
    }
  }
  return notes
}

/**
 * 载荷缺字段时按"这一节没有内容"处理，不猜：维度少一行就画少一行、分数没给就是未评分。
 * 这里造一份默认值等于替服务端说谎。
 */
function normalizeReport(raw) {
  if (!raw || typeof raw !== 'object') return null
  return {
    resume_id: raw.resume_id ?? null,
    jd_id: raw.jd_id ?? null,
    target_position: raw.target_position || '',
    report_date: raw.report_date || '',
    verdict: raw.verdict || {},
    dimensions: (Array.isArray(raw.dimensions) ? raw.dimensions : []).map((dim) => ({
      key: dim.key,
      label: dim.label || dim.key || '',
      full: typeof dim.full === 'number' ? dim.full : 0,
      star: !!dim.star,
      // 缺分数 = 未评分，不是 0 分：这一位是"不知道"，画成 0 会把一整个维度讲成红档
      score: typeof dim.score === 'number' ? dim.score : null,
      note: dim.note || '',
      missing_keywords: Array.isArray(dim.missing_keywords) ? dim.missing_keywords : [],
    })),
    total_score: raw.total_score ?? null,
    grade: raw.grade ?? null,
    grade_desc: raw.grade_desc || '',
    grade_scale: raw.grade_scale || '',
    to_next_grade: Array.isArray(raw.to_next_grade) ? raw.to_next_grade : [],
    missing_keywords: Array.isArray(raw.missing_keywords) ? raw.missing_keywords : [],
    competition: raw.competition || {},
    redline: raw.redline || null,
    interview: raw.interview || null,
    strategy: raw.apply_strategy || null,
    sections: Array.isArray(raw.sections) ? raw.sections : [],
    personalization: raw.personalization || {},
  }
}

async function applyMarks() {
  if (applying.value || !job.id || !pickedMarks.value.length) return
  applying.value = true
  applyError.value = ''
  applyResult.value = null
  try {
    const editableMarks = redlineNotes.value
      .filter((note) => note.editable && pickedMarks.value.includes(note.mark))
      .map((note) => note.mark)
    if (!editableMarks.length) return
    const data = await applyReportRedline(job.id, editableMarks)
    applyResult.value = {
      changed: !!data?.changed,
      applied: Array.isArray(data?.applied) ? data.applied : [],
      rejected: Array.isArray(data?.rejected) ? data.rejected : [],
      score: data?.score || null,
    }
    const written = new Set(applyResult.value.applied.map((row) => row.block_id))
    pickedMarks.value = pickedMarks.value.filter((mark) => {
      const note = redlineNotes.value.find((item) => item.mark === mark)
      return note && !written.has(note.block_id)
    })
    if (data?.changed) {
      resumeChanged.value = true
      ElMessage.success(`已写回 ${applyResult.value.applied.length} 处批改，简历已更新`)
    } else {
      ElMessage.warning('这几处这次没有改动被写回')
    }
  } catch (err) {
    applyError.value = userErrorCopy(err, '这些改动这次没能写回简历')
  } finally {
    applying.value = false
  }
}

/* 独立 HTML 由服务端那一份渲染器产出（§8：前端不提供第二套 HTML 拼装逻辑），
   这一页只负责把那份自包含文件取回来存盘，措辞与导出那一路一致。 */
async function doDownload() {
  if (!job.id || downloading.value) return
  downloading.value = true
  try {
    const blob = await downloadReportHtml(job.id)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `简历评估报告_${candidateName.value}.html`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告已下载')
  } catch {
    ElMessage.error('这份文件这次没能下载下来，稍后再试')
  } finally {
    downloading.value = false
  }
}

/** 段里可能夹 markdown 表格行与 `**粗体**`（投递策略那份定稿就长这样），这里只做最小切分。 */
function chapterBlocks(chapter) {
  const blocks = []
  let table = []
  const flushTable = () => {
    if (!table.length) return
    const head = splitRow(table[0])
    const rows = table
      .slice(2)
      .map(splitRow)
      .filter((row) => row.length)
    if (head.length) blocks.push({ kind: 'table', head, rows })
    table = []
  }
  for (const paragraph of chapter.paragraphs || []) {
    const lines = String(paragraph).split('\n')
    if (lines[0] && lines[0].trim().startsWith('|')) {
      table = table.concat(lines)
      continue
    }
    flushTable()
    blocks.push({ kind: 'paragraph', parts: inlineParts(paragraph) })
  }
  flushTable()
  return blocks
}

function splitRow(line) {
  return String(line)
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function inlineParts(value) {
  const parts = []
  const text = String(value ?? '')
  const re = /\*\*(.+?)\*\*/g
  let cursor = 0
  let hit
  while ((hit = re.exec(text))) {
    if (hit.index > cursor) parts.push({ kind: 'text', value: text.slice(cursor, hit.index) })
    parts.push({ kind: 'strong', value: hit[1] })
    cursor = hit.index + hit[0].length
  }
  if (cursor < text.length) parts.push({ kind: 'text', value: text.slice(cursor) })
  return parts.length ? parts : [{ kind: 'text', value: text }]
}

function rememberJobInQuery(jobId) {
  router.replace({ name: 'resume-report', query: { ...route.query, job_id: String(jobId) } })
}

function jumpTo(anchor) {
  activeAnchor.value = anchor
  const el = document.getElementById(anchor)
  if (el && typeof el.scrollIntoView === 'function')
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onScroll() {
  showBackTop.value = (window.scrollY || 0) > 320
  if (!report.value) return
  let current = MODULES[0].anchor
  for (const item of MODULES) {
    const el = document.getElementById(item.anchor)
    if (el && el.getBoundingClientRect().top <= NAV_OFFSET_PX) current = item.anchor
  }
  activeAnchor.value = current
}

function backToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function backToCenter() {
  router.push({ name: 'resume-center' })
}
</script>

<style scoped>
.rr-page {
  position: relative;
  color: var(--app-text);
}

.rr-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rr-nav {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
  padding: 8px 10px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
}

.rr-nav-link {
  padding: 4px 10px;
  border-radius: var(--app-radius-xs);
  color: var(--app-muted);
  font-size: 13px;
  text-decoration: none;
}

.rr-nav-link.is-active {
  /* 选中那一档的底走 score-soft 那一族：它们在浅色主题与深色工作台里各有一版，
     前景跟着 `--app-text` 走就不出现"浅底压浅字"。 */
  background: var(--app-score-good-soft);
  border: 1px solid var(--app-score-good-soft-line);
  color: var(--app-text);
  font-weight: 700;
}

.rr-card {
  margin-bottom: 14px;
  padding: 18px 20px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-md);
  box-shadow: var(--app-shadow-soft);
}

.rr-h3 {
  margin: 0 0 10px;
  color: var(--app-text);
  font-size: 16px;
  font-weight: 700;
}

.rr-h4 {
  margin: 14px 0 6px;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 700;
}

.rr-hint {
  display: block;
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 400;
}

.rr-lead {
  margin: 0 0 14px;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.7;
}

.rr-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.rr-field {
  display: grid;
  gap: 4px;
}

.rr-field-wide {
  grid-column: 1 / -1;
}

.rr-field-label {
  color: var(--app-muted);
  font-size: 12px;
}

.rr-start-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.rr-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--app-muted);
  font-size: 13px;
}

.rr-verdict {
  margin: 0;
  font-size: 14px;
  line-height: 1.9;
}

.rr-sep {
  margin: 0 8px;
  color: var(--app-line-strong);
}

.rr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.rr-table th,
.rr-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--app-line);
  text-align: left;
  vertical-align: top;
}

.rr-table th {
  color: var(--app-muted);
  font-weight: 600;
}

.rr-th-num {
  width: 120px;
}

.rr-dim-name {
  width: 210px;
  font-weight: 600;
}

.rr-dim-score {
  width: 150px;
}

.rr-dim-bar {
  margin-top: 4px;
}

.rr-dim-none,
.rr-dim-missing {
  margin: 4px 0 0;
  color: var(--app-muted);
  font-size: 12px;
}

.rr-dim-note {
  line-height: 1.7;
}

.rr-total-row td {
  font-weight: 700;
  border-top: 1px solid var(--app-line-strong);
}

.rr-grade {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.8;
}

.rr-next-grade,
.rr-missing-keywords {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.8;
}

.rr-list {
  margin: 4px 0 0;
  padding-left: 18px;
}

.rr-kw-row {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}

.rr-fit-line {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.8;
}

.rr-badge {
  display: inline-block;
  margin: 0 4px;
  padding: 2px 10px;
  border-radius: var(--app-radius-sm);
  background: var(--app-score-good-soft);
  border: 1px solid var(--app-score-good-soft-line);
  color: var(--app-text);
  font-size: 12px;
  font-weight: 700;
}

.rr-bul {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.9;
}

.rr-muted {
  color: var(--app-muted);
}

.rr-rvbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--app-surface-muted);
  border-radius: var(--app-radius-sm);
}

.rr-stat {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.rr-rv-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.rr-cols {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.rr-paper {
  padding-right: 12px;
  border-right: 1px solid var(--app-line);
}

.rr-block {
  margin-bottom: 12px;
}

.rr-block-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rr-block-label {
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
}

.rr-block-text {
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
}

.rr-del {
  color: var(--app-danger);
  text-decoration: line-through;
}

/* 这三处都是**文字**：品牌蓝的本体压在工作台的深色面上实测只有 3.06，够不到正文的 4.5。
   抬的幅度与 `utils/scoreTone.js` 里 good 档那一支同一个数（蓝混白 25% → 5.08）。 */
.rr-ins {
  color: color-mix(in srgb, var(--app-primary), white 25%);
  text-decoration: underline;
}

.rr-mark {
  margin-left: 2px;
  color: color-mix(in srgb, var(--app-primary), white 25%);
  font-size: 11px;
  font-weight: 700;
}

.rr-manual-hint {
  color: var(--app-warning);
  font-size: 12px;
}

.rr-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 520px;
  overflow-y: auto;
}

.rr-side-tip {
  margin: 0;
  color: var(--app-muted);
  font-size: 12px;
}

.rr-note {
  padding: 8px 10px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-surface);
}

.rr-note-key {
  border-color: var(--app-line-strong);
}

.rr-note-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rr-note-body {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.7;
}

.rr-note-where {
  margin: 4px 0 0;
  color: var(--app-muted);
  font-size: 12px;
}

.rr-note-free {
  margin: 0;
  color: var(--app-muted);
  font-size: 12px;
}

.rr-apply {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.rr-apply-score,
.rr-apply-hint {
  color: var(--app-muted);
  font-size: 12px;
}

.rr-apply-result {
  margin-top: 10px;
  font-size: 13px;
}

.rr-apply-ok {
  margin: 0;
  color: var(--app-success);
}

.rr-apply-rejected {
  margin: 4px 0 0;
  color: var(--app-warning);
}

.rr-missing,
.rr-deferred {
  margin: 0;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.8;
}

.rr-question {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--app-line);
}

.rr-question-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
}

.rr-question-no {
  margin-right: 8px;
  color: color-mix(in srgb, var(--app-primary), white 25%);
  font-weight: 700;
}

.rr-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
}

.rr-label-follow {
  margin-top: 6px;
}

.rr-answer {
  margin: 2px 0 6px;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}

.rr-status {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--app-success);
}

.rr-status-warn {
  color: var(--app-warning);
}

.rr-chapter {
  margin-bottom: 12px;
}

.rr-paragraph {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}

/* 引用候选人自己写下的那句话：靠左边框与缩进区分，不加浅底——
   浅底压浅字那一族由 styleDebtRatchet 钉着，这里的区分不需要拿它换。 */
.rr-quote {
  display: inline-block;
  margin: 2px 0 8px;
  padding: 4px 0 4px 12px;
  border-left: 3px solid var(--app-primary);
  color: var(--app-text);
  font-size: 13px;
  line-height: 1.7;
}

.rr-back-top {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 6;
}

@media (max-width: 900px) {
  .rr-cols {
    grid-template-columns: 1fr;
  }

  .rr-paper {
    padding-right: 0;
    border-right: 0;
  }
}

/* §8：打印时只留正文——导航条与回顶部按钮都不该出现在纸上。 */
@media print {
  .rr-nav,
  .rr-back-top {
    display: none;
  }
}
</style>
