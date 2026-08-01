<template>
  <div class="page-shell offer-compare-page">
    <div class="page-header">
      <div>
        <h2>Offer 决策</h2>
        <div class="page-header-sub">多维对比、AI 辅助决策、谈薪资话术、入职准备清单</div>
      </div>
    </div>

    <section v-if="offers.length" class="offer-decision-strip" aria-label="Offer 决策摘要">
      <div class="offer-lead">
        <span class="decision-label">当前优先项</span>
        <strong>{{ leadingOfferLabel }}</strong>
        <p>
          {{
            leadingOffer
              ? `按当前权重计算为 ${weightedScore(leadingOffer)} 分，仅作为比较起点。`
              : '选择 Offer 后可开始对比。'
          }}
        </p>
      </div>
      <div class="offer-signals">
        <span class="decision-label">决策信号</span>
        <div class="offer-signal-grid">
          <span
            ><b>{{ selectedOffers.length }}</b> 个已选</span
          >
          <span
            ><b>{{ offers.length }}</b> 个待决</span
          >
          <span
            ><b>{{ urgentOfferCount }}</b> 个临近截止</span
          >
        </div>
        <p>{{ urgentOfferMessage }}</p>
      </div>
      <div class="offer-next">
        <span class="decision-label">下一步</span>
        <p>
          {{
            selectedOffers.length >= 2
              ? '先确认个人权重，再生成对比建议。'
              : '至少选择两个 Offer，系统才会生成有意义的取舍建议。'
          }}
        </p>
        <el-button type="primary" size="small" :loading="adviceLoading" @click="prepareComparison">
          {{ selectedOffers.length >= 2 ? '生成决策建议' : '选择用于对比的 Offer' }}
        </el-button>
      </div>
    </section>

    <!-- Offer 列表 -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-primary)"><Trophy /></el-icon>
          <h3>我的 Offer</h3>
        </div>
        <div class="header-actions">
          <el-tag v-if="offers.length" type="success">{{ offers.length }} 个 Offer</el-tag>
          <el-button size="small" @click="loadOffers">刷新</el-button>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="loading" class="empty-inline">
          <el-icon class="is-loading"><Loading /></el-icon> 加载中...
        </div>
        <div v-else-if="loadError" class="load-error">
          <div>
            <strong>Offer 列表加载失败</strong><span>{{ loadError }}</span>
          </div>
          <el-button @click="loadOffers">重新加载</el-button>
        </div>
        <div v-else-if="!offers.length" class="empty-inline">
          <el-empty :image-size="100" description="暂无 Offer，继续投递加油">
            <el-button type="primary" @click="router.push('/jobs/pipeline/kanban')"
              >查看投递看板</el-button
            >
            <el-button @click="router.push('/jobs/recommend')">去岗位推荐</el-button>
          </el-empty>
        </div>
        <div v-else class="offer-list">
          <div
            v-for="o in offers"
            :key="o.id"
            class="offer-row"
            :class="{ selected: selectedIds.includes(o.id) }"
            @click="toggleSelect(o.id)"
          >
            <el-checkbox
              :model-value="selectedIds.includes(o.id)"
              @click.stop
              @change="toggleSelect(o.id)"
            />
            <div class="offer-info">
              <strong>{{ o.company || '未知公司' }} - {{ o.title || '未知岗位' }}</strong>
              <span>{{ o.salary_range || '薪资未定' }}</span>
            </div>
            <div class="offer-meta">
              <span v-if="o.offer_deadline"
                ><el-icon><Clock /></el-icon> {{ formatDate(o.offer_deadline) }} 到期</span
              >
              <span v-if="o.match_score"
                ><el-icon><Histogram /></el-icon> 匹配 {{ Math.round(o.match_score) }}分</span
              >
            </div>
            <el-tag :type="deadlineUrgency(o.offer_deadline)" size="small">{{
              deadlineLabel(o.offer_deadline)
            }}</el-tag>
            <el-button size="small" text @click.stop="showEditOffer(o)"
              ><el-icon><Edit /></el-icon
            ></el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 权重配置 -->
    <div v-if="selectedOffers.length >= 2" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-warning)"><Setting /></el-icon>
          <h3>评分权重配置</h3>
        </div>
        <el-button size="small" text @click="resetWeights">重置默认</el-button>
      </div>
      <div class="panel-body">
        <div class="weight-grid">
          <div v-for="w in weightKeys" :key="w.key" class="weight-item">
            <div class="weight-label">
              <span class="weight-dot" :class="'dot-' + w.color" /> {{ w.label }}
            </div>
            <el-slider
              v-model="weights[w.key]"
              :min="0"
              :max="100"
              :step="5"
              show-input
              size="small"
              style="width: 160px"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 对比表 -->
    <div v-if="selectedOffers.length >= 2" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-violet)"><DataLine /></el-icon>
          <h3>Offer 对比</h3>
        </div>
        <div class="header-actions">
          <el-button size="small" @click="showNegotiation = true">谈薪资话术</el-button>
          <el-button size="small" @click="showChecklist = true">入职清单</el-button>
        </div>
      </div>
      <div class="panel-body">
        <div class="compare-table-wrap">
          <table class="compare-table">
            <thead>
              <tr>
                <th class="dim-col">维度</th>
                <th v-for="o in selectedOffers" :key="o.id">
                  {{ o.company || '未知' }}
                  <div class="offer-sub" v-if="o.offer_details?.total_package">
                    {{ o.offer_details.total_package }}
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>岗位</td>
                <td v-for="o in selectedOffers" :key="o.id">{{ o.title || '-' }}</td>
              </tr>
              <tr>
                <td>公司</td>
                <td v-for="o in selectedOffers" :key="o.id">{{ o.company || '-' }}</td>
              </tr>
              <tr>
                <td>城市</td>
                <td v-for="o in selectedOffers" :key="o.id">{{ o.city || o.location || '-' }}</td>
              </tr>
              <tr>
                <td>底薪</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <strong>{{ o.salary_range || '-' }}</strong>
                </td>
              </tr>
              <tr>
                <td>总包</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  {{ o.offer_details?.total_package || '-' }}
                </td>
              </tr>
              <tr>
                <td>股票/期权</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  {{ o.offer_details?.equity || '-' }}
                </td>
              </tr>
              <tr>
                <td>签字费</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  {{ o.offer_details?.signing_bonus || '-' }}
                </td>
              </tr>
              <tr>
                <td>匹配分</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <span :class="scoreClass(o.match_score)">{{
                    o.match_score ? Math.round(o.match_score) : '-'
                  }}</span>
                </td>
              </tr>
              <tr>
                <td>通勤</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.commute" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>成长空间</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.growth" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>稳定性</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.stability" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>技术栈</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.tech" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>公司发展</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.company_dev" :max="5" size="small" />
                </td>
              </tr>
              <tr>
                <td>文化氛围</td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <el-rate v-model="o._scores.culture" :max="5" size="small" />
                </td>
              </tr>
              <tr class="total-row">
                <td><strong>加权综合评分</strong></td>
                <td v-for="o in selectedOffers" :key="o.id">
                  <strong class="total-score" :class="totalClass(o)">{{ weightedScore(o) }}</strong>
                  <div class="score-breakdown" v-if="showBreakdown === o.id" @click.stop>
                    <div v-for="w in weightKeys" :key="w.key" class="br-item">
                      <span>{{ w.label }}</span
                      ><span>{{ o._scores[w.key] * weights[w.key] }}%</span>
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="compare-actions">
          <el-button type="primary" size="small" @click="generateAdvice" :loading="adviceLoading">
            <el-icon><MagicStick /></el-icon> AI 决策建议
          </el-button>
          <el-button size="small" @click="showAllDetails" v-if="selectedOffers.length > 1"
            >展开明细</el-button
          >
        </div>
      </div>
    </div>

    <!-- 薪资合理性 -->
    <div v-if="selectedOffers.length >= 1" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-success)"><Coin /></el-icon>
          <h3>薪资合理性评估</h3>
        </div>
        <el-button size="small" @click="loadSalaryInsight" :loading="salaryLoading"
          >查询市场薪资</el-button
        >
      </div>
      <div class="panel-body">
        <div v-if="!salaryData" class="empty-inline">
          点击"查询市场薪资"查看该岗位的薪资分位数据
        </div>
        <div v-else>
          <div class="salary-stats">
            <div class="stat-card">
              <span class="stat-label">P25</span><strong>{{ formatK(salaryData.p25) }}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">中位数</span
              ><strong>{{ formatK(salaryData.median) }}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">P75</span><strong>{{ formatK(salaryData.p75) }}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">平均</span><strong>{{ formatK(salaryData.avg) }}</strong>
            </div>
          </div>
          <p v-if="salaryData.sample_count" class="salary-note">
            基于 {{ salaryData.sample_count }} 条岗位数据
          </p>
        </div>
      </div>
    </div>

    <!-- AI 建议 -->
    <div v-if="adviceText" class="panel">
      <div class="panel-header">
        <div class="panel-title-row">
          <el-icon :size="18" color="var(--app-violet)"><MagicStick /></el-icon>
          <h3>AI 决策建议</h3>
        </div>
      </div>
      <div class="panel-body">
        <div class="advice-content" v-for="(line, idx) in adviceLines" :key="idx">
          <p v-if="line.startsWith('【')" class="advice-section-title">{{ line }}</p>
          <p v-else>{{ line }}</p>
        </div>
      </div>
    </div>

    <!-- Offer 编辑弹窗 -->
    <el-dialog v-model="showEditDialog" title="编辑 Offer 详情" width="520px">
      <el-form label-position="top" v-if="editOffer">
        <el-form-item label="底薪"
          ><el-input v-model="editOffer.salary_range" placeholder="如 30K-50K"
        /></el-form-item>
        <el-form-item label="总包预估"
          ><el-input v-model="editForm.total_package" placeholder="如 60W"
        /></el-form-item>
        <el-form-item label="股票/期权"
          ><el-input v-model="editForm.equity" placeholder="如 1000 股 / 4年"
        /></el-form-item>
        <el-form-item label="签字费"
          ><el-input v-model="editForm.signing_bonus" placeholder="如 5W"
        /></el-form-item>
        <el-form-item label="城市"
          ><el-input v-model="editOffer.city" placeholder="如 北京"
        /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="saveOfferDetail">保存</el-button>
      </template>
    </el-dialog>

    <!-- 谈薪资话术弹窗 -->
    <el-dialog v-model="showNegotiation" title="谈薪资话术" width="600px">
      <div class="negotiation-body">
        <div class="negotiation-section">
          <h4>📌 核心原则</h4>
          <ul>
            <li><b>不要先出价：</b>让 HR 先透露预算范围，你再评估</li>
            <li><b>准备数据支撑：</b>用市场薪资数据（P25/P50/P75）作为谈判依据</li>
            <li><b>谈总包而非月薪：</b>综合底薪+年终+股票+签字费+Gap year</li>
            <li><b>保持礼貌和专业：</b>谈判不是对抗，而是寻求双赢</li>
          </ul>
        </div>
        <div class="negotiation-section">
          <h4>🗣️ 常用话术</h4>
          <div class="script-card">
            <div class="script-label">探预算</div>
            <p>
              "感谢
              Offer！在深入讨论薪资之前，想请问一下这个岗位的预算范围大概是多少？这样我也能更好地评估。"
            </p>
          </div>
          <div class="script-card">
            <div class="script-label">要加薪</div>
            <p>
              "非常感谢 Offer。基于我的经验、技能和市场数据，期望薪资在 XXX
              左右。我也在对比其他机会，希望能找到一个双方都满意的方案。"
            </p>
          </div>
          <div class="script-card">
            <div class="script-label">用 Offer 谈</div>
            <p>
              "目前我收到了另一个 Offer，总包在 XXX
              左右。贵公司是我非常心仪的平台，如果能在薪资上接近的话，我会非常倾向于选择贵公司。"
            </p>
          </div>
          <div class="script-card">
            <div class="script-label">考虑期</div>
            <p>
              "非常理解贵公司的预算限制。我可以考虑一段时间吗？同时也想了解一下除了薪资之外是否有其他成长和学习的机会。"
            </p>
          </div>
        </div>
        <div class="negotiation-section">
          <h4>⚠️ 注意事项</h4>
          <ul>
            <li>不要撒谎：不要编造不存在的 Offer</li>
            <li>不要过度谈判：2-3 轮为佳，不要超过 4 轮</li>
            <li>书面确认：口头承诺要落实到书面 Offer</li>
            <li>关注整体：公司品牌、团队、业务方向也是重要因素</li>
          </ul>
        </div>
      </div>
    </el-dialog>

    <!-- 入职清单弹窗 -->
    <el-dialog v-model="showChecklist" title="入职前清单" width="560px">
      <div class="checklist-body">
        <div v-for="(section, sIdx) in checklistSections" :key="sIdx" class="checklist-section">
          <h4>{{ section.title }}</h4>
          <div v-for="(item, iIdx) in section.items" :key="iIdx" class="checklist-item">
            <el-checkbox v-model="item.done">{{ item.text }}</el-checkbox>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Trophy,
  Clock,
  Histogram,
  DataLine,
  Coin,
  MagicStick,
  Loading,
  Setting,
  Edit,
} from '@element-plus/icons-vue'
import { ElMessage } from '@/plugins/element-services'
import { getJobPipelineList } from '@/api/jobs'
import { getSalaryOverview } from '@/api/salary'

