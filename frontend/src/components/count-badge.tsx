import { plural } from '@/lib/alert'
import { cn } from '@/lib/utils'

/** The count of unsettled links after the label of the source tab and of the navigation item: a
 * filled pill with the number, nothing at 0. The number is also visually hidden text („, 12 offene
 * Links“), not an `aria-label`, so the visible label stays the start of the accessible name. The
 * comma is inline text of no size and the space a plain one before the pill: a browser starts a
 * new word at the `sr-only` text (it is out of the flow), so a comma inside it would follow a
 * space („Anzeige hinzufügen , 12 offene Links“). */
export function CountBadge({ count, className }: { count: number; className?: string }) {
  if (count === 0) return null
  return (
    <>
      <span className="text-[0px]">,</span>{' '}
      <span aria-hidden="true"
            className={cn('ml-0.5 inline-flex min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs leading-5 font-bold text-primary-foreground', className)}>
        {count}
      </span>
      <span className="sr-only">{plural(count, 'offener Link', 'offene Links')}</span>
    </>
  )
}
