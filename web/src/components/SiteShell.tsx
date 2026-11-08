import type { ReactNode } from 'react'
import { Container } from './Container'
import { SiteFooter } from './SiteFooter'
import { MAIN_ID, SkipLink } from './SkipLink'
import styles from './SiteShell.module.css'

/** The skip link, header, main landmark and footer around every page. */
export function SiteShell({ header, children }: { header: ReactNode; children: ReactNode }) {
  return (
    <>
      <SkipLink />
      {header}
      <main className={styles.main} id={MAIN_ID} tabIndex={-1}>
        <Container>{children}</Container>
      </main>
      <SiteFooter />
    </>
  )
}
