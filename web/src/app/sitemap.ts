import type { MetadataRoute } from 'next'
import { loadTopics } from '@/lib/pages'
import { siteUrl } from '@/lib/site'

const paths = ['/', '/topics', '/how-we-grade', '/how-summaries-are-made']

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const topics = await loadTopics()
  return [...paths, ...topics.map(({ slug }) => `/topics/${slug}`)].map((path) => ({
    url: new URL(path, siteUrl()).href,
  }))
}