const router = useRouter()
const loading = ref(true)
const offers = ref([])
const loadError = ref('')
const selectedIds = ref([])
const salaryLoading = ref(false)
const salaryData = ref(null)
const adviceLoading = ref(false)
const adviceText = ref('')
const showBreakdown = ref(null)
const showNegotiation = ref(false)
const showChecklist = ref(false)
const showEditDialog = ref(false)
const editOffer = ref(null)
const editForm = reactive({ total_package: '', equity: '', signing_bonus: '' })

// 权重配置
const weights = reactive({
  commute: 20,
  growth: 25,
  stability: 15,
  tech: 15,
  company_dev: 15,
  culture: 10,
})
const defaultWeights = {
  commute: 20,
  growth: 25,
  stability: 15,
  tech: 15,
  company_dev: 15,
  culture: 10,
}
const weightKeys = [
  { key: 'commute', label: '通勤', color: 'blue' },
  { key: 'growth', label: '成长空间', color: 'violet' },
  { key: 'stability', label: '稳定性', color: 'green' },
  { key: 'tech', label: '技术栈', color: 'amber' },
  { key: 'company_dev', label: '公司发展', color: 'red' },
  { key: 'culture', label: '文化氛围', color: 'teal' },
]

function resetWeights() {
  Object.assign(weights, defaultWeights)
}

