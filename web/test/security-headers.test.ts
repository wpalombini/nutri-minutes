// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { contentSecurityPolicy, securityHeaders } from '@/lib/security-headers'

const header = (headers: { key: string; value: string }[], key: string) =>
  headers.find((entry) => entry.key === key)?.value

describe('securityHeaders', () => {
  const production = securityHeaders({ development: false, allowIndexing: false })

  it('sets the strict headers', () => {
    expect(header(production, 'Strict-Transport-Security')).toBe(
      'max-age=63072000; includeSubDomains',
    )
    expect(header(production, 'X-Content-Type-Options')).toBe('nosniff')
    expect(header(production, 'Referrer-Policy')).toBe('strict-origin-when-cross-origin')
    expect(header(production, 'Permissions-Policy')).toContain('camera=()')
    expect(header(production, 'X-Frame-Options')).toBe('DENY')
  })

  it('sends noindex unless indexing is allowed', () => {
    expect(header(production, 'X-Robots-Tag')).toBe('noindex, nofollow')
    expect(
      header(securityHeaders({ development: false, allowIndexing: true }), 'X-Robots-Tag'),
    ).toBe(undefined)
  })
})

describe('contentSecurityPolicy', () => {
  const policy = contentSecurityPolicy({ development: false })
  const directives = new Map(
    policy.split('; ').map((directive) => {
      const [name = '', ...sources] = directive.split(' ')
      return [name, sources]
    }),
  )

  it('never allows eval in production', () => {
    expect(policy).not.toContain('unsafe-eval')
  })

  it('locks down framing, plugins, base and form targets', () => {
    expect(directives.get('frame-ancestors')).toEqual(["'none'"])
    expect(directives.get('object-src')).toEqual(["'none'"])
    expect(directives.get('base-uri')).toEqual(["'none'"])
    expect(directives.get('form-action')).toEqual(["'self'"])
    expect(directives.has('upgrade-insecure-requests')).toBe(true)
  })

  it('loads scripts, styles, fonts and connections from this origin only', () => {
    expect(directives.get('default-src')).toEqual(["'self'"])
    expect(directives.get('script-src')).toEqual(["'self'", "'unsafe-inline'"])
    expect(directives.get('style-src')).toEqual(["'self'"])
    expect(directives.get('font-src')).toEqual(["'self'"])
    expect(directives.get('connect-src')).toEqual(["'self'"])
    expect(policy).not.toMatch(/https?:/)
  })

  it('relaxes only what next dev needs', () => {
    const dev = contentSecurityPolicy({ development: true })
    expect(dev).toContain("'unsafe-eval'")
    expect(dev).not.toContain('upgrade-insecure-requests')
  })
})
