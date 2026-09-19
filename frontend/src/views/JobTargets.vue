<template>
  <div class="page-shell job-targets-page">
    <div class="page-header">
      <div>
        <h2>求职目标</h2>
        <div class="page-header-sub">
          设定求职方向，AI将根据目标驱动岗位推荐、简历优化和面试题生成
        </div>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建目标
      </el-button>
    </div>

    <section v-if="targets.length" class="target-focus-strip" aria-label="求职目标摘要">
      <div class="target-focus-main">
        <span class="target-focus-label">当前主目标</span>
        <strong>{{ primaryTarget?.name || '尚未指定主目标' }}</strong>
        <p>
          {{
            primaryTarget
              ? `${primaryTarget.position || '目标岗位'}${primaryTarget.cities?.length ? ` · ${primaryTarget.cities.join(' / ')}` : ''}`
              : '选择一个优先目标，让推荐、分析和面试准备保持同一方向。'
          }}
        </p>
      </div>
      <div class="target-focus-metrics">
        <div>
          <b>{{ targets.length }}</b
          ><span>目标方向</span>
        </div>
        <div>
          <b>{{ highPriorityCount }}</b
          ><span>高优先级</span>
        </div>
        <div>
          <b>{{ totalApplications }}</b
          ><span>关联投递</span>
        </div>
      </div>
      <div class="target-focus-action">
        <span class="target-focus-label">下一步</span>
        <p>从主目标进入岗位市场，验证目标与真实机会的匹配度。</p>
        <el-button size="small" type="primary" @click="$router.push('/jobs/search')"
          >查看岗位市场</el-button
        >
      </div>
    </section>

    <!-- 目标列表 -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>

    <div v-else-if="loadError" class="load-error">
      <div>
        <strong>求职目标加载失败</strong>
        <span>{{ loadError }}</span>
      </div>
      <el-button @click="loadTargets">重新加载</el-button>
    </div>

    <div v-else-if="!targets.length" class="empty-state">
      <el-icon :size="48" color="var(--app-muted)"><Aim /></el-icon>
      <h3>还没有求职目标</h3>
      <p>设定目标后，AI会根据你的方向精准推荐岗位和优化简历</p>
      <el-button type="primary" @click="openCreate">创建第一个目标</el-button>
    </div>

    <div v-else class="targets-grid">
      <div
        v-for="t in targets"
        :key="t.id"
        class="target-card"
        :class="{ primary: t.is_primary }"
        @click="openDetail(t)"
      >
        <div class="target-header">
          <div class="target-name-row">
            <el-tag v-if="t.is_primary" type="danger" size="small" effect="dark">主目标</el-tag>
            <el-tag v-else :type="priorityType(t.priority)" size="small">{{
              priorityLabel(t.priority)
            }}</el-tag>
            <h3>{{ t.name }}</h3>
          </div>
          <el-dropdown trigger="click" @command="(cmd) => handleCommand(cmd, t)" @click.stop>
            <el-icon class="more-btn"><MoreFilled /></el-icon>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item v-if="!t.is_primary" command="primary"
                  >设为主目标</el-dropdown-item
                >
                <el-dropdown-item command="delete" divided style="color: var(--app-danger)"
                  >删除</el-dropdown-item
                >
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="target-meta">
          <span v-if="t.position"
            ><el-icon><Briefcase /></el-icon> {{ t.position }}</span
          >
          <span v-if="t.industry"
            ><el-icon><OfficeBuilding /></el-icon> {{ t.industry }}</span
          >
          <span v-if="t.cities?.length"
            ><el-icon><Location /></el-icon> {{ t.cities.join(' / ') }}</span
          >
          <span v-if="t.salary_min || t.salary_max"
            ><el-icon><Coin /></el-icon> {{ formatSalary(t) }}</span
          >
        </div>

        <div v-if="t.skills?.length" class="target-skills">
          <el-tag v-for="sk in t.skills.slice(0, 5)" :key="sk" size="small" type="info">{{
            sk
          }}</el-tag>
          <span v-if="t.skills.length > 5" class="more-skills">+{{ t.skills.length - 5 }}</span>
        </div>

        <div class="target-stats">
          <div class="stat-item">
            <strong>{{ t.application_count || 0 }}</strong>
            <span>投递</span>
          </div>
          <div class="stat-item">
            <strong>{{ t.interview_count || 0 }}</strong>
            <span>面试</span>
          </div>
          <div class="stat-item">
            <strong>{{ t.offer_count || 0 }}</strong>
            <span>Offer</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑目标' : '新建目标'"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="90px"
        label-position="top"
      >
        <el-form-item label="目标名称" prop="name">
          <el-input v-model="form.name" placeholder="如：高级前端工程师" maxlength="100" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="目标岗位" prop="position">
            <el-input v-model="form.position" placeholder="如：前端开发" />
          </el-form-item>
          <el-form-item label="目标行业" prop="industry">
            <el-input v-model="form.industry" placeholder="如：互联网" />
          </el-form-item>
        </div>
        <el-form-item label="目标城市">
          <el-select
            v-model="form.cities"
            multiple
            filterable
            allow-create
            placeholder="添加城市"
            style="width: 100%"
          >
            <el-option v-for="c in commonCities" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <div class="form-row">
          <el-form-item label="最低薪资(K/月)">
            <el-input-number
              v-model="form.salary_min"
              :min="1"
              :step="1"
              placeholder="如：20"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="最高薪资(K/月)">
            <el-input-number
              v-model="form.salary_max"
              :min="1"
              :step="1"
              placeholder="如：40"
              style="width: 100%"
            />
          </el-form-item>
        </div>
        <el-form-item label="核心技能">
          <el-select
            v-model="form.skills"
            multiple
            filterable
            allow-create
            placeholder="添加技能关键词"
            style="width: 100%"
          >
          </el-select>
        </el-form-item>
        <div class="form-row">
          <el-form-item label="优先级">
            <el-radio-group v-model="form.priority">
              <el-radio-button value="high">高</el-radio-button>
              <el-radio-button value="medium">中</el-radio-button>
              <el-radio-button value="low">低</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="设为主目标">
            <el-switch v-model="form.is_primary" :active-value="1" :inactive-value="0" />
          </el-form-item>
        </div>
        <el-form-item label="备注">
          <el-input
            v-model="form.notes"
            type="textarea"
            :rows="3"
            placeholder="关于这个目标的补充说明"
            maxlength="2000"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import {
  Aim,
  Briefcase,
  Coin,
  Location,
  Loading,
  MoreFilled,
  OfficeBuilding,
  Plus,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  getTargets,
  createTarget,
  updateTarget,
  deleteTarget,
  setPrimaryTarget,
} from '@/api/targets'