const selectedOffers = computed(() => offers.value.filter((o) => selectedIds.value.includes(o.id)))
const adviceLines = computed(() => (adviceText.value || '').split('\n').filter(Boolean))
const leadingOffer = computed(() => {
  if (!offers.value.length) return null
  return [...offers.value].sort((a, b) => weightedScore(b) - weightedScore(a))[0]
})
const leadingOfferLabel = computed(() => {
  if (!leadingOffer.value) return '等待 Offer 数据'
  return `${leadingOffer.value.company || '未知公司'} - ${leadingOffer.value.title || '未知岗位'}`
})
const urgentOfferCount = computed(
  () =>
    offers.value.filter((offer) => {
      if (!offer.offer_deadline) return false
      const days = Math.ceil((new Date(offer.offer_deadline) - new Date()) / 86400000)
      return days >= 0 && days <= 3
    }).length
)
const urgentOfferMessage = computed(() =>
  urgentOfferCount.value
    ? '存在临近截止的 Offer，先确认书面条件和可协商空间。'
    : '暂无临近截止的 Offer，可按职业优先级完成比较。'
)

// 入职清单
const checklistSections = reactive([
  {
    title: '文书准备',
    items: [
      { text: '确认 Offer 并签署 offer letter', done: false },
      { text: '准备身份证、学历学位证书复印件', done: false },
      { text: '准备离职证明或应届生就业推荐表', done: false },
      { text: '准备银行卡信息（工资卡）', done: false },
    ],
  },
  {
    title: '离职交接',
    items: [
      { text: '提交离职申请（需提前30天）', done: false },
      { text: '完成工作交接文档', done: false },
      { text: '办理社保/公积金转移', done: false },
      { text: '整理个人物品和工作文件', done: false },
    ],
  },
  {
    title: '入职准备',
    items: [
      { text: '了解公司文化和团队架构', done: false },
      { text: '准备 30-60-90 天工作计划', done: false },
      { text: '了解技术栈和开发工具', done: false },
      { text: '开通公司邮箱和系统账号', done: false },
      { text: '了解考勤和报销制度', done: false },
    ],
  },
  {
    title: '个人安排',
    items: [
      { text: '安排通勤路线/租房', done: false },
      { text: '调整作息适应新工作时间', done: false },
      { text: '关闭社交软件的求职状态', done: false },
      { text: '通知猎头和招聘平台暂停推荐', done: false },
    ],
  },
])

function formatDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return d
  }
}

function formatK(v) {
  if (!v) return '-'
  return Number(v).toFixed(1) + 'K'
}

function deadlineUrgency(d) {
  if (!d) return 'info'
  const days = (new Date(d) - new Date()) / 86400000
  if (days <= 1) return 'danger'
  if (days <= 3) return 'warning'
  return 'success'
}

function deadlineLabel(d) {
  if (!d) return '无截止日期'
  const days = Math.ceil((new Date(d) - new Date()) / 86400000)
  if (days < 0) return '已过期'
  if (days === 0) return '今天到期'
  return `${days}天后到期`
}

function scoreClass(v) {
  if (!v) return ''
  if (v >= 80) return 'score-high'
  if (v >= 60) return 'score-mid'
  return 'score-low'
}

// 加权评分
function weightedScore(o) {
  const s = o._scores
  let total = 0
  let maxPossible = 0
  weightKeys.forEach((w) => {
    total += (s[w.key] || 0) * weights[w.key]
    maxPossible += 5 * weights[w.key]
  })
  return maxPossible > 0 ? Math.round((total / maxPossible) * 100) : 0
}

function totalClass(o) {
  const t = weightedScore(o)
  if (t >= 80) return 'score-high'
  if (t >= 60) return 'score-mid'
  return 'score-low'
}

