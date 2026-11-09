import type { MetadataRoute } from 'next'
import { siteUrl } from '@/lib/site'

const paths = ['/', '/how-we-grade', '/how-summaries-are-made']

export default function sitemap(): MetadataRoute.Sitemap {
  return paths.map((path) => ({ url: new URL(path, siteUrl()).href }))
}
