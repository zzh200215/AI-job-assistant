<template>
  <div class="verify-page">
    <section class="verify-card">
      <el-icon class="icon" :size="56" :class="stateClass">
        <CircleCheckFilled v-if="status === 'done'" />
        <CircleCloseFilled v-else-if="status === 'failed'" />
        <Loading v-else />
      </el-icon>

      <h1>{{ title }}</h1>
      <p class="desc">{{ detail }}</p>

      <div class="actions">
        <el-button v-if="status === 'failed'" plain @click="retry">重试</el-button>
        <el-button type="primary" @click="goLogin">去登录</el-button>
      </div>
    </section>
  </div>
</template>

<script setup>
/* 邮箱验证的落地页。

   在这之前，验证邮件里的链接指向 `/verify-email?token=...`，而前端根本没有这条路由——
   点开就是 404。也就是说"验证邮箱"这个能力从界面到数据库都实现了，只有"人能点进去"那一环缺失。
   后端 `/auth/verify-email` 早就在（`app/api/auth.py`），这里只负责把 token 交过去并说清结果。 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleCheckFilled, CircleCloseFilled, Loading } from '@element-plus/icons-vue'

import { verifyEmail } from '@/api/auth'

const route = useRoute()
const router = useRouter()
const status = ref('checking') // checking | done | failed
const reason = ref('')

const title = computed(() => {
  if (status.value === 'done') return '邮箱已验证'
  if (status.value === 'failed') return '验证失败'
  return '正在验证…'
})

const detail = computed(() => {
  if (status.value === 'done') return '这个邮箱已经绑定到你的账号，之后可以用它接收提醒。'
  if (status.value === 'failed') {
    return reason.value || '链接无效或已过期，请回到个人中心重新发送验证邮件。'
  }
  return '请稍候，正在核对你邮件里的令牌。'
})

const stateClass = computed(() => `state-${status.value}`)

const token = computed(() => String(route.query.token || '').trim())

async function submit() {
  if (!token.value) {
    status.value = 'failed'
    reason.value = '链接里没有令牌，请复制完整链接再试一次。'
    return
  }

  status.value = 'checking'
  reason.value = ''
  try {
    await verifyEmail(token.value)
    status.value = 'done'
  } catch (error) {
    status.value = 'failed'
    // 后端把"无效/过期/用户不存在"都归到这一句里；具体原因留在 error 上，页面只说人话。
    reason.value = error?.userMessage || '链接无效或已过期，请回到个人中心重新发送验证邮件。'
  }
}

function retry() {
  submit()
}

function goLogin() {
  router.push('/login')
}

onMounted(submit)
</script>

<style scoped>
/* 这一页登录前可达，走的是 `:root` 那一档浅色令牌。
   刻意不写任何色值字面量：`styleDebtRatchet` 对视图的色值预算是"只能降不能升"，
   新文件从 0 起算，写死一个 hex 就会让那条守卫红。 */
.verify-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 16px;
  background: var(--app-bg);
}

.verify-card {
  width: min(100%, 460px);
  padding: 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: 24px;
  box-shadow: 0 22px 60px var(--app-shadow);
}

.icon {
  margin-bottom: 4px;
}

.state-checking {
  color: var(--app-muted);
}

.state-done {
  color: var(--app-success);
}

.state-failed {
  color: var(--app-danger);
}

h1 {
  margin: 0;
  font-size: 24px;
  color: var(--app-text);
}

.desc {
  margin: 0;
  line-height: 1.7;
  color: var(--app-muted);
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

@media (max-width: 640px) {
  .verify-card {
    padding: 24px 18px;
    border-radius: 20px;
  }

  .actions {
    flex-direction: column-reverse;
    width: 100%;
  }

  .actions :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }
}
</style>
