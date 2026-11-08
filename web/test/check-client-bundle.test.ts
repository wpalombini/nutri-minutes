// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { clientFiles, needlesFromEnv, scan } from '../scripts/check-client-bundle.ts'

const env = {
  API_BASE_URL: 'https://api.bundle-check.invalid',
  CF_ACCESS_CLIENT_ID: 'bundle-check-client-id.access',
  CF_ACCESS_CLIENT_SECRET: 'bundle-check-secret-value',
}

let dir: string | undefined
afterEach(() => {
  if (dir) rmSync(dir, { recursive: true, force: true })
  dir = undefined
})

function fakeBuild(files: Record<string, string>): string {
  dir = mkdtempSync(join(tmpdir(), 'bundle-check-'))
  for (const [path, content] of Object.entries(files)) {
    const full = join(dir, path)
    mkdirSync(join(full, '..'), { recursive: true })
    writeFileSync(full, content)
  }
  return dir
}

describe('needlesFromEnv', () => {
  it('looks for the variable names, the API host and both token values', () => {
    expect(needlesFromEnv(env).map((needle) => needle.value)).toEqual([
      'API_BASE_URL',
      'CF_ACCESS_CLIENT_ID',
      'CF_ACCESS_CLIENT_SECRET',
      'api.bundle-check.invalid',
      env.CF_ACCESS_CLIENT_ID,
      env.CF_ACCESS_CLIENT_SECRET,
    ])
  })

  it('needs every value set, so the check is meaningful', () => {
    expect(() => needlesFromEnv({ API_BASE_URL: env.API_BASE_URL })).toThrow(
      'Set CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET',
    )
  })
})

describe('scan', () => {
  it('finds settings in static chunks and prerendered pages, and ignores server code', () => {
    const root = fakeBuild({
      'static/chunks/app.js': 'console.log("clean")',
      'static/chunks/leak.js': 'fetch("https://api.bundle-check.invalid/v1/ping")',
      'server/app/index.html': '<p>CF_ACCESS_CLIENT_SECRET</p>',
      'server/app/index.segments/_full.segment.rsc': 'bundle-check-client-id.access',
      'server/app/page.js': 'process.env.API_BASE_URL',
    })
    const findings = scan(clientFiles(root), needlesFromEnv(env)).map(({ file, label }) => [
      file.slice(root.length + 1),
      label,
    ])
    expect(findings).toEqual(
      expect.arrayContaining([
        ['static/chunks/leak.js', 'API host'],
        ['server/app/index.html', 'variable name'],
        ['server/app/index.segments/_full.segment.rsc', 'CF_ACCESS_CLIENT_ID value'],
      ]),
    )
    expect(findings).toHaveLength(3)
  })

  it('passes a clean build', () => {
    const root = fakeBuild({ 'static/chunks/app.js': 'ok', 'server/app/index.html': '<p>ok</p>' })
    expect(scan(clientFiles(root), needlesFromEnv(env))).toEqual([])
  })
})
