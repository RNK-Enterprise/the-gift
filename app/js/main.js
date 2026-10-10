// The Gift app: shell, hash router, theme and settings.

import * as api from './api.js';
import * as store from './store.js';
import { h, icon, fillIcons, sheet, toast, confirmSheet, clear } from './ui.js';
import './progress.js';
import * as sync from './sync.js';

// Phones get the five tabs; the desktop sidebar shows everything, grouped.
const TABS = ['today', 'read', 'music', 'community', 'me'];
const NAV = [
  { section: 'Read' },
  { id: 'today', label: 'Today', icon: 'sun', hash: '#/today' },
  { id: 'read', label: 'Bible', icon: 'book', hash: '#/read' },
  { id: 'plans', label: 'Plans', icon: 'calendar', hash: '#/plans' },
  { id: 'journal', label: 'Journal', icon: 'pen', hash: '#/journal' },
  { section: 'Together' },
  { id: 'community', label: 'Groups', icon: 'users', hash: '#/community' },
  { id: 'friends', label: 'Friends', icon: 'heart', hash: '#/friends' },
  { id: 'music', label: 'Music', icon: 'music', hash: '#/music' },
  { id: 'churches', label: 'Churches', icon: 'pin', hash: '#/churches' },
  { section: 'You' },
  { id: 'me', label: 'Me', icon: 'user', hash: '#/me' },
  { id: 'rewards', label: 'Rewards', icon: 'award', hash: '#/rewards' },
];

// route → [nav id, module, export]
const ROUTES = {
  today: ['today', './views/today.js', 'render'],
  read: ['read', './views/read.js', 'render'],
  search: ['read', './views/read.js', 'renderSearch'],
  plans: ['plans', './views/plans.js', 'render'],
  journal: ['journal', './views/journal.js', 'render'],
  community: ['community', './views/community.js', 'render'],
  groups: ['community', './views/community.js', 'renderGroup'],
  join: ['community', './views/community.js', 'renderJoin'],
  churches: ['churches', './views/churches.js', 'render'],
  music: ['music', './views/music.js', 'render'],
  artist: ['music', './views/music.js', 'renderArtist'],
  hymn: ['music', './views/music.js', 'renderHymn'],
  studio: ['music', './views/music.js', 'renderStudio'],
  admin: ['me', './views/music.js', 'renderAdmin'],
  me: ['me', './views/me.js', 'render'],
  u: ['me', './views/me.js', 'renderUser'],
  friends: ['friends', './views/me.js', 'renderFriends'],
  progress: ['me', './views/me.js', 'renderProgress'],
  rewards: ['rewards', './views/me.js', 'renderRewards'],
  devices: ['me', './views/me.js', 'renderDevices'],
  premium: ['me', './views/premium.js', 'render'],
};
// on phones these live under a tab
const TAB_OF = { plans: 'today', journal: 'me', friends: 'me', churches: 'community', rewards: 'me' };

const view = document.getElementById('view');
view.addEventListener('animationend', (e) => { if (e.target === view) view.classList.remove('view-in'); });
let cleanup = null;
let current = { name: null, path: [], params: new URLSearchParams() };
let renderSeq = 0;

export function parseHash(hash = location.hash) {
  const raw = hash.replace(/^#\/?/, '');
  const [pathPart, query = ''] = raw.split('?');
  const path = pathPart.split('/').filter(Boolean).map(decodeURIComponent);
  return { name: path[0] || 'today', path: path.slice(1), params: new URLSearchParams(query) };
}

export function go(hash, { replace = false } = {}) {
  if (replace) {
    history.replaceState(null, '', hash);
    route();
  } else if (location.hash === hash) {
    route();
  } else {
    location.hash = hash;
  }
}

async function route() {
  const r = parseHash();
  const entry = ROUTES[r.name] || ROUTES.today;
  const seq = ++renderSeq;
  const sameView = current.name === r.name;
  current = r;
  setActive(entry[0]);
  if (cleanup) { try { cleanup(); } catch { /* view already gone */ } cleanup = null; }
  const mod = await import(entry[1]);
  if (seq !== renderSeq) return; // a newer navigation won
  clear(view);
  view.classList.remove('view-in');
  void view.offsetWidth;
  // the entry animation must not linger: a transform on #view would make it
  // the containing block for position:fixed children (reader arrows)
  if (!sameView) view.classList.add('view-in');
  try {
    cleanup = (await mod[entry[2]](view, r)) || null;
  } catch (e) {
    console.error(e);
    view.append(h('div', { class: 'page' }, h('div', { class: 'empty' },
      h('h3', { text: 'Something went wrong' }), h('p', { text: e.message || String(e) }))));
  }
  if (!sameView) {
    window.scrollTo(0, 0);
    view.focus({ preventScroll: true });
  }
}

// ------------------------------------------------------------- navigation

function buildNav() {
  const side = document.querySelector('[data-nav]');
  const tabs = document.querySelector('[data-nav-tabs]');
  for (const n of NAV) {
    if (n.section) { side.append(h('div', { class: 'side-section', text: n.section })); continue; }
    side.append(h('a', { class: 'side-link', href: n.hash, dataset: { nav: n.id } }, icon(n.icon), h('span', { text: n.label })));
  }
  for (const id of TABS) {
    const n = NAV.find((x) => x.id === id);
    tabs.append(h('a', { class: 'tab', href: n.hash, dataset: { nav: n.id } }, icon(n.icon), h('span', { text: n.label })));
  }
  document.querySelector('[data-settings]').addEventListener('click', openSettings);
}

function setActive(id) {
  for (const el of document.querySelectorAll('[data-nav]')) {
    if (!el.dataset.nav) continue;
    const tab = el.classList.contains('tab');
    const on = el.dataset.nav === (tab ? (TAB_OF[id] || id) : id);
    el.classList.toggle('active', on);
    if (on) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  }
}

function setDot(navId, n, label) {
  for (const el of document.querySelectorAll(`[data-nav="${navId}"]`)) {
    let dot = el.querySelector('.dot');
    if (n > 0 && !dot) el.append(dot = h('span', { class: 'dot', 'aria-label': label }));
    if (n <= 0 && dot) dot.remove();
  }
}

export function setUnread(n) { setDot('community', n, `${n} unread`); }
export function setRequests(n) { setDot('me', n, `${n} friend requests`); setDot('friends', n, `${n} friend requests`); }

// ----------------------------------------------------------------- theme

const media = window.matchMedia('(prefers-color-scheme: light)');

export function applyTheme() {
  const s = store.settings();
  const theme = s.theme === 'system' ? (media.matches ? 'light' : 'dark') : s.theme;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.setProperty('--read-size', `${s.size}px`);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'light' ? '#f7f4ec' : '#030a1d';
}
media.addEventListener('change', applyTheme);

// --------------------------------------------------------------- settings

let installPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); installPrompt = e; });

