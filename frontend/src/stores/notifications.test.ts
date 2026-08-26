// Notification store tests: 24-hour expiry, unread accounting.

import { beforeEach, describe, expect, it } from 'vitest'

import {
  NOTIF_MAX_AGE_MS,
  useNotifStore,
  type NotifItem,
} from './notifications'

function item(id: string, ageMs: number, read = false): NotifItem {
  return {
    id, kind: 'earthquake', title: id,
    at: new Date(Date.now() - ageMs).toISOString(), read,
  }
}

beforeEach(() => {
  useNotifStore.setState({ open: false, items: [], unread: 0 })
})

describe('notification 24h expiry', () => {
  it('add() silently drops items older than 24h', () => {
    const s = useNotifStore.getState()
    s.add(item('dropped', NOTIF_MAX_AGE_MS + 5_000))
    s.add(item('edge-of-window', NOTIF_MAX_AGE_MS - 60_000))
    s.add(item('fresh', 0))
    const { items } = useNotifStore.getState()
    expect(items.map((i) => i.id)).toEqual(['fresh', 'edge-of-window'])
  })

  it('seeded history older than 24h is filtered out', () => {
    useNotifStore.getState().seed([
      item('ancient', NOTIF_MAX_AGE_MS + 3_600_000, true),
      item('recent', 3_600_000, true),
    ])
    expect(useNotifStore.getState().items.map((i) => i.id))
      .toEqual(['recent'])
  })

  it('pruneExpired removes aged items and resyncs unread count', () => {
    const s = useNotifStore.getState()
    s.seed([item('aged-unread', NOTIF_MAX_AGE_MS + 60_000)])   // unread
    s.add(item('new-unread', 0))                               // unread
    // seed bypasses unread; force an inconsistent state like real usage
    useNotifStore.setState({ unread: 2 })
    expect(useNotifStore.getState().unread).toBe(2)

    useNotifStore.getState().pruneExpired()
    const st = useNotifStore.getState()
    expect(st.items.map((i) => i.id)).toEqual(['new-unread'])
    expect(st.unread).toBe(1)
  })

  it('pruneExpired is a no-op when everything is fresh', () => {
    const s = useNotifStore.getState()
    s.add(item('a', 0))
    const before = useNotifStore.getState()
    s.pruneExpired()
    expect(useNotifStore.getState().items).toBe(before.items)
  })
})
