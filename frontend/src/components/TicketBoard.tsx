import type { CSSProperties } from 'react'
import type { Ticket } from '../types'
import { STATUS_LABELS, TICKET_TYPES, agentLook } from '../agents'
import { cls, titleCase } from '../format'

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  onSelect: (id: number) => void
  onRun: (id: number) => void
  onRunBoard: () => void
  busy: boolean
  runningTicketId: number | null
  justResolved: number | null
}

function runLabel(ticket: Ticket, running: boolean): string {
  if (running) return 'Team is working…'
  if (ticket.status === 'resolved') return 'Run the team again'
  if (ticket.status === 'waiting_approval') return 'Re-work the ticket'
  return 'Run the team'
}

export function TicketBoard({ tickets, selectedId, onSelect, onRun, onRunBoard, busy, runningTicketId, justResolved }: Props) {
  const open = tickets.filter((t) => t.open).length
  return (
    <section className="panel board">
      <header className="panel-head">
        <div>
          <span className="eyebrow">The board</span>
          <h2>Tickets</h2>
        </div>
        <span className="count">
          {open} of {tickets.length} open
        </span>
      </header>
      <button className="btn btn-outline full board-run" onClick={onRunBoard} disabled={busy || open === 0} title="The Boss triages, then works every open ticket, most urgent first">
        {busy ? 'Team is working…' : 'Run the board'}
      </button>
      {tickets.length === 0 && <p className="quiet">No tickets yet. The board fills in once the back end answers.</p>}
      <ul className="ticket-list">
        {tickets.map((t) => {
          const selected = t.id === selectedId
          const running = runningTicketId === t.id
          const assignee = t.assigned_to ? agentLook(t.assigned_to) : null
          return (
            <li
              key={t.id}
              className={cls('ticket', `status-${t.status}`, selected && 'selected', running && 'running', justResolved === t.id && 'just-resolved')}
            >
              <button className="ticket-main" onClick={() => onSelect(t.id)} aria-pressed={selected}>
                <div className="ticket-top">
                  <span className="ticket-type">{TICKET_TYPES[t.type] ?? titleCase(t.type)}</span>
                  <span className="ticket-id">#{t.id}</span>
                </div>
                <h3 className="ticket-subject">{t.subject ?? titleCase(t.type)}</h3>
                <div className="ticket-requester">{t.requester}</div>
                <div className="ticket-meta">
                  {t.sku && (
                    <span>
                      {t.qty ?? 1} × {t.sku}
                      {t.size ? ` · ${t.size}` : ''}
                    </span>
                  )}
                  {t.lease_id !== null && <span>Lease {t.lease_id}</span>}
                  {t.invoice_id !== null && <span>Invoice {t.invoice_id}</span>}
                </div>
                <div className="ticket-foot">
                  <span className={`chip status ${t.status}`}>{running ? 'Working…' : STATUS_LABELS[t.status] ?? t.status}</span>
                  {t.priority !== null && <span className="chip prio">Priority {t.priority}</span>}
                  {assignee && (
                    <span className="assignee" style={{ '--agent': assignee.color } as CSSProperties} title={`Assigned to ${assignee.name}`}>
                      <span className="avatar tiny">{assignee.initial}</span>
                      {assignee.short}
                    </span>
                  )}
                </div>
                {t.status === 'resolved' && (
                  <span className="stamp" aria-hidden>
                    Resolved
                  </span>
                )}
              </button>
              {selected && (
                <div className="ticket-actions">
                  <button className="btn full" onClick={() => onRun(t.id)} disabled={busy}>
                    {runLabel(t, running)}
                  </button>
                  {t.notes && (
                    <p className="ticket-notes">
                      <span className="label">Ticket note</span>
                      {t.notes}
                    </p>
                  )}
                  {t.resolution && (
                    <p className="resolution">
                      <span className="label">Resolution</span>
                      {t.resolution}
                    </p>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
