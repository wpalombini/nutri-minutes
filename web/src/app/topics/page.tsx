import type { Metadata } from 'next'
import Link from 'next/link'
import { loadTopics } from '@/lib/pages'
import { summaryCount } from '@/lib/topics'
import header from '@/components/TopicHeader.module.css'
import styles from './page.module.css'

export const metadata: Metadata = {
  title: 'Topics',
  description: 'The nutrition topics Nutri Minutes covers, and what each one includes.',
  alternates: { canonical: '/topics' },
}

/**
 * design/screens/topics.md, "/topics". Departure from the spec: the list comes from
 * `content/topics.md` until the API has a topics endpoint, and no topic has summaries yet.
 */
export default async function TopicsPage() {
  const topics = await loadTopics()
  return (
    <>
      <h1 className={header.title}>Topics</h1>
      <ul role="list" className={styles.list}>
        {topics.map((topic) => (
          <li key={topic.slug} className={styles.row}>
            <h2 className={styles.name}>
              <Link className={styles.link} href={`/topics/${topic.slug}`}>
                {topic.name}
              </Link>
            </h2>
            <p className={`${header.description} ${styles.description}`}>{topic.description}</p>
            <p className={header.count}>{summaryCount(0)}</p>
          </li>
        ))}
      </ul>
    </>
  )
}
