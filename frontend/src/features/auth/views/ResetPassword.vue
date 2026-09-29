<template>
  <div class="reset-page">
    <section class="reset-card">
      <div class="copy">
        <p class="eyebrow">Account Recovery</p>
        <h1>重置密码</h1>
        <p class="desc">通过“账号 + 注册邮箱”完成本地身份校验，然后设置新密码。</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="form"
        @keyup.enter="handleSubmit"
      >
        <el-form-item label="邮箱或用户名" prop="account">
          <el-input
            v-model.trim="form.account"
            size="large"
            placeholder="请输入邮箱或用户名"
            :prefix-icon="User"
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item label="注册邮箱" prop="email">
          <el-input
            v-model.trim="form.email"
            size="large"
            placeholder="请输入注册时使用的邮箱"
            :prefix-icon="Message"
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="form.newPassword"
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
            v-model="form.confirmPassword"
            size="large"
            type="password"
            show-password
            placeholder="请再次输入新密码"
            :prefix-icon="Lock"
            :disabled="loading"
          />
        </el-form-item>

        <div class="actions">
          <el-button class="ghost" size="large" @click="goLogin" :disabled="loading">
            返回登录
          </el-button>
          <el-button type="primary" size="large" :loading="loading" @click="handleSubmit">
            确认重置
          </el-button>
        </div>
      </el-form>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, Message, User } from '@element-plus/icons-vue'

import { ElMessage } from '@/plugins/element-services'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  account: '',
  email: '',
  newPassword: '',
  confirmPassword: '',
})

const validatePassword = (_rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入新密码'))
    return
  }
  if (value.length < 8 || !/[A-Za-z]/.test(value) || !/\d/.test(value)) {
    callback(new Error('密码至少 8 位，且包含字母和数字'))
    return
  }
  callback()
}

const validateConfirmPassword = (_rule, value, callback) => {
  if (!value) {
    callback(new Error('请再次输入新密码'))
    return
  }
  if (value !== form.newPassword) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}

const rules = {
  account: [
    { required: true, message: '请输入邮箱或用户名', trigger: 'blur' },
    { min: 2, message: '请输入有效的邮箱或用户名', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入注册邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效邮箱', trigger: ['blur', 'change'] },
  ],
  newPassword: [{ validator: validatePassword, trigger: 'blur' }],
  confirmPassword: [{ validator: validateConfirmPassword, trigger: 'blur' }],
}

function goLogin() {
  router.push('/login')
}

async function handleSubmit() {
  if (loading.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.resetPassword(form.account, form.email, form.newPassword, form.confirmPassword)
    ElMessage.success('密码已重置，请使用新密码登录')
    router.push('/login')
  } finally {
    loading.value = false
  }
}
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
