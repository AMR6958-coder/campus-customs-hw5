import type { Draft } from '../types'
import { agentLook } from '../agents'
import { Expandable } from './Expandable'

export function DraftsPanel({ drafts }: { drafts: Draft[] }) {
  return (
    <section className="panel drafts">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Drafts on the board</span>
          <h2>Customer messages</h2>
        </div>
        {drafts.length > 0 && <span className="count">{drafts.length}</span>}
      </header>
      {drafts.length === 0 ? (
        <p className="quiet">No drafts for this ticket. Messages are written here and stay here; nothing is ever sent.</p>
      ) : (
        drafts.map((d) => (
          <article key={d.id} className="draft">
            <div className="draft-to">
              <span className="label">To</span> {d.recipient}
            </div>
            <div className="draft-subject">{d.subject}</div>
            <Expandable text={d.body} limit={260} className="draft-body" />
            <div className="draft-foot">
              Drafted by {agentLook(d.author).name} · <span className="chip">not sent</span>
            </div>
          </article>
        ))
      )}
    </section>
  )
}
