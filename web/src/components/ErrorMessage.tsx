'use client'

import Link from 'next/link'
import { useEffect } from 'react'
import { PageHeading } from './PageHeading'
import { focusHeading } from './RouteFocus'
import styles from './ErrorMessage.module.css'

export const ERROR_TITLE = 'This page didn’t load'

/** The digest Next.js attaches to server errors, if any. Nothing else about the error is shown. */
export function errorDigest(error: unknown): string | undefined {
  if (typeof error !== 'object' || error === null || !('digest' in error)) return undefined
  return typeof error.digest === 'string' && error.digest !== '' ? error.digest : undefined
}

/**
 * What a reader sees when a page fails to render (design/screens/app-shell.md, "Error").
 * Details stay in the server logs, matched by the reference.
 */
export function ErrorMessage({ error, retry }: { error: unknown; retry: () => void }) {
  const digest = errorDigest(error)

  // When the error replaces content the reader was using, move focus to its heading. On a
  // fresh page load nothing has focus yet, so leave the skip link as the first stop.
  useEffect(() => {
    if (document.activeElement !== null && document.activeElement !== document.body) {
      focusHeading()
    }
  }, [])

  return (
    <>
      <title>{`${ERROR_TITLE} – Nutri Minutes`}</title>
      <PageHeading title={ERROR_TITLE}>
        <p>
          Something went wrong on our side while loading this page. Try again, or come back in a few
          minutes.
        </p>
      </PageHeading>
      <div className={styles.actions}>
        <button className={styles.button} type="button" onClick={() => retry()}>
          Try again
        </button>
        <Link className={styles.link} href="/">
          Go to this week’s findings
        </Link>
      </div>
      {digest === undefined ? null : (
        <p className={styles.reference}>
          Reference: <span className={styles.digest}>{digest}</span>
        </p>
      )}
    </>
  )
}
