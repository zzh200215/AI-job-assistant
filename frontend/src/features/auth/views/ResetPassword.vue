<template>
  <div class="reset-page">
    <section class="reset-card">
      <div class="copy">
        <p class="eyebrow">账号找回</p>
        <h1>{{ step === 1 ? '找回密码' : '设置新密码' }}</h1>
        <p class="desc" v-if="step === 1">
          输入注册邮箱，我们会发一条重置链接。本机未接邮件服务时，令牌会直接给出来，供你走完这条链。
        </p>
        <p class="desc" v-else>
          身份已校验，请设置新密码。<template v-if="tokenFromServer"
            >本环境未配置邮件服务，令牌已自动填入。</template
          >
        </p>
      </div>

      <el-form
        v-if="step === 1"
        ref="step1Ref"
        :model="step1"
        :rules="step1Rules"
        label-position="top"
        class="form"
        @keyup.enter="handleSend"
      >
        <el-form-item label="注册邮箱" prop="email">
          <el-input
            v-model.trim="step1.email"
            size="large"
            placeholder="请输入注册时使用的邮箱"
            :prefix-icon="Message"
            :disabled="loading"
          />
        </el-form-item>

        <div class="actions">
          <el-button class="ghost" size="large" @click="goLogin" :disabled="loading">
            返回登录
          </el-button>
          <el-button type="primary" size="large" :loading="loading" @click="handleSend">
            发送重置链接
          </el-button>
        </div>
      </el-form>

      <el-form
        v-else
        ref="step2Ref"
        :model="step2"
        :rules="step2Rules"
        label-position="top"
        class="form"
        @keyup.enter="handleReset"
      >
        <el-form-item label="重置令牌" prop="token">
          <el-input
            v-model.trim="step2.token"
            size="large"
            placeholder="邮件里的重置令牌"
            :prefix-icon="Key"
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="step2.newPassword"
            size="large"
            type="password"
            show-password
            placeholder="至少 8 位，包含字母和数字"
            :prefix-icon="Lock"
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input
            v-model="step2.confirmPassword"
            size="large"
            type="password"
            show-password
            placeholder="请再次输入新密码"
            :prefix-icon="Lock"
            :disabled="loading"
          />
        </el-form-item>

        <div class="actions">
          <el-button class="ghost" size="large" @click="backToStepOne" :disabled="loading">
            换一个邮箱
          </el-button>
          <el-button type="primary" size="large" :loading="loading" @click="handleReset">
            确认重置
          </el-button>
        </div>
      </el-form>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Key, Lock, Message } from '@element-plus/icons-vue'

import { requestPasswordReset, resetPasswordWithToken } from '@/api/auth'
import { ElMessage } from '@/plugins/element-services'
import { passwordProblem } from '@/utils/passwordRules'

const route = useRoute()
const router = useRouter()
const step1Ref = ref()
const step2Ref = ref()
const loading = ref(false)
const step = ref(1)
// 后端没有配置 SMTP 时会把令牌直接放在响应里（这条链在本机是完整可走的）。
// 配了邮件服务就只有"已发送"，此时令牌要用户自己从邮件里复制。
const tokenFromServer = ref(false)

const step1 = reactive({ email: '' })
const step2 = reactive({ token: '', newPassword: '', confirmPassword: '' })

const step1Rules = {
  email: [
    { required: true, message: '请输入注册邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效邮箱', trigger: ['blur', 'change'] },
  ],
}

const validatePassword = (_rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入新密码'))
    return
  }
  // 与后端 `TokenPasswordResetReq` 同源：注册那套强度规则（不再有"至少 6 位"的松档）。
  const problem = passwordProblem(value, { email: step1.email })
  if (problem) {
    callback(new Error(problem))
    return
  }
  callback()
}

const validateConfirmPassword = (_rule, value, callback) => {
  if (!value) {
    callback(new Error('请再次输入新密码'))
    return
  }
  if (value !== step2.newPassword) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}

const step2Rules = {
  token: [{ required: true, message: '请填写重置令牌', trigger: 'blur' }],
  newPassword: [{ validator: validatePassword, trigger: 'blur' }],
  confirmPassword: [{ validator: validateConfirmPassword, trigger: 'blur' }],
}

function goLogin() {
  router.push('/login')
}

function backToStepOne() {
  step.value = 1
  tokenFromServer.value = false
  step2.token = ''
}

async function handleSend() {
  if (loading.value) return
  const valid = await step1Ref.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const data = await requestPasswordReset(step1.email)
    // 没有 SMTP 时 data.token 存在，直接进第二步；配了邮件就是空对象，要用户从邮件里拿令牌。
    step2.token = data?.token || ''
    tokenFromServer.value = Boolean(step2.token)
    step.value = 2
    ElMessage.success(
      data?.token ? '本环境未配置邮件服务，令牌已填入' : '重置链接已发送，请查收邮件'
    )
  } finally {
    loading.value = false
  }
}

async function handleReset() {
  if (loading.value) return
  const valid = await step2Ref.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await resetPasswordWithToken(step2.token, step2.newPassword, step2.confirmPassword)
    ElMessage.success('密码已重置，请使用新密码登录')
    router.push('/login')
  } finally {
    loading.value = false
  }
}

// 配了邮件服务时，邮件里的链接长这样：`/reset-password?token=...`。
// 带 token 进来就直接落在第二步，不必再让用户先填一次邮箱。
onMounted(() => {
  const fromLink = String(route.query.token || '').trim()
  if (!fromLink) return
  step2.token = fromLink
  tokenFromServer.value = false
  step.value = 2
})
</script>

<style scoped>
.reset-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 16px;
  background:
    radial-gradient(circle at top left, rgba(19, 110, 194, 0.16), transparent 30%),
    radial-gradient(circle at bottom right, rgba(29, 158, 120, 0.12), transparent 26%),
    linear-gradient(180deg, #f4f7fb 0%, #edf3f8 100%);
}

.reset-card {
  width: min(100%, 520px);
  padding: 32px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(205, 216, 229, 0.92);
  border-radius: 24px;
  box-shadow: 0 22px 60px rgba(35, 55, 80, 0.14);
}

.copy {
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 10px;
  color: #6d7d93;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.copy h1 {
  margin: 0;
  color: #13233a;
  font-size: 30px;
}

.desc {
  margin: 12px 0 0;
  color: #5e7087;
  line-height: 1.7;
}

.form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}

.ghost {
  border-color: #d7e1ee;
  color: #4f647f;
}

@media (max-width: 640px) {
  .reset-card {
    padding: 24px 18px;
    border-radius: 20px;
  }

  .actions {
    flex-direction: column-reverse;
  }

  .actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
