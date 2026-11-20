import { useState } from 'react'
import { Info } from 'lucide-react'

/** The info icon beside a disabled action: a visible, focusable button that shows `reason` on
 * hover and on focus (Escape hides it again), and gives it to screen readers through `id`, which
 * the disabled control points at with `aria-describedby`. `label` is the icon's accessible name,
 * for example "Warum ist Prüfen nicht möglich?". */
export function WhyDisabled({ id, label, reason }: { id: string; label: string; reason: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex">
      <button type="button" aria-label={label} aria-describedby={id}
              onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
              onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
              onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false) }}
              className="inline-flex size-11 items-center justify-center rounded-lg text-primary">
        <Info className="size-5" aria-hidden="true" />
      </button>
      <span id={id} role="tooltip" hidden={!open}
            className="absolute top-full left-0 z-10 mt-1.5 w-[300px] max-w-[80vw] rounded-lg border bg-card px-3.5 py-3 text-sm shadow-card">
        {reason}
      </span>
    </span>
  )
}
