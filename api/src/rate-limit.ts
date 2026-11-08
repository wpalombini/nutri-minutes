import { createMiddleware } from 'hono/factory'
import type { AccessVariables } from './access.js'
import type { Logger } from './logger.js'

export interface RateLimitSettings {
  /** Requests allowed per client in each window. */
  limit: number
  windowMs: number
  now?: () => number
}

const MAX_TRACKED_CLIENTS = 1_000

/**
 * A fixed-window limit per Access client ID, run after `requireAccess`. Cloudflare's rate limit
 * rule is the main protection; this one caps a single leaked or misbehaving token. Counts are
 * kept in memory, so they reset when the process restarts.
 */
export function rateLimit(settings: RateLimitSettings, logger: Logger) {
  const now = settings.now ?? Date.now
  const windows = new Map<string, { start: number; count: number }>()
  return createMiddleware<{ Variables: AccessVariables }>(async (c, next) => {
    const clientId = c.get('accessClientId')
    const time = now()
    let window = windows.get(clientId)
    if (!window || time - window.start >= settings.windowMs) {
      if (!window && windows.size >= MAX_TRACKED_CLIENTS) {
        for (const [key, value] of windows) {
          if (time - value.start >= settings.windowMs) windows.delete(key)
        }
      }
      window = { start: time, count: 0 }
      windows.set(clientId, window)
    }
    window.count += 1
    if (window.count > settings.limit) {
      const retryAfter = Math.ceil((window.start + settings.windowMs - time) / 1000)
      if (window.count === settings.limit + 1) {
        logger.warn('rate limited', { client_id: clientId, path: c.req.path })
      }
      c.header('Retry-After', String(Math.max(retryAfter, 1)))
      return c.json({ error: 'rate_limited' }, 429)
    }
    await next()
  })
}
