// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { generate } from '../scripts/tokens.ts'
import {
  buildThemeModule,
  buildTokenCss,
  cssVarName,
  flattenTokens,
  resolveColourHex,
  type TokenSources,
  type TokenTree,
} from '../scripts/tokens/convert.ts'

const options = {
  fontFamilyVariables: { 'font.family.serif': '--font-serif-next' },
  header: 'Test header',
}

const srgb = (hex: string, alpha?: number) => ({
  colorSpace: 'srgb',
  components: [0, 0, 0],
  hex,
  ...(alpha === undefined ? {} : { alpha }),
})

function sources(overrides: Partial<TokenSources> = {}): TokenSources {
  const base: TokenTree = {
    palette: {
      $type: 'color',
      paper: { light: { $value: srgb('#EDF2EF') }, dark: { $value: srgb('#0e1c19') } },
    },
    font: {
      family: { $type: 'fontFamily', serif: { $value: ['Literata', 'Georgia', 'serif'] } },
      scale: {
        '48': {
          size: { $type: 'dimension', $value: { value: 3, unit: 'rem' } },
          'letter-spacing': { $type: 'dimension', $value: { value: -0.48, unit: 'px' } },
          'line-height': { $type: 'number', $value: 1.1 },
        },
      },
      weight: { $type: 'fontWeight', bold: { $value: 600 } },
    },
    space: { $type: 'dimension', '16': { $value: { value: 1, unit: 'rem' } } },
    duration: { $type: 'duration', '200': { $value: { value: 200, unit: 'ms' } } },
    easing: { $type: 'cubicBezier', out: { $value: [0.2, 0.8, 0.2, 1] } },
  }
  const roles: TokenTree = {
    type: {
      headline: {
        $type: 'typography',
        $value: {
          fontFamily: '{font.family.serif}',
          fontSize: '{font.scale.48.size}',
          fontWeight: '{font.weight.bold}',
          letterSpacing: '{font.scale.48.letter-spacing}',
          lineHeight: '{font.scale.48.line-height}',
        },
        $extensions: {
          'io.github.wpalombini.nutri-minutes': { fontVariantNumeric: 'tabular-nums' },
        },
      },
    },
    measure: { body: { $type: 'number', $value: 66 } },
    border: { style: { $type: 'strokeStyle', $value: 'dashed' } },
    motion: {
      expand: {
        $type: 'transition',
        $value: {
          duration: '{duration.200}',
          delay: { value: 0, unit: 'ms' },
          timingFunction: '{easing.out}',
        },
      },
    },
  }
  const theme = (mode: 'light' | 'dark'): TokenTree => ({
    surface: { $type: 'color', page: { $value: `{palette.paper.${mode}}` } },
    border: { $type: 'color', divider: { $value: srgb('#4a5f59', 0.3) } },
  })
  return { shared: [base, roles], light: theme('light'), dark: theme('dark'), ...overrides }
}

describe('flattenTokens', () => {
  it('inherits $type from the nearest group and skips $ keys', () => {
    const tokens = flattenTokens({
      $description: 'ignored',
      group: {
        $type: 'color',
        inner: { a: { $value: '#fff' }, b: { $type: 'number', $value: 1 } },
      },
    })
    expect(tokens.map(({ path, type }) => [path, type])).toEqual([
      ['group.inner.a', 'color'],
      ['group.inner.b', 'number'],
    ])
  })

  it('rejects a token without a type', () => {
    expect(() => flattenTokens({ a: { $value: 1 } })).toThrow('a has no $type')
  })
})

describe('cssVarName', () => {
  it('joins the path with hyphens', () => {
    expect(cssVarName('text.link-visited')).toBe('--text-link-visited')
    expect(cssVarName('font.scale.60.size')).toBe('--font-scale-60-size')
  })

  it('rejects names that break the naming rules', () => {
    expect(() => cssVarName('Text.Link')).toThrow('naming rules')
  })
})

