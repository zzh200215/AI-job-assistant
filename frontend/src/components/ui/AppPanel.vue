<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title-row">
        <el-icon v-if="$slots.icon" :size="18" :color="iconColor"><slot name="icon" /></el-icon>
        <h3><slot name="title" /></h3>
        <slot name="badge" />
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
 * 槽：#icon（放进 18px 的 el-icon 里）、#title、#badge（标题行内、h3 之后的行内元素，
 * 如"今日推荐"这类 el-tag）、#actions（头部右侧）、默认（panel-body）。
 *
 * 没有副标题/描述槽：实测 79 处里 5 处 `h2 + p` 的描述型头部**全部包在 el-card 里**，
 * `div.panel` 里一处都没有——那个形状属于卡片头，不属于这个组件。别为它加 API。
 *
 * 迁移一个站点的前提是**该视图没有自己的 `.panel-header` scoped 规则**：scoped CSS 只作用于本组件
 * 模板里的节点（外加子组件的根元素），标记一旦搬进这里，父视图那条规则就再也匹配不到它了。
 * 但"有覆盖就先别迁"是错的（D20 在 Home 上实测：那两条覆盖的值从未出现在任何计算样式里，被主题层
 * 的 !important 与 token 压住）——要**逐个量覆盖到不到得了屏幕**，再决定搬规则还是直接迁。
 * 目前仍有本地覆盖的 5 个视图：JobSearch / KnowledgeBase（这两处的头部还是 el-card 里的 h2+p，
 * 属于卡片头形状）、Privacy（与 panels.css 差 1px padding）、Register（注册卡片借了个名字）、
 * OrganizationWorkspace（企业侧冻结）。
 */
defineProps({
  // 只有 #icon 存在时才用得上；值就是主题变量字符串，如 var(--app-primary)
  iconColor: { type: String, default: '' },
})
</script>
