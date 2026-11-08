'use client'

import { usePathname } from 'next/navigation'
import { useEffect, useRef } from 'react'

/**
 * After a client-side navigation to a new page, moves focus to the page's h1, so keyboard and
 * screen-reader users start at the new content (design/screens/app-shell.md, "Focus"). Not on
 * the first load, and not when the back or forward button restores a page.
 */
export function RouteFocus() {
  const pathname = usePathname()
  const previous = useRef(pathname)
  const historyNavigation = useRef(false)

  useEffect(() => {
    const onPopState = () => {
      historyNavigation.current = true
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    if (previous.current === pathname) return
    previous.current = pathname
    if (historyNavigation.current) {
      historyNavigation.current = false
      return
    }
    focusHeading()
  }, [pathname])

  return null
}

/** Focuses the main h1 without a ring and without scrolling past the header. */
export function focusHeading() {
  const heading = document.querySelector<HTMLElement>('main h1')
  if (heading === null) return
  heading.tabIndex = -1
  heading.focus()
}
