import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

const field = 'w-full rounded-lg border border-input bg-background px-3 text-base text-foreground ' +
  'placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60'

/** A single-line text field in the prototype's style (44px high). */
export function Input({ className, ...props }: ComponentProps<'input'>) {
  return <input className={cn(field, 'min-h-11', className)} {...props} />
}

/** A multi-line text field in the prototype's style, resizable vertically. */
export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return <textarea className={cn(field, 'resize-y py-2.5', className)} {...props} />
}
