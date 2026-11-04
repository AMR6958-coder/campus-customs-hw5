// The typed client for backend/main.py. The base URL is http://localhost:8000 unless
// VITE_API_URL says otherwise (see .env.example).

import type {
  Approval,
  ApproveResult,
  Cash,
  Draft,
  EventsPage,
  Health,
  Job,
  RejectResult,
  ResetResult,
  Ticket,
} from './types'

const configured = (import.meta.env.VITE_API_URL as string | undefined)?.trim()
export const API_BASE = (configured && configured.length > 0 ? configured : 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API_BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError(0, `Cannot reach the back end at ${API_BASE}. Start it from backend/ with: uvicorn main:app --reload --port 8000`)
  }
  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body && typeof (body as { detail: unknown }).detail === 'string'
        ? (body as { detail: string }).detail
        : `${response.status} ${response.statusText}`
    throw new ApiError(response.status, detail)
  }
  return body as T
}

function query(params: Record<string, string | number | null | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const api = {
  health: () => request<Health>('/health'),
  tickets: () => request<Ticket[]>('/tickets'),
  run: (ticketId: number) => request<Job>(`/tickets/${ticketId}/run`, { method: 'POST' }),
  runBoard: () => request<Job>('/board/run', { method: 'POST' }),
  job: (jobId: string) => request<Job>(`/runs/${jobId}`),
  events: (since: number | null, limit = 1000) => request<EventsPage>(`/events${query({ since, limit })}`),
  cash: () => request<Cash>('/cash'),
  approvals: () => request<Approval[]>('/approvals'),
  approve: (approvalId: number, by: string, note?: string) =>
    request<ApproveResult>(`/approvals/${approvalId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ by, note: note ?? null, rework: true }),
    }),
  reject: (approvalId: number, by: string, note?: string) =>
    request<RejectResult>(`/approvals/${approvalId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ by, note: note ?? null, rework: true }),
    }),
  drafts: () => request<Draft[]>('/drafts'),
  reset: () => request<ResetResult>('/reset', { method: 'POST' }),
}
