import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
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
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
