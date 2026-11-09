import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTypeScript from 'eslint-config-next/typescript'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import { defineConfig, globalIgnores } from 'eslint/config'

// ADR 0004: the Next.js configs, plus the full jsx-a11y recommended set, because
// eslint-config-next turns on only a few of its rules, as warnings. eslint-plugin-jsx-a11y is
// pinned to the version eslint-config-next resolves, so there is one copy. eslint-config-next
// registers it under its own wrapper object, and ESLint refuses to register a plugin name twice,
// so only the recommended rules are added here, as errors, for files the Next.js config covers.
export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  {
    name: 'jsx-a11y/recommended (rules)',
    files: ['**/*.{js,jsx,mjs,ts,tsx,mts,cts}'],
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      // Safari with VoiceOver drops list semantics from a list with `list-style: none`, so those
      // lists say role="list" on purpose. Other redundant roles are still errors.
      'jsx-a11y/no-redundant-roles': ['error', { ul: ['list'] }],
    },
  },
  globalIgnores([
    '.next/**',
    'coverage/**',
    'test-results/**',
    'playwright-report/**',
    'e2e-screenshots/**',
    'next-env.d.ts',
  ]),
])
