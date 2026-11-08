import { serve } from '@hono/node-server'
import { remoteAccessKeys, requireAccess } from './access.js'
import { createApp } from './app.js'
import { ConfigError, loadConfig } from './config.js'
import { checkDatabase, createDatabase } from './db.js'
import { createLogger, describeError } from './logger.js'
import { rateLimit } from './rate-limit.js'

// Below Docker's default 10-second stop grace period, so we exit before being killed.
const SHUTDOWN_TIMEOUT_MS = 8_000

const logger = createLogger()

function loadConfigOrExit() {
  try {
    return loadConfig()
  } catch (error) {
    const detail = error instanceof ConfigError ? error.message : describeError(error)
    logger.error('invalid configuration', { detail })
    process.exit(1)
  }
}

const config = loadConfigOrExit()
const db = createDatabase({ url: config.databaseUrl, poolMax: config.dbPoolMax }, logger)
const app = createApp({
  access: requireAccess(
    {
      teamDomain: config.accessTeamDomain,
      audience: config.accessAudience,
      keys: remoteAccessKeys(config.accessTeamDomain),
    },
    logger,
  ),
  rateLimit: rateLimit({ limit: config.rateLimitPerMinute, windowMs: 60_000 }, logger),
  checkDatabase: () => checkDatabase(db),
  logger,
})

const server = serve({ fetch: app.fetch, hostname: '0.0.0.0', port: config.port }, (info) => {
  logger.info('listening', { port: info.port })
})

let stopping = false
function shutdown(signal: string) {
  if (stopping) return
  stopping = true
  logger.info('shutting down', { signal })
  setTimeout(() => {
    logger.error('shutdown timed out')
    process.exit(1)
  }, SHUTDOWN_TIMEOUT_MS).unref()
  server.close(() => {
    db.destroy().then(
      () => process.exit(0),
      (error: unknown) => {
        logger.error('closing database pool failed', { error: describeError(error) })
        process.exit(1)
      },
    )
  })
}

process.on('SIGTERM', () => shutdown('SIGTERM'))
process.on('SIGINT', () => shutdown('SIGINT'))
process.on('unhandledRejection', (error) => {
  logger.error('unhandled rejection', { error: describeError(error) })
  process.exit(1)
})
