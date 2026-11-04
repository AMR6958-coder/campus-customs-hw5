import { useState } from 'react'
import type { Approval } from '../types'
import { APPROVAL_KINDS, agentLook } from '../agents'
import { cls, formatMoney, plain } from '../format'

interface Props {
  approvals: Approval[]
  approver: string
  pendingId: number | null
  onApprove: (approval: Approval) => void
  onReject: (approval: Approval, note?: string) => void
  onSelectTicket: (id: number) => void
}

function refLabel(a: Approval): string {
  if (a.ref_id === null) return ''
  if (a.kind === 'invoice') return `invoice ${a.ref_id}`
  if (a.kind === 'rent') return `lease ${a.ref_id}`
  if (a.kind === 'purchase_order') return `order ${a.ref_id}`
  return `ref ${a.ref_id}`
}

export function ApprovalsPanel({ approvals, approver, pendingId, onApprove, onReject, onSelectTicket }: Props) {
  const pending = approvals.filter((a) => a.status === 'pending')
  const decided = approvals.filter((a) => a.status !== 'pending').slice().reverse()
  const name = approver.trim() || 'Store Manager'
  // Rejecting opens a note field inside the card; no browser dialog.
  const [rejecting, setRejecting] = useState<number | null>(null)
  const [note, setNote] = useState('')
  return (
    <section className={cls('panel needs-you', pending.length > 0 && 'has-pending')}>
      <header className="panel-head">
        <div>
          <span className="eyebrow">Needs you</span>
          <h2>Approvals</h2>
        </div>
        {pending.length > 0 && <span className="count alert">{pending.length} waiting</span>}
      </header>
      {pending.length === 0 && <p className="quiet">Nothing is waiting on you. When an agent needs money or a price override, it lands here; agents can ask, only you can pay.</p>}
      <ul className="approval-list">
        {pending.map((a) => (
          <li key={a.id} className="approval">
            <div className="approval-top">
              <span className="approval-kind">
                {APPROVAL_KINDS[a.kind] ?? a.kind}
                {a.ref_id !== null && <span className="approval-ref"> · {refLabel(a)}</span>}
              </span>
              <span className="approval-amount">{a.amount > 0 ? formatMoney(a.amount) : 'No payment'}</span>
            </div>
            <p className="approval-why">{plain(a.rationale)}</p>
            <div className="approval-meta">
              Requested by {agentLook(a.requested_by).name}
              {a.ticket_id !== null && (
                <>
                  {' '}
                  for{' '}
                  <button className="link" onClick={() => onSelectTicket(a.ticket_id!)}>
                    ticket {a.ticket_id}
                  </button>
                </>
              )}
            </div>
            {rejecting === a.id ? (
              <div className="reject-box">
                <input
                  autoFocus
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Why? Optional, goes on the record"
                  aria-label="Reason for rejecting"
                />
                <button
                  className="btn danger"
                  disabled={pendingId !== null}
                  onClick={() => {
                    onReject(a, note.trim() || undefined)
                    setRejecting(null)
                    setNote('')
                  }}
                >
                  Confirm reject
                </button>
                <button className="btn btn-outline" onClick={() => setRejecting(null)}>
                  Keep
                </button>
              </div>
            ) : (
              <div className="approval-actions">
                <button className="btn" disabled={pendingId !== null} onClick={() => onApprove(a)}>
                  {pendingId === a.id ? 'Working…' : a.amount > 0 ? `Approve & pay ${formatMoney(a.amount, true)}` : 'Approve'}
                </button>
                <button className="btn btn-outline" disabled={pendingId !== null} onClick={() => setRejecting(a.id)}>
                  Reject
                </button>
              </div>
            )}
            <div className="approval-sign">Signed as {name}</div>
          </li>
        ))}
      </ul>
      {decided.length > 0 && (
        <details className="decided">
          <summary>Decided ({decided.length})</summary>
          <ul>
            {decided.map((a) => (
              <li key={a.id}>
                <span className={`chip ${a.status}`}>{a.status}</span>
                <span>
                  {APPROVAL_KINDS[a.kind] ?? a.kind}
                  {a.amount > 0 ? ` ${formatMoney(a.amount, true)}` : ''}
                  {a.decided_by ? ` · ${a.decided_by}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
