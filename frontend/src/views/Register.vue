<template>
  <div class="register-page">
    <section class="register-panel" aria-label="注册表单">
      <div class="panel-header">
        <div class="brand">
          <span class="brand-mark">
            <svg
              width="18"
              height="18"
              viewBox="0 0 40 40"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <rect width="40" height="40" rx="12" fill="currentColor" />
              <path d="M12 28V16l8-6 8 6v12H12z" fill="white" opacity="0.9" />
              <path
                d="M16 28V22a2 2 0 014 0v6"
                stroke="white"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </span>
          <span>智能招聘平台</span>
        </div>

        <div class="title-block">
          <h1>注册账号</h1>
          <p>创建求职者账号并完成注册</p>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="0"
        @keyup.enter="handleRegister"
      >
        <div class="field">
          <label for="username">用户名</label>
          <el-form-item prop="username">
            <div class="input-wrap">
              <el-input
                id="username"
                v-model.trim="form.username"
                :prefix-icon="User"
                placeholder="请输入用户名"
                size="large"
                autocomplete="username"
                :disabled="loading"
              />
            </div>
          </el-form-item>
        </div>

        <div class="field">
          <label for="email">邮箱</label>
          <el-form-item prop="email">
            <div class="input-wrap">
              <el-input
                id="email"
                v-model.trim="form.email"
                :prefix-icon="Message"
                placeholder="请输入邮箱"
                size="large"
                autocomplete="email"
                :disabled="loading"
              />
            </div>
          </el-form-item>
        </div>

        <div class="field">
          <label for="password">密码</label>
          <el-form-item prop="password">
            <div class="input-wrap">
              <el-input
                id="password"
                v-model="form.password"
                :prefix-icon="Lock"
                type="password"
                placeholder="请输入密码"
                size="large"
                show-password
                autocomplete="new-password"
                :disabled="loading"
              />
            </div>
          </el-form-item>
        </div>

        <div class="field">
          <label for="confirmPassword">确认密码</label>
          <el-form-item prop="confirmPassword">
            <div class="input-wrap">
              <el-input
                id="confirmPassword"
                v-model="form.confirmPassword"
                :prefix-icon="Lock"
                type="password"
                placeholder="请再次输入密码"
                size="large"
                show-password
                autocomplete="new-password"
                :disabled="loading"
              />
            </div>
          </el-form-item>
        </div>

        <p class="hint">注册后会自动进入对应工作台</p>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="submit"
            :loading="loading"
            @click="handleRegister"
          >
            注册
          </el-button>
        </el-form-item>

        <p class="signup">
          已有账号？
          <el-link type="primary" :underline="false" @click="goLogin">去登录</el-link>
        </p>
      </el-form>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, Message, User } from '@element-plus/icons-vue'

import { ElMessage } from '@/plugins/element-services'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = ref({
  role: 'candidate',
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const validateConfirm = (_rule, value, callback) => {
  if (value !== form.value.password) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}

const validatePassword = (_rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入密码'))
    return
  }
  if (value.length < 8) {
    callback(new Error('密码至少 8 位'))
    return
  }
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
    callback(new Error('密码需同时包含字母和数字'))
    return
  }
  if (value !== value.trim()) {
    callback(new Error('密码首尾不能包含空格'))
    return
  }
  callback()
}

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '用户名长度需在 2 到 50 个字符之间', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_\-\u4e00-\u9fff]+$/,
      message: '用户名仅支持中文、字母、数字、下划线和短横线',
      trigger: 'blur',
    },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [{ validator: validatePassword, trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

const goLogin = () => {
  router.push('/login')
}

const handleRegister = async () => {
  if (loading.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.register(
      form.value.username,
      form.value.email,
      form.value.password,
      form.value.role
    )
    ElMessage.success('注册成功')
    router.replace(authStore.homeRoute)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background:
    radial-gradient(circle at top left, rgba(34, 197, 94, 0.12), transparent 32%),
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.12), transparent 38%),
    linear-gradient(180deg, #f7f9fc 0%, #eef3fb 100%);
}

.register-panel {
  width: min(100%, 520px);
  padding: 40px 34px 32px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(214, 224, 239, 0.9);
  border-radius: 24px;
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.12);
}

.panel-header {
  margin-bottom: 28px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: #5d6b82;
  font-size: 14px;
  font-weight: 700;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #0f766e);
  color: #ffffff;
  display: grid;
  place-items: center;
}

.brand-mark svg {
  width: 18px;
  height: 18px;
}

.title-block {
  margin-top: 18px;
}

.title-block h1 {
  margin: 0;
  color: #14213d;
  font-size: 46px;
  line-height: 1.05;
  letter-spacing: -0.03em;
}

.title-block p {
  margin: 12px 0 0;
  color: #6b7a90;
  font-size: 16px;
  line-height: 1.6;
}

.register-panel :deep(.el-form-item) {
  margin-bottom: 0;
}

.register-panel :deep(.el-form-item__content) {
  width: 100%;
  margin-left: 0 !important;
}

.field {
  margin-bottom: 14px;
}

.field label {
  display: block;
  margin-bottom: 10px;
  color: #1e2b42;
  font-size: 15px;
  font-weight: 700;
}

.input-wrap {
  position: relative;
}

.input-wrap :deep(.el-input) {
  display: block;
  width: 100%;
}

.input-wrap :deep(.el-input__wrapper) {
  width: 100%;
  min-height: 54px;
  border: 1px solid #d5dfed;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: none !important;
  padding: 0 16px;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

.input-wrap :deep(.el-input__wrapper:hover) {
  border-color: #a8bad4;
}

.input-wrap :deep(.el-input__wrapper.is-focus) {
  border-color: #2563eb;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.12) !important;
}

.input-wrap :deep(.el-input__inner) {
  color: #172033;
  font-size: 17px;
}

.input-wrap :deep(.el-input__prefix) {
  margin-right: 8px;
}

.input-wrap :deep(.el-input__prefix-inner) {
  color: #8a97ac;
}

.hint {
  margin: 8px 0 20px;
  color: #6f8096;
  font-size: 14px;
  line-height: 1.5;
}

.submit {
  width: 100%;
  min-height: 56px;
  border: 0;
  border-radius: 16px;
  background: linear-gradient(135deg, #2b77e5, #1f63d8);
  color: #ffffff;
  font-size: 17px;
  font-weight: 800;
  box-shadow: 0 16px 28px rgba(43, 119, 229, 0.24);
}

.signup {
  margin: 24px 0 0;
  color: #6b7a90;
  text-align: center;
  font-size: 15px;
  line-height: 1.6;
}

.signup :deep(.el-link) {
  font-size: 15px;
  font-weight: 700;
}

@media (max-width: 640px) {
  .register-page {
    padding: 16px;
  }

  .register-panel {
    padding: 28px 20px 24px;
    border-radius: 20px;
  }

  .title-block h1 {
    font-size: 36px;
  }
}
</style>
