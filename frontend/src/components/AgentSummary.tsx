import { useMemo, type CSSProperties } from 'react'
import type { ShopEvent, Ticket } from '../types'
import { agentLook, toolPhrase } from '../agents'
import { plain, truncate } from '../format'

interface Row {
  agent: string
  tools: number
  verbs: string[]
  asked: string[]
  notes: number
  said: string | null
  outcome: string | null
}

const str = (value: unknown): string => (typeof value === 'string' ? value : '')

/** One line per agent: how many tools, which ones in words, who they asked, and the last thing they said. */
function summarize(events: ShopEvent[]): Row[] {
  const rows = new Map<string, Row>()
  const row = (agent: string): Row => {
    let r = rows.get(agent)
    if (!r) {
      r = { agent, tools: 0, verbs: [], asked: [], notes: 0, said: null, outcome: null }
      rows.set(agent, r)
    }
    return r
  }
  for (const e of events) {
    if (e.agent === 'system') continue
    const data = e.data ?? {}
    switch (e.kind) {
      case 'tool': {
        const r = row(e.agent)
        r.tools += 1
        const verb = toolPhrase(str(data.tool))
        if (!r.verbs.includes(verb)) r.verbs.push(verb)
        break
      }
      case 'delegate': {
        const r = row(e.agent)
        const to = agentLook(str(data.to)).name
        if (!r.asked.includes(to)) r.asked.push(to)
        break
      }
      case 'delegate_reply':
        row(e.agent).said = e.message.replace(/^\w+ replied to \w+: /, '')
        break
      case 'note':
        row(e.agent).notes += 1
        break
      case 'decision': {
        const r = row(e.agent)
        r.outcome = str(data.outcome) || null
        r.said = e.message.replace(/^Ticket \d+: \w+\. /, '')
        break
      }
      case 'approved':
      case 'rejected':
      case 'paid':
        row(e.agent).said = e.message
        break
      default:
        break
    }
  }
  return [...rows.values()].sort((a, b) => (a.agent === 'boss' ? -1 : b.agent === 'boss' ? 1 : 0))
}

export function AgentSummary({ ticket, events }: { ticket: Ticket | null; events: ShopEvent[] }) {
  const rows = useMemo(() => summarize(events), [events])
  return (
    <section className="panel who">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Who did what</span>
          <h2>{ticket ? `Ticket ${ticket.id}` : '—'}</h2>
        </div>
      </header>
      {rows.length === 0 ? (
        <p className="quiet">No one has worked this ticket yet.</p>
      ) : (
        <ul className="who-list">
          {rows.map((r) => {
            const look = agentLook(r.agent)
            return (
              <li key={r.agent} style={{ '--agent': look.color } as CSSProperties}>
                <div className="who-head">
                  <span className="avatar small">{look.initial}</span>
                  <span className="who-name">{look.name}</span>
                  {r.outcome && <span className={`chip outcome ${r.outcome}`}>{r.outcome.replace(/_/g, ' ')}</span>}
                </div>
                <div className="who-counts">
                  {r.tools > 0 && (
                    <span>
                      {r.tools} tool call{r.tools === 1 ? '' : 's'}
                    </span>
                  )}
                  {r.asked.length > 0 && <span>asked {r.asked.join(' and ')}</span>}
                  {r.notes > 0 && (
                    <span>
                      {r.notes} note{r.notes === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
                {r.verbs.length > 0 && <div className="who-verbs">{r.verbs.join(' · ')}</div>}
                {r.said && <p className="who-said">“{truncate(plain(r.said), 240)}”</p>}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
