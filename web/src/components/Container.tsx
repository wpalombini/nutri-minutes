import type { ReactNode } from 'react'
import styles from './Container.module.css'

/** The page width and side gutters shared by the header, main content and footer. */
export function Container({ children }: { children: ReactNode }) {
  return <div className={styles.container}>{children}</div>
}
