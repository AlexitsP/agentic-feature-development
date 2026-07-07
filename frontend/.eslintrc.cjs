/* Minimal, TypeScript-aware ESLint config for the Vite/React app. */
module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['react-hooks'],
  extends: ['plugin:react-hooks/recommended'],
  rules: {
    // Keep the useful hook-safety rule as an error; treat dep hints as warnings.
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
  },
  ignorePatterns: ['dist', 'routeTree.gen.ts', '*.cjs', 'vite.config.ts', 'vite.config.d.ts'],
};
