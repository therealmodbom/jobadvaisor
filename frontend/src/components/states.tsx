import type { ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** A waiting state: spinner plus `label`, announced politely to screen readers. */
export function Loading({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-4 text-muted-foreground">
      <LoaderCircle className="size-5 motion-safe:animate-spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

/** A failure: `title` names what failed, `detail` (German UI text, never a raw API detail)
 * says why or what to do, and the retry button calls `onRetry`. */
export function ErrorWithRetry({ title, detail, onRetry }: {
  title: string
  detail?: string
  onRetry: () => void
}) {
  return (
    <section role="alert"
             className="mx-auto my-12 flex max-w-[640px] flex-col gap-3.5 rounded-xl border border-danger bg-danger-soft p-5">
      <h2 className="text-xl font-bold text-foreground">{title}</h2>
      {detail && <p className="text-foreground">{detail}</p>}
      <Button variant="outline" className="self-start" onClick={onRetry}>Erneut versuchen</Button>
    </section>
  )
}

/** An empty view: `title` and `text` say what to do next; `children` hold the action. */
export function EmptyState({ title, text, children }: {
  title: string
  text: string
  children?: ReactNode
}) {
  return (
    <section className="mx-auto my-16 flex max-w-[560px] flex-col items-center gap-4 text-center">
      <h2 className="text-3xl leading-tight font-bold tracking-tight">{title}</h2>
      <p className="text-muted-foreground">{text}</p>
      {children}
    </section>
  )
}
