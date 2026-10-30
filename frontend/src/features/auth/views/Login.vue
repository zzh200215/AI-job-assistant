<template>
  <div class="login-page">
    <div class="login-shell">
      <section class="brand-pane" aria-label="产品信息">
        <div class="brand-head">
          <span class="brand-mark">
            <svg
              width="20"
              height="20"
              viewBox="0 0 32 32"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <rect
                x="1"
                y="1"
                width="30"
                height="30"
                rx="8"
                stroke="currentColor"
                stroke-width="1.8"
              />
              <path d="M9 22V12l7-5 7 5v10H9z" fill="currentColor" opacity="0.88" />
              <path
                d="M13 22v-4a3 3 0 0 1 6 0v4"
                stroke="var(--el-color-white)"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </span>
          <span class="brand-name">Career Signal</span>
        </div>

        <div class="brand-body">
          <p class="brand-kicker">AI 求职助手</p>
          <h1>把求职，走成一条清晰的路径</h1>
          <p class="brand-desc">
            从简历诊断、岗位匹配到模拟面试，一步一步推进，不用在多个工具之间来回切换。
          </p>

          <ol class="cap-list">
            <li>
              <span class="cap-index">01</span>
              <div>
                <strong>简历诊断与优化</strong>
                <p>先看清优势与短板，再动手改</p>
              </div>
            </li>
            <li>
              <span class="cap-index">02</span>
              <div>
                <strong>岗位匹配与投递</strong>
                <p>按你的经历找机会，持续跟进</p>
              </div>
            </li>
            <li>
              <span class="cap-index">03</span>
              <div>
                <strong>模拟面试与规划</strong>
                <p>按目标岗位练一遍，知道差在哪</p>
              </div>
            </li>
          </ol>
        </div>

        <p class="brand-foot">登录后，从你的简历开始</p>
      </section>

      <section class="form-pane" aria-label="登录表单">
        <div class="login-form">
          <div class="form-head">
            <h2>登录</h2>
            <p>输入邮箱或用户名继续</p>
          </div>

          <el-alert
            v-if="loginError"
            class="login-error"
            :title="loginError"
            type="error"
            :closable="false"
            show-icon
          />

          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            label-width="0"
            @keyup.enter="handleLogin"
          >
            <div class="field">
              <label for="account">邮箱或用户名</label>
              <el-form-item prop="account">
                <el-input
                  id="account"
                  v-model.trim="form.account"
                  placeholder="name@example.com"
                  size="large"
                  autocomplete="username"
                  :disabled="loading"
                  :prefix-icon="User"
                />
              </el-form-item>
            </div>

            <div class="field">
              <label for="password">密码</label>
              <el-form-item prop="password">
                <el-input
                  id="password"
                  v-model="form.password"
                  type="password"
                  placeholder="请输入密码"
                  size="large"
                  show-password
                  autocomplete="current-password"
                  :disabled="loading"
                  :prefix-icon="Lock"
                />
              </el-form-item>
            </div>

            <div class="form-options">
              <label class="remember">
                <el-checkbox v-model="rememberMe" size="small" />
                <span>记住我</span>
              </label>
              <a href="#" class="forgot-link" @click.prevent="goResetPassword">忘记密码？</a>
            </div>

            <el-form-item>
              <el-button
                type="primary"
                size="large"
                :loading="loading"
                class="submit-btn"
                @click="handleLogin"
              >
                {{ loading ? '登录中...' : '登录' }}
              </el-button>
            </el-form-item>

            <p class="signup-link">
              还没有账号？
              <el-link type="primary" underline="never" @click="goRegister">创建账号</el-link>
            </p>
          </el-form>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { userErrorCopy } from '@/utils/requestTracing'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, User } from '@element-plus/icons-vue'

import { ElMessage } from '@/plugins/element-services'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()

const loading = ref(false)
const rememberMe = ref(false)
const loginError = ref('')

