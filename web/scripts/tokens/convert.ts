/**
 * Turns the design tokens in design/tokens (W3C DTCG 2025.10) into CSS custom properties, as
 * ADR 0004 and design/tokens/README.md describe. Pure functions only: reading and writing files
 * happens in scripts/tokens.ts.
 *
 * - Each token path becomes a variable: `text.link-visited` becomes `--text-link-visited`.
 * - Base, role and light colour tokens go on `:root`; dark colour tokens are redefined under
 *   `prefers-color-scheme: dark`. Each block sets the matching `color-scheme`.
 * - Aliases (`{group.token}`) become `var()` references, so the role layer stays visible.
 * - Composite tokens (typography, transition) become one variable per field.
 * - Under `prefers-reduced-motion: reduce` every transition duration becomes 0s.
 */

export type TokenTree = { readonly [key: string]: unknown }

export interface TokenSources {
  /** Files shared by both themes, in order: base, then roles. */
  shared: readonly TokenTree[]
  light: TokenTree
  dark: TokenTree
}

export interface ConvertOptions {
  /** Maps each `font.family.*` token path to the CSS variable that next/font generates. */
  fontFamilyVariables: Readonly<Record<string, string>>
  /** Comment written at the top of the generated stylesheet. */
  header: string
}

export interface FlatToken {
  path: string
  type: string
  value: unknown
  extensions: Readonly<Record<string, unknown>> | undefined
}

export class TokenError extends Error {
  override name = 'TokenError'
}

const EXTENSION_KEY = 'io.github.wpalombini.nutri-minutes'
const ALIAS = /^\{([^{}]+)\}$/
const ROOT_FONT_SIZE_PX = 16

/** Groups whose plain numbers carry a unit that DTCG can't express (see design/tokens/README.md). */
const NUMBER_UNITS: Readonly<Record<string, string>> = { measure: 'ch' }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Lists every token in a DTCG tree, with its type inherited from the nearest group. */
export function flattenTokens(
  tree: TokenTree,
  prefix: string[] = [],
  inherited?: string,
): FlatToken[] {
  const groupType = typeof tree.$type === 'string' ? tree.$type : inherited
  const tokens: FlatToken[] = []
  for (const [key, node] of Object.entries(tree)) {
    if (key.startsWith('$')) continue
    if (!isRecord(node))
      throw new TokenError(`${[...prefix, key].join('.')} is not a group or token`)
    const path = [...prefix, key]
    if ('$value' in node) {
      const type = typeof node.$type === 'string' ? node.$type : groupType
      if (type === undefined) throw new TokenError(`${path.join('.')} has no $type`)
      const extensions = isRecord(node.$extensions) ? node.$extensions : undefined
      tokens.push({ path: path.join('.'), type, value: node.$value, extensions })
    } else {
      tokens.push(...flattenTokens(node, path, groupType))
    }
  }
  return tokens
}

export function cssVarName(path: string): string {
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)*$/.test(path)) {
    throw new TokenError(`${path} doesn't follow the naming rules (lower case, hyphens, dots)`)
  }
  return `--${path.replaceAll('.', '-')}`
}

function aliasTarget(value: unknown): string | undefined {
  return typeof value === 'string' ? ALIAS.exec(value)?.[1] : undefined
}

function round(value: number): number {
  return Number(value.toFixed(4))
}

class Converter {
  private readonly byPath: Map<string, FlatToken>
  private readonly options: ConvertOptions

  constructor(tokens: readonly FlatToken[], options: ConvertOptions) {
    this.byPath = new Map(tokens.map((token) => [token.path, token]))
    this.options = options
  }

  /** Returns the CSS declarations for one token: one for simple tokens, several for composites. */
  declarations(token: FlatToken): [string, string][] {
    const name = cssVarName(token.path)
    switch (token.type) {
      case 'typography':
        return this.composite(token, name, {
          fontFamily: 'fontFamily',
          fontSize: 'dimension',
          fontWeight: 'fontWeight',
          letterSpacing: 'dimension',
          lineHeight: 'number',
        }).concat(this.typographyExtensions(token, name))
      case 'transition':
        return this.composite(token, name, {
          duration: 'duration',
          delay: 'duration',
          timingFunction: 'cubicBezier',
        })
      default:
        return [[name, this.value(token.path, token.type, token.value)]]
    }
  }