describe('buildTokenCss', () => {
  const css = buildTokenCss(sources(), options)

  it('starts with the header and puts light values and color-scheme on :root', () => {
    expect(css.startsWith('/* Test header */\n\n:root {\n  color-scheme: light;\n')).toBe(true)
    expect(css).toContain('  --palette-paper-light: #edf2ef;\n')
    expect(css).toContain('  --surface-page: var(--palette-paper-light);\n')
  })

  it('redefines theme colours under prefers-color-scheme: dark', () => {
    const dark = css.slice(css.indexOf('@media (prefers-color-scheme: dark)'))
    expect(dark).toContain(
      '    color-scheme: dark;\n    --surface-page: var(--palette-paper-dark);\n',
    )
    expect(dark.split('@media (prefers-reduced-motion')[0]).not.toContain('--space-16')
  })

  it('turns aliases into var() references', () => {
    expect(css).toContain('--type-headline-font-size: var(--font-scale-48-size);')
    expect(css).toContain('--motion-expand-duration: var(--duration-200);')
  })

  it('writes colours with alpha as rgb()', () => {
    expect(css).toContain('--border-divider: rgb(74 95 89 / 0.3);')
  })

  it('emits dimensions, numbers, weights, durations, curves and stroke styles', () => {
    expect(css).toContain('--space-16: 1rem;')
    expect(css).toContain('--font-scale-48-line-height: 1.1;')
    expect(css).toContain('--font-weight-bold: 600;')
    expect(css).toContain('--duration-200: 200ms;')
    expect(css).toContain('--easing-out: cubic-bezier(0.2, 0.8, 0.2, 1);')
    expect(css).toContain('--border-style: dashed;')
  })

  it('converts letter spacing from px to em of its font size', () => {
    expect(css).toContain('--font-scale-48-letter-spacing: -0.01em;')
  })

  it('emits measure in ch', () => {
    expect(css).toContain('--measure-body: 66ch;')
  })

  it('maps font families to the next/font variables', () => {
    expect(css).toContain('--font-family-serif: var(--font-serif-next);')
  })

  it('splits typography into one variable per field, plus tabular figures', () => {
    for (const field of [
      'font-family',
      'font-size',
      'font-weight',
      'letter-spacing',
      'line-height',
    ]) {
      expect(css).toContain(`--type-headline-${field}: `)
    }
    expect(css).toContain('--type-headline-font-variant-numeric: tabular-nums;')
  })

  it('removes transition durations under reduced motion', () => {
    expect(css).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{\n {2}:root \{\n {4}--motion-expand-duration: 0s;\n {2}\}\n\}\n$/,
    )
  })

  it('is deterministic', () => {
    expect(buildTokenCss(sources(), options)).toBe(css)
  })
})

describe('buildTokenCss errors', () => {
  it('rejects an alias to a missing token', () => {
    const light = { surface: { $type: 'color', page: { $value: '{palette.missing}' } } }
    expect(() => buildTokenCss(sources({ light, dark: light }), options)).toThrow(
      'surface.page refers to missing palette.missing',
    )
  })

  it('rejects an alias to a token of another type', () => {
    const light = { surface: { $type: 'color', page: { $value: '{space.16}' } } }
    expect(() => buildTokenCss(sources({ light, dark: light }), options)).toThrow(
      'which is dimension',
    )
  })

  it('rejects light and dark files with different paths', () => {
    const dark = { surface: { $type: 'color', other: { $value: '{palette.paper.dark}' } } }
    expect(() => buildTokenCss(sources({ dark }), options)).toThrow('same paths')
  })

  it('rejects a token defined in two files', () => {
    const extra = { space: { $type: 'dimension', '16': { $value: { value: 2, unit: 'rem' } } } }
    const all = sources()
    expect(() => buildTokenCss({ ...all, shared: [...all.shared, extra] }, options)).toThrow(
      'space.16 is defined in more than one file',
    )
  })

  it('rejects a font family with no next/font variable', () => {
    expect(() => buildTokenCss(sources(), { ...options, fontFamilyVariables: {} })).toThrow(
      'font.family.serif has no next/font variable',
    )
  })

  it('rejects unsupported types and units', () => {
    const odd = { odd: { $type: 'gradient', $value: [] } }
    const all = sources()
    expect(() => buildTokenCss({ ...all, shared: [...all.shared, odd] }, options)).toThrow(
      'unsupported type gradient',
    )
    const em = { wide: { $type: 'dimension', $value: { value: 1, unit: 'em' } } }
    expect(() => buildTokenCss({ ...all, shared: [...all.shared, em] }, options)).toThrow(
      'px or rem',
    )
  })

  it('rejects two tokens that become the same variable', () => {
    const clash = { 'space-16': { $type: 'dimension', $value: { value: 1, unit: 'rem' } } }
    const all = sources()
    expect(() => buildTokenCss({ ...all, shared: [...all.shared, clash] }, options)).toThrow(
      'Two tokens both become --space-16',
    )
  })
})

describe('theme colours', () => {
  it('follows aliases to the page colour of each theme', () => {
    const all = sources()
    expect(resolveColourHex([...all.shared, all.dark], 'surface.page')).toBe('#0e1c19')
    expect(buildThemeModule(all, 'Test header')).toContain(
      "export const pageColour = { light: '#edf2ef', dark: '#0e1c19' } as const",
    )
  })
})

describe('the real design tokens', () => {
  it('produce the committed outputs', () => {
    const generated = generate()
    expect(readFileSync(new URL('../src/styles/tokens.css', import.meta.url), 'utf8')).toBe(
      generated.css,
    )
    expect(readFileSync(new URL('../src/generated/theme.ts', import.meta.url), 'utf8')).toBe(
      generated.theme,
    )
  })

  it('match the headline letter spacing in design/PLAN.md', () => {
    const { css } = generate()
    expect(css).toContain('--font-scale-60-letter-spacing: -0.015em;')
    expect(css).toContain('--font-scale-48-letter-spacing: -0.01em;')
  })
})
