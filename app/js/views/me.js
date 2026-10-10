// "Me": your profile, Bible progress, rewards, friends and devices, plus
// everyone else's profile pages.

import * as api from '../api.js';
import * as store from '../store.js';
import * as progress from '../progress.js';
import { OT, NT, bookName, readHash, refLabel, parseRef } from '../bible.js';
import { h, icon, sheet, toast, loading, errorBox, confirmSheet, avatar, resizeImage, pickFile, copyText, ring, progressBar } from '../ui.js';
import { go, openSettings, setRequests } from '../main.js';
import { authForms } from './community.js';
import { ago } from '../dates.js';

const TOTAL = 1189;

function row(iconName, title, sub, href, { badge = 0, onClick } = {}) {
  const el = h(href ? 'a' : 'button', { class: 'me-row', href: href || null, type: href ? null : 'button' },
    h('span', { class: 'me-row-icon' }, icon(iconName)),
    h('span', { class: 'me-row-text' }, h('b', { text: title }), sub ? h('small', { text: sub }) : null),
    badge ? h('span', { class: 'unread', text: String(badge) }) : icon('chevR'));
  if (onClick) el.addEventListener('click', onClick);
  return el;
}

function stat(value, label) {
  return h('div', { class: 'stat' }, h('b', { text: String(value) }), h('small', { text: label }));
}

function pct(n, total) { return total ? Math.round((n / total) * 100) : 0; }

// ------------------------------------------------------------------- hub

export async function render(root) {
  const page = h('div', { class: 'page' }, loading());
  root.append(page);
  const user = await api.currentUser();
  const prog = await progress.summary();
  const parts = [];

  if (user) {
    let me = null, friends = { incoming: [], friends: [] };
    try {
      [me, friends] = await Promise.all([api.get(`profiles/${user.username}`), api.get('friends')]);
      setRequests(friends.incoming.length);
    } catch { /* offline: show what we can */ }
    const r = me && me.rewards;
    parts.push(h('section', { class: 'card profile-card' },
      h('div', { class: 'profile-top' }, avatar(user, 72),
        h('div', { class: 'profile-names' }, h('h1', { text: user.name }), h('p', { class: 'muted', text: `@${user.username}` }))),
      me && me.bio ? h('p', { class: 'profile-bio', text: me.bio }) : null,
      h('div', { class: 'stats' },
        stat(`${pct(prog.read, TOTAL)}%`, 'of the Bible'),
        stat(prog.streak, prog.streak === 1 ? 'day streak' : 'day streak'),
        stat(me ? me.friends : '–', me && me.friends === 1 ? 'friend' : 'friends'),
        stat(r ? r.level : '–', r ? r.title : 'level')),
      h('div', { class: 'row wrap' },
        h('button', { class: 'btn sm', type: 'button', on: { click: () => editProfile(user, me) } }, icon('pen'), 'Edit profile'),
        h('a', { class: 'btn ghost sm', href: `#/u/${user.username}` }, 'View profile'))));
    parts.push(h('div', { class: 'me-section' }, h('h2', { text: 'Your reading' }),
      row('book', 'Bible progress', `${prog.read.toLocaleString()} of ${TOTAL.toLocaleString()} chapters`, '#/progress'),
      row('calendar', 'Reading plans', store.plan() ? 'Following a plan' : 'Pick a plan', '#/plans'),
      row('pen', 'Journal', 'Private notes and prayers', '#/journal'),
      row('bookmark', 'Bookmarks & highlights', null, '#/journal?tab=bookmarks')));
    parts.push(h('div', { class: 'me-section' }, h('h2', { text: 'Together' }),
      row('heart', 'Friends', friends.incoming.length ? `${friends.incoming.length} new request${friends.incoming.length > 1 ? 's' : ''}` : `${friends.friends.length} friend${friends.friends.length === 1 ? '' : 's'}`, '#/friends', { badge: friends.incoming.length }),
      row('users', 'Study groups', 'Your online groups', '#/community'),
      row('mic', 'Artist studio', 'Share your music', '#/studio'),
      row('pin', 'Find a church', 'Churches near you', '#/churches')));
    parts.push(h('div', { class: 'me-section' }, h('h2', { text: 'You' }),
      row('award', 'Rewards', r ? `Level ${r.level} · ${r.earned} badge${r.earned === 1 ? '' : 's'} · ${r.points.toLocaleString()} points` : 'Badges and levels', '#/rewards'),
      row('crown', 'Premium', 'Plus and Premium plans', '#/premium'),
      row('shield', 'Devices & security', 'Where you’re signed in', '#/devices'),
      row('gear', 'Settings', 'Theme, text size, account', null, { onClick: openSettings }),
      user.is_admin ? row('lock', 'Admin', 'Artists, songs and the audit log', '#/admin') : null));
  } else {
    parts.push(h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Me' }), h('h1', { text: 'Make it yours' }),
      h('p', { class: 'sub', text: 'You can read, journal and follow a plan without an account. Sign in to keep your progress on your profile, earn rewards, add friends and join groups.' })));
    parts.push(h('div', { class: 'me-section' },
      row('book', 'Bible progress', `${prog.read.toLocaleString()} of ${TOTAL.toLocaleString()} chapters on this device`, '#/progress'),
      row('calendar', 'Reading plans', null, '#/plans'),
      row('pen', 'Journal', 'Private, on this device', '#/journal'),
      row('pin', 'Find a church', null, '#/churches'),
      row('gear', 'Settings', null, null, { onClick: openSettings })));
    parts.push(h('div', { class: 'auth' }, authForms(() => go('#/me', { replace: true }), { intro: false })));
  }
  page.replaceChildren(...parts.filter(Boolean));
  return null;
}

