import type { ReactNode } from 'react'
import styles from './PageHeading.module.css'

/**
 * A page's h1 and its opening prose, as the prose page template sets them
 * (design/screens/app-shell.md, "Prose page template").
 */
export function PageHeading({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <>
      <h1 className={styles.title}>{title}</h1>
      {children === undefined ? null : <div className={styles.prose}>{children}</div>}
    </>
  )
}
