/**
 * Parser for `content/topics.md`: front matter, a short intro, then one table of Topic, Slug
 * and Description. It is strict on purpose: anything unexpected throws, so a bad edit fails the
 * build instead of publishing a broken topic list.
 *
 * Temporary source: design/screens/topics.md says the topic list comes from the API. Until the
 * API has a topics endpoint, the owner-approved file is the source.
 */

export type Topic = { name: string; slug: string; description: string }

export type TopicList = { updated: string; topics: Topic[] }

const HEADER = ['Topic', 'Slug', 'Description']
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

function cells(line: string): string[] {
  if (!line.startsWith('|') || !line.endsWith('|')) {
    throw new Error(`Topic table row must start and end with "|": ${line}`)
  }
  return line
    .slice(1, -1)
    .split('|')
    .map((cell) => cell.trim())
}

export function parseTopics(source: string): TopicList {
  const match = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(source.replaceAll('\r\n', '\n'))
  if (match === null) throw new Error('The topics file must start with front matter')

  let updated: string | undefined
  let hasTitle = false
  for (const line of (match[1] ?? '').split('\n')) {
    if (line.trim() === '') continue
    const field = /^(title|updated): (.+)$/.exec(line)
    if (field === null) throw new Error(`Unsupported front matter line: ${line}`)
    if (field[1] === 'title') hasTitle = true
    else updated = (field[2] ?? '').trim()
  }
  if (!hasTitle) throw new Error('Front matter needs a title')
  if (
    updated === undefined ||
    !/^\d{4}-\d{2}-\d{2}$/.test(updated) ||
    Number.isNaN(Date.parse(updated))
  ) {
    throw new Error('Front matter needs an updated date as YYYY-MM-DD')
  }

  const lines = (match[2] ?? '').split('\n')
  const start = lines.findIndex((line) => line.startsWith('|'))
  if (start === -1) throw new Error('The topics file has no table')
  const rows = lines.slice(start)
  const end = rows.findIndex((line) => line.trim() === '')
  const table = end === -1 ? rows : rows.slice(0, end)
  if (rows.slice(table.length).some((line) => line.trim() !== '')) {
    throw new Error('Unexpected content after the topic table')
  }

  const [header = '', divider = '', ...body] = table
  if (cells(header).join('|') !== HEADER.join('|')) {
    throw new Error(`Topic table header must be ${HEADER.join(' | ')}`)
  }
  if (!cells(divider).every((cell) => /^:?-{3,}:?$/.test(cell)) || cells(divider).length !== 3) {
    throw new Error('Topic table needs a divider row under the header')
  }
  if (body.length === 0) throw new Error('The topic table has no rows')

  const seen = new Set<string>()
  const topics = body.map((line): Topic => {
    const row = cells(line)
    if (row.length !== 3) throw new Error(`Topic row needs 3 cells: ${line}`)
    const [name = '', rawSlug = '', description = ''] = row
    const slug = /^`([^`]+)`$/.exec(rawSlug)?.[1]
    if (slug === undefined || !SLUG.test(slug)) {
      throw new Error(`Topic slug must be a lowercase, hyphenated word in backticks: ${rawSlug}`)
    }
    if (name === '' || description === '') throw new Error(`Topic row has an empty cell: ${line}`)
    if (/[`<>*_[\]]/.test(name + description)) {
      throw new Error(`Topic text must be plain, with no Markdown or HTML: ${line}`)
    }
    if (seen.has(slug)) throw new Error(`Duplicate topic slug: ${slug}`)
    seen.add(slug)
    return { name, slug, description }
  })
  return { updated, topics }
}

/** "No summaries yet", "1 summary", "12 summaries". */
export function summaryCount(count: number): string {
  if (count === 0) return 'No summaries yet'
  const one = new Intl.PluralRules('en-AU').select(count) === 'one'
  return `${count.toLocaleString('en-AU')} ${one ? 'summary' : 'summaries'}`
}
