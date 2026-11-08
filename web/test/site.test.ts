// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { allowIndexing, siteUrl } from '@/lib/site'

describe('siteUrl', () => {
  it('defaults to the production origin', () => {
    expect(siteUrl({}).href).toBe('https://nutriminutes.com/')
    expect(siteUrl({ SITE_URL: ' ' }).href).toBe('https://nutriminutes.com/')
  })

  it('accepts an origin, with or without a trailing slash', () => {
    expect(siteUrl({ SITE_URL: 'https://preview.example.test/' }).origin).toBe(
      'https://preview.example.test',
    )
  })

  it('rejects anything but an http or https origin', () => {
    for (const value of ['nutriminutes.com', 'ftp://example.test', 'https://example.test/path']) {
      expect(() => siteUrl({ SITE_URL: value }), value).toThrow('SITE_URL is invalid')
    }
  })
})

describe('allowIndexing', () => {
  it('is off unless set to exactly true', () => {
    expect(allowIndexing({})).toBe(false)
    expect(allowIndexing({ SITE_ALLOW_INDEXING: '1' })).toBe(false)
    expect(allowIndexing({ SITE_ALLOW_INDEXING: 'TRUE' })).toBe(false)
    expect(allowIndexing({ SITE_ALLOW_INDEXING: 'true' })).toBe(true)
  })
})
