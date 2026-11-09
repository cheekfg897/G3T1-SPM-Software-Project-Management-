import { useId } from 'react'
import type { ReactNode } from 'react'

interface RecordSectionProps {
  title: string
  children: ReactNode
  /** For a link elsewhere on the page to point at the section. */
  id?: string
}

/** One section of an event's record: a heading, which names it for screen readers, and its body. */
export function RecordSection({ title, children, id }: RecordSectionProps) {
  const headingId = useId()
  return (
    <section id={id} aria-labelledby={headingId} className="mt-12">
      <h2 id={headingId} className="font-display text-xl font-semibold tracking-tight">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  )
}
