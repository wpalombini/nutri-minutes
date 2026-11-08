/**
 * Response headers for every route, set from next.config.ts.
 *
 * The Content-Security-Policy is static, so pages can stay prerendered and cached. A nonce
 * would force every page to render per request, and Next.js has no built-in hashes for the
 * inline scripts it adds to App Router pages (the React Server Components payload), so
 * `script-src` allows `'unsafe-inline'`. Everything else is locked down: script files only from
 * this origin, no `eval`, no plugins, no framing, no `<base>` changes and no third-party
 * connections. React escapes all rendered text, and no code injects HTML from data.
 * See https://nextjs.org/docs/app/guides/content-security-policy ("Without Nonces").
 */

export interface SecurityHeaderOptions {
  /** `next dev` needs `eval` for React's debugging features, and a WebSocket for reloads. */
  development: boolean
  /** When false, every response also says `X-Robots-Tag: noindex, nofollow`. */
  allowIndexing: boolean
}

export interface Header {
  key: string
  value: string
}

export function contentSecurityPolicy({
  development,
}: Pick<SecurityHeaderOptions, 'development'>): string {
  const directives: Record<string, string[]> = {
    'default-src': ["'self'"],
    'script-src': ["'self'", "'unsafe-inline'", ...(development ? ["'unsafe-eval'"] : [])],
    // Stylesheets only from this origin. Inline style attributes are allowed because
    // next/image and React set them; `<style>` elements are not. Dev needs inline styles.
    'style-src': ["'self'", ...(development ? ["'unsafe-inline'"] : [])],
    'style-src-attr': ["'unsafe-inline'"],
    'img-src': ["'self'", 'data:', 'blob:'],
    'font-src': ["'self'"],
    'connect-src': ["'self'", ...(development ? ['ws:'] : [])],
    'manifest-src': ["'self'"],
    'media-src': ["'self'"],
    'worker-src': ["'self'"],
    'object-src': ["'none'"],
    'base-uri': ["'none'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'none'"],
    'frame-src': ["'none'"],
  }
  const policy = Object.entries(directives).map(([name, sources]) => `${name} ${sources.join(' ')}`)
  if (!development) policy.push('upgrade-insecure-requests')
  return policy.join('; ')
}

export function securityHeaders(options: SecurityHeaderOptions): Header[] {
  const headers: Header[] = [
    { key: 'Content-Security-Policy', value: contentSecurityPolicy(options) },
    { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains' },
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    {
      key: 'Permissions-Policy',
      value:
        'camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=(), bluetooth=(), browsing-topics=()',
    },
    { key: 'X-Frame-Options', value: 'DENY' },
    { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
  ]
  if (!options.allowIndexing) headers.push({ key: 'X-Robots-Tag', value: 'noindex, nofollow' })
  return headers
}