// ------------------------------------------------------------ edit profile

function editProfile(user, me) {
  const sh = sheet('Edit profile', { tall: true });
  let avatarId = undefined; // undefined: unchanged; null: removed
  const pic = h('div', { class: 'edit-avatar' }, avatar(user, 88));
  const name = h('input', { class: 'input', value: user.name, maxlength: 40, required: true });
  const bio = h('textarea', { class: 'textarea', rows: 3, maxlength: 300, placeholder: 'A line or two about you' });
  bio.value = (me && me.bio) || '';
  const verse = h('input', { class: 'input', placeholder: 'e.g. Psalm 23:1 or John 3:16', value: me && me.verse ? refLabel(me.verse) : '' });
  const showProgress = h('input', { type: 'checkbox', checked: me ? me.show_progress : true });
  const err = h('p', { class: 'form-error', role: 'alert' });
  const choose = h('button', { class: 'btn sm', type: 'button' }, icon('camera'), 'Change picture');
  choose.addEventListener('click', async () => {
    const file = await pickFile('image/*');
    if (!file) return;
    choose.disabled = true;
    try {
      const blob = await resizeImage(file, 512);
      const res = await api.upload(blob);
      avatarId = res.id;
      pic.replaceChildren(avatar({ ...user, avatar: res.url }, 88));
    } catch (e) { toast(e.message); } finally { choose.disabled = false; }
  });
  const remove = h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => { avatarId = null; pic.replaceChildren(avatar({ ...user, avatar: null }, 88)); } } }, 'Remove');
  sh.body.append(h('form', { class: 'form', on: { submit: async (e) => {
    e.preventDefault();
    err.textContent = '';
    const fields = { name: name.value, bio: bio.value, show_progress: showProgress.checked };
    if (avatarId !== undefined) fields.avatar = avatarId;
    const v = verse.value.trim();
    if (!v) fields.verse = null;
    else {
      const kjv = await api.books('KJV');
      const ref = parseRef(v, kjv.books.map((b) => b.name), (b) => (kjv.books.find((x) => x.name === b) || {}).chapters);
      if (!ref || !ref.v) { err.textContent = 'Type the verse like “John 3:16”.'; return; }
      fields.verse = { t: store.settings().translation || 'KJV', b: ref.b, c: ref.c, v: ref.v };
    }
    try {
      const { user: updated } = await api.post('me/profile', fields);
      api.setUser({ ...user, ...updated });
      sh.close();
      toast('Profile saved');
      go(location.hash, { replace: true });
    } catch (ex) { err.textContent = ex.message; }
  } } },
  h('div', { class: 'row' }, pic, h('div', { class: 'stack' }, choose, remove)),
  h('label', { class: 'field' }, h('span', { text: 'Name' }), name),
  h('label', { class: 'field' }, h('span', { text: 'About you' }), bio),
  h('label', { class: 'field' }, h('span', { text: 'Favourite verse' }), verse),
  h('label', { class: 'check-row' }, showProgress, h('span', { text: 'Show my Bible progress and rewards on my profile' })),
  err, h('button', { class: 'btn primary', type: 'submit' }, 'Save')));
}

