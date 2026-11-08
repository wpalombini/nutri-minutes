/**
 * Site-wide settings from plain environment variables (see the repo's `.env.example`). They are
 * read at build time for static pages, so changing one needs a new deployment.
 */

export const siteName = 'Nutri Minutes'

export const siteDescription =
  'New nutrition research in plain English, graded for how much it can be trusted and linked to its source.'

const DEFAULT_SITE_URL = 'https://nutriminutes.com'

type Env = Readonly<Record<string, string | undefined>>

/** The canonical origin for metadata, the sitemap and robots.txt. `SITE_URL`, an origin only. */
export function siteUrl(env: Env = process.env): URL {
  const raw = env.SITE_URL?.trim() || DEFAULT_SITE_URL
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    throw new Error('SITE_URL is invalid: it must be an absolute URL')
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('SITE_URL is invalid: it must use http or https')
  }
  if (url.origin !== raw.replace(/\/$/, '')) {
    throw new Error('SITE_URL is invalid: it must be an origin, with no path, query or credentials')
  }
  return new URL(url.origin)
}

/**
 * Whether search engines may index the site. Off unless `SITE_ALLOW_INDEXING` is exactly
 * `true`, so previews and the site before launch stay out of search results.
 */
export function allowIndexing(env: Env = process.env): boolean {
  return env.SITE_ALLOW_INDEXING === 'true'
}