const commonCities = [
  '北京',
  '上海',
  '深圳',
  '广州',
  '杭州',
  '成都',
  '南京',
  '武汉',
  '苏州',
  '西安',
]

const loading = ref(true)
const targets = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const submitting = ref(false)
const formRef = ref(null)
const loadError = ref('')

const defaultForm = () => ({
  name: '',
  position: '',
  industry: '',
  cities: [],
  salary_min: null,
  salary_max: null,
  skills: [],
  priority: 'medium',
  is_primary: 0,
  notes: '',
})

const form = ref(defaultForm())
const primaryTarget = computed(
  () => targets.value.find((target) => target.is_primary) || targets.value[0] || null
)
const highPriorityCount = computed(
  () => targets.value.filter((target) => target.priority === 'high').length
)
const totalApplications = computed(() =>
  targets.value.reduce((total, target) => total + Number(target.application_count || 0), 0)
)

const formRules = {
  name: [{ required: true, message: '请输入目标名称', trigger: 'blur' }],
}

function priorityLabel(p) {
  return { high: '高优先', medium: '中优先', low: '低优先' }[p] || p
}

function priorityType(p) {
  return { high: 'danger', medium: 'warning', low: 'info' }[p] || 'info'
}

function formatSalary(t) {
  if (t.salary_min && t.salary_max) return `${t.salary_min}-${t.salary_max}K`
  if (t.salary_min) return `${t.salary_min}K+`
  if (t.salary_max) return `<=${t.salary_max}K`
  return ''
}