// --------------------------------------------------------------- profiles

function relationshipButton(p, onChange) {
  const act = async (path, body, msg) => {
    try { await api.post(path, body); toast(msg); onChange(); } catch (e) { toast(e.message); }
  };
  switch (p.relationship) {
    case 'self': return null;
    case 'friends':
      return h('button', { class: 'btn sm', type: 'button', on: { click: async () => {
        if (await confirmSheet(`Remove ${p.name} as a friend?`, 'You can add each other again later.', { ok: 'Remove', danger: true })) {
          act('friends/remove', { user_id: p.id }, 'Friend removed');
        }
      } } }, icon('check'), 'Friends');
    case 'outgoing':
      return h('button', { class: 'btn sm', type: 'button', on: { click: () => act('friends/remove', { user_id: p.id }, 'Request cancelled') } }, 'Requested · Cancel');
    case 'incoming':
      return h('div', { class: 'row' },
        h('button', { class: 'btn primary sm', type: 'button', on: { click: () => act('friends/accept', { user_id: p.id }, `You and ${p.name} are friends`) } }, 'Accept request'),
        h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => act('friends/remove', { user_id: p.id }, 'Request declined') } }, 'Decline'));
    default:
      return h('button', { class: 'btn primary sm', type: 'button', on: { click: () => act('friends/request', { username: p.username }, 'Friend request sent') } }, icon('plus'), 'Add friend');
  }
}

function badgeTile(b) {
  return h('div', { class: `badge-tile${b.earned ? ' earned' : ''}`, title: b.description },
    h('span', { class: 'badge-icon' }, icon(b.icon)), h('b', { text: b.title }), h('small', { text: b.description }));
}

