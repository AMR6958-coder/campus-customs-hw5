import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import type { ShopEvent, Ticket } from '../types'
import { STATUS_LABELS, TEAM, TICKET_TYPES, agentLook, argsText, toolPhrase } from '../agents'
import { clock, cls, eventTime, plain } from '../format'
import { Expandable } from './Expandable'

interface Props {
  ticket: Ticket | null
  events: ShopEvent[]
  busy: boolean
  activeAgent: string | null
}

const str = (value: unknown): string => (typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value))

/** What an agent is doing right now, from its latest event. */
function doing(event: ShopEvent | undefined): string {
  if (!event) return 'waiting'
  const data = event.data ?? {}
  switch (event.kind) {
    case 'tool':
      return toolPhrase(str(data.tool))
    case 'delegate':
      return `asking ${agentLook(str(data.to)).name}`
    case 'delegate_reply':
      return 'reported back'
    case 'note':
      return 'writing on the ticket'
    case 'decision':
      return 'made the call'
    case 'approval_requested':
      return 'asked for your approval'
    case 'run':
      return 'reading the ticket'
    case 'retry':
      return 'sent back to finish'
    case 'resolved':
      return 'closed the ticket'
    default:
      return event.kind.replace(/_/g, ' ')
  }
}

function stripPrefix(message: string, pattern: RegExp): string {
  return message.replace(pattern, '')
}

