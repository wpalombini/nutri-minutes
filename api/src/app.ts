import { Hono, type MiddlewareHandler } from 'hono'
import { bodyLimit } from 'hono/body-limit'
import { createMiddleware } from 'hono/factory'
import { secureHeaders } from 'hono/secure-headers'
import type { AccessVariables } from './access.js'
import { describeError, type Logger } from './logger.js'

export interface AppDependencies {
  /** Authenticates `/v1` requests, usually `requireAccess`. */
  access: MiddlewareHandler<{ Variables: AccessVariables }>
  /** Limits authenticated `/v1` requests, usually `rateLimit`. */
  rateLimit?: MiddlewareHandler<{ Variables: AccessVariables }>
  checkDatabase: () => Promise<void>
  logger: Logger
  readinessTimeoutMs?: number
}

type Env = { Variables: Partial<AccessVariables> }

const MAX_BODY_BYTES = 64 * 1024

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: NodeJS.Timeout | undefined
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('Timed out')), ms)
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer))
}

/** Logs one line per request: no query string, headers or body, which may hold IDs or tokens. */
function requestLog(logger: Logger) {
  return createMiddleware<Env>(async (c, next) => {
    const started = performance.now()
    await next()
    if (c.req.path === '/healthz') return
    logger.info('request', {
      method: c.req.method,
      path: c.req.path,
      status: c.res.status,
      duration_ms: Math.round(performance.now() - started),
      client_id: c.get('accessClientId'),
    })
  })
}

export function createApp(deps: AppDependencies) {
  const app = new Hono<Env>()
  app.use(requestLog(deps.logger))
  app.use(secureHeaders())
  app.use(
    bodyLimit({
      maxSize: MAX_BODY_BYTES,
      onError: (c) => c.json({ error: 'payload_too_large' }, 413),
    }),
  )

  // Health checks are for Docker and operators on the VM. Requests through Cloudflare carry
  // CF-Ray, so they get a 404 and can't run database checks at will.
  const internalOnly = createMiddleware<Env>(async (c, next) => {
    if (c.req.header('cf-ray')) return c.json({ error: 'not_found' }, 404)
    await next()
  })
  app.use('/healthz', internalOnly)
  app.use('/readyz', internalOnly)

  // Liveness: the process is serving requests. It doesn't touch the database.
  app.get('/healthz', (c) => c.json({ status: 'ok' }))

  // Readiness: the database answers.
  app.get('/readyz', async (c) => {
    try {
      await withTimeout(deps.checkDatabase(), deps.readinessTimeoutMs ?? 2_000)
      return c.json({ status: 'ok' })
    } catch (error) {
      deps.logger.warn('readiness check failed', { error: describeError(error) })
      return c.json({ status: 'unavailable' }, 503)
    }
  })

  const v1 = new Hono<{ Variables: AccessVariables }>()
  v1.use(deps.access)
  if (deps.rateLimit) v1.use(deps.rateLimit)
  // Confirms a caller's credentials work end to end. Data endpoints come with published views.
  v1.get('/ping', (c) => c.json({ status: 'ok' }))
  app.route('/v1', v1)

  app.notFound((c) => c.json({ error: 'not_found' }, 404))
  app.onError((error, c) => {
    deps.logger.error('unhandled error', { error: describeError(error), path: c.req.path })
    return c.json({ error: 'internal_error' }, 500)
  })
  return app
}
