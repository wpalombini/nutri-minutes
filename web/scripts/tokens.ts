/**
 * Regenerates the token stylesheet and theme colours from design/tokens (ADR 0004).
 *
 *   npm run tokens          write src/styles/tokens.css and src/generated/theme.ts
 *   npm run tokens:check    exit 1 if either committed file differs from what the tokens produce
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  buildThemeModule,
  buildTokenCss,
  type TokenSources,
  type TokenTree,
} from './tokens/convert.ts'

const tokensDir = new URL('../../design/tokens/', import.meta.url)
const outputs = {
  css: new URL('../src/styles/tokens.css', import.meta.url),
  theme: new URL('../src/generated/theme.ts', import.meta.url),
}

/** Must match the `variable` options in src/app/fonts.ts. */
export const fontFamilyVariables = {
  'font.family.serif': '--font-literata',
  'font.family.sans': '--font-atkinson',
} as const

const header =
  'Generated from design/tokens by web/scripts/tokens.ts. Do not edit: run npm run tokens.'

function read(name: string): TokenTree {
  return JSON.parse(readFileSync(new URL(name, tokensDir), 'utf8')) as TokenTree
}

export function generate(): Record<keyof typeof outputs, string> {
  const sources: TokenSources = {
    shared: [read('base.tokens.json'), read('roles.tokens.json')],
    light: read('color.light.tokens.json'),
    dark: read('color.dark.tokens.json'),
  }
  return {
    css: buildTokenCss(sources, { fontFamilyVariables, header }),
    theme: buildThemeModule(sources, header),
  }
}

function main(check: boolean): number {
  const generated = generate()
  let stale = 0
  for (const key of Object.keys(outputs) as (keyof typeof outputs)[]) {
    const file = outputs[key]
    const path = fileURLToPath(file)
    if (check) {
      let current = ''
      try {
        current = readFileSync(file, 'utf8')
      } catch {
        // A missing file counts as stale.
      }
      if (current !== generated[key]) {
        console.error(`${path} is out of date. Run npm run tokens and commit the result.`)
        stale += 1
      }
    } else {
      writeFileSync(file, generated[key])
      console.log(`Wrote ${path}`)
    }
  }
  if (check && stale === 0) console.log('Token outputs are up to date.')
  return stale === 0 ? 0 : 1
}

if (import.meta.main) {
  process.exitCode = main(process.argv.includes('--check'))
}
