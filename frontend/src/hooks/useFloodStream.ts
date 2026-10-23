// Real-time flood data stream hook via Server-Sent Events.
// Provides live updates for flood station measurements and alerts.

import { useEffect, useRef, useState } from 'react'

interface FloodEvent {
  type: 'connected' | 'heartbeat' | 'alert' | 'error'
  timestamp?: string
  station_id?: string
  station_name?: string
  level?: string
  reason?: string
  lat?: number
  lon?: number
  message?: string
}

interface FloodStreamState {
  connected: boolean
  lastEvent: FloodEvent | null
  events: FloodEvent[]
}

export function useFloodStream() {
  const [state, setState] = useState<FloodStreamState>({
    connected: false,
    lastEvent: null,
    events: [],
  })
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false

    const connect = () => {
      if (cancelled) return

      try {
        const eventSource = new EventSource('/api/flood/stream')
        eventSourceRef.current = eventSource

        eventSource.onopen = () => {
          if (!cancelled) {
            setState(prev => ({ ...prev, connected: true }))
          }
        }

        eventSource.onmessage = (event) => {
          if (cancelled) return

          try {
            const data: FloodEvent = JSON.parse(event.data)
            setState(prev => ({
              ...prev,
              lastEvent: data,
              events: [data, ...prev.events].slice(0, 100), // Keep last 100 events
            }))
          } catch {
            // Ignore parse errors
          }
        }

        eventSource.onerror = () => {
          if (!cancelled) {
            setState(prev => ({ ...prev, connected: false }))
            eventSource.close()

            // Reconnect after 5 seconds
            reconnectTimeoutRef.current = setTimeout(connect, 5000)
          }
        }
      } catch {
        // Connection failed, retry
        reconnectTimeoutRef.current = setTimeout(connect, 5000)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [])

  return state
}

export default useFloodStream
