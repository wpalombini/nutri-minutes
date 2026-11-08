/**
 * Fails if anything a browser can download contains the API host, the Access client ID or
 * secret, or the names of the variables that hold them (ADR 0003). Run after `npm run build`,
 * with the same API_BASE_URL, CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET the build used
 * (dummy values in CI).
 *
 * Scanned: everything under .next/static (scripts, styles, source maps) and the prerendered
 * pages and React Server Components payloads under .next/server/app.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

export const SECRET_VARIABLES = [
  'API_BASE_URL',
  'CF_ACCESS_CLIENT_ID',
  'CF_ACCESS_CLIENT_SECRET',
] as const

/** Prerendered output that is sent to browsers as is. */
const PRERENDERED = /\.(html|rsc|body|txt|xml|webmanifest)$/

export interface Needle {
  label: string
  value: string
}

export function needlesFromEnv(env: Readonly<Record<string, string | undefined>>): Needle[] {
  const needles: Needle[] = SECRET_VARIABLES.map((name) => ({
    label: 'variable name',
    value: name,
  }))
  const missing: string[] = []
  for (const name of SECRET_VARIABLES) {
    const value = env[name]?.trim()
    if (!value) {
      missing.push(name)
      continue
    }
    if (name === 'API_BASE_URL') {
      needles.push({ label: 'API host', value: new URL(value).host })
    } else {
      needles.push({ label: `${name} value`, value })
    }
  }
  if (missing.length > 0) {
    throw new Error(
      `Set ${missing.join(', ')} (dummy values are fine) for the build and this check`,
    )
  }
  return needles
}

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(path)
    else if (entry.isFile()) yield path
  }
}

export function clientFiles(nextDir: string): string[] {
  const files = [...walk(join(nextDir, 'static'))]
  const app = join(nextDir, 'server', 'app')
  for (const file of walk(app)) {
    if (PRERENDERED.test(relative(app, file))) files.push(file)
  }
  return files
}

export interface Finding {
  file: string
  label: string
}

/** Findings name the file and what matched, never the matched value. */
export function scan(files: readonly string[], needles: readonly Needle[]): Finding[] {
  const findings: Finding[] = []
  for (const file of files) {
    const text = readFileSync(file).toString('latin1')
    for (const needle of needles) {
      if (text.includes(needle.value)) findings.push({ file, label: needle.label })
    }
  }
  return findings
}

if (import.meta.main) {
  const root = fileURLToPath(new URL('..', import.meta.url))
  const nextDir = join(root, '.next')
  const files = clientFiles(nextDir)
  if (files.length === 0) {
    console.error('No build output found. Run npm run build first.')
    process.exitCode = 1
  } else {
    const findings = scan(files, needlesFromEnv(process.env))
    for (const finding of findings) {
      console.error(`${relative(root, finding.file)} contains the ${finding.label}`)
    }
    if (findings.length > 0) {
      console.error('Server-only API settings reached the client bundle (ADR 0003).')
      process.exitCode = 1
    } else {
      console.log(`Checked ${files.length} client files: no API settings found.`)
    }
  }
}
