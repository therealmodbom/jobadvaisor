import { X } from 'lucide-react'

/** The X that hides a pass or check result card, named `label`, calling `onDismiss`. It sits in
 * the card's top right corner, level with the first line: the negative margins pull the icon to
 * the card's padding and keep the 36 px hit area. */
export function DismissButton({ label, onDismiss }: { label: string; onDismiss: () => void }) {
  return (
    <button type="button" aria-label={label} onClick={onDismiss}
            className="-mr-2.5 -my-1.5 inline-flex size-9 flex-none items-center justify-center rounded-lg hover:bg-muted">
      <X className="size-4" aria-hidden="true" />
    </button>
  )
}
