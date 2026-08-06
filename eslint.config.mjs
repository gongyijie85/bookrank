import js from '@eslint/js';
import globals from 'globals';

/**
 * Flat config for the 9 build-less frontend files.
 *
 * Cross-file globals are declared centrally here, per consuming file set.
 * The defining file never declares its own global (avoids no-redeclare):
 *   - t / setGlobalLanguage / applyPageTranslation  -> defined in translations.js
 *   - applyFilters / clearFilters / showToast / updateLangDropdown -> defined in base.js
 *   - BookI18n -> defined in book-i18n.js
 */
export default [
  {
    ignores: ['static/mobile/**'],
  },
  js.configs.recommended,
  {
    files: ['static/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      // Legacy no-op shims keep underscore-prefixed params for signature compatibility.
      // Only args are exempt; unused underscore-prefixed *variables* still error so
      // dead code cannot hide behind a leading underscore.
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  {
    // ESM files use import/export.
    files: ['static/js/api.js', 'static/js/config.js', 'static/js/index.js', 'static/js/utils.js'],
    languageOptions: {
      sourceType: 'module',
    },
  },
  {
    // index.js consumes globals defined by the classic scripts above.
    files: ['static/js/index.js'],
    languageOptions: {
      globals: {
        t: 'readonly',
        applyFilters: 'readonly',
        clearFilters: 'readonly',
        applyPageTranslation: 'readonly',
        BookI18n: 'readonly',
        showToast: 'readonly',
      },
    },
  },
  {
    // translations.js consumes globals from base.js / book-i18n.js but defines
    // t, setGlobalLanguage and applyPageTranslation itself.
    files: ['static/js/translations.js'],
    languageOptions: {
      globals: {
        BookI18n: 'readonly',
        showToast: 'readonly',
        updateLangDropdown: 'readonly',
      },
    },
  },
  {
    // base.js consumes setGlobalLanguage from translations.js but defines
    // applyFilters / clearFilters / showToast / updateLangDropdown itself.
    files: ['static/js/base.js'],
    languageOptions: {
      globals: {
        setGlobalLanguage: 'readonly',
      },
    },
  },
  {
    files: ['static/service-worker.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        ...globals.serviceworker,
      },
    },
  },
];
