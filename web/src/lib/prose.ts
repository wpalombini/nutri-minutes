/**
 * A tiny Markdown converter for exactly the subset the prose pages use: paragraphs, `##` and
 * `###` headings, bulleted and numbered lists, bold and links. It returns a plain data tree,
 * never HTML, so raw HTML in the source can only ever be shown as text. Anything outside the
 * subset throws, so an author finds out at build time instead of getting a silent misrender.
 */

export type Inline =
  | { type: 'text'; text: string }
  | { type: 'bold'; children: Inline[] }
  | { type: 'link'; href: string; children: Inline[] }

export type Block =
  | { type: 'heading'; level: 2 | 3; children: Inline[] }
  | { type: 'paragraph'; children: Inline[] }
  | { type: 'list'; ordered: boolean; items: Inline[][] }

export type ProseDocument = { title: string; updated: string; blocks: Block[] }

const UNSUPPORTED_BLOCK = /^(#(?!#{1,2} )|#{4,}|>|```|~~~|\||<|---|\*\*\*|!\[|\s{2,}\S)/
const BULLET = /^[-*] (.*)$/
const NUMBERED = /^\d+\. (.*)$/
const HEADING = /^(#{2,3}) (.+)$/
const LINK = /^\[([^\]]+)\]\(([^)\s]+)\)/

/** Where a link may go: this site, or http(s). Anything else (such as `javascript:`) is refused. */
export function isSafeHref(href: string): boolean {
  if (href.startsWith('/')) return !href.startsWith('//') && !href.includes('\\')
  try {
    const { protocol } = new URL(href)
    return protocol === 'https:' || protocol === 'http:'
  } catch {
    return false
  }
}

/** Bold and links, with no nesting beyond a link inside bold or bold inside a link text. */
export function parseInline(source: string): Inline[] {
  const nodes: Inline[] = []
  let text = ''
  const flush = () => {
    if (text !== '') nodes.push({ type: 'text', text })
    text = ''
  }
  let i = 0
  while (i < source.length) {
    const rest = source.slice(i)
    if (rest.startsWith('**')) {
      const end = rest.indexOf('**', 2)
      if (end < 3) throw new Error(`Unclosed bold text in: ${source}`)
      flush()
      nodes.push({ type: 'bold', children: parseInline(rest.slice(2, end)) })
      i += end + 2
      continue
    }
    if (rest.startsWith('[')) {
      const match = LINK.exec(rest)
      if (match === null) throw new Error(`Malformed link in: ${source}`)
      const [whole, label = '', href = ''] = match
      if (!isSafeHref(href)) throw new Error(`Unsafe link target "${href}"`)
      flush()
      nodes.push({ type: 'link', href, children: parseInline(label) })
      i += whole.length
      continue
    }
    if (rest.startsWith('*') || rest.startsWith('_') || rest.startsWith('`')) {
      throw new Error(`Unsupported Markdown "${rest[0]}" in: ${source}`)
    }
    text += source[i]
    i += 1
  }
  flush()
  return nodes
}

/** The body of a page, after its front matter. Blocks are separated by blank lines. */
export function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = []
  const lines = markdown.replaceAll('\r\n', '\n').split('\n')
  let paragraph: string[] = []
  let list: { ordered: boolean; items: string[] } | undefined

  const endParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ type: 'paragraph', children: parseInline(paragraph.join(' ')) })
    }
    paragraph = []
  }
  const endList = () => {
    if (list)
      blocks.push({ type: 'list', ordered: list.ordered, items: list.items.map(parseInline) })
    list = undefined
  }

  for (const line of lines) {
    if (line.trim() === '') {
      endParagraph()
      endList()
      continue
    }
    const bullet = BULLET.exec(line)
    const numbered = NUMBERED.exec(line)
    const heading = HEADING.exec(line)
    if (UNSUPPORTED_BLOCK.test(line) && !bullet && !heading) {
      throw new Error(`Unsupported Markdown block: ${line}`)
    }
    if (heading) {
      endParagraph()
      endList()
      blocks.push({
        type: 'heading',
        level: heading[1]?.length === 3 ? 3 : 2,
        children: parseInline(heading[2] ?? ''),
      })
    } else if (bullet || numbered) {
      endParagraph()
      const ordered = numbered !== null
      if (list && list.ordered !== ordered) endList()
      list ??= { ordered, items: [] }
      list.items.push((bullet ?? numbered)?.[1] ?? '')
    } else if (list) {
      throw new Error(`Multi-line list items are not supported: ${line}`)
    } else {
      paragraph.push(line.trim())
    }
  }
  endParagraph()
  endList()
  return blocks
}

/** A whole page file: `title` and `updated` (YYYY-MM-DD) front matter, then the body. */
export function parseProsePage(source: string): ProseDocument {
  const match = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(source.replaceAll('\r\n', '\n'))
  if (match === null) throw new Error('A prose page must start with front matter')
  const fields = new Map<string, string>()
  for (const line of (match[1] ?? '').split('\n')) {
    if (line.trim() === '') continue
    const field = /^(\w+): (.+)$/.exec(line)
    if (field === null) throw new Error(`Unsupported front matter line: ${line}`)
    fields.set(field[1] ?? '', (field[2] ?? '').trim())
  }
  const title = fields.get('title')
  const updated = fields.get('updated')
  if (!title) throw new Error('Front matter needs a title')
  if (!updated || !/^\d{4}-\d{2}-\d{2}$/.test(updated) || Number.isNaN(Date.parse(updated))) {
    throw new Error('Front matter needs an updated date as YYYY-MM-DD')
  }
  return { title, updated, blocks: parseBlocks(match[2] ?? '') }
}

/** "9 November 2026", for a YYYY-MM-DD date, regardless of the server's time zone. */
export function formatUpdated(updated: string): string {
  return new Intl.DateTimeFormat('en-AU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${updated}T00:00:00Z`))
}
