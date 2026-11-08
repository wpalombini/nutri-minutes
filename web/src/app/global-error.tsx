'use client'

// Replaces the root layout when it fails, so it loads its own styles and fonts, and shows the
// wordmark without the navigation (design/screens/app-shell.md, "Error"). Next.js's built-in
// version uses inline styles, which the Content-Security-Policy blocks.
import '@/styles/tokens.css'
import './globals.css'
import { ErrorMessage } from '@/components/ErrorMessage'
import { SiteHeader } from '@/components/SiteHeader'
import { SiteShell } from '@/components/SiteShell'
import { atkinson, literata } from './fonts'

export default function GlobalError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <html lang="en-AU" className={`${literata.variable} ${atkinson.variable}`}>
      <body>
        <SiteShell header={<SiteHeader />}>
          <ErrorMessage error={error} retry={retry} />
        </SiteShell>
      </body>
    </html>
  )
}
