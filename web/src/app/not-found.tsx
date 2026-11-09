import type { Metadata } from 'next'
import Link from 'next/link'
import { PageHeading } from '@/components/PageHeading'
import styles from './not-found.module.css'

export const metadata: Metadata = {
  title: 'Page not found',
}

/** design/screens/app-shell.md, "Page not found (404)". */
export default function NotFound() {
  return (
    <>
      <PageHeading title="Page not found">
        <p>There’s no page at this address. The link may be wrong, or the page may have moved.</p>
      </PageHeading>
      <ul role="list" className={styles.links}>
        <li>
          <Link className={styles.link} href="/">
            This week’s findings
          </Link>
        </li>
        <li>
          <Link className={styles.link} href="/topics">
            Browse topics
          </Link>
        </li>
      </ul>
    </>
  )
}
