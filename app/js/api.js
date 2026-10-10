// Talking to /api. Library answers are cached in memory for the session (the
// service worker also keeps them for offline use); account answers never are.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Which build is this? The Google Play app opens /app/?source=play (and the
// Android referrer says so too). The server uses it to keep restricted-
// licence texts out of the paid Play app; on the web they stay free.
export const channel = (() => {
  try {
    if (new URLSearchParams(location.search).get('source') === 'play' || document.referrer.startsWith('android-app://')) {
      localStorage.setItem('gift.channel', 'play');
    }
    return localStorage.getItem('gift.channel') || 'web';
  } catch { return 'web'; }
})();

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, { credentials: 'same-origin', ...options,
      headers: { ...(options.headers || {}), 'X-Gift-Channel': channel } });
  } catch {
    throw new ApiError("You're offline, or the server can't be reached.", 0);
  }
  let data = {};
  try { data = await res.json(); } catch { /* empty or non-JSON body */ }
  if (!res.ok) throw new ApiError(data.error || `Request failed (${res.status})`, res.status);
  return data;
}

export function get(path, params) {
  const qs = params ? `?${new URLSearchParams(params)}` : '';
  return request(`/api/${path}${qs}`);
}

export function post(path, body = {}) {
  return request(`/api/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// Upload a picture or audio file as the raw request body.
export async function upload(blob) {
  let res;
  try {
    res = await fetch('/api/media', { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': blob.type || 'application/octet-stream', 'X-Gift-Channel': channel }, body: blob });
  } catch {
    throw new ApiError("The upload didn't go through. Check your connection.", 0);
  }
  let data = {};
  try { data = await res.json(); } catch { /* nothing */ }
  if (!res.ok) throw new ApiError(data.error || `Upload failed (${res.status})`, res.status);
  return data;
}

// Admin work needs a recently typed password (zero trust "step-up"). If
// the server asks for it, prompt, confirm, and try once more.
let askPassword = null;
export function onVerifyNeeded(fn) { askPassword = fn; }
export async function verified(call) {
  try {
    return await call();
  } catch (e) {
    if (e.status === 403 && /Confirm your password/.test(e.message) && askPassword) {
      const pw = await askPassword();
      if (!pw) throw e;
      await post('me/verify', { password: pw });
      return call();
    }
    throw e;
  }
}

const memo = new Map();
function cached(key, fn) {
  if (!memo.has(key)) {
    const p = fn().catch((e) => { memo.delete(key); throw e; });
    memo.set(key, p);
  }
  return memo.get(key);
}

export const translations = () => cached('translations', () => get('translations').then((d) => d.translations));
export const books = (t) => cached(`books:${t}`, () => get('books', { t }));
export const chapter = (t, b, c) => cached(`ch:${t}|${b}|${c}`, () => get('chapter', { t, b, c }));
export const plans = () => cached('plans', () => get('plans').then((d) => d.plans));
export const planDetail = (id) => cached(`plan:${id}`, () => get(`plans/${id}`));
export const commentaries = () => cached('commentaries', () => get('commentaries').then((d) => d.commentaries));
export const commentary = (m, b, c, v) => cached(`note:${m}|${b}|${c}|${v}`, () => get('commentary', { m, b, c, v }));
export const dictionary = (q) => cached(`dict:${q.toLowerCase()}`, () => get('dictionary', { q }));

// The person's plan ('free' | 'plus' | 'premium'), cached briefly.
let planCache = null;
export async function plan(refresh = false) {
  const user = await currentUser();
  if (!user) return { tier: 'free' };
  if (!planCache || refresh || Date.now() - planCache.at > 120000) {
    try { planCache = { at: Date.now(), data: await get('billing') }; } catch { return planCache ? planCache.data : { tier: 'free' }; }
  }
  return planCache.data;
}
export const tierRank = (t) => ({ free: 0, plus: 1, premium: 2 }[t] || 0);
export const devotional = (date) => cached(`devo:${date}`, () => get('devotional', { date }));

// ----------------------------------------------------------------- account

let me; // undefined = not asked yet, null = signed out
const authListeners = new Set();

export async function currentUser(refresh = false) {
  if (me === undefined || refresh) {
    try { me = (await get('me')).user; } catch { me = me ?? null; }
  }
  return me;
}

export function setUser(user) {
  me = user;
  planCache = null;
  for (const fn of authListeners) fn(me);
}

export function onAuth(fn) {
  authListeners.add(fn);
  return () => authListeners.delete(fn);
}
