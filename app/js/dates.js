// Local-calendar dates as YYYY-MM-DD strings: a plan's "day 12" depends on
// the reader's own midnight, not the server's.

const pad = (n) => String(n).padStart(2, '0');

export function todayISO(d = new Date()) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function parseISO(s) {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function addDays(iso, n) {
  const d = parseISO(iso);
  d.setDate(d.getDate() + n);
  return todayISO(d);
}

// Day 1 is the start date itself.
export function dayNumber(startISO, now = new Date()) {
  return Math.round((parseISO(todayISO(now)) - parseISO(startISO)) / 86400000) + 1;
}

export function fmtDate(iso, opts = { weekday: 'short', day: 'numeric', month: 'short' }) {
  return parseISO(iso).toLocaleDateString(undefined, opts);
}

export function monthDay(d = new Date()) {
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function fmtTime(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

export function fmtDayLabel(seconds) {
  const d = new Date(seconds * 1000);
  const today = todayISO();
  const iso = todayISO(d);
  if (iso === today) return 'Today';
  if (iso === addDays(today, -1)) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
}

export function ago(ms) {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(ms).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

// Consecutive finished days ending today (or yesterday, if today isn't done yet).
export function streak(doneDays, today) {
  const done = new Set(doneDays);
  let d = done.has(today) ? today : today - 1;
  let n = 0;
  while (d >= 1 && done.has(d)) { n += 1; d -= 1; }
  return n;
}
