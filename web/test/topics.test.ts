// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { parseTopics, summaryCount } from '@/lib/topics'

const front = '---\ntitle: Topic descriptions\nupdated: 2026-11-09\n---\n\nIntro.\n\n'
const head = '| Topic | Slug | Description |\n|---|---|---|\n'
const row = '| Bone health | `bone-health` | Research on bones. |\n'
const make = (table: string, frontMatter = front) => frontMatter + table

describe('parseTopics', () => {
  it('reads the approved file: seven topics in order', () => {
    const { topics, updated } = parseTopics(readFileSync('content/topics.md', 'utf8'))
    expect(updated).toBe('2026-11-09')
    expect(topics.map((t) => t.slug)).toEqual([
      'bone-health',
      'muscle-and-strength',
      'falls-and-independence',
      'heart-and-metabolism',
      'brain-health',
      'longevity',
      'genes-and-diet',
    ])
    expect(topics.every((t) => t.name && t.description)).toBe(true)
  })

  it('reads a row', () => {
    expect(parseTopics(make(head + row)).topics).toEqual([
      { name: 'Bone health', slug: 'bone-health', description: 'Research on bones.' },
    ])
  })

  it.each([
    ['no front matter', head + row],
    ['no title', make(head + row, '---\nupdated: 2026-11-09\n---\n')],
    ['a bad date', make(head + row, '---\ntitle: T\nupdated: 9/11/2026\n---\n')],
    ['no table', make('Just text.\n')],
    ['a wrong header', make('| Name | Slug | Description |\n|---|---|---|\n' + row)],
    ['no divider', make('| Topic | Slug | Description |\n' + row)],
    ['no rows', make(head)],
    ['a missing cell', make(head + '| Bone health | `bone-health` |\n')],
    ['an extra cell', make(head + '| Bone health | `bone-health` | x | y |\n')],
    ['an unquoted slug', make(head + '| Bone health | bone-health | x |\n')],
    ['an uppercase slug', make(head + '| Bone health | `Bone_Health` | x |\n')],
    ['an empty description', make(head + '| Bone health | `bone-health` |  |\n')],
    ['Markdown in a cell', make(head + '| Bone **health** | `bone-health` | x |\n')],
    ['HTML in a cell', make(head + '| Bone health | `bone-health` | <b>x</b> |\n')],
    ['a duplicate slug', make(head + row + row)],
    ['content after the table', make(head + row + '\nMore text.\n')],
  ])('throws for %s', (_name, source) => {
    expect(() => parseTopics(source)).toThrow()
  })
})

describe('summaryCount', () => {
  it('says no summaries yet for 0, and pluralises', () => {
    expect(summaryCount(0)).toBe('No summaries yet')
    expect(summaryCount(1)).toBe('1 summary')
    expect(summaryCount(12)).toBe('12 summaries')
  })
})
