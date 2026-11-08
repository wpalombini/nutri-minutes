// @vitest-environment node
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// ADR 0004: components use token variables only, never raw colours, sizes or font values.
// Media queries are the exception, because custom properties can't be used there; they may
// only use the breakpoint token values. So may the visually hidden pattern.

const src = fileURLToPath(new URL('../src', import.meta.url))
const generated = join(src, 'styles', 'tokens.css')
const breakpoints = new Set(['720px', '960px'])
// The visually hidden pattern's fixed values (design/screens/app-shell.md).
const visuallyHidden = new Set(['inline-size: 1px;', 'block-size: 1px;'])

function cssFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return cssFiles(path)
    return entry.name.endsWith('.css') && path !== generated ? [path] : []
  })
}

const rules: [string, RegExp][] = [
  ['hex colour', /#[0-9a-f]{3,8}\b/i],
  ['colour function', /\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/i],
  ['length', /(?<![\w-])-?\d*\.?\d+(px|rem|em|ch|pt|vw|vh|ex|lh)\b/],
  ['font family', /font-family:(?!\s*var\()/],
  ['font size', /font-size:(?!\s*var\()/],
  ['font weight', /font-weight:(?!\s*var\()/],
  ['line height', /line-height:(?!\s*var\()/],
  ['transition', /transition(-duration)?:(?!\s*var\()/],
]

describe('CSS values', () => {
  const files = cssFiles(src)

  it('finds the stylesheets', () => {
    expect(files.length).toBeGreaterThan(3)
  })

  for (const file of files) {
    it(`${relative(src, file)} uses token variables only`, () => {
      const problems: string[] = []
      const text = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
      text.split('\n').forEach((line, index) => {
        const media = /^\s*@media\b/.test(line)
        if (media) {
          for (const length of line.match(/\d+px/g) ?? []) {
            if (!breakpoints.has(length)) problems.push(`line ${index + 1}: breakpoint ${length}`)
          }
          return
        }
        if (visuallyHidden.has(line.trim())) return
        for (const [name, pattern] of rules) {
          if (pattern.test(line)) problems.push(`line ${index + 1}: ${name}: ${line.trim()}`)
        }
      })
      expect(problems).toEqual([])
    })
  }

  it('knows the breakpoint tokens', () => {
    const tokens = readFileSync(generated, 'utf8')
    for (const value of breakpoints) expect(tokens).toContain(`: ${value};`)
  })
})
