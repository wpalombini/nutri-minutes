import {
  createLocalJWKSet,
  exportJWK,
  generateKeyPair,
  type JWTPayload,
  type JWTVerifyGetKey,
  SignJWT,
} from 'jose'
import type { LogFields, Logger } from '../src/logger.js'

export const TEAM_DOMAIN = 'https://example-team.cloudflareaccess.com'
export const AUDIENCE = 'a'.repeat(64)
export const CLIENT_ID = '0123456789abcdef.access'

export interface TestKeys {
  keys: JWTVerifyGetKey
  sign: (claims?: JWTPayload, options?: SignOptions) => Promise<string>
}

interface SignOptions {
  issuer?: string
  audience?: string
  /** `null` leaves out the expiry claim. */
  expiresAt?: number | string | null
  kid?: string
}

/** A local key set standing in for the Access certs endpoint, and a signer for its key. */
export async function testKeys(): Promise<TestKeys> {
  const { publicKey, privateKey } = await generateKeyPair('RS256')
  const jwk = { ...(await exportJWK(publicKey)), kid: 'test-key', alg: 'RS256' }
  const keys = createLocalJWKSet({ keys: [jwk] })
  const sign = (claims: JWTPayload = { common_name: CLIENT_ID }, options: SignOptions = {}) => {
    const jwt = new SignJWT(claims)
      .setProtectedHeader({ alg: 'RS256', kid: options.kid ?? 'test-key' })
      .setIssuer(options.issuer ?? TEAM_DOMAIN)
      .setAudience(options.audience ?? AUDIENCE)
      .setIssuedAt()
    if (options.expiresAt !== null) jwt.setExpirationTime(options.expiresAt ?? '5m')
    return jwt.sign(privateKey)
  }
  return { keys, sign }
}

export interface Captured {
  logger: Logger
  lines: Array<LogFields & { level: string; message: string }>
  text: () => string
}

export function captureLogs(): Captured {
  const raw: string[] = []
  const lines: Captured['lines'] = []
  const write =
    (level: string) =>
    (message: string, fields: LogFields = {}) => {
      const line = { ...fields, level, message }
      lines.push(line)
      raw.push(JSON.stringify(line))
    }
  return {
    logger: { info: write('info'), warn: write('warn'), error: write('error') },
    lines,
    text: () => raw.join('\n'),
  }
}
