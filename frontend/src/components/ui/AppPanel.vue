<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title-row">
        <el-icon v-if="$slots.icon" :size="18" :color="iconColor"><slot name="icon" /></el-icon>
        <h3><slot name="title" /></h3>
      </div>
      <slot name="actions" />
    </div>
    <div class="panel-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
/**
 * 面板外壳：`.panel / .panel-header / .panel-title-row / .panel-body` 这四层结构在 31 个视图里
 * 手写了 93 遍，样式早就集中在 styles/panels.css（`main.js` 全局引入），重复的只是标记。
 *
 * 迁移一个站点的前提是**该视图没有自己的 `.panel-header` scoped 规则**：scoped CSS 只作用于本组件
 * 模板里的节点（外加子组件的根元素），标记一旦搬进这里，父视图那条规则就再也匹配不到它了。
 * 实测仍有 6 个视图各自覆盖了 .panel-header（Home / JobSearch / KnowledgeBase / Privacy /
 * Register / OrganizationWorkspace），它们要先把覆盖搬进 panels.css 或换成 props 才能迁。
 */
defineProps({
  // 只有 #icon 存在时才用得上；值就是主题变量字符串，如 var(--app-primary)
  iconColor: { type: String, default: '' },
})
</script>