function segmented(options, value, onPick) {
  const wrap = h('div', { class: 'seg', role: 'radiogroup' });
  for (const [val, label] of options) {
    const b = h('button', { type: 'button', class: val === value ? 'on' : '', role: 'radio',
      'aria-checked': String(val === value), text: label });
    b.addEventListener('click', () => {
      for (const x of wrap.children) { x.classList.remove('on'); x.setAttribute('aria-checked', 'false'); }
      b.classList.add('on');
      b.setAttribute('aria-checked', 'true');
      onPick(val);
    });
    wrap.append(b);
  }
  return wrap;
}
export { segmented };

export async function openSettings() {
  const s = store.settings();
  const sh = sheet('Settings');
  const size = h('input', { type: 'range', min: 15, max: 30, step: 1, value: s.size, 'aria-label': 'Text size' });
  size.addEventListener('input', () => { store.setSetting('size', Number(size.value)); applyTheme(); });

  sh.body.append(
    h('div', { class: 'sheet-section' }, h('h4', { text: 'Reading' }),
      h('div', { class: 'setting' }, h('span', { text: 'Theme' }),
        segmented([['system', 'Auto'], ['dark', 'Dark'], ['light', 'Light']], s.theme,
          (v) => { store.setSetting('theme', v); applyTheme(); })),
      h('div', { class: 'setting' }, h('span', { text: 'Text size' }), size),
      h('div', { class: 'setting' }, h('span', {}, 'Verses', h('small', { text: 'Flowing paragraphs, or one per line' })),
        segmented([['flow', 'Paragraph'], ['lines', 'Lines']], s.layout,
          (v) => { store.setSetting('layout', v); if (current.name === 'read') route(); }))),
  );

  const account = h('div', { class: 'sheet-section' }, h('h4', { text: 'Account' }));
  sh.body.append(account);
  const user = await api.currentUser();
  if (user) {
    const name = h('input', { class: 'input', value: user.name, maxlength: 40, 'aria-label': 'Your name' });
    account.append(
      h('p', { class: 'muted small', text: `Signed in as @${user.username}. Only your study groups see your name.` }),
      h('form', { class: 'row', on: { submit: async (e) => {
        e.preventDefault();
        try { api.setUser((await api.post('me', { name: name.value })).user); toast('Name saved'); } catch (err) { toast(err.message); }
      } } }, name, h('button', { class: 'btn', type: 'submit' }, 'Save')),
      h('div', { class: 'row wrap' },
        h('button', { class: 'btn', type: 'button', on: { click: () => { sh.close(); changePassword(); } } }, icon('lock'), 'Change password'),
        h('a', { class: 'btn', href: '#/devices', on: { click: () => sh.close() } }, icon('shield'), 'Devices & security'),
        h('button', { class: 'btn', type: 'button', on: { click: async () => {
          await api.post('logout').catch(() => {});
          await sync.forgetKey(user.username);
          api.setUser(null);
          sh.close();
          toast('Signed out');
          route();
        } } }, icon('logout'), 'Sign out'),
        h('button', { class: 'btn ghost danger', type: 'button', on: { click: () => { sh.close(); deleteAccount(user); } } },
          'Delete account')));
  } else {
    account.append(
      h('p', { class: 'muted small', text: "You don't need an account to read, journal or follow a plan. Sign in only to join study groups." }),
      h('a', { class: 'btn', href: '#/community', on: { click: () => sh.close() } }, 'Sign in or create an account'));
  }

  const about = h('div', { class: 'sheet-section' }, h('h4', { text: 'About' }),
    h('p', { class: 'muted small', text: 'Your journal, highlights, bookmarks and personal reading plan are stored only on this device. Study groups and their chat are stored on the server.' }),
    h('div', { class: 'about-links' },
      h('a', { href: '/' }, 'The library'),
      h('a', { href: '/Bibles/README.md' }, 'Translation licences'),
      h('a', { href: 'https://github.com/lisasdungeon/the-gift', rel: 'noopener', target: '_blank' }, 'Source code')));
  if (installPrompt) {
    about.append(h('button', { class: 'btn primary', type: 'button', on: { click: async () => {
      installPrompt.prompt();
      await installPrompt.userChoice.catch(() => {});
      installPrompt = null;
      sh.close();
    } } }, icon('install'), 'Install the app'));
  }
  sh.body.append(about);
}