function Body({ event }: { event: ShopEvent }) {
  const data = event.data ?? {}
  switch (event.kind) {
    case 'tool': {
      const tool = str(data.tool)
      const result = str(data.result)
      const refused = result.startsWith('{"error"')
      return (
        <details className={cls('tool', refused && 'refused')}>
          <summary>
            <span className="tool-verb">{toolPhrase(tool)}</span>
            {refused && <span className="chip refused">refused</span>}
            <code>
              {tool}({argsText(data.args)})
            </code>
          </summary>
          <pre>{result}</pre>
        </details>
      )
    }
    case 'delegate': {
      const to = agentLook(str(data.to))
      const chain = Array.isArray(data.chain) ? (data.chain as string[]).map((a) => agentLook(a).short).join(' → ') : null
      return (
        <div className="bubble ask" style={{ '--to': to.color } as CSSProperties}>
          <div className="bubble-tag">
            asked <b>{to.name}</b>
            {chain && <span className="chain">{chain}</span>}
          </div>
          <Expandable text={stripPrefix(event.message, /^\w+ asked \w+: /)} limit={360} />
        </div>
      )
    }
    case 'delegate_reply': {
      const to = agentLook(str(data.to))
      return (
        <div className="bubble reply">
          <div className="bubble-tag">
            reported back to <b>{to.name}</b>
          </div>
          <Expandable text={stripPrefix(event.message, /^\w+ replied to \w+: /)} limit={420} />
        </div>
      )
    }
    case 'note':
      return (
        <div className="bubble note">
          <div className="bubble-tag">wrote on the ticket</div>
          <Expandable text={stripPrefix(event.message, /^Note(?: on ticket \d+)?: /)} limit={360} />
        </div>
      )
    case 'decision': {
      const outcome = str(data.outcome) || 'decision'
      return (
        <div className={cls('decision', outcome)}>
          <div className="decision-head">
            <span className="eyebrow">The Boss's call</span>
            <span className={`chip outcome ${outcome}`}>{outcome.replace(/_/g, ' ')}</span>
          </div>
          <Expandable text={stripPrefix(event.message, /^Ticket \d+: \w+\. /)} limit={600} />
        </div>
      )
    }
    case 'approval_requested':
      return (
        <div className="money ask-money">
          <span className="chip money-tag">Needs your approval</span>
          <Expandable text={event.message} limit={360} />
        </div>
      )
    case 'paid':
      return (
        <div className="money paid">
          <span className="chip money-tag good">Paid</span>
          <p>{plain(event.message)}</p>
        </div>
      )
    case 'approved':
    case 'rejected':
      return (
        <div className={cls('money', event.kind)}>
          <span className={cls('chip money-tag', event.kind === 'approved' ? 'good' : 'bad')}>{event.kind}</span>
          <p>{plain(event.message)}</p>
        </div>
      )
    case 'retry':
      return (
        <div className="notice warn">
          <span className="chip warn">Sent back</span>
          <Expandable text={stripPrefix(event.message, /^Boss's decision did not match the ticket: /)} limit={300} />
        </div>
      )
    case 'error':
      return (
        <div className="notice bad">
          <span className="chip bad">Error</span>
          <p>{plain(event.message)}</p>
        </div>
      )
    case 'resolved':
      return (
        <div className="notice good">
          <span className="chip good">Resolved</span>
          <Expandable text={event.message} limit={400} />
        </div>
      )
    default:
      return <p className="line">{plain(event.message)}</p>
  }
}

const QUIET_KINDS = new Set(['run', 'assigned', 'priority', 'status', 'opened', 'draft', 'purchase_order', 'triage', 'reset'])

function EventRow({ event, previous }: { event: ShopEvent; previous?: ShopEvent }) {
  const look = agentLook(event.agent)
  const quiet = QUIET_KINDS.has(event.kind)
  const continued = Boolean(previous && previous.agent === event.agent && !QUIET_KINDS.has(previous.kind) && !quiet)
  return (
    <article className={cls('event', `kind-${event.kind}`, continued && 'continued', quiet && 'quiet-row')} style={{ '--agent': look.color } as CSSProperties}>
      <div className="event-side">{!continued && !quiet && <span className="avatar">{look.initial}</span>}</div>
      <div className="event-main">
        {!continued && !quiet && (
          <div className="event-head">
            <span className="event-agent">{look.name}</span>
            <time>{clock(eventTime(event))}</time>
          </div>
        )}
        {quiet ? (
          <p className="line">
            <span className="line-agent">{look.name}</span> {plain(event.message)} <time>{clock(eventTime(event))}</time>
          </p>
        ) : (
          <Body event={event} />
        )}
      </div>
    </article>
  )
}

export function LiveFloor({ ticket, events, busy, activeAgent }: Props) {
  const feedRef = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(true)

  useEffect(() => {
    const el = feedRef.current
    if (pinned && el) el.scrollTop = el.scrollHeight
  }, [events.length, pinned, ticket?.id])

  const onScroll = () => {
    const el = feedRef.current
    if (!el) return
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 80)
  }

  const lastByAgent = useMemo(() => {
    const map = new Map<string, ShopEvent>()
    for (const e of events) map.set(e.agent, e)
    return map
  }, [events])

  const toolCalls = events.filter((e) => e.kind === 'tool').length
  const delegations = events.filter((e) => e.kind === 'delegate').length

  return (
    <section className={cls('panel floor', busy && 'busy')}>
      <header className="panel-head floor-head">
        <div>
          <span className="eyebrow">Live floor</span>
          <h2>{ticket ? `Ticket ${ticket.id} · ${ticket.subject ?? TICKET_TYPES[ticket.type]}` : 'Pick a ticket'}</h2>
          {ticket && (
            <p className="floor-sub">
              {ticket.requester} · {TICKET_TYPES[ticket.type] ?? ticket.type} ·{' '}
              <span className={`chip status ${ticket.status}`}>{STATUS_LABELS[ticket.status] ?? ticket.status}</span>
              {events.length > 0 && (
                <span className="floor-counts">
                  {toolCalls} tool call{toolCalls === 1 ? '' : 's'} · {delegations} delegation{delegations === 1 ? '' : 's'}
                </span>
              )}
            </p>
          )}
        </div>
        {busy && (
          <div className="working-tag">
            <span className="spinner" />
            Team at work
          </div>
        )}
      </header>
      <div className="progress" aria-hidden>
        <span />
      </div>

      <div className="team-strip">
        {TEAM.map((a) => {
          const last = lastByAgent.get(a.id)
          const active = busy && activeAgent === a.id
          return (
            <div key={a.id} className={cls('member', active && 'active', last && 'took-part')} style={{ '--agent': a.color } as CSSProperties} title={a.role}>
              <span className="avatar">{a.initial}</span>
              <span className="member-name">{a.name}</span>
              <span className="member-doing">{active ? doing(last) : last ? 'took part' : busy ? 'standing by' : 'not needed'}</span>
            </div>
          )
        })}
      </div>

      <div className="feed" ref={feedRef} onScroll={onScroll}>
        {events.length === 0 && (
          <div className="empty">
            {!ticket ? 'Pick a ticket on the board.' : busy ? 'The Boss is reading the ticket…' : 'No activity yet. Run the team to put this ticket on the floor.'}
          </div>
        )}
        {events.map((e, i) => (
          <EventRow key={e.id} event={e} previous={events[i - 1]} />
        ))}
        {busy && events.length > 0 && (
          <div className="typing">
            <span className="avatar" style={{ '--agent': agentLook(activeAgent ?? 'boss').color } as CSSProperties}>
              {agentLook(activeAgent ?? 'boss').initial}
            </span>
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
      </div>
      {!pinned && events.length > 0 && (
        <button className="jump" onClick={() => setPinned(true)}>
          Jump to latest ↓
        </button>
      )}
    </section>
  )
}
