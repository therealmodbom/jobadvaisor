import { plural } from '@/lib/alert'
import { cn } from '@/lib/utils'

/** The count of unsettled links after the label of the source tab and of the navigation item: a
 * filled pill with the number, nothing at 0. The number is also visually hidden text („, 12 offene
 * Links“), not an `aria-label`, so the visible label stays the start of the accessible name. */
export function CountBadge({ count, className }: { count: number; className?: string }) {
  if (count === 0) return null
  return (
    <>
      <span aria-hidden="true"
            className={cn('ml-1.5 inline-flex min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs leading-5 font-bold text-primary-foreground', className)}>
        {count}
      </span>
      <span className="sr-only">{`, ${plural(count, 'offener Link', 'offene Links')}`}</span>
    </>
  )
}
