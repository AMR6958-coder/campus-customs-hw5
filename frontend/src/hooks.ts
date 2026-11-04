import { useEffect, useRef, useState } from 'react'

/** Run `callback` every `delay` ms (null pauses). The latest callback is always the one called. */
export function useInterval(callback: () => void, delay: number | null): void {
  const saved = useRef(callback)
  useEffect(() => {
    saved.current = callback
  }, [callback])
  useEffect(() => {
    if (delay === null) return
    const id = window.setInterval(() => saved.current(), delay)
    return () => window.clearInterval(id)
  }, [delay])
}

/** A number that glides from its previous value to the new one (for the cash counter). */
export function useTweenedNumber(target: number | null, duration = 900): number | null {
  const [value, setValue] = useState<number | null>(target)
  const from = useRef<number | null>(target)
  useEffect(() => {
    if (target === null) return
    if (from.current === null) {
      from.current = target
      setValue(target)
      return
    }
    const start = from.current
    const delta = target - start
    if (delta === 0) return
    const began = performance.now()
    let frame = 0
    const step = (now: number) => {
      const t = Math.min(1, (now - began) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(start + delta * eased)
      if (t < 1) frame = requestAnimationFrame(step)
      else from.current = target
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, duration])
  return value
}

/** The previous value of something, for "what changed" effects. */
export function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T | undefined>(undefined)
  useEffect(() => {
    ref.current = value
  }, [value])
  return ref.current
}
