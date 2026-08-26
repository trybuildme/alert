// Notification center state — Facebook-style bell feed.
//
// Sources wired today:
//   earthquake  live SSE hazard.alert + persisted /api/earthquakes/alerts
//   cyclone     new-storm detection by diffing /api/cyclones
//   volcano     level transitions from polled /api/volcanoes/activity
//               (curated flag + live nearby seismicity synthesis)
//   tsunami     polls /api/tsunamis (tsunami.gov CAP bulletins)
//   flood       NO SOURCE EXISTS YET — reserved for the flood module

import { create } from 'zustand'

export type NotifKind =
  | 'earthquake' | 'cyclone' | 'tsunami' | 'flood' | 'volcano'

export interface NotifItem {
  id: string
  kind: NotifKind
  severity?: string
  title: string
  detail?: string
  at: string          // ISO timestamp of the underlying event
  read?: boolean      // set by the store when added while dropdown closed
}

interface NotifState {
  open: boolean
  items: NotifItem[]
  unread: number
  toggle: () => void
  close: () => void
  add: (item: NotifItem) => void
  seed: (items: NotifItem[]) => void   // history loaded as already-read
  markAllRead: () => void
  /** Drop items older than NOTIF_MAX_AGE_MS and resync the unread count. */
  pruneExpired: () => void
}

// Notifications auto-expire after 24 hours — a hazard feed is news,
// not an archive. Official alert history lives in the earthquake panel.
export const NOTIF_MAX_AGE_MS = 24 * 60 * 60_000

function freshOnly(items: NotifItem[]): NotifItem[] {
  const cutoff = Date.now() - NOTIF_MAX_AGE_MS
  return items.filter((i) => {
    const ts = new Date(i.at).getTime()
    return Number.isFinite(ts) && ts >= cutoff
  })
}

export const useNotifStore = create<NotifState>((set) => ({
  open: false,
  items: [],
  unread: 0,
  toggle: () =>
    set((s) => s.open
      ? { open: false }
      : { open: true, unread: 0, items: s.items.map((i) => ({ ...i, read: true })) }),
  close: () => set({ open: false }),
  add: (item) =>
    set((s) => {
      if (s.items.some((i) => i.id === item.id)) return s   // dedup
      // Arrivals land UNREAD unless the dropdown is already open on
      // screen (then the user is watching the feed arrive). The old
      // inverted condition marked everything read instantly, which is
      // why the badge never showed.
      const read = s.open
      const items = freshOnly([{ ...item, read }, ...s.items]).slice(0, 50)
      return {
        items,
        unread: items.filter((i) => !i.read).length,
      }
    }),
  seed: (items) =>
    set((s) => {
      const incoming = freshOnly(
        items.filter((n) => !s.items.some((i) => i.id === n.id)))
      const merged = [...s.items, ...incoming].slice(0, 50)
      return { items: merged }
    }),
  markAllRead: () =>
    set((s) => ({ unread: 0, items: s.items.map((i) => ({ ...i, read: true })) })),
  pruneExpired: () =>
    set((s) => {
      const items = freshOnly(s.items)
      const unread = items.filter((i) => !i.read).length
      if (items.length === s.items.length && unread === s.unread) return s
      return { items, unread }
    }),
}))
