import type { Metadata, Viewport } from 'next'
import type { ReactNode } from 'react'
// Order matters: the token variables load before the global styles that use them.
import '@/styles/tokens.css'
import './globals.css'
import { MainNav } from '@/components/MainNav'
import { RouteFocus } from '@/components/RouteFocus'
import { SiteHeader } from '@/components/SiteHeader'
import { SiteShell } from '@/components/SiteShell'
import { pageColour } from '@/generated/theme'
import { allowIndexing, siteDescription, siteName, siteUrl } from '@/lib/site'
import { atkinson, literata } from './fonts'

const indexable = allowIndexing()

export const metadata: Metadata = {
  metadataBase: siteUrl(),
  title: { default: siteName, template: `%s – ${siteName}` },
  description: siteDescription,
  applicationName: siteName,
  robots: { index: indexable, follow: indexable },
  openGraph: { siteName, locale: 'en_AU', type: 'website' },
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: pageColour.light },
    { media: '(prefers-color-scheme: dark)', color: pageColour.dark },
  ],
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-AU" className={`${literata.variable} ${atkinson.variable}`}>
      <body>
        <SiteShell
          header={
            <SiteHeader>
              <MainNav />
            </SiteHeader>
          }
        >
          {children}
        </SiteShell>
        <RouteFocus />
      </body>
    </html>
  )
}