export async function renderUser(root, r) {
  const username = r.path[0];
  const page = h('div', { class: 'page' }, loading());
  root.append(page);
  const user = await api.currentUser();
  if (!user) {
    page.replaceChildren(h('div', { class: 'empty' }, h('h3', { text: 'Sign in to see profiles' }),
      h('p', { text: 'Profiles are visible to people with an account.' }), h('a', { class: 'btn primary', href: '#/me' }, 'Sign in')));
    return null;
  }
  let p;
  try { p = await api.get(`profiles/${encodeURIComponent(username)}`); } catch (e) { page.replaceChildren(errorBox(e)); return null; }
  const reload = () => go(location.hash, { replace: true });
  const prog = p.progress;
  page.replaceChildren(...[
    h('section', { class: 'card profile-card' },
      h('div', { class: 'profile-top' }, avatar(p, 80),
        h('div', { class: 'profile-names' }, h('h1', { text: p.name }), h('p', { class: 'muted', text: `@${p.username}` }),
          p.artist ? h('a', { class: 'pill pd', href: `#/artist/${p.artist.id}` }, icon('music'), p.artist.name) : null)),
      p.bio ? h('p', { class: 'profile-bio', text: p.bio }) : null,
      h('div', { class: 'stats' },
        prog ? stat(`${pct(prog.read, prog.total)}%`, 'of the Bible') : null,
        prog ? stat(prog.streak, 'day streak') : null,
        stat(p.friends, p.friends === 1 ? 'friend' : 'friends'),
        p.rewards ? stat(p.rewards.level, p.rewards.title) : stat(p.groups, 'groups')),
      h('div', { class: 'row wrap' }, relationshipButton(p, reload),
        p.relationship === 'self' ? h('button', { class: 'btn sm', type: 'button', on: { click: () => editProfile(user, p) } }, icon('pen'), 'Edit profile') : null,
        h('button', { class: 'btn ghost sm', type: 'button', on: { click: async () => {
          const url = `${location.origin}/app/#/u/${p.username}`;
          if (navigator.share) navigator.share({ title: p.name, url }).catch(() => {});
          else toast((await copyText(url)) ? 'Profile link copied' : "Couldn't copy");
        } } }, icon('share'), 'Share'),
        p.relationship !== 'self' ? h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => reportUser(p) } }, 'Report or block') : null)),
    p.verse ? h('a', { class: 'card link verse-card', href: readHash(p.verse) },
      h('div', { class: 'card-head' }, icon('heart'), h('span', { class: 'label', text: 'Favourite verse' })),
      h('blockquote', { class: 'devo-verse', text: `“${p.verse.text}”` }), h('span', { class: 'devo-ref', text: `${refLabel(p.verse)} · ${p.verse.t}` })) : null,
    p.rewards && p.rewards.badges.length ? h('section', { class: 'card' },
      h('div', { class: 'card-head' }, icon('award'), h('span', { class: 'label', text: `${p.rewards.earned} badges · ${p.rewards.points.toLocaleString()} points` })),
      h('div', { class: 'badges' }, p.rewards.badges.slice(0, 12).map(badgeTile))) : null,
    p.shared_groups.length ? h('p', { class: 'muted small', text: `You’re both in: ${p.shared_groups.join(', ')}` }) : null,
  ].filter(Boolean));
  return null;
}

export function reportUser(p) {
  import('./safety.js').then((m) => m.reportSheet({ kind: 'user', id: p.id, name: p.name }));
}

// ----------------------------------------------------------------- friends

export async function renderFriends(root) {
  const page = h('div', { class: 'page' }, h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Friends' }), h('h1', { text: 'Your friends' })), loading());
  root.append(page);
  const user = await api.currentUser();
  if (!user) { page.lastChild.replaceWith(h('div', { class: 'auth' }, authForms(() => go('#/friends', { replace: true }), { intro: false }))); return null; }
  let f;
  try { f = await api.get('friends'); } catch (e) { page.lastChild.replaceWith(errorBox(e)); return null; }
  setRequests(f.incoming.length);
  const reload = () => go('#/friends', { replace: true });
  const act = async (path, body, msg) => { try { await api.post(path, body); toast(msg); reload(); } catch (e) { toast(e.message); } };
  const person = (p, ...actions) => h('div', { class: 'member' }, avatar(p, 40),
    h('a', { href: `#/u/${p.username}`, class: 'person-link' }, h('b', { text: p.name }), h('small', { class: 'muted', text: ` @${p.username}` })),
    h('div', { class: 'row' }, ...actions));
  const add = h('input', { class: 'input', placeholder: 'Their username', autocapitalize: 'none', spellcheck: 'false', 'aria-label': 'Username to add' });
  page.lastChild.replaceWith(h('div', { class: 'stack' },
    h('form', { class: 'row', on: { submit: (e) => { e.preventDefault(); if (add.value.trim()) act('friends/request', { username: add.value.trim() }, 'Friend request sent'); } } },
      add, h('button', { class: 'btn primary', type: 'submit' }, icon('plus'), 'Add')),
    f.incoming.length ? h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('span', { class: 'label', text: 'Requests' })),
      h('div', { class: 'members' }, f.incoming.map((p) => person(p,
        h('button', { class: 'btn primary sm', type: 'button', on: { click: () => act('friends/accept', { user_id: p.id }, `You and ${p.name} are friends`) } }, 'Accept'),
        h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => act('friends/remove', { user_id: p.id }, 'Declined') } }, 'Decline'))))) : null,
    h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('span', { class: 'label', text: `${f.friends.length} friend${f.friends.length === 1 ? '' : 's'}` })),
      f.friends.length ? h('div', { class: 'members' }, f.friends.map((p) => person(p))) : h('p', { class: 'muted', text: 'Add friends by username, or from a study group’s member list.' })),
    f.outgoing.length ? h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('span', { class: 'label', text: 'Sent' })),
      h('div', { class: 'members' }, f.outgoing.map((p) => person(p,
        h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => act('friends/remove', { user_id: p.id }, 'Request cancelled') } }, 'Cancel'))))) : null));
  return null;
}

