'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import styles from './MainNav.module.css'

export const navigation = [
  { href: '/', label: 'This week' },
  { href: '/topics', label: 'Topics' },
  { href: '/how-we-grade', label: 'How we grade' },
] as const

/**
 * `aria-current` for a nav link: "page" on the exact page, "true" on a page inside its section
 * (a topic archive under Topics), otherwise nothing. Home is a section of one page.
 */
export function currentState(href: string, pathname: string): 'page' | 'true' | undefined {
  if (pathname === href) return 'page'
  if (href !== '/' && pathname.startsWith(`${href}/`)) return 'true'
  return undefined
}

/** The three header links (design/screens/app-shell.md, "Header"). */
export function MainNav() {
  const pathname = usePathname()
  return (
    <nav className={styles.nav} aria-label="Main">
      <ul className={styles.list}>
        {navigation.map((item) => (
          <li key={item.href}>
            <Link
              className={styles.link}
              href={item.href}
              aria-current={currentState(item.href, pathname)}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
