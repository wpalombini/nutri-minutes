import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import NotFound from '@/app/not-found'
import TopicsPage from '@/app/topics/page'
import { ErrorMessage, errorDigest } from '@/components/ErrorMessage'
import { currentState, MainNav } from '@/components/MainNav'
import { SiteFooter } from '@/components/SiteFooter'
import { SiteHeader } from '@/components/SiteHeader'
import { SiteShell } from '@/components/SiteShell'

const pathname = vi.hoisted(() => ({ current: '/' }))
vi.mock('@/lib/pages', () => ({
  loadTopics: async () => [
    { name: 'Bone health', slug: 'bone-health', description: 'Research on bones.' },
  ],
}))
vi.mock('next/navigation', () => ({ usePathname: () => pathname.current }))

afterEach(() => {
  cleanup()
  pathname.current = '/'
})

function renderShell() {
  return render(
    <SiteShell
      header={
        <SiteHeader tagline="Nutrition science for a longer, stronger life.">
          <MainNav />
        </SiteHeader>
      }
    >
      <h1>Page</h1>
    </SiteShell>,
  )
}

describe('SiteShell', () => {
  it('starts with a skip link to the main landmark', () => {
    renderShell()
    const first = screen.getAllByRole('link')[0]
    expect(first?.textContent).toBe('Skip to main content')
    expect(first?.getAttribute('href')).toBe('#main')
    const main = screen.getByRole('main')
    expect(main.id).toBe('main')
    expect(main.getAttribute('tabindex')).toBe('-1')
  })

  it('has one banner, one main navigation, one main and one footer, and nothing else', () => {
    renderShell()
    expect(screen.getAllByRole('banner')).toHaveLength(1)
    expect(screen.getAllByRole('navigation')).toHaveLength(1)
    expect(screen.getAllByRole('contentinfo')).toHaveLength(1)
  })

  it('has the wordmark and the main navigation in order', () => {
    renderShell()
    const banner = screen.getByRole('banner')
    const wordmark = within(banner).getByRole('link', { name: 'Nutri Minutes' })
    expect(wordmark.getAttribute('href')).toBe('/')
    expect(wordmark.getAttribute('translate')).toBe('no')
    expect(wordmark.textContent).toBe('Nutri Minutes')
    expect(wordmark.getAttribute('aria-current')).toBeNull()
    const nav = within(banner).getByRole('navigation', { name: 'Main' })
    expect(nav.querySelector('ul')?.getAttribute('role')).toBe('list')
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => [link.textContent, link.getAttribute('href')]),
    ).toEqual([
      ['This week', '/'],
      ['Topics', '/topics'],
      ['How we grade', '/how-we-grade'],
    ])
  })

  it('shows the tagline in the header, outside the wordmark link', () => {
    renderShell()
    const banner = screen.getByRole('banner')
    const tagline = within(banner).getByText('Nutrition science for a longer, stronger life.')
    expect(tagline.tagName).toBe('P')
    expect(tagline.closest('a')).toBeNull()
    expect(within(banner).getByRole('link', { name: 'Nutri Minutes' })).toBeTruthy()
  })

  it('leaves out the tagline when none is given', () => {
    render(<SiteHeader />)
    expect(screen.queryByText('Nutrition science for a longer, stronger life.')).toBeNull()
    expect(screen.getByRole('banner').querySelector('p')).toBeNull()
  })

  it('marks the current page, and the current section', () => {
    pathname.current = '/topics'
    renderShell()
    expect(screen.getByRole('link', { name: 'Topics' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'This week' }).getAttribute('aria-current')).toBeNull()
  })
})

describe('currentState', () => {
  it('follows design/screens/app-shell.md', () => {
    expect(currentState('/', '/')).toBe('page')
    expect(currentState('/', '/studies/abc')).toBeUndefined()
    expect(currentState('/topics', '/topics')).toBe('page')
    expect(currentState('/topics', '/topics/bone-health')).toBe('true')
    expect(currentState('/topics', '/topicsx')).toBeUndefined()
    expect(currentState('/how-we-grade', '/how-we-grade')).toBe('page')
  })
})

describe('SiteFooter', () => {
  it('carries the disclosure exactly as the spec words it', () => {
    render(<SiteFooter />)
    const footer = screen.getByRole('contentinfo')
    const paragraphs = [...footer.querySelectorAll('p')].map((p) => p.textContent)
    expect(paragraphs).toEqual([
      'Summaries on Nutri Minutes are written by artificial intelligence from each study and checked against it. They are not medical advice.',
      'No advertising, sponsorship or affiliate links.',
    ])
    expect(footer.textContent).not.toMatch(/\bAI\b/)
  })

  it('links to how summaries are made and how we grade, outside any nav landmark', () => {
    render(<SiteFooter />)
    const footer = screen.getByRole('contentinfo')
    expect(
      within(footer)
        .getAllByRole('link')
        .map((link) => [link.textContent, link.getAttribute('href')]),
    ).toEqual([
      ['How summaries are made', '/how-summaries-are-made'],
      ['How we grade', '/how-we-grade'],
    ])
    expect(within(footer).queryByRole('navigation')).toBeNull()
    expect(footer.querySelector('ul')?.getAttribute('role')).toBe('list')
  })
})

describe('ErrorMessage', () => {
  it('offers a retry and a way home, and shows only the digest', () => {
    const retry = vi.fn()
    const error = Object.assign(new Error('secret upstream detail'), { digest: '3141592653' })
    render(<ErrorMessage error={error} retry={retry} />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('This page didn’t load')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledOnce()
    expect(
      screen.getByRole('link', { name: 'Go to this week’s findings' }).getAttribute('href'),
    ).toBe('/')
    expect(screen.getByText('3141592653').parentElement?.textContent).toBe('Reference: 3141592653')
    expect(document.body.textContent).not.toContain('secret upstream detail')
  })

  it('reads the digest only when there is one', () => {
    expect(errorDigest(new Error('x'))).toBeUndefined()
    expect(errorDigest('thrown string')).toBeUndefined()
    expect(errorDigest({ digest: '' })).toBeUndefined()
    expect(errorDigest({ digest: 'abc' })).toBe('abc')
  })
})

describe('unstyled lists', () => {
  it('keep list semantics for Safari with VoiceOver on the 404 page', () => {
    render(<NotFound />)
    expect(screen.getByRole('list').getAttribute('role')).toBe('list')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('keep list semantics on the topics page', async () => {
    render(await TopicsPage())
    expect(screen.getByRole('list').getAttribute('role')).toBe('list')
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(0)
  })
})