// ---------------------------------------------------------------- progress

export async function renderProgress(root) {
  const page = h('div', { class: 'page' }, loading());
  root.append(page);
  const [prog, kjv, user] = await Promise.all([progress.summary(), api.books('KJV').catch(() => null), api.currentUser()]);
  if (!kjv) { page.replaceChildren(errorBox(new Error('Couldn’t load the book list.'), () => go(location.hash))); return null; }
  const chapterCount = Object.fromEntries(kjv.books.map((b) => [b.name, b.chapters.length]));
  const otTotal = OT.reduce((n, b) => n + (chapterCount[b] || 0), 0);
  const ntTotal = NT.reduce((n, b) => n + (chapterCount[b] || 0), 0);
  const t = (store.load('last', null) || {}).t || store.settings().translation;
  const tile = (b) => {
    const read = (prog.chapters[b] || []).length;
    const total = chapterCount[b] || 0;
    const el = h('button', { class: `book-tile${read === total && total ? ' done' : ''}`, type: 'button' },
      h('b', { text: bookName(b) }), h('small', { text: `${read}/${total}` }), progressBar(total ? read / total : 0));
    el.addEventListener('click', () => chapterSheet(b, total, new Set(prog.chapters[b] || []), t));
    return el;
  };
  page.replaceChildren(
    h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Progress' }), h('h1', { text: 'Through the Bible' }),
      h('p', { class: 'sub', text: user ? 'Saved to your account and shown on your profile (you can hide it in Edit profile).' : 'Saved on this device. Sign in to keep it on your profile and earn rewards.' })),
    h('section', { class: 'card progress-hero' },
      h('img', { class: 'hero-art', src: '/app/img/journey.svg', alt: '' }),
      h('div', { class: 'plan-top' }, ring(prog.read / TOTAL, `${pct(prog.read, TOTAL)}%`),
        h('div', {}, h('h2', { text: `${prog.read.toLocaleString()} of ${TOTAL.toLocaleString()} chapters` }),
          h('p', { class: 'muted', text: prog.streak ? `${prog.streak}-day reading streak` : 'Mark a chapter as read to start a streak' }))),
      h('div', { class: 'split' },
        h('div', {}, h('small', { class: 'muted', text: `Old Testament · ${prog.ot}/${otTotal}` }), progressBar(prog.ot / otTotal)),
        h('div', {}, h('small', { class: 'muted', text: `New Testament · ${prog.nt}/${ntTotal}` }), progressBar(prog.nt / ntTotal)))),
    h('p', { class: 'muted small', text: 'Tap a book to mark chapters. In the reader, “Mark as read” at the end of each chapter does it for you.' }),
    h('h3', { class: 'jmonth', text: 'Old Testament' }), h('div', { class: 'book-grid' }, OT.map(tile)),
    h('h3', { class: 'jmonth', text: 'New Testament' }), h('div', { class: 'book-grid' }, NT.map(tile)));
  return null;
}

function chapterSheet(book, total, read, t) {
  const sh = sheet(bookName(book), { onClose: () => go('#/progress', { replace: true }) });
  const grid = h('div', { class: 'chapters' });
  for (let c = 1; c <= total; c += 1) {
    const b = h('button', { class: `chn${read.has(c) ? ' on' : ''}`, type: 'button', text: String(c), 'aria-pressed': String(read.has(c)) });
    b.addEventListener('click', async () => {
      const on = !b.classList.contains('on');
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
      await progress.mark([[book, c]], on);
    });
    grid.append(b);
  }
  sh.body.append(h('div', { class: 'row wrap' },
    h('button', { class: 'btn sm', type: 'button', on: { click: async () => {
      await progress.mark(Array.from({ length: total }, (_, i) => [book, i + 1]), true);
      for (const b of grid.children) b.classList.add('on');
    } } }, icon('check'), 'Mark the whole book'),
    h('a', { class: 'btn ghost sm', href: readHash({ t, b: book, c: 1 }), on: { click: () => sh.close() } }, icon('book'), 'Read it')), grid);
}