const form = ref({ account: '', password: '' })

const rules = {
  account: [
    { required: true, message: '请输入邮箱或用户名', trigger: 'blur' },
    { min: 2, message: '请输入有效的邮箱或用户名', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 1, message: '请输入密码', trigger: 'blur' },
  ],
}

const goRegister = () => router.push('/register')
const goResetPassword = () => router.push('/reset-password')

const handleLogin = async () => {
  if (loading.value) return
  loginError.value = ''
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.login(form.value.account, form.value.password)
    ElMessage.success('登录成功')
    router.replace(authStore.homeRoute)
  } catch (error) {
    loginError.value = userErrorCopy(error, '登录失败，请检查账号和密码')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 32px;
  background: var(--app-bg);
}

.login-shell {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  width: min(100%, 960px);
  min-height: 620px;
  overflow: hidden;
  border: 1px solid var(--app-line);
  border-radius: 16px;
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-lg);
}

/* ===== Brand Panel ===== */
.brand-pane {
  display: flex;
  flex-direction: column;
  padding: 40px;
  border-right: 1px solid var(--app-line);
  background: var(--app-surface-muted);
}

.brand-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--app-radius-sm);
  background: var(--app-primary);
  color: var(--el-color-white);
}

.brand-name {
  color: var(--app-text);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.brand-body {
  flex: 1;
  padding-top: 48px;
}

.brand-kicker {
  margin: 0 0 10px;
  color: var(--app-muted);
  font-size: 12px;
  font-weight: 500;
}

.brand-body h1 {
  max-width: 400px;
  margin: 0;
  color: var(--app-text);
  font-size: 30px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.02em;
  text-wrap: balance;
}

.brand-desc {
  max-width: 380px;
  margin: 14px 0 0;
  color: var(--app-muted);
  font-size: 14px;
  line-height: 1.7;
}

.cap-list {
  display: grid;
  gap: 10px;
  margin: 32px 0 0;
  padding: 0;
  list-style: none;
}

.cap-list li {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-surface-strong);
}

.cap-index {
  padding-top: 1px;
  color: var(--app-muted);
  font-family: var(--app-font-mono);
  font-size: 11px;
  font-weight: 500;
}

.cap-list strong {
  display: block;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 600;
}

.cap-list p {
  margin: 2px 0 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.5;
}

.brand-foot {
  margin: 32px 0 0;
  color: var(--app-muted);
  font-size: 12px;
}

/* ===== Form Panel ===== */
.form-pane {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: var(--app-surface-strong);
}

.login-form {
  width: min(100%, 360px);
}

.form-head {
  margin-bottom: 26px;
}

.form-head h2 {
  margin: 0;
  color: var(--app-text);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.form-head p {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 14px;
}

.login-error {
  margin: -8px 0 18px;
}

.field {
  margin-bottom: 16px;
}

.field label {
  display: block;
  margin-bottom: 6px;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 600;
}

.form-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 20px;
}

.remember {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--app-muted);
  font-size: 13px;
}

.forgot-link {
  color: var(--app-primary);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
}

.forgot-link:hover {
  color: var(--app-primary-dark);
}

.submit-btn {
  width: 100%;
  min-height: 44px;
}

.signup-link {
  margin: 22px 0 0;
  color: var(--app-muted);
  font-size: 13px;
  text-align: center;
}

/* ===== Responsive ===== */
@media (max-width: 860px) {
  .login-page {
    padding: 16px;
  }

  .login-shell {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .brand-pane {
    padding: 28px 24px;
    border-right: none;
    border-bottom: 1px solid var(--app-line);
  }

  .brand-body {
    padding-top: 28px;
  }

  .brand-body h1 {
    font-size: 26px;
    text-wrap: balance;
  }

  .cap-list {
    margin-top: 22px;
  }

  .brand-foot {
    display: none;
  }

  .form-pane {
    padding: 28px 20px 32px;
  }
}
</style>
