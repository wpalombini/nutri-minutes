/**
 * JSON-lines logging to stdout. Fields are limited to primitive values so that whole objects,
 * such as requests, headers or errors, can't be logged by accident. Never log tokens, the
 * `CF-Access-*` headers, credentials or personal data.
 */
export type LogValue = string | number | boolean | null | undefined
export type LogFields = Record<string, LogValue>
type Level = 'info' | 'warn' | 'error'

export interface Logger {
  info(message: string, fields?: LogFields): void
  warn(message: string, fields?: LogFields): void
  error(message: string, fields?: LogFields): void
}

export function createLogger(
  write: (line: string) => void = (line) => process.stdout.write(`${line}\n`),
): Logger {
  const log = (level: Level, message: string, fields: LogFields = {}) => {
    write(JSON.stringify({ ...fields, time: new Date().toISOString(), level, message }))
  }
  return {
    info: (message, fields) => log('info', message, fields),
    warn: (message, fields) => log('warn', message, fields),
    error: (message, fields) => log('error', message, fields),
  }
}

/** A loggable description of an error: its name, and its code when it has one, not its message. */
export function describeError(error: unknown): string {
  if (!(error instanceof Error)) return typeof error
  const code = (error as { code?: unknown }).code
  return typeof code === 'string' ? `${error.name} (${code})` : error.name
}
