import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import prettierConfig from 'eslint-config-prettier'
import prettierPlugin from 'eslint-plugin-prettier'

export default [
  {
    name: 'app/files-to-lint',
    files: ['**/*.{js,mjs,vue}'],
  },
  {
    name: 'app/files-to-ignore',
    ignores: ['dist/**', 'node_modules/**', '.vite/**', 'coverage/**', 'public/**', '*.lock'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    name: 'app/custom-rules',
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        URL: 'readonly',
      },
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'warn',
      'vue/attributes-order': 'off',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    },
  },
  prettierConfig,
  {
    // 构建配置文件跑在 Node 里，`process` 是真实存在的全局；
    // 浏览器侧的 src/** 不给它，避免有人在组件里读 process.env 混过检查。
    name: 'app/node-config-files',
    files: ['vite.config.js', '*.config.mjs'],
    languageOptions: { globals: { process: 'readonly' } },
  },
  {
    name: 'app/prettier-plugin',
    plugins: { prettier: prettierPlugin },
    rules: { 'prettier/prettier': 'warn' },
  },
  {
    name: 'app/no-raw-axios',
    files: ['src/**/*.{js,vue}'],
    ignores: ['src/api/request.js'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            { name: 'axios', message: 'Use the shared instance in src/api/request.js instead.' },
          ],
        },
      ],
    },
  },
  {
    // Views must go through src/api/<domain>.js so the response interceptor,
    // auth headers and error toasts stay in one place. The files below still
    // reach for the raw instance; removing one from this list is a cleanup.
    name: 'app/views-use-api-layer',
    files: ['src/views/**/*.vue', 'src/layouts/**/*.vue'],
    ignores: [
      'src/views/admin/Orders.vue',
      'src/views/admin/Overview.vue',
      'src/views/admin/Users.vue',
      'src/views/Privacy.vue',
      'src/views/Profile.vue',
      'src/views/Subscription.vue',
      'src/views/TaskCenter.vue',
    ],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            { name: 'axios', message: 'Use the shared instance in src/api/request.js instead.' },
            {
              name: '@/api/request',
              message:
                'Add the endpoint to a src/api/<domain>.js module instead of importing the request instance.',
            },
          ],
        },
      ],
    },
  },
]
