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
    // 构建配置与 scripts/ 下的 Node 小工具跑在服务端，`process` 是真实存在的全局；
    // 浏览器侧的 src/** 不给它，避免有人在组件里读 process.env 混过检查。
    name: 'app/node-config-files',
    files: ['vite.config.js', '*.config.mjs', 'scripts/**/*.mjs'],
    languageOptions: { globals: { process: 'readonly' } },
  },
  {
    name: 'app/prettier-plugin',
    plugins: { prettier: prettierPlugin },
    rules: { 'prettier/prettier': 'warn' },
  },
  {
    // dev-only 的浏览器探针（probe/）要用这批全局；D67 当年为了不给它们放开**共享**配置，
    // 干脆没把探针提交进来。这一块的 files 只匹配 probe/**，src 与 tests 的口径一个字没动。
    name: 'app/probe-globals',
    files: ['probe/**/*.js'],
    languageOptions: {
      globals: {
        getComputedStyle: 'readonly',
        localStorage: 'readonly',
        requestAnimationFrame: 'readonly',
        setTimeout: 'readonly',
        MouseEvent: 'readonly',
        location: 'readonly',
      },
    },
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
    // auth headers and error toasts stay in one place. D69 closed the last of
    // the exemptions, so this block has no ignore list: a new raw import here
    // is a lint error, not a budget.
    name: 'app/views-use-api-layer',
    files: ['src/features/**/*.vue', 'src/layouts/**/*.vue'],
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
