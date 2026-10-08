<template>
  <div class="login-page">
    <div class="login-shell">
      <!-- Brand Panel -->
      <section class="brand-pane" aria-label="产品信息">
        <div class="brand-head">
          <span class="brand-mark">
            <svg
              width="20"
              height="20"
              viewBox="0 0 32 32"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
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
                stroke="#fff"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </span>
          <span class="brand-name">Career Signal</span>
        </div>

        <div class="brand-body">
          <h1>职业情报工作台</h1>
          <p class="brand-desc">
            Agentic RAG、多智能体协作、岗位分析与职业规划，<br />
            统一在一个工作台通过信号驱动决策。
          </p>

          <!-- Terminal-style capability list -->
          <div class="cap-grid">
            <div class="cap-item">
              <span class="cap-tag mono">agent.run</span>
              <span class="cap-label">Agent 编排</span>
              <span class="cap-desc">多策略协同分析</span>
            </div>
            <div class="cap-item">
              <span class="cap-tag mono">rag.query</span>
              <span class="cap-label">RAG 增强</span>
              <span class="cap-desc">知识检索辅助判断</span>
            </div>
            <div class="cap-item">
              <span class="cap-tag mono">pipeline.board</span>
              <span class="cap-label">投递看板</span>
              <span class="cap-desc">多份投递进度跟踪</span>
            </div>
          </div>

          <p class="role-note">登录后进入求职工作台</p>
        </div>

        <!-- Decorative pipeline lines -->
        <div class="pipeline-deco" aria-hidden="true">
          <svg
            width="320"
            height="320"
            viewBox="0 0 320 320"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle cx="160" cy="160" r="140" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
            <circle cx="160" cy="160" r="100" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
            <circle cx="160" cy="160" r="60" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
            <path
              d="M30 160 Q 80 80 160 60 Q 240 40 290 160"
              stroke="rgba(255,255,255,0.08)"
              stroke-width="1"
              fill="none"
              stroke-dasharray="4 4"
            />
            <path
              d="M30 160 Q 80 240 160 260 Q 240 280 290 160"
              stroke="rgba(255,255,255,0.08)"
              stroke-width="1"
              fill="none"
              stroke-dasharray="4 4"
            />
            <circle cx="80" cy="80" r="3" fill="rgba(255,255,255,0.15)" />
            <circle cx="240" cy="80" r="3" fill="rgba(255,255,255,0.15)" />
            <circle cx="80" cy="240" r="3" fill="rgba(255,255,255,0.15)" />
            <circle cx="240" cy="240" r="3" fill="rgba(255,255,255,0.15)" />
            <circle cx="160" cy="60" r="4" fill="rgba(255,255,255,0.2)" />
            <circle cx="160" cy="260" r="4" fill="rgba(255,255,255,0.2)" />
          </svg>
        </div>
      </section>

      <!-- Form Panel -->
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
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--app-bg);
}

.login-shell {
  width: min(100%, 960px);
  min-height: 600px;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  border-radius: 20px;
  overflow: hidden;
  background: var(--app-surface-strong);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.08);
  border: 1px solid var(--app-line);
}

/* ===== Brand Panel ===== */
.brand-pane {
  position: relative;
  overflow: hidden;
  /* 白色标签随企业侧一起出树：`--app-login-bg` 全仓 0 处声明、src 里 0 次 setProperty，
     所以这层 var() 间接恒等于下面那个渐变，直接写死。 */
  background: linear-gradient(145deg, #0f1729 0%, #162544 100%) center / cover no-repeat;
  color: #f0f4ff;
  padding: 44px 40px;
  display: flex;
  flex-direction: column;
  isolation: isolate;
}

.brand-pane::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg, rgba(25, 107, 219, 0.25) 0%, transparent 50%),
    linear-gradient(225deg, rgba(109, 79, 199, 0.15) 0%, transparent 50%);
  z-index: -1;
}

.pipeline-deco {
  position: absolute;
  right: -60px;
  bottom: -40px;
  opacity: 0.6;
  pointer-events: none;
}

/* Brand head */
.brand-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 32px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

/* Brand body */
.brand-body {
  flex: 1;
}

.brand-body h1 {
  margin: 0;
  font-size: 36px;
  line-height: 1.1;
  font-weight: 800;
  letter-spacing: -0.03em;
}

.brand-desc {
  margin: 14px 0 0;
  max-width: 400px;
  color: rgba(240, 244, 255, 0.65);
  line-height: 1.7;
  font-size: 14px;
}

/* Capability grid */
.cap-grid {
  display: grid;
  gap: 10px;
  margin-top: 32px;
}

.cap-item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 14px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.cap-tag {
  grid-row: 1 / 3;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(240, 244, 255, 0.5);
  letter-spacing: 0.02em;
}

.cap-label {
  font-size: 14px;
  font-weight: 600;
  color: #f0f4ff;
}

.cap-desc {
  font-size: 12px;
  color: rgba(240, 244, 255, 0.5);
}

.role-note {
  margin: 24px 0 0;
  color: rgba(240, 244, 255, 0.4);
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
  margin-bottom: 28px;
}

.form-head h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  color: var(--app-text);
}

.form-head p {
  margin: 8px 0 0;
  color: var(--app-muted);
  font-size: 14px;
}

.login-error {
  margin: -10px 0 18px;
}

/* Fields */
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

/* Options */
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
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
}

.forgot-link:hover {
  color: var(--app-primary-dark);
}

/* Submit */
.submit-btn {
  width: 100%;
  min-height: 46px;
}

/* Signup link */
.signup-link {
  margin: 22px 0 0;
  text-align: center;
  color: var(--app-muted);
  font-size: 13px;
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
    padding: 28px 24px 24px;
  }

  .brand-body h1 {
    font-size: 28px;
  }

  .pipeline-deco {
    display: none;
  }

  .cap-grid {
    grid-template-columns: 1fr;
  }

  .form-pane {
    padding: 28px 20px 32px;
  }
}
</style>
