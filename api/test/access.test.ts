import { Hono } from 'hono'
import { errors, SignJWT } from 'jose'
import { describe, expect, it } from 'vitest'
import { ACCESS_JWT_HEADER, type AccessVariables, requireAccess } from '../src/access.js'
import { AUDIENCE, CLIENT_ID, captureLogs, TEAM_DOMAIN, testKeys } from './helpers.js'

async function setup(keysOverride?: Parameters<typeof requireAccess>[0]['keys']) {
  const keys = await testKeys()
  const logs = captureLogs()
  const app = new Hono<{ Variables: AccessVariables }>()
  app.use(
    requireAccess(
      { teamDomain: TEAM_DOMAIN, audience: AUDIENCE, keys: keysOverride ?? keys.keys },
      logs.logger,
    ),
  )
  app.get('/', (c) => c.json({ clientId: c.get('accessClientId') }))
  const request = (token?: string) =>
    app.request('/', { headers: token ? { [ACCESS_JWT_HEADER]: token } : {} })
  return { ...keys, logs, request }
}

describe('requireAccess', () => {
  it('accepts a valid service token and exposes its client ID', async () => {
    const { sign, request } = await setup()
    const res = await request(await sign())
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ clientId: CLIENT_ID })
  })

  it('rejects a request without a token', async () => {
    const { request, logs } = await setup()
    const res = await request()
    expect(res.status).toBe(401)
    expect(await res.json()).toEqual({ error: 'unauthorized' })
    expect(logs.lines.at(-1)?.reason).toBe('missing_token')
  })

  it.each([
    ['another application', { audience: 'b'.repeat(64) }, 'claim_aud'],
    ['another team', { issuer: 'https://other.cloudflareaccess.com' }, 'claim_iss'],
    ['an expired token', { expiresAt: Math.floor(Date.now() / 1000) - 120 }, 'expired'],
    ['an unknown key', { kid: 'other-key' }, 'unknown_key'],
  ])('rejects a token for %s', async (_, options, reason) => {
    const { sign, request, logs } = await setup()
    const res = await request(await sign(undefined, options))
    expect(res.status).toBe(401)
    expect(logs.lines.at(-1)?.reason).toBe(reason)
  })

  it('allows a little clock skew on expiry', async () => {
    const { sign, request } = await setup()
    const res = await request(
      await sign(undefined, { expiresAt: Math.floor(Date.now() / 1000) - 5 }),
    )
    expect(res.status).toBe(200)
  })

  it('rejects a token signed by a different key with the same key ID', async () => {
    const { request } = await setup()
    const impostor = await testKeys()
    const res = await request(await impostor.sign())
    expect(res.status).toBe(401)
  })

  it('rejects an HS256 token', async () => {
    const { request } = await setup()
    const token = await new SignJWT({ common_name: CLIENT_ID })
      .setProtectedHeader({ alg: 'HS256', kid: 'test-key' })
      .setIssuer(TEAM_DOMAIN)
      .setAudience(AUDIENCE)
      .setIssuedAt()
      .setExpirationTime('5m')
      .sign(new TextEncoder().encode('x'.repeat(32)))
    const res = await request(token)
    expect(res.status).toBe(401)
  })

  it('rejects a token from a person rather than a service token', async () => {
    const { sign, request, logs } = await setup()
    const res = await request(await sign({ email: 'person@example.org' }))
    expect(res.status).toBe(401)
    expect(logs.lines.at(-1)?.reason).toBe('not_a_service_token')
  })

  it('rejects a malformed token', async () => {
    const { request } = await setup()
    const res = await request('not-a-jwt')
    expect(res.status).toBe(401)
  })

  it('returns 503 when the signing keys cannot be fetched', async () => {
    const { sign, request, logs } = await setup(async () => {
      throw new errors.JWKSTimeout()
    })
    const res = await request(await sign())
    expect(res.status).toBe(503)
    expect(logs.lines.at(-1)?.message).toBe('access keys unavailable')
  })

  it('never logs the token', async () => {
    const { sign, request, logs } = await setup()
    const token = await sign(undefined, { audience: 'b'.repeat(64) })
    await request(token)
    expect(logs.text()).not.toContain(token)
  })
})
