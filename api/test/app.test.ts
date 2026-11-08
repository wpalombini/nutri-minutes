import { describe, expect, it } from 'vitest'
import { ACCESS_JWT_HEADER, requireAccess } from '../src/access.js'
import { createApp } from '../src/app.js'
import { AUDIENCE, CLIENT_ID, captureLogs, TEAM_DOMAIN, testKeys } from './helpers.js'

async function setup(checkDatabase: () => Promise<void> = async () => {}) {
  const keys = await testKeys()
  const logs = captureLogs()
  const app = createApp({
    access: requireAccess(
      { teamDomain: TEAM_DOMAIN, audience: AUDIENCE, keys: keys.keys },
      logs.logger,
    ),
    checkDatabase,
    logger: logs.logger,
    readinessTimeoutMs: 50,
  })
  return { app, logs, sign: keys.sign }
}

describe('health checks', () => {
  it('reports liveness without a token or a database, and does not log it', async () => {
    const { app, logs } = await setup(async () => {
      throw new Error('down')
    })
    const res = await app.request('/healthz')
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ status: 'ok' })
    expect(logs.lines).toHaveLength(0)
  })

  it('reports ready when the database answers', async () => {
    const { app } = await setup()
    const res = await app.request('/readyz')
    expect(res.status).toBe(200)
  })

  it('reports unavailable when the database fails', async () => {
    const { app } = await setup(async () => {
      throw new Error('connection refused')
    })
    const res = await app.request('/readyz')
    expect(res.status).toBe(503)
    expect(await res.json()).toEqual({ status: 'unavailable' })
  })

  it('reports unavailable when the database hangs', async () => {
    const { app } = await setup(() => new Promise(() => {}))
    const res = await app.request('/readyz')
    expect(res.status).toBe(503)
  })
})

describe('/v1', () => {
  it('requires an Access token', async () => {
    const { app } = await setup()
    const res = await app.request('/v1/ping')
    expect(res.status).toBe(401)
  })

  it('serves an authenticated request and logs the client ID without the query string', async () => {
    const { app, logs, sign } = await setup()
    const res = await app.request('/v1/ping?secret=value', {
      headers: { [ACCESS_JWT_HEADER]: await sign() },
    })
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ status: 'ok' })
    const line = logs.lines.find((l) => l.message === 'request')
    expect(line).toMatchObject({
      method: 'GET',
      path: '/v1/ping',
      status: 200,
      client_id: CLIENT_ID,
    })
    expect(logs.text()).not.toContain('secret=value')
  })
})

describe('errors and headers', () => {
  it('returns JSON for unknown paths', async () => {
    const { app } = await setup()
    const res = await app.request('/nope')
    expect(res.status).toBe(404)
    expect(await res.json()).toEqual({ error: 'not_found' })
  })

  it('hides internal error details', async () => {
    const { app, logs } = await setup()
    app.get('/boom', () => {
      throw new Error('password=hunter2')
    })
    const res = await app.request('/boom')
    expect(res.status).toBe(500)
    expect(await res.text()).not.toContain('hunter2')
    expect(logs.text()).not.toContain('hunter2')
  })

  it('rejects large request bodies', async () => {
    const { app } = await setup()
    const res = await app.request('/v1/ping', {
      method: 'POST',
      body: 'x'.repeat(65 * 1024),
      headers: { 'content-type': 'text/plain' },
    })
    expect(res.status).toBe(413)
  })

  it('sets security headers', async () => {
    const { app } = await setup()
    const res = await app.request('/healthz')
    expect(res.headers.get('x-content-type-options')).toBe('nosniff')
    expect(res.headers.get('strict-transport-security')).toContain('max-age=')
  })
})
