import { createMiddleware } from 'hono/factory'
import { createRemoteJWKSet, errors, type JWTVerifyGetKey, jwtVerify } from 'jose'
import type { Logger } from './logger.js'

/** Header in which Cloudflare Access forwards its signed JWT to the origin. */
export const ACCESS_JWT_HEADER = 'cf-access-jwt-assertion'

export interface AccessSettings {
  /** The team domain, such as https://example.cloudflareaccess.com. Also the expected `iss`. */
  teamDomain: string
  /** The Access application's AUD tag. */
  audience: string
  /** Resolves the signing key for a token, usually `remoteAccessKeys`. */
  keys: JWTVerifyGetKey
  clockToleranceSeconds?: number
}

export type AccessVariables = {
  /** The service token's client ID, which isn't secret, for logs. */
  accessClientId: string
}

/**
 * The team's public signing keys, fetched from Access and cached. Keys rotate, so a token
 * with an unknown `kid` triggers a refetch, at most once per cooldown period.
 */
export function remoteAccessKeys(teamDomain: string): JWTVerifyGetKey {
  return createRemoteJWKSet(new URL('/cdn-cgi/access/certs', teamDomain), {
    timeoutDuration: 5_000,
    cooldownDuration: 30_000,
    cacheMaxAge: 10 * 60_000,
  })
}

function denialReason(error: unknown): string {
  if (error instanceof errors.JWTExpired) return 'expired'
  if (error instanceof errors.JWTClaimValidationFailed) return `claim_${error.claim}`
  if (error instanceof errors.JOSEAlgNotAllowed) return 'algorithm_not_allowed'
  if (error instanceof errors.JWKSNoMatchingKey) return 'unknown_key'
  if (error instanceof errors.JWSSignatureVerificationFailed) return 'bad_signature'
  return 'malformed'
}

function keysUnavailable(error: unknown): boolean {
  // jose throws the base JOSEError when the certs endpoint answers with an error status.
  return (
    error instanceof errors.JWKSTimeout ||
    error instanceof errors.JWKSInvalid ||
    (error instanceof Error && error.constructor === errors.JOSEError)
  )
}

/**
 * Require a valid Cloudflare Access JWT from a service token, as described in ADR 0003. This is
 * the second check behind Access itself, so a misrouted tunnel can't skip authentication.
 */
export function requireAccess(settings: AccessSettings, logger: Logger) {
  const tolerance = settings.clockToleranceSeconds ?? 30
  return createMiddleware<{ Variables: AccessVariables }>(async (c, next) => {
    const token = c.req.header(ACCESS_JWT_HEADER)
    if (!token) {
      logger.warn('access denied', { reason: 'missing_token', path: c.req.path })
      return c.json({ error: 'unauthorized' }, 401)
    }
    let clientId: unknown
    try {
      const { payload } = await jwtVerify(token, settings.keys, {
        issuer: settings.teamDomain,
        audience: settings.audience,
        algorithms: ['RS256'],
        clockTolerance: tolerance,
        requiredClaims: ['exp', 'iat'],
      })
      clientId = payload.common_name
    } catch (error) {
      if (keysUnavailable(error) || !(error instanceof errors.JOSEError)) {
        // Also covers network errors while fetching keys, which aren't JOSE errors.
        logger.error('access keys unavailable', {
          error: error instanceof Error ? error.name : 'unknown',
        })
        return c.json({ error: 'unavailable' }, 503)
      }
      logger.warn('access denied', { reason: denialReason(error), path: c.req.path })
      return c.json({ error: 'unauthorized' }, 401)
    }
    // Only service tokens carry `common_name`. A user's browser session doesn't, and isn't allowed.
    if (typeof clientId !== 'string' || clientId === '') {
      logger.warn('access denied', { reason: 'not_a_service_token', path: c.req.path })
      return c.json({ error: 'unauthorized' }, 401)
    }
    c.set('accessClientId', clientId)
    await next()
  })
}
