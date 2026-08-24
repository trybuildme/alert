// Notification feeds — bridges live sources into the notification store.
//
// earthquake: persisted alert history seeded (read), then SSE hazard.alert
//             pushes arrive unread in real time.
// cyclone:    polls /api/cyclones; a storm SID never seen before counts as
//             "new cyclone detected". First fetch initializes the baseline
//             without notifying (no spam about pre-existing storms).
// tsunami /   reserved channels — no machine-readable source exists yet;
// flood:      the bell architecture accepts them the moment their modules
//             publish events.

import { useEffect } from 'react'
import { useNotifStore, type NotifItem } from '../stores/notifications'

const CYCLONE_POLL_MS = 5 * 60_000

export function useNotificationFeeds() {
  useEffect(() => {
    const { add, seed } = useNotifStore.getState()

    // ---- Earthquake: seed persisted alert history (marked read) ----
    fetch('/api/earthquakes/alerts?limit=10')
      .then((r) => r.ok ? r.json() : null)
      .then((body) => {
        if (!body?.alerts?.length) return
        const items: NotifItem[] = body.alerts.map((a: {
          id: number; severity: string; rule_name: string
          summary: string; created_at: string; event_uid: string
        }) => ({
          id: `eq-alert:${a.id}`,
          kind: 'earthquake',
          severity: a.severity,
          title: `Earthquake alert · ${a.severity}`,
          detail: a.summary,
          at: a.created_at,
        }))
        seed(items)
      })
      .catch(() => { /* backend down: nothing to seed */ })

    // ---- Earthquake: live alerts over SSE ----
    let es: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    const connectEq = () => {
      es = new EventSource('/api/earthquakes/stream')
      es.addEventListener('hazard.alert', (ev) => {
        try {
          const m = JSON.parse((ev as MessageEvent).data)
          add({
            id: `eq-live:${m.event_uid}:${m.summary}`,
            kind: 'earthquake',
            severity: m.severity,
            title: `Earthquake · ${m.severity}`,
            detail: m.summary,
            at: new Date().toISOString(),
          })
        } catch { /* malformed */ }
      })
      es.onerror = () => {
        es?.close()
        retry = setTimeout(connectEq, 8000)
      }
    }
    connectEq()

    // ---- Cyclone: new-storm detection by SID diff ----
    let knownSids: Set<string> | null = null
    const pollCyclones = async () => {
      try {
        const res = await fetch('/api/cyclones')
        if (!res.ok) return
        const body = await res.json()
        if (body.source === 'unavailable') return
        const tracks = body.features.filter(
          (f: { properties?: { kind?: string } }) =>
            f.properties?.kind === 'track')
        const current = new Set<string>(
          tracks.map((f: { properties: { sid: string } }) => f.properties.sid))
        if (knownSids !== null) {
          for (const t of tracks) {
            const sid = t.properties.sid as string
            if (knownSids.has(sid)) continue
            add({
              id: `cyclone:${sid}`,
              kind: 'cyclone',
              title: `New cyclone detected · ${t.properties.name ?? sid}`,
              detail: `${t.properties.n_points} fixes recorded · basin ${t.properties.basin ?? '?'}`,
              at: new Date().toISOString(),
            })
          }
        }
        knownSids = current
      } catch { /* upstream unavailable */ }
    }
    pollCyclones()
    const cycTimer = setInterval(pollCyclones, CYCLONE_POLL_MS)

    // NOTE: tsunami and flood channels are intentionally absent — no real
    // source exists. Wire them here when their modules ship.

    return () => {
      es?.close()
      if (retry) clearTimeout(retry)
      clearInterval(cycTimer)
    }
  }, [])
}
