<template>
  <div v-if="demoMode || degraded" class="runtime-banners">
    <!-- 两条刻意分开：一条说的是"数据不是真的"，另一条说的是"AI 能力降级了"。
         合写成一句会让两件事同时不成立——示例数据下模型也可能正常，真实模型下也可能降级。 -->
    <p v-if="demoMode" class="runtime-banner is-demo">
      <el-icon class="runtime-icon"><InfoFilled /></el-icon>
      <span>
        当前为示例数据：这个环境没有接入真实模型，分析与评分类结果由模板和模拟数据生成。
      </span>
    </p>
    <p v-if="degraded" class="runtime-banner is-degraded">
      <el-icon class="runtime-icon"><WarningFilled /></el-icon>
      <span> AI 服务降级中：最近一次生成走了备用模型或规则兜底，结果可能不如平时准确。 </span>
    </p>
  </div>
</template>

<script setup>
/* 运行时的两条提示，挂在布局里，所以每一页都能看到它。

   为什么需要：这套系统最贵的一笔投入是"区分真实推理与模板"（A 阶段的全部工作），
   而那笔投入原先只有管理员在 PromptTrace 里看得见——候选人屏上一片干净，
   等于把诚实性做成了内部指标。这里把它变成候选人能读到的一行字。

   判据来自 `/system/status`（候选人本来就有权限调）：
   * `demo_mode` —— 没接真实模型（mock provider）；
   * `runtime_notes.ai_degraded_recent` —— 最近 30 分钟内有降级。

   失败即静默：这是一条辅助提示，它自己挂掉不该变成页面上的一条错误。 */
import { onMounted, ref } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'

import { getSystemStatus } from '@/api/system'

const demoMode = ref(false)
const degraded = ref(false)

onMounted(async () => {
  try {
    const status = await getSystemStatus({ notifyError: false })
    demoMode.value = Boolean(status?.demo_mode)
    degraded.value = Boolean(status?.runtime_notes?.ai_degraded_recent)
  } catch {
    // 探测失败就不显示：宁可不提示，也不要在不知道的时候假装一切正常。
  }
})
</script>

<style scoped>
/* 只读令牌，不写字面色值：布局层的样式预算同样是"只能降不能升"。 */
.runtime-banners {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.runtime-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--app-text);
  background: var(--app-surface-muted);
}

.runtime-icon {
  flex: none;
  margin-top: 2px;
}

/* 用左侧色条区分两种状态，不动底色——底色一动就要在深色/浅色两套里各配一遍。 */
.is-demo {
  border-left: 3px solid var(--app-muted);
}

.is-degraded {
  border-left: 3px solid var(--app-warning);
}
</style>
