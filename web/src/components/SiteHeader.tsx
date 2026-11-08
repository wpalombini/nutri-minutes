import Link from 'next/link'
import type { ReactNode } from 'react'
import { Container } from './Container'
import styles from './SiteHeader.module.css'

/**
 * The banner: the wordmark, then whatever navigation the page passes in. The root error page
 * shows the wordmark only (design/screens/app-shell.md, "Error").
 */
export function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className={styles.header}>
      <Container>
        <div className={styles.inner}>
          {/*
            A normal space, not the non-breaking space app-shell.md asks for: at 320px and 200%
            text the joined words are wider than the screen, which breaks reflow (WCAG 1.4.10).
            At normal text sizes the wordmark fits on one line anyway.
          */}
          <Link className={styles.wordmark} href="/" translate="no">
            Nutri Minutes
          </Link>
          {children}
        </div>
      </Container>
    </header>
  )
}
