// Bible reading progress: which chapters someone has read. Kept on this
// device always; when signed in, also on their account (so it shows on
// their profile and follows them to other devices). Signing in merges the
// device's chapters into the account.

import * as api from './api.js';
import * as store from './store.js';
import { OT, NT } from './bible.js';
import { todayISO } from './dates.js';

const key = (b, c) => `${b}|${c}`;
const CANON = new Set([...OT, ...NT]);

function local() { return store.load('progress', {}); }

export function isRead(b, c) { return Boolean(local()[key(b, c)]); }

// [[book, chapter]] → mark read (or unread) here and, if signed in, there.
export async function mark(items, done = true) {
  items = items.filter(([b]) => CANON.has(b));
  if (!items.length) return null;
  const all = local();
  const day = todayISO();
  for (const [b, c] of items) {
    if (done) all[key(b, c)] = all[key(b, c)] || day; else delete all[key(b, c)];
  }
  store.save('progress', all);
  const user = await api.currentUser();
  if (!user) return null;
  try {
    return await api.post('me/progress', { items, done, day });
  } catch { return null; } // offline: the next sign-in or visit merges it
}

// Push everything read on this device to the account (union).
export async function syncUp() {
  const items = Object.keys(local()).map((k) => { const [b, c] = k.split('|'); return [b, Number(c)]; });
  if (!items.length) return;
  for (let i = 0; i < items.length; i += 500) {
    try { await api.post('me/progress', { items: items.slice(i, i + 500), done: true, day: todayISO() }); } catch { return; }
  }
}

// {chapters: {book: [c…]}, read, total, ot, nt, …}: the account's when
// signed in (merged with this device), otherwise this device's.
export async function summary() {
  const user = await api.currentUser();
  let server = null;
  if (user) { try { server = await api.get('me/progress'); } catch { server = null; } }
  const chapters = {};
  for (const k of Object.keys(local())) {
    const [b, c] = k.split('|');
    (chapters[b] = chapters[b] || new Set()).add(Number(c));
  }
  if (server) {
    for (const [b, cs] of Object.entries(server.chapters || {})) {
      for (const c of cs) (chapters[b] = chapters[b] || new Set()).add(c);
    }
  }
  const out = { chapters: {}, read: 0, ot: 0, nt: 0, streak: server ? server.streak : localStreak() };
  for (const [b, set] of Object.entries(chapters)) {
    out.chapters[b] = [...set].sort((x, y) => x - y);
    out.read += set.size;
    if (NT.includes(b)) out.nt += set.size; else out.ot += set.size;
  }
  return out;
}

function localStreak() {
  const days = new Set(Object.values(local()));
  const d = new Date();
  if (!days.has(todayISO(d))) d.setDate(d.getDate() - 1);
  let n = 0;
  while (days.has(todayISO(d))) { n += 1; d.setDate(d.getDate() - 1); }
  return n;
}

api.onAuth((user) => { if (user) syncUp(); });
