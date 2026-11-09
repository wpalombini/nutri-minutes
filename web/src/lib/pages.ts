import 'server-only'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { type ProseDocument, parseProsePage } from './prose'

export type ProseSlug = 'how-we-grade' | 'how-summaries-are-made'

/** Reads a prose page from `content/pages` at build time. Only known slugs reach the disk. */
export async function loadProsePage(slug: ProseSlug): Promise<ProseDocument> {
  const file = path.join(process.cwd(), 'content', 'pages', `${slug}.md`)
  return parseProsePage(await readFile(file, 'utf8'))
}
