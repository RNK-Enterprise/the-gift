// Everything personal lives here, on this device: settings, reading position,
// highlights, bookmarks, the journal and personal plan progress. Nothing in
// this file is ever sent to the server. Storage can be unavailable (private
// windows, blocked site data), so every access falls back to memory.

const PREFIX = 'gift.';
const memory = new Map();
const listeners = new Map();

// Sync (Plus) hears about every personal change; see sync.js.
let syncHook = () => {};
export function setSyncHook(fn) { syncHook = fn; }

export function load(key, fallback) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (raw != null) return JSON.parse(raw);
  } catch { /* fall through to memory */ }
  return memory.has(key) ? memory.get(key) : fallback;
}

export function save(key, value) {
  memory.set(key, value);
  try { localStorage.setItem(PREFIX + key, JSON.stringify(value)); } catch { /* memory only */ }
  for (const fn of listeners.get(key) || []) fn(value);
}

export function watch(key, fn) {
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key).add(fn);
  return () => listeners.get(key).delete(fn);
}

// ---------------------------------------------------------------- settings

const DEFAULTS = { theme: 'system', size: 20, layout: 'flow', translation: 'KJV' };

export function settings() {
  return { ...DEFAULTS, ...load('settings', {}) };
}

export function setSetting(name, value) {
  save('settings', { ...settings(), [name]: value });
}

// -------------------------------------------------------------- highlights

// keyed by passage, not translation: a highlight shows in every translation
const vkey = (b, c, v) => `${b}|${c}|${v}`;

export function highlights() { return load('highlights', {}); }

export function setHighlight(b, c, verses, color) {
  const all = highlights();
  for (const v of verses) {
    if (color) all[vkey(b, c, v)] = color;
    else delete all[vkey(b, c, v)];
    syncHook('hl', vkey(b, c, v), color || null);
  }
  save('highlights', all);
}

export function highlightOf(b, c, v) { return highlights()[vkey(b, c, v)] || null; }

// --------------------------------------------------------------- bookmarks

export function bookmarks() { return load('bookmarks', []); }

export function isBookmarked(b, c, v) {
  return bookmarks().some((x) => x.b === b && x.c === c && x.v === v);
}

export function toggleBookmark(b, c, v, t) {
  const list = bookmarks();
  const i = list.findIndex((x) => x.b === b && x.c === c && x.v === v);
  if (i >= 0) list.splice(i, 1);
  else list.unshift({ b, c, v, t, at: Date.now() });
  save('bookmarks', list);
  syncHook('bm', vkey(b, c, v), i < 0 ? list[0] : null);
  return i < 0;
}

// ----------------------------------------------------------------- journal

export function journal() { return load('journal', []); }

export function journalEntry(id) { return journal().find((e) => e.id === id) || null; }

export function saveEntry(entry) {
  const list = journal();
  const i = list.findIndex((e) => e.id === entry.id);
  const now = Date.now();
  const next = { ...entry, updated: now, created: entry.created || now };
  if (i >= 0) list[i] = next; else list.unshift(next);
  save('journal', list);
  syncHook('journal', next.id, next);
  return next;
}

export function deleteEntry(id) {
  save('journal', journal().filter((e) => e.id !== id));
  syncHook('journal', id, null);
}

export function newId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// Merge an exported journal back in: by id, the newer edit wins.
export function importJournal(entries) {
  const byId = new Map(journal().map((e) => [e.id, e]));
  let added = 0;
  for (const e of entries) {
    if (!e || typeof e.id !== 'string' || typeof e.body !== 'string') continue;
    const mine = byId.get(e.id);
    if (!mine || (e.updated || 0) > (mine.updated || 0)) {
      byId.set(e.id, {
        id: e.id, title: String(e.title || ''), body: e.body, ref: e.ref || null,
        prompt: e.prompt ? String(e.prompt) : '', created: Number(e.created) || Date.now(),
        updated: Number(e.updated) || Date.now(),
      });
      added += 1;
    }
  }
  save('journal', [...byId.values()].sort((a, b) => b.created - a.created));
  return added;
}

// ------------------------------------------------------------ reading plan

export function plan() { return load('plan', null); }

export function startPlan(id, start) { save('plan', { id, start, done: [] }); syncHook('plan', 'current', plan()); }

export function stopPlan() { save('plan', null); syncHook('plan', 'current', null); }

export function setDayDone(day, done) {
  const p = plan();
  if (!p) return;
  const set = new Set(p.done);
  if (done) set.add(day); else set.delete(day);
  save('plan', { ...p, done: [...set].sort((a, b) => a - b) });
  syncHook('plan', 'current', plan());
}

// A change that came from another device: apply it without echoing it back.
export function applyRemote(kind, key, value, updated) {
  if (kind === 'hl') {
    const all = highlights();
    if (value) all[key] = value; else delete all[key];
    save('highlights', all);
  } else if (kind === 'bm') {
    const list = bookmarks().filter((x) => `${x.b}|${x.c}|${x.v}` !== key);
    if (value) list.unshift(value);
    save('bookmarks', list);
  } else if (kind === 'plan') {
    save('plan', value || null);
  } else if (kind === 'journal') {
    const list = journal();
    const i = list.findIndex((e) => e.id === key);
    if (!value) { if (i >= 0) { list.splice(i, 1); save('journal', list); } return; }
    if (i >= 0 && (list[i].updated || 0) >= updated) return;
    if (i >= 0) list[i] = value; else list.unshift(value);
    list.sort((a, b) => (b.created || 0) - (a.created || 0));
    save('journal', list);
  }
}