function toggleSelect(id) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

function prepareComparison() {
  if (selectedOffers.value.length < 2) {
    selectedIds.value = offers.value.slice(0, 2).map((offer) => offer.id)
    ElMessage.success('已选择两个 Offer 用于对比')
    return
  }
  generateAdvice()
}

async function loadOffers() {
  loading.value = true
  try {
    const data = await getJobPipelineList({ stage: 'offer', limit: 50 })
    const items = data?.items || data || []
    offers.value = items.map((o) => ({
      ...o,
      city: o.city || o.location || '',
      _scores: { commute: 3, growth: 3, stability: 3, tech: 3, company_dev: 3, culture: 3 },
    }))
    if (items.length <= 4 && items.length >= 2) {
      selectedIds.value = items.map((o) => o.id)
    }
    loadError.value = ''
  } catch (error) {
    offers.value = []
    loadError.value = error?.userMessage || '暂时无法获取 Offer 列表，请检查网络后重试。'
  } finally {
    loading.value = false
  }
}

function showEditOffer(o) {
  editOffer.value = o
  const d = o.offer_details || {}
  editForm.total_package = d.total_package || ''
  editForm.equity = d.equity || ''
  editForm.signing_bonus = d.signing_bonus || ''
  showEditDialog.value = true
}

function saveOfferDetail() {
  if (editOffer.value) {
    editOffer.value.offer_details = {
      ...editOffer.value.offer_details,
      total_package: editForm.total_package,
      equity: editForm.equity,
      signing_bonus: editForm.signing_bonus,
    }
    ElMessage.success('Offer 详情已更新')
    showEditDialog.value = false
  }
}

function showAllDetails() {
  showBreakdown.value = showBreakdown.value ? null : selectedOffers.value[0]?.id
}

async function loadSalaryInsight() {
  const offer = selectedOffers.value[0]
  if (!offer) return
  salaryLoading.value = true
  try {
    const data = await getSalaryOverview({ position: offer.title || '', city: offer.city || '' })
    salaryData.value = data
  } catch {
    ElMessage.error('薪资数据加载失败')
  } finally {
    salaryLoading.value = false
  }
}

