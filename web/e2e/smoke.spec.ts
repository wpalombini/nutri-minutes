import { mkdirSync } from 'node:fs'
import AxeBuilder from '@axe-core/playwright'
import { expect, type Page, test } from '@playwright/test'

// ADR 0004: axe on every page with these tags; any violation fails.
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

// Screenshots are saved for review and uploaded by CI, never compared as baselines.
const SCREENSHOT_DIR = 'e2e-screenshots'

const pages = [
  {
    name: 'home',
    path: '/',
    status: 200,
    heading: 'Nutri Minutes is being rebuilt',
    title: 'Nutri Minutes',
  },
  {
    name: 'not-found',
    path: '/no-such-page',
    status: 404,
    heading: 'Page not found',
    title: 'Page not found – Nutri Minutes',
  },
] as const
const widths = [360, 1280] as const
const schemes = ['light', 'dark'] as const

/** Fails the test on any console error, including Content-Security-Policy violations. */
function watchConsole(page: Page): string[] {
  const problems: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error' && !/status of 404/.test(message.text())) {
      problems.push(message.text())
    }
  })
  page.on('pageerror', (error) => problems.push(error.message))
  return problems
}

/** Collects every request that leaves this origin. */
function watchRequests(page: Page, origin: string): string[] {
  const external: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.protocol.startsWith('http') && url.origin !== origin) external.push(url.href)
  })
  return external
}

for (const { name, path, status, heading, title } of pages) {
  for (const width of widths) {
    for (const scheme of schemes) {
      test(`${name} at ${width}px in ${scheme}`, async ({ page, baseURL }) => {
        const problems = watchConsole(page)
        const external = watchRequests(page, new URL(baseURL ?? '').origin)
        await page.emulateMedia({ colorScheme: scheme })
        await page.setViewportSize({ width, height: 800 })

        const response = await page.goto(path)
        expect(response?.status()).toBe(status)
        await page.waitForLoadState('networkidle')
        await page.evaluate(() => document.fonts.ready)

        await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
        await expect(page).toHaveTitle(title)
        await expect(page.getByRole('contentinfo')).toContainText(
          'written by artificial intelligence from each study and checked against it',
        )
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
          width,
        )

        const loadedFonts = await page.evaluate(() =>
          [...document.fonts].filter((font) => font.status === 'loaded').map((font) => font.family),
        )
        expect(new Set(loadedFonts.map((family) => family.replaceAll('"', '')))).toEqual(
          new Set(['Literata', 'Atkinson Hyperlegible Next']),
        )

        const background = await page.evaluate(
          () => getComputedStyle(document.body).backgroundColor,
        )
        expect(background).toBe(scheme === 'light' ? 'rgb(237, 242, 239)' : 'rgb(14, 28, 25)')

        const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
        expect(results.violations).toEqual([])

        mkdirSync(SCREENSHOT_DIR, { recursive: true })
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/${name}-${width}-${scheme}.png`,
          fullPage: true,
        })

        expect(problems).toEqual([])
        expect(external).toEqual([])
      })
    }
  }
}

test('the skip link is the first tab stop and moves focus to main', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Skip to main content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeInViewport()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
})

test('the document is set up for Australian English and both colour schemes', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('lang', 'en-AU')
  await expect(page).toHaveTitle('Nutri Minutes')
  const themeColours = await page
    .locator('meta[name="theme-color"]')
    .evaluateAll((metas) =>
      metas.map((meta) => [meta.getAttribute('media'), meta.getAttribute('content')]),
    )
  expect(themeColours).toEqual([
    ['(prefers-color-scheme: light)', '#edf2ef'],
    ['(prefers-color-scheme: dark)', '#0e1c19'],
  ])
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
    'href',
    '/manifest.webmanifest',
  )
  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveCount(1)
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveCount(1)
})

test('pages are kept out of search engines until launch', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow')
  const robots = await request.get('/robots.txt')
  expect(await robots.text()).toMatch(/User-Agent: \*\s+Disallow: \//)
})

test('every response carries the security headers', async ({ request }) => {
  for (const path of ['/', '/no-such-page', '/robots.txt', '/icons/icon-192.png']) {
    const response = await request.get(path)
    const headers = response.headers()
    expect(headers['content-security-policy'], path).toContain("frame-ancestors 'none'")
    expect(headers['content-security-policy'], path).not.toContain('unsafe-eval')
    expect(headers['strict-transport-security'], path).toBe('max-age=63072000; includeSubDomains')
    expect(headers['x-content-type-options'], path).toBe('nosniff')
    expect(headers['referrer-policy'], path).toBe('strict-origin-when-cross-origin')
    expect(headers['permissions-policy'], path).toContain('camera=()')
    expect(headers['x-robots-tag'], path).toBe('noindex, nofollow')
    expect(headers['x-powered-by'], path).toBeUndefined()
  }
})

test('the manifest lists the icons', async ({ request }) => {
  const manifest = await (await request.get('/manifest.webmanifest')).json()
  expect(manifest.theme_color).toBe('#edf2ef')
  for (const icon of manifest.icons as { src: string }[]) {
    expect((await request.get(icon.src)).status(), icon.src).toBe(200)
  }
})

test('pages reflow at 320px and at 200% text size without scrolling sideways', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  for (const { path } of pages) {
    await page.goto(path)
    // Through the CSSOM: the Content-Security-Policy blocks injected <style> elements.
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '200%'
    })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
      path,
    ).toBeLessThanOrEqual(320)
  }
})

test('after a client-side navigation, focus moves to the new page heading', async ({ page }) => {
  await page.goto('/no-such-page')
  await page.getByRole('link', { name: 'This week’s findings' }).click()
  await expect(page).toHaveURL('/')
  const heading = page.getByRole('heading', { level: 1 })
  await expect(heading).toHaveText('Nutri Minutes is being rebuilt')
  await expect(heading).toBeFocused()
})
