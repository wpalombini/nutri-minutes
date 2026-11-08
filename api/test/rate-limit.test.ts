import { Hono } from 'hono'
import { describe, expect, it } from 'vitest'
import type { AccessVariables } from '../src/access.js'
import { rateLimit } from '../src/rate-limit.js'
import { captureLogs } from './helpers.js'

function setup(limit: number) {
  let time = 1_000_000
  const logs = captureLogs()
  const app = new Hono<{ Variables: AccessVariables }>()
  app.use(async (c, next) => {
    c.set('accessClientId', c.req.header('x-test-client') ?? 'client-a')
    await next()
  })
  app.use(rateLimit({ limit, windowMs: 60_000, now: () => time }, logs.logger))
  app.get('/', (c) => c.json({ ok: true }))
  const request = (client = 'client-a') =>
    app.request('/', { headers: { 'x-test-client': client } })
  return { request, logs, advance: (ms: number) => (time += ms) }
}

describe('rateLimit', () => {
  it('allows requests up to the limit, then returns 429 with Retry-After', async () => {
    const { request, logs, advance } = setup(2)
    expect((await request()).status).toBe(200)
    advance(10_000)
    expect((await request()).status).toBe(200)
    const limited = await request()
    expect(limited.status).toBe(429)
    expect(await limited.json()).toEqual({ error: 'rate_limited' })
    expect(limited.headers.get('retry-after')).toBe('50')
    await request()
    expect(logs.lines.filter((l) => l.message === 'rate limited')).toHaveLength(1)
  })

  it('counts each client separately', async () => {
    const { request } = setup(1)
    expect((await request('client-a')).status).toBe(200)
    expect((await request('client-a')).status).toBe(429)
    expect((await request('client-b')).status).toBe(200)
  })

  it('keeps memory bounded by forgetting the oldest client', async () => {
    const { request } = setup(1)
    expect((await request('first')).status).toBe(200)
    for (let i = 0; i < 1_000; i++) await request(`client-${i}`)
    expect((await request('first')).status).toBe(200)
  })

  it('starts a new window after the period', async () => {
    const { request, advance } = setup(1)
    expect((await request()).status).toBe(200)
    expect((await request()).status).toBe(429)
    advance(60_000)
    expect((await request()).status).toBe(200)
  })
})
