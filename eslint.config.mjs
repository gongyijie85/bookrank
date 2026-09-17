// ESLint Flat Config：static/js 最小机械检查层（CI job: lint-frontend）
import js from '@eslint/js';
import globals from 'globals';

export default [
  {
    ignores: ['node_modules/**', 'research/**', '.claude/**'],
  },
  js.configs.recommended,
  {
    files: ['static/js/**/*.js', 'static/mobile/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: { ...globals.browser },
    },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^_', args: 'none', caughtErrors: 'none' }],
    },
  },
  {
    // ESM 文件（以 <script type="module"> 加载，使用 import/export）
    files: ['static/js/api.js', 'static/js/config.js', 'static/js/index.js', 'static/js/utils.js'],
    languageOptions: { sourceType: 'module' },
  },
  {
    // 跨文件全局变量：translations.js 定义，base.js 以裸名引用（typeof 守卫）
    files: ['static/js/base.js'],
    languageOptions: {
      globals: { setGlobalLanguage: 'readonly' },
    },
  },
  {
    // 项目自有跨文件全局（classic 脚本互相引用，base.js 定义并挂 window）：
    // esc/showToast 由 base.js 定义，categories.js / index.js 以裸名引用。
    files: ['static/js/categories.js', 'static/mobile/js/mobile.js'],
    languageOptions: {
      globals: { esc: 'readonly', showToast: 'readonly' },
    },
  },
  {
    // 跨文件全局变量：base.js / book-i18n.js 定义，translations.js 以裸名引用（typeof 守卫）
    files: ['static/js/translations.js'],
    languageOptions: {
      globals: {
        updateLangDropdown: 'readonly',
        showToast: 'readonly',
        BookI18n: 'readonly',
      },
    },
  },
  {
    // 跨文件全局变量：由 classic 脚本挂载到 window，index.js（ESM）以裸名访问
    files: ['static/js/index.js'],
    languageOptions: {
      globals: {
        t: 'readonly',
        BookI18n: 'readonly',
        applyFilters: 'readonly',
        clearFilters: 'readonly',
        applyPageTranslation: 'readonly',
        esc: 'readonly',
        showToast: 'readonly',
      },
    },
  },
];
