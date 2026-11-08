import { Kysely, PostgresDialect, sql } from 'kysely'
import pg from 'pg'
import { describeError, type Logger } from './logger.js'

/**
 * Tables and views the API can query. Nothing is exposed yet: when the first published view is
 * added, this is replaced by types generated with kysely-codegen (ADR 0002).
 */
export type Database = Record<string, never>

export interface DatabaseSettings {
  url: string
  poolMax: number
}

export function createDatabase(settings: DatabaseSettings, logger: Logger): Kysely<Database> {
  const pool = new pg.Pool({
    connectionString: settings.url,
    max: settings.poolMax,
    application_name: 'research-api',
    connectionTimeoutMillis: 5_000,
    idleTimeoutMillis: 30_000,
    // Postgres cancels slow statements, and the client gives up shortly after.
    statement_timeout: 5_000,
    query_timeout: 6_000,
  })
  // Without a listener, an error on an idle connection would crash the process.
  pool.on('error', (error) => {
    logger.error('idle database connection failed', { error: describeError(error) })
  })
  return new Kysely<Database>({ dialect: new PostgresDialect({ pool }) })
}

export async function checkDatabase(db: Kysely<Database>): Promise<void> {
  await sql`select 1`.execute(db)
}
