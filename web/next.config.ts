import type { NextConfig } from 'next'
import { securityHeaders } from './src/lib/security-headers'
import { allowIndexing } from './src/lib/site'

const nextConfig: NextConfig = {
  cacheComponents: true,
  // Off so a request for an unknown topic waits for `params` and gets a real 404. With it on,
  // Next.js sends the route's App Shell first, which is already a 200 (first request only).
  partialPrefetching: false,
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