  private composite(
    token: FlatToken,
    name: string,
    fields: Readonly<Record<string, string>>,
  ): [string, string][] {
    if (!isRecord(token.value)) throw new TokenError(`${token.path} must be an object`)
    const value = token.value
    const extra = Object.keys(value).filter((field) => !(field in fields))
    if (extra.length > 0)
      throw new TokenError(`${token.path} has unknown fields: ${extra.join(', ')}`)
    return Object.entries(fields).map(([field, type]) => {
      if (!(field in value)) throw new TokenError(`${token.path} is missing ${field}`)
      const suffix = field.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)
      return [`${name}-${suffix}`, this.value(`${token.path}.${field}`, type, value[field])]
    })
  }

  private typographyExtensions(token: FlatToken, name: string): [string, string][] {
    const ours = token.extensions?.[EXTENSION_KEY]
    if (!isRecord(ours)) return []
    const declarations: [string, string][] = []
    if (typeof ours.fontVariantNumeric === 'string') {
      declarations.push([`${name}-font-variant-numeric`, ours.fontVariantNumeric])
    }
    if (typeof ours.fontFeatureSettings === 'string') {
      declarations.push([`${name}-font-feature-settings`, ours.fontFeatureSettings])
    }
    return declarations
  }

  private value(path: string, type: string, value: unknown): string {
    const target = aliasTarget(value)
    if (target !== undefined) {
      const referenced = this.byPath.get(target)
      if (referenced === undefined) throw new TokenError(`${path} refers to missing ${target}`)
      if (referenced.type !== type) {
        throw new TokenError(
          `${path} is ${type} but refers to ${target}, which is ${referenced.type}`,
        )
      }
      return `var(${cssVarName(target)})`
    }
    switch (type) {
      case 'color':
        return colour(path, value)
      case 'dimension':
        return this.dimension(path, value)
      case 'duration':
        return duration(path, value)
      case 'number':
        return number(path, value)
      case 'fontWeight':
        if (typeof value !== 'number') throw new TokenError(`${path} must be a number weight`)
        return String(value)
      case 'fontFamily': {
        const variable = this.options.fontFamilyVariables[path]
        if (variable === undefined) {
          throw new TokenError(`${path} has no next/font variable mapped in scripts/tokens.ts`)
        }
        return `var(${variable})`
      }
      case 'cubicBezier':
        if (
          !Array.isArray(value) ||
          value.length !== 4 ||
          !value.every((n) => typeof n === 'number')
        ) {
          throw new TokenError(`${path} must be four numbers`)
        }
        return `cubic-bezier(${value.join(', ')})`
      case 'strokeStyle':
        if (typeof value !== 'string' || !/^[a-z-]+$/.test(value)) {
          throw new TokenError(`${path} must be a keyword stroke style`)
        }
        return value
      default:
        throw new TokenError(`${path} has unsupported type ${type}`)
    }
  }

  /**
   * Dimensions are px or rem. Letter spacing is stored in px but is meant in em (README,
   * "Naming"), so a `letter-spacing` next to a `size` in rem is converted to em of that size.
   */
  private dimension(path: string, value: unknown): string {
    if (!isRecord(value) || typeof value.value !== 'number' || typeof value.unit !== 'string') {
      throw new TokenError(`${path} must be { value, unit }`)
    }
    if (value.unit !== 'px' && value.unit !== 'rem') {
      throw new TokenError(`${path} uses unit ${value.unit}; DTCG dimensions are px or rem`)
    }
    if (path.endsWith('.letter-spacing') && value.unit === 'px') {
      const size = this.byPath.get(path.replace(/letter-spacing$/, 'size'))?.value
      if (isRecord(size) && size.unit === 'rem' && typeof size.value === 'number') {
        return `${round(value.value / (size.value * ROOT_FONT_SIZE_PX))}em`
      }
    }
    return `${value.value}${value.unit}`
  }
}

function colour(path: string, value: unknown): string {
  if (!isRecord(value) || value.colorSpace !== 'srgb' || typeof value.hex !== 'string') {
    throw new TokenError(`${path} must be an sRGB colour with a hex value`)
  }
  const hex = value.hex.toLowerCase()
  if (!/^#[0-9a-f]{6}$/.test(hex)) throw new TokenError(`${path} has an invalid hex ${value.hex}`)
  const alpha = value.alpha ?? 1
  if (typeof alpha !== 'number' || alpha < 0 || alpha > 1) {
    throw new TokenError(`${path} has an invalid alpha`)
  }
  if (alpha === 1) return hex
  const [r, g, b] = [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16))
  return `rgb(${r} ${g} ${b} / ${alpha})`
}

