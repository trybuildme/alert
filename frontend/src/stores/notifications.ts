// Notification center state — Facebook-style bell feed.
//
// Sources wired today:
//   earthquake  live SSE hazard.alert + persisted /api/earthquakes/alerts
//   cyclone     new-storm detection by diffing /api/cyclones
//   tsunami     NO SOURCE EXISTS YET — reserved; nothing is fabricated
//   flood       NO SOURCE EXISTS YET — reserved for the flood module

import { create } from 'zustand'

export type NotifKind = 'earthquake' | 'cyclone' | 'tsunami' | 'flood'

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
      const read = !s.open
      return {
        items: [{ ...item, read }, ...s.items].slice(0, 50),
        unread: read ? s.unread : s.unread + 1,
      }
    }),
  seed: (items) =>
    set((s) => {
      const fresh = items.filter((n) => !s.items.some((i) => i.id === n.id))
      return { items: [...s.items, ...fresh].slice(0, 50) }
    }),
  markAllRead: () =>
    set((s) => ({ unread: 0, items: s.items.map((i) => ({ ...i, read: true })) })),
}))
