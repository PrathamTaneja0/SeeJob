import { useEffect, useRef, useState } from 'react'
import type { AgentEvent } from '../api/types'
import { API_BASE } from '../api/client'

export function useEventStream(onEvent?: (event: AgentEvent) => void) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cursorRef = useRef(0)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    const url = `${API_BASE}/api/v1/events/stream?after_id=${cursorRef.current}`
    const source = new EventSource(url)

    source.onopen = () => {
      setConnected(true)
      setError(null)
    }

    source.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as AgentEvent
        cursorRef.current = event.id
        setEvents((prev) => [...prev.slice(-199), event])
        onEventRef.current?.(event)
      } catch {
        /* ignore malformed */
      }
    }

    source.onerror = () => {
      setConnected(false)
      setError('SSE connection lost — reconnecting…')
    }

    return () => source.close()
  }, [])

  return { events, connected, error }
}
