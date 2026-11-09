import { mkdirSync } from 'node:fs'
import AxeBuilder from '@axe-core/playwright'
import { expect, type Page, test } from '@playwright/test'

const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const SCREENSHOT_DIR = 'e2e-screenshots'
const LIGHT = 'rgb(237, 242, 239)'
const DARK = 'rgb(14, 28, 25)'

const background = (page: Page) =>
  page.evaluate(() => getComputedStyle(document.body).backgroundColor)
const dataTheme = (page: Page) =>
  page.evaluate(() => document.documentElement.getAttribute('data-theme'))
const stored = (page: Page) => page.evaluate(() => window.localStorage.getItem('nm-theme'))

/** The visible option: the radios themselves are hidden and drawn by their labels. */
const option = (page: Page, name: 'System' | 'Light' | 'Dark') =>
  page.getByRole('group', { name: 'Colour theme' }).getByText(name, { exact: true })
const radio = (page: Page, name: 'System' | 'Light' | 'Dark') => page.getByRole('radio', { name })

/** Blocks the app's scripts, so the page stays as the server and the head script left it. */
async function blockHydration(page: Page): Promise<void> {
  await page.route('**/_next/static/**/*.js', (route) => route.abort())
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
})

test('choosing a theme applies at once and persists across a reload', async ({ page }) => {
  await page.goto('/')
  await expect(radio(page, 'System')).toBeChecked()
  expect(await stored(page)).toBeNull()

  await option(page, 'Dark').click()
  await expect(radio(page, 'Dark')).toBeChecked()
  expect(await dataTheme(page)).toBe('dark')
  expect(await background(page)).toBe(DARK)
  expect(await stored(page)).toBe('dark')
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe(
    'dark',
  )

  await page.reload()
  await expect(radio(page, 'Dark')).toBeChecked()
  expect(await background(page)).toBe(DARK)

  await option(page, 'System').click()
  expect(await stored(page)).toBeNull()
  expect(await dataTheme(page)).toBeNull()
  expect(await background(page)).toBe(LIGHT)
})

test('Light overrides a dark device', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/')
  expect(await background(page)).toBe(DARK)
  await option(page, 'Light').click()
  expect(await background(page)).toBe(LIGHT)
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe(
    'light',
  )
})

test('the stored theme is applied before hydration, so there is no flash', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('nm-theme', 'dark'))
  await blockHydration(page)
  await page.goto('/')
  expect(await dataTheme(page)).toBe('dark')
  expect(await background(page)).toBe(DARK)
  // Still the server's markup: the control has not been revealed.
  await expect(page.locator('fieldset[data-ready="false"]')).toHaveCount(1)
})

test('System follows the device without a reload', async ({ page }) => {
  await page.goto('/')
  expect(await background(page)).toBe(LIGHT)
  await page.emulateMedia({ colorScheme: 'dark' })
  expect(await background(page)).toBe(DARK)
  await page.emulateMedia({ colorScheme: 'light' })
  expect(await background(page)).toBe(LIGHT)
})

test('both theme-color tags follow the choice, and System restores them', async ({ page }) => {
  const colours = () =>
    page
      .locator('meta[name="theme-color"]')
      .evaluateAll((metas) => metas.map((meta) => meta.getAttribute('content')))
  await page.goto('/')
  await option(page, 'Dark').click()
  await expect.poll(colours).toEqual(['#0e1c19', '#0e1c19'])
  await option(page, 'Light').click()
  await expect.poll(colours).toEqual(['#edf2ef', '#edf2ef'])
  await option(page, 'System').click()
  await expect.poll(colours).toEqual(['#edf2ef', '#0e1c19'])
})

test('another open tab follows the change without moving focus', async ({ context, page }) => {
  await page.goto('/')
  await radio(page, 'System').focus()
  const other = await context.newPage()
  await other.goto('/')
  await option(other, 'Dark').click()
  await expect.poll(() => dataTheme(page)).toBe('dark')
  await expect(radio(page, 'Dark')).toBeChecked()
  await expect(radio(page, 'System')).toBeFocused()
})

test('arrow keys move between options and apply each one', async ({ page }) => {
  await page.goto('/')
  await radio(page, 'System').focus()
  await page.keyboard.press('ArrowRight')
  await expect(radio(page, 'Light')).toBeFocused()
  await expect(radio(page, 'Light')).toBeChecked()
  expect(await dataTheme(page)).toBe('light')
  await page.keyboard.press('ArrowRight')
  await expect(radio(page, 'Dark')).toBeChecked()
  expect(await background(page)).toBe(DARK)
  await page.keyboard.press('ArrowLeft')
  await expect(radio(page, 'Light')).toBeChecked()
})

test('Tab reaches the group once, on the checked option', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'How we grade' }).last().focus()
  await page.keyboard.press('Tab')
  await expect(radio(page, 'System')).toBeFocused()
  await page.keyboard.press('Tab')
  expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe('INPUT')
})

test('without JavaScript the control is invisible and the page follows the system', async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false, colorScheme: 'dark' })
  const page = await context.newPage()
  await page.goto('/')
  await expect(page.locator('fieldset')).toBeHidden()
  await expect(page.getByRole('group', { name: 'Colour theme' })).toHaveCount(0)
  expect(await background(page)).toBe(DARK)
  await context.close()
})

test('revealing the control moves nothing on a short page', async ({ browser }) => {
  const footerTop = async (hydrate: boolean) => {
    const context = await browser.newContext({ viewport: { width: 360, height: 800 } })
    const page = await context.newPage()
    if (!hydrate) await blockHydration(page)
    await page.goto('/no-such-page')
    await page.waitForLoadState('networkidle')
    if (hydrate) await expect(page.locator('fieldset[data-ready="true"]')).toHaveCount(1)
    else await expect(page.locator('fieldset[data-ready="false"]')).toHaveCount(1)
    const box = await page.getByRole('contentinfo').boundingBox()
    await context.close()
    return box
  }
  const before = await footerTop(false)
  const after = await footerTop(true)
  expect(before).not.toBeNull()
  expect(after).toEqual(before)
})

for (const width of [360, 1280]) {
  for (const theme of ['system-light', 'system-dark', 'light', 'dark'] as const) {
    test(`axe is clean with ${theme} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await page.emulateMedia({ colorScheme: theme === 'system-dark' ? 'dark' : 'light' })
      await page.goto('/')
      if (theme === 'light' || theme === 'dark') {
        await option(page, theme === 'light' ? 'Light' : 'Dark').click()
        await expect(radio(page, theme === 'light' ? 'Light' : 'Dark')).toBeChecked()
      }
      await page.getByRole('radio', { checked: true }).focus()
      const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
      expect(results.violations).toEqual([])

      mkdirSync(SCREENSHOT_DIR, { recursive: true })
      await page.getByRole('contentinfo').screenshot({
        path: `${SCREENSHOT_DIR}/footer-${width}-${theme}.png`,
      })
    })
  }
}
