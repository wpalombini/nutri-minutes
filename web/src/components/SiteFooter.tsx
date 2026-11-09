import Link from 'next/link'
import { Container } from './Container'
import styles from './SiteFooter.module.css'
import { ThemeControl } from './ThemeControl'

/** Exactly as design/screens/app-shell.md, "Footer", from PLAN principle 7. */
export const DISCLOSURE =
  'Summaries on Nutri Minutes are written by artificial intelligence from each study and checked against it. They are not medical advice.'

/** Pending the owner's decision (design/OPEN-QUESTIONS.md). */
export const NO_ADVERTISING = 'No advertising, sponsorship or affiliate links.'

export const footerLinks = [
  { href: '/how-summaries-are-made', label: 'How summaries are made' },
  { href: '/how-we-grade', label: 'How we grade' },
] as const

/** The disclosure every page carries, and the footer links. */
export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <Container>
        <div className={styles.inner}>
          <p className={styles.disclosure}>{DISCLOSURE}</p>
          <ul className={styles.links}>
            {footerLinks.map((link) => (
              <li key={link.href}>
                <Link className={styles.link} href={link.href}>
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
          <p className={styles.note}>{NO_ADVERTISING}</p>
          <div className={styles.theme}>
            <ThemeControl />
          </div>
        </div>
      </Container>
    </footer>
  )
}
