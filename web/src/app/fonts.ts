import { Atkinson_Hyperlegible_Next, Literata } from 'next/font/google'

// next/font downloads these from Google Fonts at build time and serves them from this site, so
// browsers never contact Google. The `variable` names must match fontFamilyVariables in
// scripts/tokens.ts, and the fallbacks the font.family.* tokens in design/tokens.

/** Headlines and summary body. Variable weight and optical size, roman and italic. */
export const literata = Literata({
  subsets: ['latin', 'latin-ext'],
  style: ['normal', 'italic'],
  axes: ['opsz'],
  display: 'swap',
  variable: '--font-literata',
  fallback: ['Georgia', 'serif'],
})

/** Interface, navigation, metadata and numbers. Variable weight, roman only. */
export const atkinson = Atkinson_Hyperlegible_Next({
  subsets: ['latin', 'latin-ext'],
  style: ['normal'],
  display: 'swap',
  variable: '--font-atkinson',
  fallback: ['system-ui', 'sans-serif'],
})