function duration(path: string, value: unknown): string {
  if (
    !isRecord(value) ||
    typeof value.value !== 'number' ||
    (value.unit !== 'ms' && value.unit !== 's')
  ) {
    throw new TokenError(`${path} must be { value, unit: ms | s }`)
  }
  return `${value.value}${value.unit}`
}

function number(path: string, value: unknown): string {
  if (typeof value !== 'number') throw new TokenError(`${path} must be a number`)
  const unit = NUMBER_UNITS[path.split('.')[0] ?? '']
  return unit === undefined ? String(value) : `${value}${unit}`
}

function combine(trees: readonly TokenTree[]): FlatToken[] {
  const seen = new Set<string>()
  const tokens: FlatToken[] = []
  for (const tree of trees) {
    for (const token of flattenTokens(tree)) {
      if (seen.has(token.path))
        throw new TokenError(`${token.path} is defined in more than one file`)
      seen.add(token.path)
      tokens.push(token)
    }
  }
  return tokens
}

function block(selector: string, lines: readonly string[], indent = ''): string {
  return [
    `${indent}${selector} {`,
    ...lines.map((line) => `${indent}  ${line}`),
    `${indent}}`,
  ].join('\n')
}

function render(converter: Converter, tokens: readonly FlatToken[], names: Set<string>): string[] {
  const lines: string[] = []
  for (const token of tokens) {
    for (const [name, value] of converter.declarations(token)) {
      if (names.has(name)) throw new TokenError(`Two tokens both become ${name}`)
      names.add(name)
      lines.push(`${name}: ${value};`)
    }
  }
  return lines
}

function checkSamePaths(light: readonly FlatToken[], dark: readonly FlatToken[]): void {
  const lightPaths = light.map((token) => token.path).join('\n')
  const darkPaths = dark.map((token) => token.path).join('\n')
  if (lightPaths !== darkPaths) {
    throw new TokenError(
      'The light and dark colour files must define the same paths in the same order',
    )
  }
}

/** Builds the full stylesheet. */
export function buildTokenCss(sources: TokenSources, options: ConvertOptions): string {
  const shared = combine(sources.shared)
  const light = combine([...sources.shared, sources.light]).slice(shared.length)
  const dark = combine([...sources.shared, sources.dark]).slice(shared.length)
  checkSamePaths(light, dark)

  const lightConverter = new Converter([...shared, ...light], options)
  const darkConverter = new Converter([...shared, ...dark], options)

  const rootNames = new Set<string>()
  const root = [
    'color-scheme: light;',
    ...render(lightConverter, shared, rootNames),
    ...render(lightConverter, light, rootNames),
  ]
  const darkLines = ['color-scheme: dark;', ...render(darkConverter, dark, new Set())]
  const reducedMotion = shared
    .filter((token) => token.type === 'transition')
    .map((token) => `${cssVarName(token.path)}-duration: 0s;`)

  const sections = [
    `/* ${options.header} */`,
    block(':root', root),
    `@media (prefers-color-scheme: dark) {\n${block(':root', darkLines, '  ')}\n}`,
  ]
  if (reducedMotion.length > 0) {
    sections.push(
      `@media (prefers-reduced-motion: reduce) {\n${block(':root', reducedMotion, '  ')}\n}`,
    )
  }
  return `${sections.join('\n\n')}\n`
}

/** Follows aliases to a colour's hex value, for `theme-color` and the web app manifest. */
export function resolveColourHex(trees: readonly TokenTree[], path: string): string {
  const byPath = new Map(combine(trees).map((token) => [token.path, token]))
  let current = path
  for (let depth = 0; depth < 10; depth += 1) {
    const token = byPath.get(current)
    if (token === undefined) throw new TokenError(`${current} is not defined`)
    if (token.type !== 'color') throw new TokenError(`${current} is not a colour`)
    const target = aliasTarget(token.value)
    if (target === undefined) {
      const value = colour(current, token.value)
      if (!value.startsWith('#')) throw new TokenError(`${path} must be opaque`)
      return value
    }
    current = target
  }
  throw new TokenError(`${path} has an alias chain that is too long`)
}

/** Builds the TypeScript module with the page colour of each theme. */
export function buildThemeModule(sources: TokenSources, header: string): string {
  const light = resolveColourHex([...sources.shared, sources.light], 'surface.page')
  const dark = resolveColourHex([...sources.shared, sources.dark], 'surface.page')
  return [
    `// ${header}`,
    '',
    '/** `surface.page` in each theme, for `theme-color` and the web app manifest. */',
    `export const pageColour = { light: '${light}', dark: '${dark}' } as const`,
    '',
  ].join('\n')
}
