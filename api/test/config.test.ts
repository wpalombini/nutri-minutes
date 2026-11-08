import { describe, expect, it } from 'vitest'
import { ConfigError, loadConfig } from '../src/config.js'

const valid = {
  DATABASE_URL: 'postgresql://api_runner:s3cretvalue@db:5432/pipeline',
  ACCESS_TEAM_DOMAIN: 'https://example-team.cloudflareaccess.com/',
  ACCESS_AUD: 'f'.repeat(64),
}

describe('loadConfig', () => {
  it('reads valid settings and applies defaults', () => {
    expect(loadConfig(valid)).toEqual({
      databaseUrl: valid.DATABASE_URL,
      dbPoolMax: 5,
      port: 3000,
      accessTeamDomain: 'https://example-team.cloudflareaccess.com',
      accessAudience: 'f'.repeat(64),
    })
  })

  it('treats blank settings as missing', () => {
    expect(() => loadConfig({ ...valid, ACCESS_AUD: '  ' })).toThrow('ACCESS_AUD is not set')
  })

  it.each([
    ['ACCESS_AUD', 'not-a-tag'],
    ['ACCESS_TEAM_DOMAIN', 'http://example-team.cloudflareaccess.com'],
    ['ACCESS_TEAM_DOMAIN', 'https://example.com'],
    ['DATABASE_URL', 'mysql://user:pw@db/x'],
    ['DB_POOL_MAX', '0'],
    ['PORT', 'eighty'],
  ])('rejects an invalid %s', (key, value) => {
    expect(() => loadConfig({ ...valid, [key]: value })).toThrow(`${key} is invalid`)
  })

  it('never includes values in errors', () => {
    try {
      loadConfig({ ...valid, DATABASE_URL: 'ftp://api_runner:s3cretvalue@db/x' })
      expect.unreachable()
    } catch (error) {
      expect(error).toBeInstanceOf(ConfigError)
      expect(String(error)).not.toContain('s3cretvalue')
    }
  })
})