function changePassword() {
  const sh = sheet('Change password');
  const current = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: true });
  const next = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', required: true, minlength: 8 });
  const err = h('p', { class: 'form-error', role: 'alert' });
  sh.body.append(h('form', { class: 'form', on: { submit: async (e) => {
    e.preventDefault();
    try {
      await api.post('me/password', { current: current.value, new: next.value });
      const user = await api.currentUser();
      if (user && await sync.rememberKey(user.username, next.value)) { sync.requeueJournal(); sync.syncNow(); }
      sh.close();
      toast('Password changed. Other devices are signed out.');
    } catch (ex) { err.textContent = ex.message; }
  } } },
  h('label', { class: 'field' }, h('span', { text: 'Current password' }), current),
  h('label', { class: 'field' }, h('span', { text: 'New password (8+ characters)' }), next),
  err, h('button', { class: 'btn primary', type: 'submit' }, 'Change password')));
}

function deleteAccount(user) {
  const sh = sheet('Delete your account');
  const pw = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: true });
  const err = h('p', { class: 'form-error' });
  sh.body.append(
    h('p', { text: `This deletes @${user.username}, your messages and your place in every group. Groups you lead pass to another member. Your journal stays on this device.` }),
    h('form', { class: 'form', on: { submit: async (e) => {
      e.preventDefault();
      if (!(await confirmSheet('Delete account?', 'This cannot be undone.', { ok: 'Delete', danger: true }))) return;
      try {
        await api.post('me/delete', { password: pw.value });
        await sync.forgetKey(user.username);
        api.setUser(null);
        sh.close();
        toast('Account deleted');
        go('#/today');
      } catch (ex) { err.textContent = ex.message; }
    } } },
    h('label', { class: 'field' }, h('span', { text: 'Your password' }), pw), err,
    h('button', { class: 'btn danger', type: 'submit' }, icon('trash'), 'Delete my account')));
}

// ----------------------------------------------------------------- unread

let unreadTimer = null;
async function pollUnread() {
  clearTimeout(unreadTimer);
  const user = await api.currentUser();
  if (user) {
    try {
      const [{ groups }, friends] = await Promise.all([api.get('groups'), api.get('friends')]);
      setUnread(groups.reduce((n, g) => n + g.unread, 0));
      setRequests(friends.incoming.length);
    } catch { /* offline: keep the last state */ }
  } else {
    setUnread(0);
    setRequests(0);
  }
  unreadTimer = setTimeout(pollUnread, document.hidden ? 120000 : 45000);
}

// ---------------------------------------------------------------- startup

function keyboard(e) {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
  const tag = (e.target && e.target.tagName) || '';
  if (/INPUT|TEXTAREA|SELECT/.test(tag) || document.querySelector('dialog[open]')) return;
  if (e.key === '/') {
    e.preventDefault();
    go(`#/search?t=${encodeURIComponent(store.load('last', {}).t || store.settings().translation)}`);
  }
}

// zero trust step-up: admin pages ask for the password again
api.onVerifyNeeded(() => new Promise((resolve) => {
  let value = null;
  const sh = sheet('Confirm it’s you', { onClose: () => resolve(value) });
  const pw = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: true });
  sh.body.append(h('p', { class: 'muted', text: 'Admin work needs your password again every 30 minutes.' }),
    h('form', { class: 'form', on: { submit: (e) => { e.preventDefault(); value = pw.value; sh.close(); } } },
      h('label', { class: 'field' }, h('span', { text: 'Password' }), pw),
      h('button', { class: 'btn primary', type: 'submit' }, 'Confirm')));
  pw.focus();
}));

applyTheme();
buildNav();
fillIcons();
window.addEventListener('hashchange', route);
document.addEventListener('keydown', keyboard);
api.onAuth(() => pollUnread());
document.addEventListener('visibilitychange', () => { if (!document.hidden) pollUnread(); });
route();
pollUnread();

// offline support and installability (service workers need https or localhost)
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/app/sw.js', { scope: '/app/' }).catch(() => {});
}
