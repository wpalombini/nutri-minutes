// @vitest-environment node
import { readdirSync, readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { ProsePage } from '@/components/ProsePage'
import { formatUpdated, isSafeHref, parseBlocks, parseInline, parseProsePage } from '@/lib/prose'

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href} data-next-link="">
      {children}
    </a>
  ),
}))

describe('parseInline', () => {
  it('reads text, bold and links', () => {
    expect(parseInline('a **b** [c](/d)')).toEqual([
      { type: 'text', text: 'a ' },
      { type: 'bold', children: [{ type: 'text', text: 'b' }] },
      { type: 'text', text: ' ' },
      { type: 'link', href: '/d', children: [{ type: 'text', text: 'c' }] },
    ])
  })

  it('keeps raw HTML as text, never as markup', () => {
    expect(parseInline('<script>x</script>')).toEqual([
      { type: 'text', text: '<script>x</script>' },
    ])
  })

  it('refuses unsafe link targets and unsupported syntax', () => {
    expect(() => parseInline('[x](javascript:alert(1))')).toThrow('Unsafe')
    expect(() => parseInline('[x](//evil.test)')).toThrow('Unsafe')
    expect(() => parseInline('[x](data:text/html,hi)')).toThrow('Unsafe')
    expect(() => parseInline('*em*')).toThrow('Unsupported')
    expect(() => parseInline('`code`')).toThrow('Unsupported')
    expect(() => parseInline('**open')).toThrow('Unclosed')
    expect(() => parseInline('[open](/x')).toThrow('Malformed')
  })
})

describe('isSafeHref', () => {
  it('allows this site and http(s) only', () => {
    expect(isSafeHref('/how-we-grade')).toBe(true)
    expect(isSafeHref('https://example.test/a')).toBe(true)
    expect(isSafeHref('mailto:a@b.test')).toBe(false)
    expect(isSafeHref('/\\evil.test')).toBe(false)
    expect(isSafeHref('relative')).toBe(false)
    expect(isSafeHref('/\t/evil.test')).toBe(false)
    expect(isSafeHref('/\u0000x')).toBe(false)
    expect(isSafeHref('JAVASCRIPT:alert(1)')).toBe(false)
    expect(isSafeHref('http://example.test/a')).toBe(false)
  })
})

describe('parseBlocks', () => {
  it('reads headings, joined paragraph lines and both list kinds', () => {
    const blocks = parseBlocks('## H\n\none\ntwo\n\n- a\n- b\n\n1. x\n2. y\n\n### Sub\n')
    expect(blocks.map((b) => b.type)).toEqual(['heading', 'paragraph', 'list', 'list', 'heading'])
    expect(blocks[1]).toEqual({ type: 'paragraph', children: [{ type: 'text', text: 'one two' }] })
    expect(blocks[2]).toMatchObject({ ordered: false })
    expect(blocks[3]).toMatchObject({ ordered: true })
    expect(blocks[4]).toMatchObject({ level: 3 })
  })

  it('ends a list at a blank line and when the kind changes', () => {
    expect(parseBlocks('- a\n1. b')).toHaveLength(2)
    expect(parseBlocks('- a\n\n- b')).toHaveLength(2)
  })

  it('rejects syntax outside the subset', () => {
    for (const bad of [
      '# One',
      '#### Four',
      '> quote',
      '```\ncode',
      '<div>x</div>',
      '| a | b |',
      '---',
      '![i](/x.png)',
    ]) {
      expect(() => parseBlocks(bad), bad).toThrow('Unsupported')
    }
    expect(() => parseBlocks('- a\n  more')).toThrow()
  })
})

describe('parseProsePage', () => {
  it('reads front matter and body', () => {
    const page = parseProsePage('---\ntitle: T\nupdated: 2026-11-09\n---\n\nBody\n')
    expect(page).toMatchObject({ title: 'T', updated: '2026-11-09' })
    expect(page.blocks).toHaveLength(1)
  })

  it('needs a title and a valid date', () => {
    expect(() => parseProsePage('no front matter')).toThrow('front matter')
    expect(() => parseProsePage('---\nupdated: 2026-11-09\n---\nx')).toThrow('title')
    expect(() => parseProsePage('---\ntitle: T\nupdated: 9 Nov\n---\nx')).toThrow('updated')
    expect(() => parseProsePage('---\ntitle: T\nupdated: 2026-13-45\n---\nx')).toThrow('updated')
  })
})

describe('formatUpdated', () => {
  it('writes an Australian long date', () => {
    expect(formatUpdated('2026-11-09')).toBe('9 November 2026')
    expect(formatUpdated('2026-01-01')).toBe('1 January 2026')
  })
})

describe('the real pages', () => {
  const dir = new URL('../content/pages/', import.meta.url)
  for (const file of readdirSync(dir)) {
    it(`${file} parses and renders with an h2 outline, links and a date`, () => {
      const page = parseProsePage(readFileSync(new URL(file, dir), 'utf8'))
      const html = renderToStaticMarkup(<ProsePage page={page} />)
      expect(html.match(/<h1/g)).toHaveLength(1)
      expect(html).toContain('<h2>')
      expect(html).toContain('Last updated <time dateTime="2026-11-09">9 November 2026</time>')
      expect(html).not.toContain('&lt;')
    })
  }

  it('renders an internal link with next/link', () => {
    const page = parseProsePage(
      '---\ntitle: T\nupdated: 2026-11-09\n---\n[A](/how-we-grade) [B](https://e.test)',
    )
    const html = renderToStaticMarkup(<ProsePage page={page} />)
    expect(html).toContain('<a href="/how-we-grade" data-next-link="">A</a>')
    expect(html).toContain('<a href="https://e.test" rel="noopener noreferrer">B</a>')
  })
})
