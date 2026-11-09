import 'server-only'
import { cacheLife } from 'next/cache'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { type ProseDocument, parseProsePage } from './prose'
import { type Topic, parseTopics } from './topics'

export type ProseSlug = 'how-we-grade' | 'how-summaries-are-made'

/** Reads a prose page from `content/pages` at build time. Only known slugs reach the disk. */
export async function loadProsePage(slug: ProseSlug): Promise<ProseDocument> {
  const file = path.join(process.cwd(), 'content', 'pages', `${slug}.md`)
  return parseProsePage(await readFile(file, 'utf8'))
}

/** Reads the owner-approved topic list at build time (temporary, until the API has topics). */
export async function loadTopics(): Promise<Topic[]> {
  'use cache'
  cacheLife('max') // The file only changes with a deploy.
  const file = path.join(process.cwd(), 'content', 'topics.md')
  return parseTopics(await readFile(file, 'utf8')).topics
}
