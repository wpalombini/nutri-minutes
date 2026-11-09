import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { loadTopics } from '@/lib/pages'
import { summaryCount } from '@/lib/topics'
import header from '@/components/TopicHeader.module.css'
import styles from './page.module.css'

type Props = { params: Promise<{ topic: string }> }

export async function generateStaticParams() {
  return (await loadTopics()).map(({ slug }) => ({ topic: slug }))
}

async function findTopic(slug: string) {
  const topic = (await loadTopics()).find((candidate) => candidate.slug === slug)
  if (topic === undefined) notFound()
  return topic
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const topic = await findTopic((await params).topic)
  return {
    title: topic.name,
    description: topic.description,
    alternates: { canonical: `/topics/${topic.slug}` },
  }
}

/**
 * design/screens/topics.md, "/topics/[topic]", empty-topic state only. Departure from the
 * spec: the topic comes from `content/topics.md` until the API has a topics endpoint. Finding
 * rows and pagination come with the API, so `?page=` is not read and the page stays static.
 */
export default async function TopicPage({ params }: Props) {
  const topic = await findTopic((await params).topic)
  return (
    <>
      <Link className={header.back} href="/topics">
        Topics
      </Link>
      <h1 className={`${header.title} ${header.archiveTitle}`}>{topic.name}</h1>
      <p className={header.description}>{topic.description}</p>
      <p className={header.count}>{summaryCount(0)}</p>
      <p className={styles.empty}>No summaries in this topic yet.</p>
      <Link className={styles.findings} href="/">
        See this week’s findings
      </Link>
    </>
  )
}
