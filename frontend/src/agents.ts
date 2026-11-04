// The people on the floor: how each agent reads on screen, and how a tool call is said in
// plain words. Colours come from the HW4 palette (Yale blue, green, amber, red) plus a teal and
// a plum so five agents can be told apart at a glance.

export interface AgentLook {
  id: string
  name: string
  short: string
  initial: string
  role: string
  color: string
}

export const TEAM: AgentLook[] = [
  { id: 'boss', name: 'Boss', short: 'Boss', initial: 'B', role: 'reads, delegates, makes the call', color: '#00356b' },
  { id: 'inventory', name: 'Inventory', short: 'Inv', initial: 'I', role: 'shelves and vendors', color: '#1a7f37' },
  { id: 'accounting', name: 'Accounting', short: 'Acct', initial: 'A', role: 'cash, invoices, margins', color: '#9a6700' },
  { id: 'facilities', name: 'Facilities', short: 'Fac', initial: 'F', role: 'the lease and the landlord', color: '#0e7490' },
  { id: 'customer_service', name: 'Customer Service', short: 'CS', initial: 'C', role: 'drafts to customers', color: '#7a3e9d' },
]

const OTHERS: Record<string, AgentLook> = {
  human: { id: 'human', name: 'You', short: 'You', initial: 'H', role: 'the human on the desk', color: '#222222' },
  system: { id: 'system', name: 'Shop', short: 'Shop', initial: 'S', role: 'the back office itself', color: '#8a8a8a' },
}

export function agentLook(id: string): AgentLook {
  return TEAM.find((a) => a.id === id) ?? OTHERS[id] ?? { id, name: id, short: id, initial: id.slice(0, 1).toUpperCase(), role: '', color: '#8a8a8a' }
}

// What a tool call means, in the words a manager would use.
const TOOL_PHRASES: Record<string, string> = {
  get_today: 'checked the shop calendar',
  list_tickets: 'looked over the board',
  get_ticket: 'read the ticket',
  list_ticket_events: 'read the ticket history',
  open_ticket: 'opened a new ticket',
  assign_ticket: 'assigned the ticket',
  set_ticket_priority: 'set the priority',
  set_ticket_status: 'moved the ticket',
  add_ticket_note: 'wrote a note on the ticket',
  resolve_ticket: 'resolved the ticket',
  get_stock: 'counted the shelf',
  list_stock: 'walked the shelves',
  get_pricing: 'checked the pricing',
  list_vendors: 'checked the vendors',
  get_vendor: 'checked a vendor',
  list_invoices: 'went through the invoices',
  get_invoice: 'read an invoice',
  get_lease: 'checked the lease',
  list_leases: 'checked the leases',
  get_cash: 'checked the cash',
  list_payments: 'looked at payments made',
  list_purchase_orders: 'looked at purchase orders',
  create_purchase_order: 'drafted a purchase order',
  list_approvals: 'looked at the approval queue',
  request_approval: 'asked you to approve',
  draft_customer_message: 'drafted a message to the customer',
  list_drafts: 'looked at the drafts',
}

export function toolPhrase(tool: string): string {
  return TOOL_PHRASES[tool] ?? tool.replace(/_/g, ' ')
}

export function argsText(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  return Object.entries(args as Record<string, unknown>)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(', ')
}

// Ticket types and statuses, in words.
export const TICKET_TYPES: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
  restock: 'Restock',
}

export const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  in_progress: 'In progress',
  waiting_approval: 'Needs approval',
  resolved: 'Resolved',
}

export const APPROVAL_KINDS: Record<string, string> = {
  invoice: 'Invoice',
  rent: 'Rent',
  purchase_order: 'Purchase order',
  price_override: 'Price override',
}
