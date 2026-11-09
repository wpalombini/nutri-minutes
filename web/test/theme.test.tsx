import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeControl, resetThemeMemoryForTests } from '@/components/ThemeControl'
import {
  applyTheme,
  parseTheme,
  readStoredTheme,
  THEME_KEY,
  themeFromStorageEvent,
  themeInitScript,
  writeStoredTheme,
} from '@/lib/theme'

beforeEach(() => {
  resetThemeMemoryForTests()
  window.localStorage.clear()
  delete document.documentElement.dataset.theme
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('parseTheme', () => {
  it('accepts light and dark and treats anything else as system', () => {
    expect(parseTheme('light')).toBe('light')
    expect(parseTheme('dark')).toBe('dark')
    for (const value of ['system', 'Dark', '', 'sepia', null, undefined]) {
      expect(parseTheme(value)).toBe('system')
    }
  })
})

describe('storage', () => {
  it('stores light and dark, and removes the key for system', () => {
    expect(writeStoredTheme('dark')).toBe(true)
    expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(readStoredTheme()).toBe('dark')
    writeStoredTheme('system')
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull()
    expect(readStoredTheme()).toBe('system')
  })

  it('never throws when storage is blocked', () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    expect(readStoredTheme()).toBeUndefined()
    expect(writeStoredTheme('light')).toBe(false)
  })
})

describe('storage events', () => {
  it('acts on the theme key, and on a cleared store, and ignores other keys', () => {
    expect(themeFromStorageEvent({ key: THEME_KEY, newValue: 'dark' })).toBe('dark')
    expect(themeFromStorageEvent({ key: THEME_KEY, newValue: 'odd' })).toBe('system')
    expect(themeFromStorageEvent({ key: THEME_KEY, newValue: null })).toBe('system')
    expect(themeFromStorageEvent({ key: null, newValue: null })).toBe('system')
    expect(themeFromStorageEvent({ key: 'other', newValue: 'dark' })).toBeUndefined()
  })
})

describe('applyTheme', () => {
  it('sets data-theme for light and dark and removes it for system', () => {
    applyTheme('dark', document.documentElement)
    expect(document.documentElement.dataset.theme).toBe('dark')
    applyTheme('system', document.documentElement)
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
})

describe('themeInitScript', () => {
  const run = () => new Function(themeInitScript)()

  it('sets data-theme from a stored value', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    run()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('sets nothing for system or an unknown value', () => {
    window.localStorage.setItem(THEME_KEY, 'sepia')
    run()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('does not throw when storage is blocked', () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    expect(run).not.toThrow()
  })
})

describe('ThemeControl', () => {
  function metas() {
    document.head.innerHTML =
      '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#edf2ef">' +
      '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0e1c19">'
    return [...document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')]
  }

  it('is a labelled group of three radios, checked from storage after mount', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    render(<ThemeControl />)
    const group = screen.getByRole('group', { name: 'Theme' })
    expect(group.getAttribute('data-ready')).toBe('true')
    expect(screen.getAllByRole('radio').map((radio) => radio.getAttribute('value'))).toEqual([
      'system',
      'light',
      'dark',
    ])
    expect((screen.getByRole('radio', { name: 'Dark' }) as HTMLInputElement).checked).toBe(true)
  })

  it('checks System when nothing is stored', () => {
    render(<ThemeControl />)
    expect((screen.getByRole('radio', { name: 'System' }) as HTMLInputElement).checked).toBe(true)
  })

  it('applies a choice at once, stores it and sets both theme-color tags', () => {
    const [light, dark] = metas()
    render(<ThemeControl />)
    fireEvent.click(screen.getByRole('radio', { name: 'Dark' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
    expect([light?.content, dark?.content]).toEqual(['#0e1c19', '#0e1c19'])

    fireEvent.click(screen.getByRole('radio', { name: 'System' }))
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull()
    expect([light?.content, dark?.content]).toEqual(['#edf2ef', '#0e1c19'])
  })

  it('still applies the choice for this page view when storage is blocked', () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    render(<ThemeControl />)
    fireEvent.click(screen.getByRole('radio', { name: 'Light' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect((screen.getByRole('radio', { name: 'Light' }) as HTMLInputElement).checked).toBe(true)
  })

  it('applies the choice for this page view when a write fails but reads still work', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    render(<ThemeControl />)
    fireEvent.click(screen.getByRole('radio', { name: 'Light' }))
    expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect((screen.getByRole('radio', { name: 'Light' }) as HTMLInputElement).checked).toBe(true)
  })

  it('starts each test from System, after the reset', () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    render(<ThemeControl />)
    expect((screen.getByRole('radio', { name: 'System' }) as HTMLInputElement).checked).toBe(true)
  })

  it('follows a change made in another tab without moving focus', () => {
    render(<ThemeControl />)
    screen.getByRole('radio', { name: 'System' }).focus()
    act(() => {
      window.localStorage.setItem(THEME_KEY, 'dark')
      window.dispatchEvent(new StorageEvent('storage', { key: THEME_KEY, newValue: 'dark' }))
    })
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect((screen.getByRole('radio', { name: 'Dark' }) as HTMLInputElement).checked).toBe(true)
    expect(document.activeElement).toBe(screen.getByRole('radio', { name: 'System' }))
  })
})
