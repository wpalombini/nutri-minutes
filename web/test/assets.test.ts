// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { fontFamilyVariables } from '../scripts/tokens.ts'

const read = (path: string) => readFileSync(new URL(path, import.meta.url))

describe('icons', () => {
  // design/icons/README.md, "Using it in the web app".
  const copies = {
    'favicon.ico': '../src/app/favicon.ico',
    'icon.svg': '../src/app/icon.svg',
    'apple-touch-icon.png': '../src/app/apple-icon.png',
    'icon-192.png': '../public/icons/icon-192.png',
    'icon-512.png': '../public/icons/icon-512.png',
    'icon-maskable-512.png': '../public/icons/icon-maskable-512.png',
  }

  for (const [source, copy] of Object.entries(copies)) {
    it(`${copy} matches design/icons/${source}`, () => {
      expect(read(copy).equals(read(`../../design/icons/${source}`))).toBe(true)
    })
  }
})

describe('fonts', () => {
  // next/font needs literal options, so src/app/fonts.ts can't import the tokens. Check by text.
  const fonts = read('../src/app/fonts.ts').toString('utf8')
  const base = JSON.parse(read('../../design/tokens/base.tokens.json').toString('utf8')) as {
    font: { family: Record<string, unknown> }
  }
  const families = Object.entries(base.font.family).filter(([key]) => !key.startsWith('$')) as [
    string,
    { $value: string[] },
  ][]

  it('finds the font family tokens', () => {
    expect(families.map(([key]) => key)).toEqual(['serif', 'sans'])
  })

  for (const [key, token] of families) {
    it(`font.family.${key} matches src/app/fonts.ts`, () => {
      const variable = fontFamilyVariables[`font.family.${key}` as keyof typeof fontFamilyVariables]
      expect(variable).toBeDefined()
      const [, ...fallback] = token.$value
      const call = new RegExp(
        `variable: '${variable}',\\n\\s+fallback: \\[${fallback.map((name) => `'${name}'`).join(', ')}\\]`,
      )
      expect(fonts).toMatch(call)
    })
  }
})
