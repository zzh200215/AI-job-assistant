<template>
  <div class="panel">
    <!-- §10.14 决定 ①：标题容器由调用方给的那一支。槽内容编译在**调用方**作用域里，
         所以 `.side-title` / `.transcript-header` 这类调用方自己的规则仍然匹配得到；
         外层 `.panel-header` 仍由这里渲染，全局规格照旧生效。 -->
    <div v-if="$slots.heading" class="panel-header">
      <slot name="heading" />
    </div>
    <div v-else class="panel-header">
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
 * 如"今日推荐"这类 el-tag）、#actions（头部右侧）、默认（panel-body），
 * 以及 **#heading**（§10.14 决定 ①，D96 起）：调用方自带标题容器时用，给了它就**不**渲染
 * `.panel-title-row` 那一支。代价要说清：D23 统一过的 `.panel-header h3` 规格对这一支不再自动生效，
 * "标题由谁渲染"从组件契约里交回调用方——所以它是可选出口，不是新的默认写法。
 *
 * 没有副标题/描述槽：实测 79 处里 5 处 `h2 + p` 的描述型头部**全部包在 el-card 里**，
 * `div.panel` 里一处都没有——那个形状属于卡片头，不属于这个组件。别为它加 API。
 *
 * 迁移一个站点的前提是**该视图没有自己的 `.panel-header` scoped 规则**：scoped CSS 只作用于本组件
 * 模板里的节点（外加子组件的根元素），标记一旦搬进这里，父视图那条规则就再也匹配不到它了。
 * 但"有覆盖就先别迁"是错的（D20 在 Home 上实测：那两条覆盖的值从未出现在任何计算样式里，被主题层
 * 的 !important 与 token 压住）——要**逐个量覆盖到不到得了屏幕**，再决定搬规则还是直接迁。
 * **D96 决定 ③ 之后这一句变了**：候选人侧那几处覆盖（JobSearch / Privacy / Register）已经带页根类
 * 搬进 `panels.css`，只剩 §2 冻结的 `KnowledgeBase`(4) 与 `OrganizationWorkspace`(3)。
 * 而 D96 也量到：覆盖搬走之后**纯 drop-in 一处都没多出来**——那 4 处接着被"包裹不是静态
 * `div.panel`"（el-card 的 #header、`<section class="register-panel">`）挡住，
 * 所以"本地覆盖"从来只是前置条件，不是约束本身。
 */
defineProps({
  // 只有 #icon 存在时才用得上；值就是主题变量字符串，如 var(--app-primary)
  iconColor: { type: String, default: '' },
})
</script>
