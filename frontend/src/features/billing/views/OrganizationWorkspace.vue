<template>
  <div class="organization-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Organization</p>
        <h2>团队工作区</h2>
        <div class="page-header-sub">管理组织成员、共享知识范围和飞书单点登录。</div>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" circle title="刷新工作区" @click="loadOrganizations" />
        <el-button type="primary" :icon="Plus" @click="createDialog = true">创建组织</el-button>
      </div>
    </header>

    <section class="workspace-strip" v-loading="loadingOrganizations">
      <div class="workspace-select">
        <span class="strip-label">当前工作区</span>
        <el-select
          v-model="selectedId"
          placeholder="选择组织"
          :disabled="!organizations.length"
          @change="switchWorkspace"
        >
          <el-option
            v-for="organization in organizations"
            :key="organization.id"
            :label="organization.name"
            :value="organization.id"
          >
            <span>{{ organization.name }}</span>
            <span class="option-slug">{{ organization.slug }}</span>
          </el-option>
        </el-select>
      </div>
      <template v-if="activeOrganization">
        <div class="workspace-fact">
          <span>我的权限</span>
          <strong>{{ roleLabel(activeOrganization.member_role) }}</strong>
        </div>
        <div class="workspace-fact">
          <span>共享知识</span>
          <strong>已启用</strong>
        </div>
        <div class="workspace-fact">
          <span>飞书登录</span>
          <strong :class="activeOrganization.sso_provider === 'feishu' ? 'state-ready' : ''">
            {{ activeOrganization.sso_provider === 'feishu' ? '已启用' : '未启用' }}
          </strong>
        </div>
      </template>
      <div v-else class="workspace-empty">创建或加入组织后，可在这里管理共享资源。</div>
    </section>

    <template v-if="activeOrganization">
      <section class="panel members-panel">
        <div class="panel-header">
          <div>
            <h3>成员与权限</h3>
            <span class="panel-tip">所有者可调整管理员角色，管理员可维护普通成员。</span>
          </div>
          <el-button v-if="isManager" :icon="UserFilled" @click="memberDialog = true"
            >添加成员</el-button
          >
        </div>
        <div class="panel-body">
          <el-table :data="members" v-loading="loadingMembers" size="default">
            <el-table-column label="成员" min-width="230">
              <template #default="{ row }">
                <div class="member-cell">
                  <span class="member-avatar">{{ row.username?.slice(0, 1).toUpperCase() }}</span>
                  <div>
                    <strong>{{ row.username }}</strong>
                    <span>{{ row.email }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="权限" width="150">
              <template #default="{ row }">
                <el-select
                  v-if="isOwner && row.role !== 'owner'"
                  v-model="row.role"
                  size="small"
                  @change="(role) => updateRole(row, role)"
                >
                  <el-option label="管理员" value="admin" />
                  <el-option label="成员" value="member" />
                </el-select>
                <el-tag v-else :type="roleTagType(row.role)" effect="plain">{{
                  roleLabel(row.role)
                }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="96" align="right">
              <template #default="{ row }">
                <el-button
                  v-if="canRemove(row)"
                  text
                  type="danger"
                  size="small"
                  @click="confirmRemove(row)"
                >
                  移除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <section class="management-grid">
        <article class="panel integration-panel">
          <div class="panel-header">
            <div>
              <h3>飞书单点登录</h3>
              <span class="panel-tip">仅组织管理员可修改。</span>
            </div>
            <el-switch
              :model-value="activeOrganization.sso_provider === 'feishu'"
              :disabled="!isManager || savingSso"
              active-text="启用"
              inactive-text="关闭"
              @change="toggleSso"
            />
          </div>
          <div class="panel-body">
            <p class="integration-copy">
              {{
                activeOrganization.sso_provider === 'feishu'
                  ? '组织成员可通过专属入口跳转飞书进行身份验证。'
                  : '启用后，组织成员可用飞书账号进入该工作区。'
              }}
            </p>
            <div class="sso-url">
              <code>{{ ssoEntryUrl }}</code>
              <el-button text :icon="CopyDocument" title="复制登录链接" @click="copySsoUrl" />
            </div>
          </div>
        </article>

        <article class="panel knowledge-panel">
          <div class="panel-header">
            <div>
              <h3>共享知识范围</h3>
              <span class="panel-tip">个人简历和投递记录始终保持私有。</span>
            </div>
            <el-icon class="knowledge-icon"><Document /></el-icon>
          </div>
          <div class="panel-body">
            <ul class="scope-list">
              <li><span>组织资料</span><strong>成员可检索</strong></li>
              <li><span>上传与维护</span><strong>所有者与管理员</strong></li>
              <li><span>个人资料</span><strong>不自动共享</strong></li>
            </ul>
          </div>
        </article>
      </section>
    </template>

    <el-dialog v-model="createDialog" title="创建组织工作区" width="440px" destroy-on-close>
      <el-form label-position="top" @submit.prevent="handleCreate">
        <el-form-item label="组织名称" required>
          <el-input
            v-model.trim="createForm.name"
            placeholder="例如：华北人才团队"
            maxlength="100"
          />
        </el-form-item>
        <el-form-item label="组织标识" required>
          <el-input
            v-model.trim="createForm.slug"
            placeholder="例如：north-talent"
            maxlength="80"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建工作区</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="memberDialog" title="添加组织成员" width="440px" destroy-on-close>
      <el-form label-position="top" @submit.prevent="handleAddMember">
        <el-form-item label="账号邮箱" required>
          <el-input v-model.trim="memberForm.email" placeholder="member@example.com" />
        </el-form-item>
        <el-form-item label="初始权限">
          <el-select v-model="memberForm.role" style="width: 100%">
            <el-option label="成员" value="member" />
            <el-option v-if="isOwner" label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memberDialog = false">取消</el-button>
        <el-button type="primary" :loading="addingMember" @click="handleAddMember"
          >添加成员</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { CopyDocument, Document, Plus, Refresh, UserFilled } from '@element-plus/icons-vue'

import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import {
  addOrganizationMember,
  configureOrganizationSso,
  createOrganization,
  listOrganizationMembers,
  listOrganizations,
  removeOrganizationMember,
  switchOrganization,
  updateOrganizationMemberRole,
} from '@/api/organization'
const organizations = ref([])
const members = ref([])
const selectedId = ref(null)
const loadingOrganizations = ref(false)
const loadingMembers = ref(false)
const createDialog = ref(false)
const memberDialog = ref(false)
const creating = ref(false)
const addingMember = ref(false)
const savingSso = ref(false)
const createForm = reactive({ name: '', slug: '' })
const memberForm = reactive({ email: '', role: 'member' })

const activeOrganization = computed(() =>
  organizations.value.find((organization) => organization.id === selectedId.value)
)
const isOwner = computed(() => activeOrganization.value?.member_role === 'owner')
const isManager = computed(() => ['owner', 'admin'].includes(activeOrganization.value?.member_role))
const ssoEntryUrl = computed(() => {
  if (!activeOrganization.value) return ''
  const base = import.meta.env.VITE_API_BASE || '/api'
  const apiBase = base.startsWith('http') ? base : `${window.location.origin}${base}`
  return `${apiBase}/organizations/sso/feishu/${activeOrganization.value.slug}/start`
})

function roleLabel(role) {
  return { owner: '所有者', admin: '管理员', member: '成员' }[role] || role
}

function roleTagType(role) {
  return { owner: 'warning', admin: 'success', member: 'info' }[role] || 'info'
}

function canRemove(member) {
  if (!isManager.value || member.role === 'owner') return false
  return isOwner.value || member.role === 'member'
}

async function loadOrganizations() {
  loadingOrganizations.value = true
  try {
    const data = await listOrganizations()
    organizations.value = data.items || []
    const storedId = Number(localStorage.getItem('organization.active_id'))
    const preferredId = data.active_organization_id || storedId
    selectedId.value = organizations.value.some((organization) => organization.id === preferredId)
      ? preferredId
      : organizations.value[0]?.id || null
    if (selectedId.value) {
      localStorage.setItem('organization.active_id', String(selectedId.value))
      await loadMembers()
    } else {
      localStorage.removeItem('organization.active_id')
      members.value = []
    }
  } finally {
    loadingOrganizations.value = false
  }
}

async function loadMembers() {
  if (!selectedId.value) return
  loadingMembers.value = true
  try {
    const data = await listOrganizationMembers(selectedId.value)
    members.value = data.items || []
  } finally {
    loadingMembers.value = false
  }
}

async function switchWorkspace(organizationId) {
  await switchOrganization(organizationId)
  localStorage.setItem('organization.active_id', String(organizationId))
  members.value = []
  await loadMembers()
  ElMessage.success('已切换工作区')
}

async function handleCreate() {
  if (!createForm.name || !createForm.slug) {
    ElMessage.warning('请填写组织名称和组织标识')
    return
  }
  creating.value = true
  try {
    const organization = await createOrganization(createForm)
    createDialog.value = false
    createForm.name = ''
    createForm.slug = ''
    await loadOrganizations()
    selectedId.value = organization.id
    await switchWorkspace(organization.id)
    ElMessage.success('组织工作区已创建')
  } finally {
    creating.value = false
  }
}

async function handleAddMember() {
  if (!memberForm.email || !selectedId.value) {
    ElMessage.warning('请输入成员邮箱')
    return
  }
  addingMember.value = true
  try {
    await addOrganizationMember(selectedId.value, memberForm)
    memberDialog.value = false
    memberForm.email = ''
    memberForm.role = 'member'
    await loadMembers()
    ElMessage.success('成员已添加')
  } finally {
    addingMember.value = false
  }
}

async function updateRole(member, role) {
  try {
    await updateOrganizationMemberRole(selectedId.value, member.user_id, role)
    await loadMembers()
    ElMessage.success('成员权限已更新')
  } catch {
    await loadMembers()
  }
}

async function confirmRemove(member) {
  await ElMessageBox.confirm(`移除 ${member.username} 后将立即失去工作区访问权限。`, '移除成员', {
    confirmButtonText: '移除成员',
    cancelButtonText: '取消',
    type: 'warning',
  })
  await removeOrganizationMember(selectedId.value, member.user_id)
  await loadMembers()
  ElMessage.success('成员已移除')
}

async function toggleSso(enabled) {
  savingSso.value = true
  try {
    await configureOrganizationSso(selectedId.value, enabled ? 'feishu' : '')
    await loadOrganizations()
    ElMessage.success(enabled ? '飞书登录已启用' : '飞书登录已关闭')
  } finally {
    savingSso.value = false
  }
}

async function copySsoUrl() {
  try {
    await window.navigator.clipboard.writeText(ssoEntryUrl.value)
    ElMessage.success('登录链接已复制')
  } catch {
    ElMessage.warning('浏览器未允许复制，请手动复制登录链接')
  }
}

onMounted(loadOrganizations)
</script>

<style scoped>
.organization-page {
  padding: 24px;
}

.header-actions,
.workspace-select,
.member-cell,
.sso-url {
  display: flex;
  align-items: center;
}

.header-actions {
  gap: 8px;
}

.workspace-strip {
  display: flex;
  align-items: stretch;
  min-height: 92px;
  margin-bottom: 16px;
  border: 1px solid var(--app-line-strong);
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
}

.workspace-select {
  min-width: 310px;
  padding: 18px 20px;
  gap: 12px;
  border-right: 1px solid var(--app-line);
}

.workspace-select :deep(.el-select) {
  flex: 1;
}

.strip-label,
.workspace-fact span,
.member-cell span,
.integration-copy,
.option-slug {
  color: var(--app-muted);
  font-size: 13px;
}

.option-slug {
  float: right;
  font-family: var(--app-font-mono);
}

.workspace-fact {
  display: grid;
  min-width: 142px;
  align-content: center;
  gap: 5px;
  padding: 16px 22px;
  border-right: 1px solid var(--app-line);
}

.workspace-fact strong {
  font-size: 15px;
}

.state-ready {
  color: var(--app-success);
}

.workspace-empty {
  display: flex;
  align-items: center;
  padding: 18px 22px;
  color: var(--app-muted);
}

.members-panel {
  margin-bottom: 16px;
}

.panel-header h3 {
  margin: 0 0 3px;
}

.member-cell {
  gap: 10px;
}

.member-avatar {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 8px;
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-weight: 700;
}

.member-cell div {
  display: grid;
  gap: 1px;
}

.member-cell strong {
  font-size: 14px;
}

.management-grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 16px;
}

.integration-copy {
  margin: 0 0 16px;
  line-height: 1.7;
}

.sso-url {
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--app-line);
  background: var(--app-surface-muted);
}

.sso-url code {
  flex: 1;
  overflow: hidden;
  color: var(--app-text);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-icon {
  color: var(--app-primary);
  font-size: 20px;
}

.scope-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.scope-list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--app-line);
  font-size: 13px;
}

.scope-list li:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.scope-list strong {
  color: var(--app-primary-dark);
  text-align: right;
}

@media (max-width: 900px) {
  .workspace-strip,
  .management-grid {
    grid-template-columns: 1fr;
  }

  .workspace-strip {
    display: grid;
  }

  .workspace-select,
  .workspace-fact {
    min-width: 0;
    border-right: 0;
    border-bottom: 1px solid var(--app-line);
  }

  .workspace-fact {
    grid-template-columns: 1fr auto;
    align-items: center;
  }
}

@media (max-width: 640px) {
  .organization-page {
    padding: 16px;
  }

  .page-header {
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