async function loadTargets() {
  loading.value = true
  try {
    const data = await getTargets()
    targets.value = data?.targets || data || []
    loadError.value = ''
  } catch (error) {
    targets.value = []
    loadError.value = error?.userMessage || '暂时无法获取目标列表，请检查网络后重试。'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  editId.value = null
  form.value = defaultForm()
  dialogVisible.value = true
}

function openDetail(t) {
  isEdit.value = true
  editId.value = t.id
  form.value = {
    name: t.name || '',
    position: t.position || '',
    industry: t.industry || '',
    cities: t.cities || [],
    salary_min: t.salary_min,
    salary_max: t.salary_max,
    skills: t.skills || [],
    priority: t.priority || 'medium',
    is_primary: t.is_primary || 0,
    notes: t.notes || '',
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    if (isEdit.value) {
      await updateTarget(editId.value, form.value)
      ElMessage.success('目标已更新')
    } else {
      await createTarget(form.value)
      ElMessage.success('目标已创建')
    }
    dialogVisible.value = false
    loadTargets()
  } catch {
    // error handled by interceptor
  } finally {
    submitting.value = false
  }
}

async function handleCommand(cmd, t) {
  if (cmd === 'edit') {
    openDetail(t)
  } else if (cmd === 'primary') {
    try {
      await setPrimaryTarget(t.id)
      ElMessage.success('已设为主目标')
      loadTargets()
    } catch {
      // 请求失败由统一请求层提示。
    }
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`确定删除目标「${t.name}」？`, '删除确认', { type: 'warning' })
      await deleteTarget(t.id)
      ElMessage.success('已删除')
      loadTargets()
    } catch {
      // 用户取消删除或请求失败时保持当前列表。
    }
  }
}

onMounted(loadTargets)
</script>

<style scoped>
.page-shell {
  width: 100%;
  color: var(--app-text);
}

.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
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
  font-size: 15px;
}
.load-error span {
  margin-top: 4px;
  color: var(--app-muted);
  font-size: 13px;
}

.targets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.target-focus-strip {
  display: grid;
  grid-template-columns: minmax(240px, 1.25fr) minmax(230px, 0.85fr) minmax(220px, 0.85fr);
  gap: 0;
  margin-bottom: 18px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-left: 4px solid var(--app-primary);
  border-radius: var(--app-radius-sm, 8px);
  box-shadow: var(--app-shadow-soft);
}

.target-focus-strip > div {
  min-width: 0;
  padding: 18px 20px;
  border-left: 1px solid var(--app-line);
}
.target-focus-strip > div:first-child {
  border-left: 0;
}
.target-focus-label {
  display: block;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.target-focus-main strong {
  display: block;
  margin-top: 7px;
  overflow: hidden;
  color: var(--app-text);
  font-size: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.target-focus-strip p {
  margin: 7px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
}
.target-focus-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.target-focus-metrics div {
  display: grid;
  gap: 4px;
  padding: 2px 10px;
  text-align: center;
}
.target-focus-metrics div + div {
  border-left: 1px solid var(--app-line);
}
.target-focus-metrics b {
  color: var(--app-primary-dark);
  font-size: 23px;
  line-height: 1;
}
.target-focus-metrics span {
  color: var(--app-muted);
  font-size: 12px;
}
.target-focus-action .el-button {
  margin-top: 12px;
}

.target-card {
  padding: 20px;
  border-radius: var(--app-radius-xs, 6px);
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  cursor: pointer;
  transition: all 0.18s;
  position: relative;
}

.target-card:hover {
  box-shadow: var(--app-shadow-lg);
  transform: translateY(-2px);
}

.target-card.primary {
  border-color: var(--app-primary);
  box-shadow: 0 0 0 1px var(--app-primary-light);
}

.target-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.target-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.target-name-row h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.more-btn {
  cursor: pointer;
  color: var(--app-muted);
  padding: 4px;
  border-radius: var(--app-radius-xs, 8px);
  transition: background 0.15s;
}

.more-btn:hover {
  background: var(--el-fill-color-light);
}

/* Meta */
.target-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--app-muted);
}

.target-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Skills */
.target-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.more-skills {
  font-size: 12px;
  color: var(--app-muted);
  line-height: 24px;
}

/* Stats */
.target-stats {
  display: flex;
  gap: 20px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.stat-item {
  text-align: center;
}

.stat-item strong {
  display: block;
  font-size: 18px;
  font-weight: 700;
  font-family: var(--app-font-mono);
}

.stat-item span {
  font-size: 12px;
  color: var(--app-muted);
}

/* Form */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 768px) {
  .target-focus-strip,
  .target-focus-metrics {
    grid-template-columns: 1fr;
  }
  .target-focus-strip > div,
  .target-focus-strip > div:first-child {
    border-top: 1px solid var(--app-line);
    border-left: 0;
  }
  .target-focus-strip > div:first-child {
    border-top: 0;
  }
  .target-focus-metrics {
    gap: 8px;
  }
  .target-focus-metrics div,
  .target-focus-metrics div + div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-top: 1px solid var(--app-line);
    border-left: 0;
    text-align: left;
  }
  .target-focus-action .el-button {
    width: 100%;
  }

  .load-error {
    align-items: flex-start;
    flex-direction: column;
  }

  .targets-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .page-shell :deep(.page-header) {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