async function generateAdvice() {
  if (selectedOffers.value.length < 2) {
    ElMessage.warning('请至少选择 2 个 Offer')
    return
  }
  adviceLoading.value = true
  try {
    const sorted = [...selectedOffers.value].sort((a, b) => weightedScore(b) - weightedScore(a))
    const best = sorted[0]
    const lines = sorted.map((o, i) => {
      const detailParts = []
      if (o.offer_details?.total_package) detailParts.push(`总包${o.offer_details.total_package}`)
      if (o.offer_details?.equity) detailParts.push(`股票${o.offer_details.equity}`)
      if (o.offer_details?.signing_bonus) detailParts.push(`签字费${o.offer_details.signing_bonus}`)
      const detailStr = detailParts.length ? ` (${detailParts.join(', ')})` : ''
      return `${i + 1}. ${o.company}(${o.title}) - 薪资${o.salary_range || '未知'}${detailStr}, 加权评分${weightedScore(o)}分`
    })

    const dimBest = weightKeys.map((w) => {
      const bestDim = [...sorted].sort((a, b) => b._scores[w.key] - a._scores[w.key])[0]
      return { dim: w.label, company: bestDim.company, score: bestDim._scores[w.key] }
    })

    adviceText.value = [
      '【综合评估】',
      ...lines,
      '',
      `【推荐】`,
      `加权评分最高：${best.company} (${weightedScore(best)}分)`,
      '',
      `【各维度最佳】`,
      ...dimBest.map((d) => `- ${d.dim}：${d.company} (${d.score}分)`),
      '',
      '【决策参考】',
      '- 对比总包（底薪+年终+股票+签字费），而不仅是月薪',
      '- 考虑行业趋势：互联网/AI 赛道 vs 传统行业',
      '- 考虑职业发展：平台大小、技术栈成长性、管理路径',
      '- 考虑个人偏好：通勤时间、城市生活成本、团队文化',
      '',
      '【建议】',
      sorted.length >= 2 ? `如果还没有明确的倾向，建议：` : '',
      sorted.length >= 2 ? `1. 联系 ${sorted[0].company} 的 HR，确认是否有谈薪空间` : '',
      sorted.length >= 2 ? `2. 与 ${sorted[1].company} 的面试官或未来同事沟通，感受团队氛围` : '',
      `3. 使用入职清单做好入职准备`,
      '',
      '提示：评分仅供参考，最终决策请结合个人实际情况。',
    ].join('\n')
    ElMessage.success('AI 决策建议已生成')
  } finally {
    adviceLoading.value = false
  }
}

onMounted(() => {
  loadOffers()
})
</script>

<style scoped>
.panel + .panel {
  margin-top: 16px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.offer-decision-strip {
  display: grid;
  grid-template-columns: minmax(230px, 1.2fr) minmax(240px, 1fr) minmax(220px, 0.85fr);
  gap: 0;
  margin-bottom: 16px;
  background: #fff;
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.offer-decision-strip > div {
  min-width: 0;
  padding: 18px 20px;
  border-left: 1px solid var(--app-line);
}

.offer-decision-strip > div:first-child {
  border-left: 0;
}

.decision-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.offer-lead strong {
  display: block;
  margin-top: 7px;
  overflow: hidden;
  color: var(--app-text);
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.offer-decision-strip p {
  margin: 7px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}

.offer-signal-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 9px;
}

.offer-signal-grid span {
  padding: 4px 7px;
  border-radius: 3px;
  background: var(--app-bg);
  color: var(--app-muted);
  font-size: 12px;
}

.offer-signal-grid b {
  color: var(--app-text);
}

.offer-next .el-button {
  margin-top: 12px;
}
.empty-inline {
  text-align: center;
  padding: 16px 0;
  color: var(--app-muted);
  font-size: 14px;
}
.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 20px;
  border: 1px solid #f2c5bf;
  border-radius: 8px;
  background: var(--app-accent-soft);
}
.load-error strong,
.load-error span {
  display: block;
}
.load-error strong {
  color: var(--app-danger);
  font-size: 14px;
}
.load-error span {
  margin-top: 3px;
  color: var(--app-muted);
  font-size: 12px;
}

/* Offer list */
.offer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.offer-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  border: 2px solid transparent;
}
.offer-row:hover {
  background: var(--el-fill-color-light);
}
.offer-row.selected {
  border-color: var(--app-primary);
  background: var(--app-primary-light);
}
.offer-info {
  flex: 1;
}
.offer-info strong {
  display: block;
  font-size: 14px;
}
.offer-info span {
  font-size: 12px;
  color: var(--app-muted);
}
.offer-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
}
.offer-meta span {
  display: flex;
  align-items: center;
  gap: 3px;
}
.offer-sub {
  font-size: 11px;
  color: var(--app-muted);
  font-weight: 400;
}

