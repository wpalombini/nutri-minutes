'use client'

import { ErrorMessage } from '@/components/ErrorMessage'

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  return <ErrorMessage error={error} retry={retry} />
}
