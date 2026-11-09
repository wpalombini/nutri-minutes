'use client'

import { useEffect, useSyncExternalStore } from 'react'
import { pageColour } from '@/generated/theme'
import {
  applyTheme,
  readStoredTheme,
  type ThemeChoice,
  themeChoices,
  themeFromStorageEvent,
  writeStoredTheme,
} from '@/lib/theme'
import styles from './ThemeControl.module.css'

const listeners = new Set<() => void>()
/** The choice for this page view when storage is blocked. */
let memoryChoice: ThemeChoice = 'system'

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange)
  const onStorage = (event: StorageEvent) => {
    if (themeFromStorageEvent(event) !== undefined) onChange()
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(onChange)
    window.removeEventListener('storage', onStorage)
  }
}

function getSnapshot(): ThemeChoice {
  return readStoredTheme() ?? memoryChoice
}

/** No option is checked and the control isn't ready until the client has read storage. */
function getServerSnapshot(): null {
  return null
}

function choose(choice: ThemeChoice): void {
  memoryChoice = choice
  writeStoredTheme(choice)
  for (const listener of listeners) listener()
}

/** With an override both tags show the chosen page colour; System restores the originals. */
function syncThemeColour(choice: ThemeChoice): void {
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    const system = meta.getAttribute('media')?.includes('dark') ? pageColour.dark : pageColour.light
    meta.content = choice === 'system' ? system : pageColour[choice]
  }
}

/** The reader's choice of System, Light or Dark: a native radio group (theme-control.md). */
export function ThemeControl() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  useEffect(() => {
    if (theme === null) return
    applyTheme(theme, document.documentElement)
    syncThemeColour(theme)
  }, [theme])

  return (
    <fieldset className={styles.control} data-ready={theme === null ? 'false' : 'true'}>
      <legend className={styles.legend}>Colour theme</legend>
      <div className={styles.options}>
        {themeChoices.map(({ value, label }) => (
          <label key={value} className={styles.option}>
            <input
              className={`${styles.input} visually-hidden-always`}
              type="radio"
              name="theme"
              value={value}
              checked={theme === value}
              onChange={() => choose(value)}
            />
            <span className={styles.box}>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
