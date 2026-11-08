import styles from './SkipLink.module.css'

export const MAIN_ID = 'main'

/** The first focusable element on every page. Hidden until it has focus. */
export function SkipLink() {
  return (
    <a className={styles.skipLink} href={`#${MAIN_ID}`}>
      Skip to main content
    </a>
  )
}