/* Weight config */
.weight-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.weight-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-radius: 6px;
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}
.weight-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  min-width: 80px;
}
.weight-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot-blue {
  background: var(--app-primary);
}
.dot-violet {
  background: var(--app-violet);
}
.dot-green {
  background: var(--app-success);
}
.dot-amber {
  background: var(--app-warning);
}
.dot-red {
  background: var(--app-danger);
}
.dot-teal {
  background: #0d9488;
}

/* Compare table */
.compare-table-wrap {
  overflow-x: auto;
}
.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.compare-table th,
.compare-table td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  text-align: center;
}
.compare-table th {
  background: var(--el-fill-color-lighter);
  font-weight: 700;
  white-space: nowrap;
}
.compare-table .dim-col {
  text-align: left;
  font-weight: 600;
  background: var(--el-fill-color-lighter);
  min-width: 100px;
}
.compare-table td {
  min-width: 140px;
}
.total-row {
  background: var(--el-fill-color-lighter);
}
.total-score {
  font-size: 20px;
}
.score-breakdown {
  margin-top: 6px;
  font-size: 11px;
  text-align: left;
}
.br-item {
  display: flex;
  justify-content: space-between;
  padding: 2px 0;
}
.compare-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}
.score-high {
  color: var(--app-success);
}
.score-mid {
  color: var(--app-warning);
}
.score-low {
  color: var(--app-danger);
}

/* Salary stats */
.salary-stats {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.stat-card {
  text-align: center;
  padding: 12px 20px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  min-width: 80px;
}
.stat-label {
  display: block;
  font-size: 12px;
  color: var(--app-muted);
}
.stat-card strong {
  font-size: 20px;
  font-weight: 700;
  color: var(--app-primary);
}
.salary-note {
  margin-top: 10px;
  font-size: 12px;
  color: var(--app-muted);
}

/* Advice */
.advice-content {
  line-height: 1.8;
  font-size: 14px;
}
.advice-section-title {
  font-weight: 700;
  font-size: 15px;
  margin: 0 0 4px;
}

/* Negotiation */
.negotiation-body {
  max-height: 60vh;
  overflow-y: auto;
}
.negotiation-section {
  margin-bottom: 20px;
}
.negotiation-section h4 {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 700;
}
.negotiation-section ul {
  margin: 0;
  padding-left: 18px;
}
.negotiation-section li {
  margin-bottom: 6px;
  line-height: 1.6;
  font-size: 14px;
}
.script-card {
  padding: 12px;
  border-radius: 8px;
  background: var(--app-bg);
  border: 1px solid var(--app-line);
  margin-bottom: 8px;
}
.script-label {
  font-weight: 700;
  font-size: 12px;
  color: var(--app-primary);
  margin-bottom: 4px;
}
.script-card p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--app-muted);
}

/* Checklist */
.checklist-body {
  max-height: 60vh;
  overflow-y: auto;
}
.checklist-section {
  margin-bottom: 20px;
}
.checklist-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 700;
}
.checklist-item {
  padding: 6px 0;
  font-size: 14px;
}

@media (max-width: 768px) {
  .offer-decision-strip {
    grid-template-columns: 1fr;
  }

  .offer-decision-strip > div,
  .offer-decision-strip > div:first-child {
    border-top: 1px solid var(--app-line);
    border-left: 0;
  }

  .offer-decision-strip > div:first-child {
    border-top: 0;
  }

  .offer-next .el-button {
    width: 100%;
  }

  .load-error {
    align-items: flex-start;
    flex-direction: column;
  }
  .compare-table th,
  .compare-table td {
    padding: 8px 10px;
    font-size: 13px;
  }
  .offer-meta {
    flex-direction: column;
    gap: 4px;
  }
  .weight-grid {
    flex-direction: column;
  }
}
</style>
