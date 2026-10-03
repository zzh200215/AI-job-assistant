import { vLoading } from 'element-plus/es/components/loading/index.mjs'

/* D90（§9.1 那条覆盖）：`<el-*>` 的组件解析交给 `unplugin-vue-components` + `ElementPlusResolver`
   （配置与代价都写在 `vite.config.js`），这里原先那份 **59 项手写组件列表**删除。

   为什么这个文件不整个删掉：`v-loading` 是**指令**，不是标签——模板里的指令没有组件名可让解析器去
   解析，本项目 6 处 `v-loading` 全靠这里的全局注册；`ElMessage` / `ElMessageBox` 两个服务同理住在
   `element-services.js`。所以"删手写注册表"不等于"注册表整个消失"，这条判据由
   `tests/unit/elementRegistration.test.js` 的双源断言（`5ef7f68`）钉着：可解析集 = 这里的注册 ∪
   解析器生成的 `components.d.ts`，且两个来源不许同时为空。 */
export function installElement(app) {
  app.directive('loading', vLoading)
}