// ----------------------------------------------------------------- rewards

export async function renderRewards(root) {
  const page = h('div', { class: 'page' }, h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Rewards' }), h('h1', { text: 'Badges & levels' }),
    h('p', { class: 'sub', text: 'Earned by reading, keeping a streak, finishing books and studying together. Worked out by the server from what you’ve done, so they’re real.' })), loading());
  root.append(page);
  const user = await api.currentUser();
  if (!user) { page.lastChild.replaceWith(h('div', { class: 'auth' }, authForms(() => go('#/rewards', { replace: true }), { intro: false }))); return null; }
  let r;
  try { r = await api.get('me/rewards'); } catch (e) { page.lastChild.replaceWith(errorBox(e)); return null; }
  const earned = r.badges.filter((b) => b.earned);
  const locked = r.badges.filter((b) => !b.earned);
  page.lastChild.replaceWith(h('div', { class: 'stack' },
    h('section', { class: 'card level-card' },
      h('div', { class: 'plan-top' }, ring(r.fraction, `${r.level}`),
        h('div', {}, h('h2', { text: `Level ${r.level} · ${r.title}` }),
          h('p', { class: 'muted', text: `${r.points.toLocaleString()} points · ${(r.next - r.points).toLocaleString()} to level ${r.level + 1}` }))),
      progressBar(r.fraction),
      h('p', { class: 'muted small', text: '2 points for every chapter read, plus each badge’s points.' })),
    h('h3', { class: 'jmonth', text: `Earned · ${earned.length}` }),
    earned.length ? h('div', { class: 'badges' }, earned.map(badgeTile)) : h('p', { class: 'muted', text: 'Mark your first chapter as read to earn “First steps”.' }),
    h('h3', { class: 'jmonth', text: `To earn · ${locked.length}` }),
    h('div', { class: 'badges' }, locked.map(badgeTile))));
  return null;
}

// ----------------------------------------------------------------- devices

export async function renderDevices(root) {
  const page = h('div', { class: 'page' }, h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Security' }), h('h1', { text: 'Devices & security' }),
    h('p', { class: 'sub', text: 'Every request is checked against your session, and sessions end after 30 days, or 14 days unused. Sign out anything you don’t recognise.' })), loading());
  root.append(page);
  const user = await api.currentUser();
  if (!user) { go('#/me', { replace: true }); return null; }
  const draw = (list) => page.lastChild.replaceWith(h('div', { class: 'stack' },
    h('section', { class: 'card' }, h('div', { class: 'members' }, list.map((s) => h('div', { class: 'member' },
      h('span', { class: 'me-row-icon' }, icon('device')),
      h('div', {}, h('b', { text: s.device }), h('div', { class: 'muted small', text: s.current ? 'This device' : `Last used ${ago(s.last_seen * 1000)}` })),
      s.current ? h('span', { class: 'pill pd', text: 'You' }) : h('button', { class: 'btn ghost sm', type: 'button', on: { click: async () => {
        try { const res = await api.post('me/sessions/revoke', { id: s.id }); toast('Signed out'); draw(res.sessions); } catch (e) { toast(e.message); }
      } } }, 'Sign out'))))),
    list.length > 1 ? h('button', { class: 'btn', type: 'button', on: { click: async () => {
      try { const res = await api.post('me/sessions/revoke', { id: 'others' }); toast('Signed out everywhere else'); draw(res.sessions); } catch (e) { toast(e.message); }
    } } }, icon('logout'), 'Sign out everywhere else') : null));
  try { draw((await api.get('me/sessions')).sessions); } catch (e) { page.lastChild.replaceWith(errorBox(e)); }
  return null;
}
