import type { Metadata } from 'next'
import { PageHeading } from '@/components/PageHeading'

export const metadata: Metadata = {
  alternates: { canonical: '/' },
}

/** A placeholder until the home page is built from design/screens/home.md. */
export default function HomePage() {
  return (
    <PageHeading title="Nutri Minutes is being rebuilt">
      <p>
        Soon this page will show each week’s new nutrition research in plain English, with how much
        each study can be trusted and a link to its source.
      </p>
      <p>Please check back soon.</p>
    </PageHeading>
  )
}
