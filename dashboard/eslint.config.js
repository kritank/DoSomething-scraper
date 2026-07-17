import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import { defineConfig, globalIgnores } from 'eslint/config';

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'no-unused-vars': ['warn', { varsIgnorePattern: '^[A-Z_]' }],
      // This codebase fetches data with `useEffect(() => { load(); }, [load])`
      // throughout (Overview, CreatorProfile, Influencers, QueryConsole,
      // etc.) -- the standard pre-Suspense data-fetching pattern, not a bug.
      // This rule is part of react-hooks' newer React Compiler-oriented
      // preset and flags every one of those call sites; the codebase isn't
      // targeting the compiler, so it's disabled rather than rewritten.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
]);
