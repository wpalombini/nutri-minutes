/**
 * The reader's colour theme choice (design/components/theme-control.md). Light and Dark are
 * stored on this device only; System is the absence of a stored value. Every storage access is
 * guarded, because browsers throw when storage is blocked.
 */

export type ThemeChoice = 'system' | 'light' | 'dark'

export const THEME_KEY = 'nm-theme'

export const themeChoices: readonly { value: ThemeChoice; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

/** Anything other than `light` or `dark` means System. */
export function parseTheme(value: string | null | undefined): ThemeChoice {
  return value === 'light' || value === 'dark' ? value : 'system'
}

/** The stored choice, or undefined when storage can't be read. */
export function readStoredTheme(): ThemeChoice | undefined {
  try {
    return parseTheme(window.localStorage.getItem(THEME_KEY))
  } catch {
    return undefined
  }
}

/** Stores Light or Dark, or removes the key for System. Returns false if storage is blocked. */
export function writeStoredTheme(choice: ThemeChoice): boolean {
  try {
    if (choice === 'system') window.localStorage.removeItem(THEME_KEY)
    else window.localStorage.setItem(THEME_KEY, choice)
    return true
  } catch {
    return false
  }
}

/** Sets `data-theme` on the root element for Light or Dark, and removes it for System. */
export function applyTheme(choice: ThemeChoice, root: HTMLElement): void {
  if (choice === 'system') delete root.dataset.theme
  else root.dataset.theme = choice
}

/** What the `storage` event means for the theme, or undefined if it isn't about the theme. */
export function themeFromStorageEvent(
  event: Pick<StorageEvent, 'key' | 'newValue'>,
): ThemeChoice | undefined {
  if (event.key !== null && event.key !== THEME_KEY) return undefined
  return event.key === null ? 'system' : parseTheme(event.newValue)
}

/**
 * Runs in `<head>` before first paint, so the page never flashes the wrong theme. Plain ES5,
 * no dependencies, and it never throws.
 */
export const themeInitScript = `try{var t=window.localStorage.getItem(${JSON.stringify(THEME_KEY)});if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`
