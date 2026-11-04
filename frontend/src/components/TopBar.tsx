import { useEffect, useRef, useState } from 'react'
import type { Cash, Health } from '../types'
import { formatMoney, longDate } from '../format'
import { useTweenedNumber } from '../hooks'

interface Props {
  health: Health | null
  cash: Cash | null
  busy: boolean
  runningLabel: string | null
  approver: string
  onApprover: (name: string) => void
  onReset: () => void
}

export function TopBar({ health, cash, busy, runningLabel, approver, onApprover, onReset }: Props) {
  const checking = cash?.checking ?? null
  const shown = useTweenedNumber(checking)
  const lastSeen = useRef<number | null>(null)
  const [delta, setDelta] = useState<number | null>(null)

  // When the balance changes, float the difference next to it for a moment.
  useEffect(() => {
    if (checking === null) return
    if (lastSeen.current !== null && lastSeen.current !== checking) {
      setDelta(checking - lastSeen.current)
      const timer = window.setTimeout(() => setDelta(null), 3200)
      lastSeen.current = checking
      return () => window.clearTimeout(timer)
    }
    lastSeen.current = checking
  }, [checking])

  // Reset is two clicks: arm, then confirm within a few seconds. No browser dialog.
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const timer = window.setTimeout(() => setArmed(false), 15000)
    return () => window.clearTimeout(timer)
  }, [armed])

  const online = health?.ok ?? false
  const status = busy ? `Team working${runningLabel ? ` ${runningLabel}` : ''}` : online ? 'Team idle' : 'Back end offline'

  return (
    <header className="topbar">
      <div className="brand">
        <span className="eyebrow">Campus Customs</span>
        <h1>Back Office</h1>
      </div>

      <div className="stat">
        <span className="label">Shop date</span>
        <span className="value">{health?.shop ? longDate(health.shop.date_today) : '—'}</span>
      </div>

      <div className={`stat cash ${delta !== null && delta < 0 ? 'dropping' : ''}`}>
        <span className="label">Checking</span>
        <span className="value cash-value">{shown === null ? '—' : formatMoney(shown)}</span>
        {delta !== null && (
          <span className={`cash-delta ${delta < 0 ? 'down' : 'up'}`} aria-live="polite">
            {delta < 0 ? '−' : '+'}
            {formatMoney(Math.abs(delta))}
          </span>
        )}
      </div>

      <div className="stat team-status">
        <span className="label">Team</span>
        <span className="value">
          <span className={`dot ${busy ? 'busy' : online ? 'ok' : 'off'}`} />
          {status}
        </span>
        <span className="sub">
          {health ? `${health.model} · MCP ${health.mcp_connected ? 'connected' : 'unreachable'}` : 'connecting…'}
        </span>
      </div>

      <label className="stat approver">
        <span className="label">Approving as</span>
        <input value={approver} onChange={(e) => onApprover(e.target.value)} placeholder="Your name" aria-label="Your name for approvals" />
      </label>

      <div className="reset-wrap">
        {armed ? (
          <>
            <button
              className="btn danger"
              onClick={() => {
                setArmed(false)
                onReset()
              }}
            >
              Yes, reset to seed
            </button>
            <button className="btn btn-outline" onClick={() => setArmed(false)}>
              Keep
            </button>
          </>
        ) : (
          <button
            className="btn btn-outline reset"
            onClick={() => setArmed(true)}
            disabled={busy || !online}
            aria-label="Reset shop"
            title="Copy the original data over the working copy; the audit trail keeps everything"
          >
            Reset shop
          </button>
        )}
      </div>
    </header>
  )
}
