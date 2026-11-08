import { z } from 'zod'

/** Settings read from the environment. See `.env.example` at the repo root. */
export interface Config {
  databaseUrl: string
  dbPoolMax: number
  port: number
  accessTeamDomain: string
  accessAudience: string
  rateLimitPerMinute: number
}

export class ConfigError extends Error {
  override name = 'ConfigError'
}

const schema = z.object({
  DATABASE_URL: z.url({ protocol: /^postgres(ql)?$/ }),
  // api_runner is limited to 10 connections in infra/postgres/login-roles.sql.
  DB_POOL_MAX: z.coerce.number().int().min(1).max(10).default(5),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3000),
  // The Cloudflare Access team domain, such as https://example.cloudflareaccess.com.
  ACCESS_TEAM_DOMAIN: z.url({ protocol: /^https$/, hostname: /\.cloudflareaccess\.com$/ }),
  // The Access application's AUD tag: 64 hex characters.
  ACCESS_AUD: z.string().regex(/^[0-9a-f]{64}$/),
  // Requests per minute allowed for each Access client.
  RATE_LIMIT_PER_MINUTE: z.coerce.number().int().min(1).max(100_000).default(600),
})

/**
 * Validate the environment. Error messages name the setting and the problem only, never the
 * value, because some values contain credentials.
 */
export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const blankAsMissing = Object.fromEntries(
    Object.entries(env).map(([key, value]) => [key, value?.trim() === '' ? undefined : value]),
  )
  const result = schema.safeParse(blankAsMissing)
  if (!result.success) {
    const problems = result.error.issues.map((issue) => {
      const setting = String(issue.path[0] ?? 'environment')
      return blankAsMissing[setting] === undefined
        ? `${setting} is not set`
        : `${setting} is invalid`
    })
    throw new ConfigError(`Invalid configuration: ${problems.join('; ')}`)
  }
  const values = result.data
  return {
    databaseUrl: values.DATABASE_URL,
    dbPoolMax: values.DB_POOL_MAX,
    port: values.PORT,
    accessTeamDomain: new URL(values.ACCESS_TEAM_DOMAIN).origin,
    accessAudience: values.ACCESS_AUD,
    rateLimitPerMinute: values.RATE_LIMIT_PER_MINUTE,
  }
}
