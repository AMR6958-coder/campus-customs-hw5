import { useState } from 'react'
import { plain } from '../format'

/** Long text folded to `limit` characters with a "more" toggle; short text shows whole. */
export function Expandable({ text, limit = 320, className }: { text: string; limit?: number; className?: string }) {
  const [open, setOpen] = useState(false)
  const clean = plain(text).trim()
  if (clean.length <= limit) return <p className={className}>{clean}</p>
  return (
    <p className={className}>
      {open ? clean : `${clean.slice(0, limit).trimEnd()}… `}
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? ' less' : 'more'}
      </button>
    </p>
  )
}
