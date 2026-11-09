import type { Metadata } from 'next'
import { ProsePage } from '@/components/ProsePage'
import { loadProsePage } from '@/lib/pages'

const page = await loadProsePage('how-we-grade')

export const metadata: Metadata = {
  title: page.title,
  description:
    'How Nutri Minutes grades the evidence in each study, from high to very low certainty, and what a grade does and doesn’t tell you.',
  alternates: { canonical: '/how-we-grade' },
}

export default function Page() {
  return <ProsePage page={page} />
}
