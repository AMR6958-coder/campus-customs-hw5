// Shapes the back end returns (backend/main.py, backend/models.py). The dashboard never
// talks to the database or the MCP server directly; every fact here came through the API.

export type TicketStatus = 'open' | 'in_progress' | 'waiting_approval' | 'resolved'

export interface Ticket {
  id: number
  type: string
  requester: string | null
  subject: string | null
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  notes: string | null
  status: TicketStatus
  open: boolean
  assigned_to: string | null
  priority: number | null
  resolution: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ShopEvent {
  id: number
  ticket_id: number | null
  agent: string
  kind: string
  message: string
  data: Record<string, unknown> | null
  at?: string
  created_at?: string
}

export type ApprovalKind = 'invoice' | 'rent' | 'purchase_order' | 'price_override'
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'executed'

export interface Approval {
  id: number
  ticket_id: number | null
  kind: ApprovalKind
  ref_id: number | null
  amount: number
  account: string
  rationale: string
  requested_by: string
  status: ApprovalStatus
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  created_at: string
}

export interface CashAccount {
  name: string
  balance: number
  date: string
}

export interface Cash {
  checking: number
  accounts: CashAccount[]
  total: number
}

export type Outcome = 'resolved' | 'waiting_approval' | 'blocked'

export interface BossDecision {
  ticket_id: number
  outcome: Outcome
  summary: string
  delegated_to: string[]
  approvals_requested: number[]
  drafts_written: number[]
  purchase_orders: number[]
}

export interface Job {
  id: string
  kind: 'ticket' | 'board' | 'rework'
  ticket_id: number | null
  status: 'running' | 'done' | 'error'
  started_at: string
  finished_at: string | null
  result: BossDecision | BossDecision[] | null
  error: string | null
}

export interface Health {
  ok: boolean
  model: string
  mcp_url: string
  mcp_connected: boolean
  mcp_error: string | null
  shop: { date_today: string; notes?: string | null } | null
  busy: Job | null
  jobs: number
}

export interface Draft {
  id: number
  ticket_id: number
  recipient: string
  subject: string
  body: string
  author: string
  created_at: string
}

export interface Payment {
  id: number
  amount: number
  account: string
  paid_at: string
  approved_by: string
  balance_after: number
}

export interface ApproveResult {
  approval: Approval
  decision: unknown
  payment: Payment | null
  refused: string | null
  checking: number
  rework: Job | null
}

export interface RejectResult {
  approval: Approval
  decision: unknown
  rework: Job | null
}

export interface ResetResult {
  target: string
  event_id: number
  counts: Record<string, number>
  checking_balance: number
}

export interface EventsPage {
  events: ShopEvent[]
  last_id: number | null
}
