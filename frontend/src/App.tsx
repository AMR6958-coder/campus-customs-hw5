import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import type { Approval, BossDecision, Cash, Draft, Health, Job, ShopEvent, Ticket } from './types'
import { TopBar } from './components/TopBar'
import { TicketBoard } from './components/TicketBoard'
import { LiveFloor } from './components/LiveFloor'
import { ApprovalsPanel } from './components/ApprovalsPanel'
import { AgentSummary } from './components/AgentSummary'
import { DraftsPanel } from './components/DraftsPanel'
import { Toasts, type Toast } from './components/Toasts'
import { useInterval } from './hooks'
import { formatMoney } from './format'

const APPROVER_KEY = 'campus-customs.approver'

function readApprover(): string {
  try {
    return localStorage.getItem(APPROVER_KEY) ?? 'Store Manager'
  } catch {
    return 'Store Manager'
  }
}

function lastDecisionOf(job: Job): BossDecision | null {
  if (!job.result) return null
  if (Array.isArray(job.result)) return job.result[job.result.length - 1] ?? null
  return job.result
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [events, setEvents] = useState<ShopEvent[]>([])
  const lastEventId = useRef<number | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [starting, setStarting] = useState(false)
  const [justResolved, setJustResolved] = useState<number | null>(null)
  const [approver, setApprover] = useState<string>(readApprover)
  const [pendingApproval, setPendingApproval] = useState<number | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])

  const liveJob = job?.status === 'running' ? job : (health?.busy ?? null)
  const busy = Boolean(liveJob)
  // A board run has no ticket of its own; the ticket being worked is the last one the Boss started.
  const followBoard = useRef(false)
  const lastStarted = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const e = events[i]
      if (e.kind === 'run' && e.ticket_id !== null) return e.ticket_id
    }
    return null
  }, [events])
  const runningTicketId = liveJob ? (liveJob.ticket_id ?? lastStarted) : null
  const runningLabel = liveJob ? (liveJob.kind === 'board' ? `on the board${runningTicketId ? `, ticket ${runningTicketId}` : ''}` : `on ticket ${liveJob.ticket_id}`) : null

  const toast = useCallback((tone: Toast['tone'], title: string, body?: string) => {
    const id = Date.now() + Math.random()
    setToasts((list) => [...list, { id, tone, title, body }])
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 8000)
  }, [])

  // ---- polling: the shop's state and the timeline -------------------------------------

  const refresh = useCallback(async () => {
    const [h, t, c, a, d] = await Promise.allSettled([api.health(), api.tickets(), api.cash(), api.approvals(), api.drafts()])
    if (h.status === 'fulfilled') {
      setHealth(h.value)
      setApiError(null)
    } else {
      setApiError((h.reason as Error).message)
    }
    if (t.status === 'fulfilled') setTickets(t.value)
    if (c.status === 'fulfilled') setCash(c.value)
    if (a.status === 'fulfilled') setApprovals(a.value)
    if (d.status === 'fulfilled') setDrafts(d.value)
  }, [])

  const pullEvents = useCallback(async () => {
    try {
      const page = await api.events(lastEventId.current)
      if (page.events.length) {
        setEvents((current) => {
          const seen = new Set(current.map((e) => e.id))
          const fresh = page.events.filter((e) => !seen.has(e.id))
          return fresh.length ? [...current, ...fresh].sort((x, y) => x.id - y.id) : current
        })
        // During a board run the page follows the Boss from ticket to ticket.
        if (followBoard.current) {
          const started = [...page.events].reverse().find((e) => e.kind === 'run' && e.ticket_id !== null)
          if (started && started.ticket_id !== null) setSelectedId(started.ticket_id)
        }
      }
      if (page.last_id !== null) lastEventId.current = page.last_id
    } catch {
      // the health poll reports an outage; the feed just waits
    }
  }, [])

  useEffect(() => {
    void refresh()
    void pullEvents()
  }, [refresh, pullEvents])
  useInterval(() => void refresh(), busy ? 2500 : 8000)
  useInterval(() => void pullEvents(), busy ? 1500 : 5000)

  useEffect(() => {
    try {
      localStorage.setItem(APPROVER_KEY, approver)
    } catch {
      // a private window may refuse; the name still works for this visit
    }
  }, [approver])

  useEffect(() => {
    if (selectedId === null && tickets.length) setSelectedId(tickets[0].id)
  }, [tickets, selectedId])

  // A run started elsewhere (the approve route's re-work, the console runner) is adopted so the
  // board shows it the same way.
  useEffect(() => {
    const live = health?.busy
    if (live && live.id !== job?.id && job?.status !== 'running') setJob(live)
  }, [health, job])

  // Watch the run we are following until it ends, then refresh and tell the human what happened.
  useInterval(
    async () => {
      if (!job || job.status !== 'running') return
      try {
        const latest = await api.job(job.id)
        if (latest.status === 'running') return
        setJob(latest)
        followBoard.current = false
        await Promise.all([refresh(), pullEvents()])
        if (latest.status === 'error') {
          toast('bad', 'The run stopped with an error', latest.error ?? undefined)
          return
        }
        if (latest.kind === 'board') {
          const decisions = Array.isArray(latest.result) ? latest.result : []
          const summary = decisions.map((d) => `Ticket ${d.ticket_id}: ${d.outcome.replace(/_/g, ' ')}`).join(' · ') || 'nothing was open'
          const resolved = decisions.filter((d) => d.outcome === 'resolved')
          toast(resolved.length === decisions.length && decisions.length > 0 ? 'good' : 'warn', 'Board run finished', summary)
          if (resolved.length) {
            setJustResolved(resolved[resolved.length - 1].ticket_id)
            window.setTimeout(() => setJustResolved(null), 6000)
          }
          return
        }
        const decision = lastDecisionOf(latest)
        if (!decision) return
        if (decision.outcome === 'resolved') {
          setJustResolved(decision.ticket_id)
          window.setTimeout(() => setJustResolved(null), 6000)
          toast('good', `Ticket ${decision.ticket_id} resolved`, decision.summary)
        } else if (decision.outcome === 'waiting_approval') {
          toast('warn', `Ticket ${decision.ticket_id} is waiting on you`, decision.summary)
        } else {
          toast('bad', `Ticket ${decision.ticket_id} is blocked`, decision.summary)
        }
      } catch {
        // keep polling
      }
    },
    job?.status === 'running' ? 2000 : null,
  )

  // ---- the human's actions --------------------------------------------------------------

  const startRun = async (ticketId: number) => {
    setStarting(true)
    try {
      const started = await api.run(ticketId)
      setJob(started)
      setSelectedId(ticketId)
      toast('info', `The Boss has started on ticket ${ticketId}`, 'Watch the floor; the team reports as it works.')
      void refresh()
    } catch (error) {
      toast('bad', 'Could not start the run', (error as Error).message)
    } finally {
      setStarting(false)
    }
  }

  const startBoard = async () => {
    setStarting(true)
    try {
      const started = await api.runBoard()
      followBoard.current = true
      setJob(started)
      toast('info', 'The Boss is triaging the board', 'Then every open ticket, most urgent first. The page follows the Boss.')
      void refresh()
    } catch (error) {
      toast('bad', 'Could not start the board run', (error as Error).message)
    } finally {
      setStarting(false)
    }
  }

  const approve = async (approval: Approval) => {
    setPendingApproval(approval.id)
    try {
      const result = await api.approve(approval.id, approver.trim() || 'Store Manager')
      setCash((current) => (current ? { ...current, checking: result.checking } : current))
      const rework = result.rework ? ` The Boss is re-working ticket ${result.rework.ticket_id}.` : ''
      if (result.refused) toast('warn', 'Approved, but the payment was refused', result.refused)
      else if (result.payment) toast('good', `Paid ${formatMoney(result.payment.amount)}`, `Checking is now ${formatMoney(result.checking)}.${rework}`)
      else toast('good', `Approval ${approval.id} recorded`, `No payment is attached to a price override.${rework}`)
      if (result.rework) {
        setJob(result.rework)
        if (result.rework.ticket_id !== null) setSelectedId(result.rework.ticket_id)
      }
      await Promise.all([refresh(), pullEvents()])
    } catch (error) {
      toast('bad', 'Could not approve', (error as Error).message)
    } finally {
      setPendingApproval(null)
    }
  }

  const reject = async (approval: Approval, note?: string) => {
    setPendingApproval(approval.id)
    try {
      const result = await api.reject(approval.id, approver.trim() || 'Store Manager', note)
      toast('info', `Approval ${approval.id} rejected`, result.rework ? `The Boss is re-working ticket ${result.rework.ticket_id} with your answer.` : undefined)
      if (result.rework) {
        setJob(result.rework)
        if (result.rework.ticket_id !== null) setSelectedId(result.rework.ticket_id)
      }
      await Promise.all([refresh(), pullEvents()])
    } catch (error) {
      toast('bad', 'Could not reject', (error as Error).message)
    } finally {
      setPendingApproval(null)
    }
  }

  const reset = async () => {
    try {
      const result = await api.reset()
      setEvents([])
      lastEventId.current = null
      setJob(null)
      setJustResolved(null)
      toast('info', 'Shop reset to the seed', `${result.counts.tickets} tickets open, checking ${formatMoney(result.checking_balance)}.`)
      await Promise.all([refresh(), pullEvents()])
    } catch (error) {
      toast('bad', 'Could not reset', (error as Error).message)
    }
  }

  // ---- what the screen shows ------------------------------------------------------------

  const selected = tickets.find((t) => t.id === selectedId) ?? null
  const ticketEvents = useMemo(() => events.filter((e) => e.ticket_id === selectedId), [events, selectedId])
  const latest = events.length ? events[events.length - 1] : null
  const activeAgent = busy && latest ? latest.agent : null
  const ticketDrafts = drafts.filter((d) => d.ticket_id === selectedId)

  return (
    <div className="app">
      <TopBar
        health={health}
        cash={cash}
        busy={busy}
        runningLabel={runningLabel}
        approver={approver}
        onApprover={setApprover}
        onReset={reset}
      />
      {apiError && (
        <div className="banner bad" role="alert">
          {apiError}
        </div>
      )}
      {health && !health.mcp_connected && (
        <div className="banner warn" role="alert">
          The back end is up but cannot reach the MCP server at {health.mcp_url}. Start it with: .venv\Scripts\python -m mcp_server.server
          {health.mcp_error ? ` (${health.mcp_error})` : ''}
        </div>
      )}
      <main className="main">
        <aside className="col col-left">
          <TicketBoard
            tickets={tickets}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onRun={startRun}
            onRunBoard={startBoard}
            busy={busy || starting}
            runningTicketId={runningTicketId}
            justResolved={justResolved}
          />
        </aside>
        <section className="col col-center">
          <LiveFloor ticket={selected} events={ticketEvents} busy={busy && runningTicketId === selectedId} activeAgent={activeAgent} />
        </section>
        <aside className="col col-right">
          <ApprovalsPanel
            approvals={approvals}
            approver={approver}
            pendingId={pendingApproval}
            onApprove={approve}
            onReject={reject}
            onSelectTicket={setSelectedId}
          />
          <AgentSummary ticket={selected} events={ticketEvents} />
          <DraftsPanel drafts={ticketDrafts} />
        </aside>
      </main>
      <Toasts toasts={toasts} onDismiss={(id) => setToasts((list) => list.filter((t) => t.id !== id))} />
    </div>
  )
}
