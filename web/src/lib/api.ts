import 'server-only'

/**
 * The only module that talks to our API (ADR 0003). Server-side only: the `server-only` import
 * makes the build fail if a Client Component imports it. Settings are plain environment
 * variables, never `NEXT_PUBLIC_`, so they are not inlined into browser code.
 *
 * Every request sends the web app's Cloudflare Access service token and has a timeout. Errors
 * name the path and the problem only, never the token or the response body.
 */

export interface ApiConfig {
  baseUrl: URL
  clientId: string
  clientSecret: string
}

export class ApiConfigError extends Error {
  override name = 'ApiConfigError'
}

export type ApiErrorKind =
  | 'invalid-request'
  | 'timeout'
  | 'aborted'
  | 'network'
  | 'http'
  | 'invalid-response'

export class ApiError extends Error {
  override name = 'ApiError'
  readonly kind: ApiErrorKind
  readonly path: string
  readonly status: number | undefined

  constructor(kind: ApiErrorKind, path: string, message: string, status?: number) {
    super(`API ${path}: ${message}`)
    this.kind = kind
    this.path = path
    this.status = status
  }
}

type Env = Readonly<Record<string, string | undefined>>

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])
// Header-safe token characters. Cloudflare client IDs look like `<hex>.access`, secrets are hex.
const CLIENT_ID = /^[A-Za-z0-9._-]{1,256}$/
const CLIENT_SECRET = /^[A-Za-z0-9._~+/=-]{16,512}$/
const PATH_CHARS = /^[A-Za-z0-9\-._~/%]*$/
const QUERY_CHARS = /^[A-Za-z0-9\-._~%=&+]*$/

/** Versioned paths only, already encoded: no `.` or `..` segments, no `//`, no fragment. */
export function isValidPath(path: string): boolean {
  const [pathname = '', query, ...rest] = path.split('?')
  if (rest.length > 0 || !pathname.startsWith('/v1/') || !PATH_CHARS.test(pathname)) return false
  if (query !== undefined && !QUERY_CHARS.test(query)) return false
  const segments = pathname.slice(1).split('/')
  return segments.every((segment, index) =>
    segment === '' ? index === segments.length - 1 : segment !== '.' && segment !== '..',
  )
}

function parseBaseUrl(raw: string): URL | undefined {
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    return undefined
  }
  const httpsOrLocal =
    url.protocol === 'https:' || (url.protocol === 'http:' && LOCAL_HOSTS.has(url.hostname))
  const originOnly = url.origin === raw.replace(/\/$/, '')
  return httpsOrLocal && originOnly ? new URL(url.origin) : undefined
}

/**
 * Validates the API settings. Messages name the setting and the problem, never the value.
 */
export function readApiConfig(env: Env = process.env): ApiConfig {
  const value = (name: string) => env[name]?.trim() || undefined
  const problems: string[] = []

  const rawBaseUrl = value('API_BASE_URL')
  const baseUrl = rawBaseUrl === undefined ? undefined : parseBaseUrl(rawBaseUrl)
  if (rawBaseUrl === undefined) problems.push('API_BASE_URL is not set')
  else if (baseUrl === undefined) {
    problems.push('API_BASE_URL is invalid (an https origin, such as https://api.example.com)')
  }

  const clientId = value('CF_ACCESS_CLIENT_ID')
  if (clientId === undefined) problems.push('CF_ACCESS_CLIENT_ID is not set')
  else if (!CLIENT_ID.test(clientId)) problems.push('CF_ACCESS_CLIENT_ID is invalid')

  const clientSecret = value('CF_ACCESS_CLIENT_SECRET')
  if (clientSecret === undefined) problems.push('CF_ACCESS_CLIENT_SECRET is not set')
  else if (!CLIENT_SECRET.test(clientSecret)) problems.push('CF_ACCESS_CLIENT_SECRET is invalid')

  if (
    baseUrl === undefined ||
    clientId === undefined ||
    clientSecret === undefined ||
    problems.length > 0
  ) {
    throw new ApiConfigError(`Invalid API configuration: ${problems.join('; ')}`)
  }
  return { baseUrl, clientId, clientSecret }
}

export interface ApiClientOptions {
  fetch?: typeof fetch
  /** Per request, including reading the body. */
  timeoutMs?: number
}

export interface RequestOptions {
  signal?: AbortSignal
}

export interface ApiClient {
  /**
   * GETs a versioned path and returns the JSON body after `parse` has checked it. `parse` must
   * throw if the body isn't the expected shape, so nothing unchecked reaches a page.
   */
  getJson<T>(
    path: `/v1/${string}`,
    parse: (body: unknown) => T,
    options?: RequestOptions,
  ): Promise<T>
}

export const DEFAULT_TIMEOUT_MS = 8000

export function createApiClient(config: ApiConfig, options: ApiClientOptions = {}): ApiClient {
  const fetchImpl = options.fetch ?? globalThis.fetch
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS

  return {
    async getJson(path, parse, { signal } = {}) {
      if (!isValidPath(path)) throw new ApiError('invalid-request', path, 'invalid request path')
      const url = new URL(path, config.baseUrl)

      const timeout = AbortSignal.timeout(timeoutMs)
      const combined = signal === undefined ? timeout : AbortSignal.any([timeout, signal])
      const failure = (): ApiError =>
        timeout.aborted
          ? new ApiError('timeout', path, `no response within ${timeoutMs} ms`)
          : signal?.aborted
            ? new ApiError('aborted', path, 'request aborted')
            : new ApiError('network', path, 'request failed')

      let response: Response
      try {
        response = await fetchImpl(url, {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            'CF-Access-Client-Id': config.clientId,
            'CF-Access-Client-Secret': config.clientSecret,
          },
          // A redirect from Access means the token was refused; never follow it.
          redirect: 'manual',
          signal: combined,
        })
      } catch {
        throw failure()
      }

      if (!response.ok) {
        await response.body?.cancel().catch(() => undefined)
        throw new ApiError('http', path, `HTTP ${response.status}`, response.status)
      }
      const contentType = response.headers.get('content-type') ?? ''
      if (!/^application\/json\b/i.test(contentType)) {
        await response.body?.cancel().catch(() => undefined)
        throw new ApiError('invalid-response', path, 'response is not JSON', response.status)
      }

      let body: unknown
      try {
        body = await response.json()
      } catch {
        if (combined.aborted) throw failure()
        throw new ApiError('invalid-response', path, 'response is not valid JSON', response.status)
      }
      try {
        return parse(body)
      } catch {
        throw new ApiError(
          'invalid-response',
          path,
          'response has an unexpected shape',
          response.status,
        )
      }
    },
  }
}

let defaultClient: ApiClient | undefined

/** The client configured from the environment, created on first use. */
export function getApiClient(): ApiClient {
  defaultClient ??= createApiClient(readApiConfig())
  return defaultClient
}
