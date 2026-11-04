import type { ShopEvent } from './types'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const wholeMoney = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export function formatMoney(value: number, whole = false): string {
  return (whole && Number.isInteger(value) ? wholeMoney : money).format(value)
}

export function eventTime(event: ShopEvent): string {
  return event.at ?? event.created_at ?? ''
}

export function clock(iso: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function longDate(iso: string): string {
  const date = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString([], { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
}

export function truncate(text: string, max: number): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean.length <= max ? clean : `${clean.slice(0, max - 1).trimEnd()}…`
}

// Light markdown the models like to use (**bold**) rendered as plain text with the emphasis kept.
export function plain(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1')
}

export function titleCase(text: string): string {
  return text.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function cls(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
