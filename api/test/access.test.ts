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

  it('rejects an unsigned token', async () => {
    const { request } = await setup()
    const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString('base64url')
    const now = Math.floor(Date.now() / 1000)
    const claims = {
      iss: TEAM_DOMAIN,
      aud: AUDIENCE,
      iat: now,
      exp: now + 300,
      common_name: CLIENT_ID,
    }
    const res = await request(`${encode({ alg: 'none' })}.${encode(claims)}.`)
    expect(res.status).toBe(401)
  })

  it('rejects a token without an expiry', async () => {
    const { sign, request, logs } = await setup()
    const res = await request(await sign(undefined, { expiresAt: null }))
    expect(res.status).toBe(401)
    expect(logs.lines.at(-1)?.reason).toBe('claim_exp')
  })

  it.each([
    ['a timeout', () => new errors.JWKSTimeout()],
    ['an error status from the certs endpoint', () => new errors.JOSEError('Expected 200 OK')],
    ['a network error', () => new TypeError('fetch failed')],
  ])('returns 503 when the signing keys cannot be fetched because of %s', async (_, makeError) => {
    const { sign, request, logs } = await setup(async () => {
      throw makeError()
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

describe('remoteAccessKeys', () => {
  it('fetches keys from the team certs endpoint', async () => {
    const { remoteAccessKeys } = await import('../src/access.js')
    const requested: string[] = []
    const realFetch = globalThis.fetch
    globalThis.fetch = (async (input: string | URL | Request) => {
      requested.push(String(input instanceof Request ? input.url : input))
      return new Response('{"keys":[]}', { headers: { 'content-type': 'application/json' } })
    }) as typeof fetch
    try {
      const getKey = remoteAccessKeys(TEAM_DOMAIN)
      await expect(
        getKey({ alg: 'RS256', kid: 'x' }, { payload: '', signature: '' } as never),
      ).rejects.toThrow()
    } finally {
      globalThis.fetch = realFetch
    }
    expect(requested).toEqual([`${TEAM_DOMAIN}/cdn-cgi/access/certs`])
  })
})
