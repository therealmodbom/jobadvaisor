import type { ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

/** The progress of a running pass or check, in the column of its button: a head line with the
 * loader (`head`), a bar at `value` of `max` named `barLabel`, and a hint line (`hint`, with
 * `hintId`, so a cancel button can point at it as its description). `label` names the region.
 * The head and the bar have a fixed height, and `hintClass` sets the hint's height and tone, so a
 * block keeps its size while only texts and the bar change. */
export function ProgressBlock({ label, head, barLabel, value, max, hintId, hint, hintClass }: {
  label: string
  head: string
  barLabel: string
  value: number
  max: number
  hintId: string
  hint: ReactNode
  hintClass: string
}) {
  return (
    <section aria-label={label} className="flex w-full min-w-0 flex-col gap-1.5">
      <div className="flex h-6 items-center gap-2">
        <LoaderCircle className="size-[18px] flex-none motion-safe:animate-spin" aria-hidden="true" />
        <strong>{head}</strong>
      </div>
      <progress value={value} max={max} aria-label={barLabel}
                className="h-2.5 w-full appearance-none overflow-hidden rounded-full border-0 bg-border [&::-moz-progress-bar]:bg-primary [&::-webkit-progress-bar]:rounded-full [&::-webkit-progress-bar]:bg-border [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:bg-primary" />
      <p id={hintId} className={cn('text-sm leading-5', hintClass)}>{hint}</p>
    </section>
  )
}
