import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    /* D90（§9.1 那条覆盖）：`<el-*>` 的组件解析交给解析器，`src/plugins/element.js` 里 59 项手写
       列表随之删除。**`importStyle: false` 是量出来的选择**——样式仍走 `plugins/element.css` 那 47 行，
       因为 `importStyle: 'css'` 更贵（2298.89 vs 2242.63 kB）而 js 侧成因相同（解析器从
       `element-plus` 全量入口引组件，vendor-element 451.75 → 774.63 kB）。
       两个刻意的收敛：`dirs: []` 不去自动注册本项目自己的 `src/components/**`（那 3 个共享组件仍走
       显式 import，否则它们的解析方式会在同一刀里悄悄换掉）；`dts` 生成的 `components.d.ts` 是
       注册守卫的第二来源（双源判据在 `5ef7f68`）。
       代价写进账：构建总量 1894.58 → 约 2242.63 kB（+18.4%），由产品负责人指令覆盖测量建议。 */
    Components({
      dirs: [],
      resolvers: [ElementPlusResolver({ importStyle: false })],
      dts: 'components.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      onwarn(warning, defaultHandler) {
        // Element Plus pulls @vueuse/core; Rollup reports harmless pure-annotation comments in that dependency.
        if (
          warning.code === 'INVALID_ANNOTATION' &&
          typeof warning.id === 'string' &&
          warning.id.includes('@vueuse/core')
        ) {
          return
        }
        defaultHandler(warning)
      },
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('@element-plus/icons-vue')) return 'vendor-icons'
          if (id.includes('element-plus')) return 'vendor-element'
          if (id.includes('dayjs')) return 'vendor-dayjs'
          if (id.includes('async-validator')) return 'vendor-async-validator'
          if (id.includes('@floating-ui')) return 'vendor-floating-ui'
          if (id.includes('@popperjs/core')) return 'vendor-popper'
          if (id.includes('lodash')) return 'vendor-lodash'
          if (
            id.includes('/vue/') ||
            id.includes('/vue-router/') ||
            id.includes('/pinia/') ||
            id.includes('/@vue/')
          ) {
            return 'vendor-vue'
          }
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 5173,
    open: false,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.js'],
    setupFiles: ['./tests/unit/setup.js'],
    testEnvironmentOptions: { url: 'http://localhost:5173/' },
    /* D104：这条上限以前没设过，于是 82 个文件里每一条时序敏感断言共用 vitest 的隐式 5s 墙。
       实测（同一台机器，单跑全量）最慢的一条是 3.88s——离那堵墙只剩 1.28 倍余量；而 `tests/unit/jobPipelinePane.test.js`
       早就自己抬到 20000ms 并留了注释说它"并发时中位慢 3–4 倍、撞过两次"。故意同时跑两份全量（≈2 倍负载）时，
       红的是 8–9 个文件、清一色 `Test timed out in 5000ms`。抬的是**墙钟上限**，不是断言：断言错照样红。
       20000 = 空闲最慢那条的 5 倍，也是那条手工抬高值的同一个数（现在全局覆盖它，那处已撤）。 */
    testTimeout: 20000,
    server: { deps: { inline: ['element-plus'] } },
  },
})
