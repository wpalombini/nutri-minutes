import type { NextConfig } from 'next'
import { securityHeaders } from './src/lib/security-headers'
import { allowIndexing } from './src/lib/site'

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/:path*',
        headers: securityHeaders({
          development: process.env.NODE_ENV === 'development',
          allowIndexing: allowIndexing(),
        }),
      },
    ]
  },
}

export default nextConfig
