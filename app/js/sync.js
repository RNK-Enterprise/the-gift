// Sync & backup (Plus). Highlights, bookmarks, the reading plan and the
// journal follow you between devices. Journal entries are encrypted here,
// on the device, before upload: AES-GCM with a key derived from your
// password (PBKDF2, 310,000 rounds), so the server only ever stores
// ciphertext. The key is kept in this browser (IndexedDB, not extractable).

import * as api from './api.js';
import * as store from './store.js';

const ROUNDS = 310000;
let timer = null;
let running = false;

// ------------------------------------------------------------- the key

function idb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('gift-keys', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('keys');
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function keyOp(mode, name, value) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('keys', mode);
    const st = tx.objectStore('keys');
    const req = mode === 'readonly' ? st.get(name) : value === undefined ? st.delete(name) : st.put(value, name);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// Called with the password at sign-in, sign-up and password change.
export async function rememberKey(username, password) {
  try {
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
    const key = await crypto.subtle.deriveKey(
      { name: 'PBKDF2', salt: new TextEncoder().encode(`the-gift/journal/${username}`), iterations: ROUNDS, hash: 'SHA-256' },
      base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
    await keyOp('readwrite', `journal:${username}`, key);
    return true;
  } catch { return false; } // no WebCrypto (plain http): journal sync stays off
}
export async function forgetKey(username) { try { await keyOp('readwrite', `journal:${username}`); } catch { /* none */ } }
async function journalKey(username) { try { return await keyOp('readonly', `journal:${username}`); } catch { return null; } }
export async function hasKey() { const u = await api.currentUser(); return Boolean(u && await journalKey(u.username)); }

const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function seal(key, obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(JSON.stringify(obj)));
  return { v: 1, iv: b64(iv), ct: b64(ct) };
}
async function open(key, box) {
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(box.iv) }, key, unb64(box.ct));
  return JSON.parse(new TextDecoder().decode(pt));
}

// ------------------------------------------------------------- queue

function queue() { return store.load('sync.queue', {}); }

store.setSyncHook((kind, key, value) => {
  const q = queue();
  q[`${kind}|${key}`] = { kind, key, value, updated: Date.now() };
  store.save('sync.queue', q);
  clearTimeout(timer);
  timer = setTimeout(() => syncNow(), 2500);
});

// everything on this device, queued once when sync is first switched on here
function seedAll() {
  const q = queue();
  const now = Date.now();
  for (const e of store.journal()) q[`journal|${e.id}`] = { kind: 'journal', key: e.id, value: e, updated: e.updated || now };
  for (const [k, color] of Object.entries(store.highlights())) q[`hl|${k}`] = { kind: 'hl', key: k, value: color, updated: now };
  for (const b of store.bookmarks()) q[`bm|${b.b}|${b.c}|${b.v}`] = { kind: 'bm', key: `${b.b}|${b.c}|${b.v}`, value: b, updated: b.at || now };
  const p = store.plan();
  if (p) q['plan|current'] = { kind: 'plan', key: 'current', value: p, updated: now };
  store.save('sync.queue', q);
}

// ------------------------------------------------------------- sync

// After a password change: re-encrypt every journal entry with the new key.
export function requeueJournal() {
  const q = queue();
  const now = Date.now();
  for (const e of store.journal()) q[`journal|${e.id}`] = { kind: 'journal', key: e.id, value: e, updated: now };
  store.save('sync.queue', q);
}

export function status() { return store.load('sync.status', { last: 0, locked: 0 }); }

export async function syncNow() {
  if (running) return status();
  const user = await api.currentUser();
  if (!user) return status();
  const plan = await api.plan();
  if (api.tierRank(plan.tier) < 1) return status();
  running = true;
  try {
    const seeded = store.load(`sync.seeded.${user.id}`, false);
    if (!seeded) { seedAll(); store.save(`sync.seeded.${user.id}`, true); }
    const key = await journalKey(user.username);
    const q = queue();
    const changes = [];
    for (const item of Object.values(q)) {
      if (item.kind === 'journal' && item.value) {
        if (!key) continue; // locked: kept queued until the password unlocks it
        changes.push({ ...item, value: await seal(key, item.value) });
      } else changes.push(item);
      if (changes.length >= 400) break;
    }
    let cursor = store.load(`sync.cursor.${user.id}`, 0);
    const res = await api.post('sync', { since: cursor, changes });
    const after = queue();
    for (const c of changes) {
      const k = `${c.kind}|${c.key}`;
      if (after[k] && after[k].updated === c.updated) delete after[k];
    }
    store.save('sync.queue', after);
    let locked = 0;
    for (const ch of res.changes) {
      let value = ch.value;
      if (ch.kind === 'journal' && value) {
        if (!key) { locked += 1; continue; }
        try { value = await open(key, value); } catch { locked += 1; continue; }
      }
      store.applyRemote(ch.kind, ch.key, value, ch.updated);
    }
    cursor = res.cursor;
    store.save(`sync.cursor.${user.id}`, cursor);
    const st = { last: Date.now(), locked, pending: Object.keys(after).length };
    store.save('sync.status', st);
    if (res.more) setTimeout(() => syncNow(), 500);
    return st;
  } catch (e) {
    return { ...status(), error: e.message };
  } finally {
    running = false;
  }
}

api.onAuth((user) => { if (user) setTimeout(() => syncNow(), 1500); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) syncNow(); });
setInterval(() => { if (!document.hidden) syncNow(); }, 5 * 60 * 1000);
setTimeout(() => syncNow(), 3000);
