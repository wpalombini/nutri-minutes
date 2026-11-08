import type { MetadataRoute } from 'next'
import { allowIndexing, siteUrl } from '@/lib/site'

export default function robots(): MetadataRoute.Robots {
  if (!allowIndexing()) {
    return { rules: { userAgent: '*', disallow: '/' } }
  }
  return {
    rules: { userAgent: '*', allow: '/' },
    sitemap: new URL('/sitemap.xml', siteUrl()).href,
  }
}
