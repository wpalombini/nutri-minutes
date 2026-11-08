// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import {
  ApiConfigError,
  ApiError,
  createApiClient,
  isValidPath,
  readApiConfig,
  type ApiConfig,
} from '@/lib/api'

const SECRET = 'f'.repeat(64)
const env = {
  API_BASE_URL: 'https://api.example.test',
  CF_ACCESS_CLIENT_ID: '0123456789abcdef0123456789abcdef.access',
  CF_ACCESS_CLIENT_SECRET: SECRET,
}
const config: ApiConfig = readApiConfig(env)

const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json; charset=utf-8' },
    ...init,
  })

const asPing = (body: unknown): { status: string } => {
  if (
    typeof body === 'object' &&
    body !== null &&
    'status' in body &&
    typeof body.status === 'string'
  ) {
    return { status: body.status }
  }
  throw new Error('not a ping')
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiError) return error
    throw error
  }
  throw new Error('expected an ApiError')
}

function expectNoSecrets(error: Error) {
  const text = `${error.message} ${JSON.stringify(error)} ${String(error.stack)}`
  expect(text).not.toContain(SECRET)
  expect(text).not.toContain(env.CF_ACCESS_CLIENT_ID)
}

describe('readApiConfig', () => {
  it('reads valid settings', () => {
    expect(config.baseUrl.href).toBe('https://api.example.test/')
    expect(config.clientId).toBe(env.CF_ACCESS_CLIENT_ID)
    expect(
      readApiConfig({ ...env, API_BASE_URL: 'https://api.example.test/' }).baseUrl.origin,
    ).toBe('https://api.example.test')
  })

  it('allows http only for a local API', () => {
    expect(readApiConfig({ ...env, API_BASE_URL: 'http://localhost:3000' }).baseUrl.port).toBe(
      '3000',
    )
    expect(() => readApiConfig({ ...env, API_BASE_URL: 'http://api.example.test' })).toThrow(
      'API_BASE_URL is invalid',
    )
  })

  it('rejects base URLs with paths, queries or credentials', () => {
    for (const url of [
      'https://api.example.test/v1',
      'https://api.example.test?x=1',
      'https://user:pass@api.example.test',
      'not a url',
    ]) {
      expect(() => readApiConfig({ ...env, API_BASE_URL: url })).toThrow(ApiConfigError)
    }
  })

  it('lists every missing or blank setting', () => {
    expect(() => readApiConfig({ CF_ACCESS_CLIENT_ID: '  ' })).toThrow(
      'API_BASE_URL is not set; CF_ACCESS_CLIENT_ID is not set; CF_ACCESS_CLIENT_SECRET is not set',
    )
  })

  it('names invalid settings without their values', () => {
    const secret = 'short secret'
    try {
      readApiConfig({ ...env, CF_ACCESS_CLIENT_ID: 'has space', CF_ACCESS_CLIENT_SECRET: secret })
      expect.unreachable()
    } catch (error) {
      expect(error).toBeInstanceOf(ApiConfigError)
      const message = (error as Error).message
      expect(message).toContain('CF_ACCESS_CLIENT_ID is invalid')
      expect(message).toContain('CF_ACCESS_CLIENT_SECRET is invalid')
      expect(message).not.toContain(secret)
      expect(message).not.toContain('has space')
    }
  })
})

describe('isValidPath', () => {
  it('accepts versioned, encoded paths', () => {
    expect(isValidPath('/v1/ping')).toBe(true)
    expect(isValidPath('/v1/studies/10.1000%2Fabc')).toBe(true)
    expect(isValidPath('/v1/topics/?page=2&size=10')).toBe(true)
  })

  it('rejects anything else', () => {
    for (const path of [
      '/v2/ping',
      '/v1',
      '/v1//ping',
      '/v1/../admin',
      '/v1/./ping',
      '/v1/a b',
      '/v1/ping#x',
      '/v1/ping?a=1?b=2',
      'https://evil.test/v1/ping',
    ]) {
      expect(isValidPath(path), path).toBe(false)
    }
  })
})

describe('createApiClient', () => {
  it('sends the Access service token and returns the parsed body', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => json({ status: 'ok' }))
    const client = createApiClient(config, { fetch })

    await expect(client.getJson('/v1/ping', asPing)).resolves.toEqual({ status: 'ok' })

    const [url, init] = fetch.mock.calls[0] ?? []
    expect(String(url)).toBe('https://api.example.test/v1/ping')
    expect(init?.method).toBe('GET')
    expect(init?.redirect).toBe('manual')
    expect(init?.headers).toEqual({
      Accept: 'application/json',
      'CF-Access-Client-Id': env.CF_ACCESS_CLIENT_ID,
      'CF-Access-Client-Secret': SECRET,
    })
    expect(init?.signal).toBeInstanceOf(AbortSignal)
  })

  it('refuses invalid paths without sending a request', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>()
    const error = await caught(createApiClient(config, { fetch }).getJson('/v1/../x', asPing))
    expect(error.kind).toBe('invalid-request')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('times out', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(init.signal?.reason))
        }),
    )
    const error = await caught(
      createApiClient(config, { fetch, timeoutMs: 20 }).getJson('/v1/ping', asPing),
    )
    expect(error.kind).toBe('timeout')
    expect(error.message).toBe('API /v1/ping: no response within 20 ms')
  })

  it('reports a caller abort separately from a timeout', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(init.signal?.reason))
        }),
    )
    const controller = new AbortController()
    const pending = createApiClient(config, { fetch }).getJson('/v1/ping', asPing, {
      signal: controller.signal,
    })
    controller.abort()
    expect((await caught(pending)).kind).toBe('aborted')
  })

  it('reports network failures without the token', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => {
      throw new TypeError('fetch failed')
    })
    const error = await caught(createApiClient(config, { fetch }).getJson('/v1/ping', asPing))
    expect(error.kind).toBe('network')
    expectNoSecrets(error)
  })

  it('reports HTTP errors and redirects with their status', async () => {
    for (const status of [302, 403, 404, 500]) {
      const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response('denied', { status }))
      const error = await caught(createApiClient(config, { fetch }).getJson('/v1/ping', asPing))
      expect(error.kind).toBe('http')
      expect(error.status).toBe(status)
      expect(error.message).toBe(`API /v1/ping: HTTP ${status}`)
      expectNoSecrets(error)
    }
  })

  it('rejects responses that are not JSON', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(
      async () => new Response('<html>login</html>', { headers: { 'content-type': 'text/html' } }),
    )
    const error = await caught(createApiClient(config, { fetch }).getJson('/v1/ping', asPing))
    expect(error.kind).toBe('invalid-response')
    expect(error.message).not.toContain('login')
  })

  it('rejects malformed JSON', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(
      async () => new Response('{', { headers: { 'content-type': 'application/json' } }),
    )
    const error = await caught(createApiClient(config, { fetch }).getJson('/v1/ping', asPing))
    expect(error.kind).toBe('invalid-response')
  })

  it('rejects bodies the parser refuses, without echoing them', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => json({ unexpected: 'private detail' }))
    const error = await caught(createApiClient(config, { fetch }).getJson('/v1/ping', asPing))
    expect(error.kind).toBe('invalid-response')
    expect(error.message).toBe('API /v1/ping: response has an unexpected shape')
  })

  it('never logs', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((method) =>
      vi.spyOn(console, method).mockImplementation(() => undefined),
    )
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response('', { status: 500 }))
    await caught(createApiClient(config, { fetch }).getJson('/v1/ping', asPing))
    for (const spy of spies) {
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    }
  })
})
