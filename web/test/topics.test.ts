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

  it('ignores trailing spaces on table rows', () => {
    expect(
      parseTopics(
        make('| Topic | Slug | Description |  \n|---|---|---|\t\n' + row.trimEnd() + '   \n'),
      ).topics,
    ).toHaveLength(1)
  })

  it.each([
    ['no front matter', head + row, 'must start with front matter'],
    ['no title', make(head + row, '---\nupdated: 2026-11-09\n---\n'), 'needs a title'],
    ['a bad date', make(head + row, '---\ntitle: T\nupdated: 9/11/2026\n---\n'), 'updated date'],
    [
      'an impossible date',
      make(head + row, '---\ntitle: T\nupdated: 2026-02-30\n---\n'),
      'updated date',
    ],
    ['no table', make('Just text.\n'), 'has no table'],
    [
      'a wrong header',
      make('| Name | Slug | Description |\n|---|---|---|\n' + row),
      'header must be',
    ],
    ['no divider', make('| Topic | Slug | Description |\n' + row), 'divider row'],
    ['no rows', make(head), 'has no rows'],
    ['a missing cell', make(head + '| Bone health | `bone-health` |\n'), 'needs 3 cells'],
    ['an extra cell', make(head + '| Bone health | `bone-health` | x | y |\n'), 'needs 3 cells'],
    ['an unquoted slug', make(head + '| Bone health | bone-health | x |\n'), 'slug must be'],
    ['an uppercase slug', make(head + '| Bone health | `Bone_Health` | x |\n'), 'slug must be'],
    ['an empty description', make(head + '| Bone health | `bone-health` |  |\n'), 'empty cell'],
    [
      'Markdown in a cell',
      make(head + '| Bone **health** | `bone-health` | x |\n'),
      'must be plain',
    ],
    [
      'HTML in a cell',
      make(head + '| Bone health | `bone-health` | <b>x</b> |\n'),
      'must be plain',
    ],
    ['a duplicate slug', make(head + row + row), 'Duplicate topic slug'],
    ['content after the table', make(head + row + '\nMore text.\n'), 'after the topic table'],
  ])('throws for %s', (_name, source, message) => {
    expect(() => parseTopics(source)).toThrow(message)
  })
})

describe('summaryCount', () => {
  it('says no summaries yet for 0, and pluralises', () => {
    expect(summaryCount(0)).toBe('No summaries yet')
    expect(summaryCount(1)).toBe('1 summary')
    expect(summaryCount(12)).toBe('12 summaries')
  })
})
