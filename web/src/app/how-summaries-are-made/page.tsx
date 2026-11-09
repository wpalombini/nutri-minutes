import type { Metadata } from 'next'
import { ProsePage } from '@/components/ProsePage'
import { loadProsePage } from '@/lib/pages'

const page = await loadProsePage('how-summaries-are-made')

export const metadata: Metadata = {
  title: page.title,
  description:
    'How Nutri Minutes finds new nutrition studies, writes plain-English summaries with AI, and checks each one against the study before publishing.',
  alternates: { canonical: '/how-summaries-are-made' },
}

export default function Page() {
  return <ProsePage page={page} />
}
