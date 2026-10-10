// Study groups: private, invite-only, each with a chat and (optionally) a
// reading plan the members follow together. The group's leader moderates.

import * as api from '../api.js';
import * as store from '../store.js';
import { refLabel, readHash } from '../bible.js';
import { dayNumber, fmtTime, fmtDayLabel, todayISO, fmtDate } from '../dates.js';
import { h, icon, sheet, toast, loading, errorBox, confirmSheet, copyText, initials, autoGrow, avatar } from '../ui.js';
import { reportSheet } from './safety.js';
import * as sync from '../sync.js';
import { go, segmented, setUnread } from '../main.js';
import { segLabel, readingLinks } from './today.js';
import { startPlanSheet } from './plans.js';

const inviteUrl = (code) => `${location.origin}/app/#/join/${code}`;

// ------------------------------------------------------------------ auth

export function authForms(onDone, { intro = true } = {}) {
  let mode = 'signup';
  const err = h('p', { class: 'form-error', role: 'alert' });
  const username = h('input', { class: 'input', autocomplete: 'username', required: true, minlength: 3, maxlength: 24,
    autocapitalize: 'none', spellcheck: 'false', placeholder: 'e.g. grace_j' });
  const name = h('input', { class: 'input', autocomplete: 'name', maxlength: 40, placeholder: 'How your group sees you' });
  const password = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', required: true, minlength: 8 });
  const nameField = h('label', { class: 'field' }, h('span', { text: 'Your name' }), name);
  const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Create account');
  const switcher = h('p', { class: 'muted small center' });

  const setMode = (m) => {
    mode = m;
    nameField.hidden = m === 'login';
    password.autocomplete = m === 'login' ? 'current-password' : 'new-password';
    submit.textContent = m === 'login' ? 'Sign in' : 'Create account';
    err.textContent = '';
    switcher.replaceChildren(m === 'login' ? 'New here? ' : 'Have an account? ',
      h('a', { href: '#', on: { click: (e) => { e.preventDefault(); setMode(m === 'login' ? 'signup' : 'login'); } } },
        m === 'login' ? 'Create an account' : 'Sign in'));
  };
  const form = h('form', { class: 'form card', on: { submit: async (e) => {
    e.preventDefault();
    err.textContent = '';
    submit.disabled = true;
    try {
      const body = { username: username.value.trim(), password: password.value };
      if (mode === 'signup') body.name = name.value.trim();
      const { user } = await api.post(mode === 'login' ? 'login' : 'signup', body);
      await sync.rememberKey(user.username, body.password); // journal encryption key, kept on this device
      api.setUser(user);
      toast(mode === 'login' ? `Welcome back, ${user.name}` : `Welcome, ${user.name}`);
      onDone(user);
    } catch (ex) {
      err.textContent = ex.message;
    } finally {
      submit.disabled = false;
    }
  } } },
  h('label', { class: 'field' }, h('span', { text: 'Username' }), username),
  nameField,
  h('label', { class: 'field' }, h('span', { text: 'Password' }), password),
  err, submit, switcher);
  setMode('signup');

  if (!intro) return form;
  return h('div', { class: 'auth-grid' },
    h('section', { class: 'card' },
      h('div', { class: 'card-head' }, icon('users'), h('span', { class: 'label', text: 'Study groups' })),
      h('h2', { text: 'Read the Bible together' }),
      h('ul', { class: 'feature-list' },
        h('li', {}, icon('lock'), h('span', { text: 'Private by design: people join only with your invite link. No public rooms, no directory.' })),
        h('li', {}, icon('chat'), h('span', { text: 'A group chat where you can share verses straight from the reader.' })),
        h('li', {}, icon('calendar'), h('span', { text: 'Follow a reading plan together and see who has read today.' })),
        h('li', {}, icon('globe'), h('span', { text: 'Groups meet online, so members can be anywhere: friends, family, your church, or people across the world.' })),
        h('li', {}, icon('pen'), h('span', { text: "Your journal and highlights stay on your device. A group only sees what you post." })))),
    form);
}

// ---------------------------------------------------------------- groups

function groupCard(g) {
  const preview = g.last_body ? `${g.last_name}: ${g.last_body}` : g.area || 'No messages yet';
  return h('a', { class: 'card link gcard', href: `#/groups/${g.id}` },
    h('div', { class: 'gavatar', text: initials(g.name) }),
    h('div', { class: '' },
      h('div', { class: 'gname', text: g.name }),
      h('div', { class: 'gmeta', text: [g.area, `${g.members} member${g.members === 1 ? '' : 's'}`, g.role === 'leader' ? 'You lead' : ''].filter(Boolean).join(' · ') }),
      h('div', { class: 'gprev', text: preview })),
    g.unread ? h('span', { class: 'unread', text: String(g.unread) }) : icon('chevR'));
}

async function groupForm(sh, initial = {}, { submitLabel = 'Create group', onSubmit }) {
  const plans = await api.plans().catch(() => []);
  const err = h('p', { class: 'form-error', role: 'alert' });
  const name = h('input', { class: 'input', required: true, maxlength: 60, value: initial.name || '', placeholder: 'e.g. Romans Online Study' });
  const about = h('textarea', { class: 'textarea', rows: 3, maxlength: 500, placeholder: 'What you’re studying, who it’s for, when you check in (optional)' });
  about.value = initial.about || '';
  const plan = h('select', { class: 'input', 'aria-label': 'Reading plan' },
    h('option', { value: '', text: 'No plan for now' }),
    plans.map((p) => h('option', { value: p.id, text: `${p.title} (${p.length} days)`, selected: p.id === initial.plan })));
  const start = h('input', { class: 'input', type: 'date', value: initial.plan_start || todayISO() });
  const startField = h('label', { class: 'field' }, h('span', { text: 'Plan starts' }), start);
  const sync = () => { startField.hidden = !plan.value; };
  plan.addEventListener('change', sync);
  sync();
  const submit = h('button', { class: 'btn primary', type: 'submit', text: submitLabel });
  sh.body.append(h('form', { class: 'form', on: { submit: async (e) => {
    e.preventDefault();
    submit.disabled = true;
    err.textContent = '';
    try {
      await onSubmit({ name: name.value, about: about.value,
        plan: plan.value || null, plan_start: plan.value ? start.value : null });
      sh.close();
    } catch (ex) { err.textContent = ex.message; } finally { submit.disabled = false; }
  } } },
  h('label', { class: 'field' }, h('span', { text: 'Group name' }), name),
  h('label', { class: 'field' }, h('span', { text: 'About' }), about),
  h('label', { class: 'field' }, h('span', { text: 'Read together' }), plan),
  startField, err, submit));
  name.focus();
}

function newGroup() {
  const sh = sheet('New study group');
  groupForm(sh, {}, { onSubmit: async (fields) => {
    const g = await api.post('groups', fields);
    toast('Group created. Share the invite link to bring people in.');
    go(`#/groups/${g.id}?tab=members`);
  } });
}

function joinByLink() {
  const sh = sheet('Join a group');
  const input = h('input', { class: 'input', required: true, placeholder: 'Paste the invite link', 'aria-label': 'Invite link' });
  sh.body.append(h('p', { class: 'muted', text: 'Ask the group leader for their invite link, then paste it here.' }),
    h('form', { class: 'form', on: { submit: (e) => {
      e.preventDefault();
      const code = input.value.trim().split('/join/').pop().split(/[?#&\s]/)[0];
      sh.close();
      go(`#/join/${encodeURIComponent(code)}`);
    } } }, input, h('button', { class: 'btn primary', type: 'submit' }, 'Continue')));
  input.focus();
}

export async function render(root) {
  const page = h('div', { class: 'page' },
    h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Community' }),
      h('h1', { text: 'Study groups' })),
    loading());
  root.append(page);
  const user = await api.currentUser();
  if (!user) {
    page.lastChild.replaceWith(authForms(() => go('#/community', { replace: true })));
    return null;
  }
  page.querySelector('.page-head').append(h('div', { class: 'row wrap' },
    h('button', { class: 'btn primary', type: 'button', on: { click: newGroup } }, icon('plus'), 'New group'),
    h('button', { class: 'btn', type: 'button', on: { click: joinByLink } }, icon('link'), 'Join with a link'),
    h('span', { class: 'spacer' }),
    h('a', { class: 'btn ghost', href: '#/churches' }, icon('pin'), 'Find a church')));
  try {
    const { groups } = await api.get('groups');
    setUnread(groups.reduce((n, g) => n + g.unread, 0));
    page.lastChild.replaceWith(groups.length ? h('div', { class: 'glist' }, groups.map(groupCard))
      : h('div', { class: 'empty' }, h('h3', { text: 'No groups yet' }),
        h('p', { text: 'Start an online group for friends, family or your church, and share its invite link. Or paste a link someone sent you.' }),
        h('button', { class: 'btn primary', type: 'button', on: { click: newGroup } }, icon('plus'), 'Start a group')));
  } catch (e) {
    page.lastChild.replaceWith(errorBox(e, () => go(location.hash)));
  }
  return null;
}

// ------------------------------------------------------------------- join

export async function renderJoin(root, r) {
  const code = r.path[0] || '';
  const page = h('div', { class: 'page' }, loading());
  root.append(page);
  let g;
  try { g = await api.get(`invites/${encodeURIComponent(code)}`); } catch (e) {
    page.replaceChildren(h('div', { class: 'empty' }, h('h3', { text: 'Invite not found' }),
      h('p', { text: e.message }), h('a', { class: 'btn', href: '#/community' }, 'Study groups')));
    return null;
  }
  const join = async () => {
    try {
      const joined = await api.post('groups/join', { code });
      toast(`You joined ${joined.name}`);
      go(`#/groups/${joined.id}`, { replace: true });
    } catch (e) { toast(e.message); }
  };
  const user = await api.currentUser();
  const invite = h('section', { class: 'card' },
    h('div', { class: 'card-head' }, icon('users'), h('span', { class: 'label', text: "You're invited" })),
    h('div', { class: 'row' }, h('div', { class: 'gavatar', text: initials(g.name) }),
      h('div', {}, h('h2', { text: g.name }),
        h('p', { class: 'muted', text: [g.area, `${g.members} member${g.members === 1 ? '' : 's'}`].filter(Boolean).join(' · ') }))),
    g.about ? h('p', { class: 'muted', text: g.about }) : null,
    user ? h('button', { class: 'btn primary', type: 'button', on: { click: join } }, `Join as ${user.name}`) : null);
  page.replaceChildren(h('div', { class: 'stack' }, invite,
    user ? null : h('div', { class: 'auth' }, h('p', { class: 'muted', text: 'Create an account (or sign in) to join. It takes a few seconds; no email needed.' }),
      authForms(join, { intro: false }))));
  return null;
}

// ------------------------------------------------------------------ group

const ROLE_LABEL = { leader: 'Leader', moderator: 'Moderator' };

function roleBadges(p) {
  return [ROLE_LABEL[p.role] ? h('span', { class: 'pill pd role-pill', text: ROLE_LABEL[p.role] }) : null,
    p.title ? h('span', { class: 'pill role-pill', text: p.title }) : null];
}

function messageEl(m, me, role, gid, onDelete) {
  const mine = m.user_id === me.id;
  const canModerate = role === 'leader' || role === 'moderator';
  const del = (mine || canModerate) ? h('button', { type: 'button', on: { click: async () => {
    if (!(await confirmSheet('Delete message?', mine ? 'It will be removed for everyone.' : `Remove ${m.name}'s message for everyone?`, { ok: 'Delete', danger: true }))) return;
    try { await api.post(`groups/${gid}/messages/${m.id}/delete`); onDelete(m.id); } catch (e) { toast(e.message); }
  } } }, 'Delete') : null;
  const report = mine ? null : h('button', { type: 'button', on: { click: () => reportSheet({ kind: 'message', id: m.id, userId: m.user_id }) } }, 'Report');
  return h('div', { class: `msg${mine ? ' mine' : ''}`, dataset: { id: m.id, user: m.user_id } },
    mine ? null : h('div', { class: 'msg-head' }, avatar(m, 22),
      h('a', { class: 'mname', href: `#/u/${m.username}`, text: m.name }), ...roleBadges(m)),
    h('div', { class: 'bubble' },
      m.ref ? h('a', { class: 'vcard', href: readHash(m.ref) }, h('q', { text: m.ref.text }),
        h('small', { text: `${refLabel(m.ref)} · ${m.ref.t}` })) : null,
      m.body || null),
    h('div', { class: 'mtime' }, fmtTime(m.created), del, report));
}

function chatTab(area, g, me) {
  const msgs = h('div', { class: 'msgs', role: 'log', 'aria-live': 'polite' });
  const input = h('textarea', { class: 'textarea', rows: 1, maxlength: 2000, placeholder: 'Message', 'aria-label': 'Message' });
  const send = h('button', { class: 'btn primary send', type: 'submit', 'aria-label': 'Send' }, icon('send'));
  const older = h('button', { class: 'btn ghost sm', type: 'button', hidden: true }, 'Earlier messages');
  autoGrow(input);
  let lastId = 0, firstId = null, lastDay = null, timer = null, alive = true;
  const known = new Set();

  const remove = (id) => { msgs.querySelector(`.msg[data-id="${id}"]`)?.remove(); };
  const daySep = (m) => h('div', { class: 'day-sep', text: fmtDayLabel(m.created) });
  const appendAll = (list) => {
    const nearBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 160;
    for (const m of list) {
      if (known.has(m.id)) continue;
      known.add(m.id);
      const day = fmtDayLabel(m.created);
      if (day !== lastDay) { msgs.append(daySep(m)); lastDay = day; }
      msgs.append(messageEl(m, me, g.role, g.id, remove));
      lastId = Math.max(lastId, m.id);
      if (firstId === null || m.id < firstId) firstId = m.id;
    }
    if (list.length && nearBottom) window.scrollTo(0, document.body.scrollHeight);
  };
  const poll = async () => {
    clearTimeout(timer);
    if (!alive) return;
    try {
      const { messages } = await api.get(`groups/${g.id}/messages`, lastId ? { after: lastId } : undefined);
      appendAll(messages);
      if (!lastId && !messages.length) msgs.replaceChildren(h('p', { class: 'muted center small', text: 'No messages yet. Say hello, or share a verse from the reader.' }));
      if (!older.dataset.done && messages.length >= 50 && firstId !== null) older.hidden = false;
    } catch (e) {
      if (e.status === 404 || e.status === 401) { alive = false; toast(e.message); go('#/community', { replace: true }); return; }
    }
    timer = setTimeout(poll, document.hidden ? 30000 : 4000);
  };
  older.addEventListener('click', async () => {
    try {
      const { messages } = await api.get(`groups/${g.id}/messages`, { before: firstId });
      if (messages.length < 50) { older.hidden = true; older.dataset.done = '1'; }
      const frag = document.createDocumentFragment();
      let day = null;
      for (const m of messages) {
        if (known.has(m.id)) continue;
        known.add(m.id);
        const d = fmtDayLabel(m.created);
        if (d !== day) { frag.append(daySep(m)); day = d; }
        frag.append(messageEl(m, me, g.role, g.id, remove));
        firstId = Math.min(firstId, m.id);
      }
      msgs.prepend(frag);
    } catch (e) { toast(e.message); }
  });

  const form = h('form', { class: 'composer', on: { submit: async (e) => {
    e.preventDefault();
    const body = input.value.trim();
    if (!body) return;
    send.disabled = true;
    try {
      const m = await api.post(`groups/${g.id}/messages`, { body });
      input.value = '';
      input.dispatchEvent(new Event('input'));
      if (msgs.querySelector('p.muted')) msgs.replaceChildren();
      appendAll([m]);
      window.scrollTo(0, document.body.scrollHeight);
    } catch (ex) { toast(ex.message); } finally { send.disabled = false; input.focus(); }
  } } }, input, send);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  area.append(h('div', { class: 'chat' }, h('div', { class: 'center' }, older), msgs, form));
  poll().then(() => window.scrollTo(0, document.body.scrollHeight));
  const vis = () => { if (!document.hidden) poll(); };
  document.addEventListener('visibilitychange', vis);
  return () => { alive = false; clearTimeout(timer); document.removeEventListener('visibilitychange', vis); };
}

async function readingTab(area, g, me, reload) {
  const wrap = h('div', { class: 'page stack' });
  area.append(wrap);
  if (!g.plan) {
    wrap.append(h('div', { class: 'empty' }, h('h3', { text: 'No reading plan yet' }),
      h('p', { text: g.can && g.can.edit ? 'Pick a plan and everyone in the group can tick off each day and see how the others are doing.'
        : 'The group leader can choose a plan for everyone to read together.' }),
      g.can && g.can.edit ? h('button', { class: 'btn primary', type: 'button', on: { click: () => choosePlan(g, reload) } }, icon('calendar'), 'Choose a plan') : null));
    return null;
  }
  wrap.append(loading());
  let p;
  try { p = await api.planDetail(g.plan); } catch (e) { wrap.replaceChildren(errorBox(e)); return null; }
  const n = dayNumber(g.plan_start);
  const t = (store.load('last', null) || {}).t || store.settings().translation;
  const mine = new Set(g.my_days);
  const parts = [h('div', { class: 'row wrap' }, h('div', {}, h('h2', { text: p.title }),
    h('p', { class: 'muted', text: n < 1 ? `Starts ${fmtDate(g.plan_start)}` : n > p.length ? 'Finished' : `Day ${n} of ${p.length} · started ${fmtDate(g.plan_start)}` })),
  h('span', { class: 'spacer' }),
  g.can && g.can.edit ? h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => choosePlan(g, reload) } }, 'Change plan') : null)];
  if (n >= 1 && n <= p.length) {
    const done = mine.has(n);
    parts.push(h('section', { class: 'card' },
      h('div', { class: 'card-head' }, icon('book'), h('span', { class: 'label', text: "Today's reading" }), h('span', { class: 'spacer' }),
        h('span', { class: 'muted small', text: `${g.day_counts[String(n)] || 0} of ${g.members.length} read` })),
      readingLinks(p.days[n - 1], t),
      h('div', { class: 'row devo-foot' }, h('span', { class: 'spacer' }),
        h('button', { class: `btn ${done ? '' : 'primary'} sm`, type: 'button', on: { click: async () => {
          try { await api.post(`groups/${g.id}/progress`, { day: n, done: !done }); toast(done ? 'Unmarked' : 'Marked as read'); reload('reading'); } catch (e) { toast(e.message); }
        } } }, icon('check'), done ? 'You read today' : "I've read today"))));
  }
  const today = Math.min(Math.max(n, 0), p.length);
  parts.push(h('section', { class: 'card' },
    h('div', { class: 'card-head' }, icon('users'), h('span', { class: 'label', text: 'Group progress' })),
    h('div', { class: 'progress-list' }, g.members.map((m) => h('div', { class: 'member' },
      avatar(m, 38),
      h('div', {}, h('div', { text: m.id === me.id ? `${m.name} (you)` : m.name }),
        h('div', { class: 'progress' }, (() => { const s = h('span'); s.style.width = `${today ? Math.min(100, Math.round((m.days_done / today) * 100)) : 0}%`; return s; })())),
      h('span', { class: 'muted small', text: `${m.days_done} day${m.days_done === 1 ? '' : 's'}` }))))));
  if (n > 1) {
    const recent = [];
    for (let d = Math.min(n, p.length); d >= Math.max(1, n - 6); d -= 1) recent.push(d);
    parts.push(h('section', { class: 'card' },
      h('div', { class: 'card-head' }, icon('calendar'), h('span', { class: 'label', text: 'This week' })),
      h('div', { class: 'days' }, recent.map((d) => {
        const isDone = mine.has(d);
        const check = h('button', { class: `check${isDone ? ' on' : ''}`, type: 'button', 'aria-pressed': String(isDone), 'aria-label': `Day ${d} read` }, icon('check'));
        check.addEventListener('click', async () => {
          try { await api.post(`groups/${g.id}/progress`, { day: d, done: !isDone }); reload('reading'); } catch (e) { toast(e.message); }
        });
        return h('div', { class: `day${d === n ? ' today' : ''}${isDone ? ' done' : ''}` },
          h('div', { class: 'day-n' }, String(d), h('small', { text: `${g.day_counts[String(d)] || 0}/${g.members.length}` })),
          h('div', { class: 'day-segs' }, p.days[d - 1].map((sg) => h('a', { href: readHash({ t, b: sg[0], c: sg[1] }), text: segLabel(sg) }))),
          check);
      }))));
  }
  wrap.replaceChildren(...parts);
  return null;
}

async function choosePlan(g, reload) {
  const plans = await api.plans();
  const sh = sheet('Read a plan together', { tall: true });
  sh.body.append(h('p', { class: 'muted', text: 'Changing the plan clears everyone’s ticks for the old one.' }),
    h('div', { class: 'stack' }, plans.map((p) => h('button', { class: 'card link', type: 'button', on: { click: () => {
      sh.close();
      startPlanSheet(p, { onStart: async (start) => {
        try { await api.post(`groups/${g.id}`, { plan: p.id, plan_start: start }); toast('Plan set for the group'); reload('reading'); } catch (e) { toast(e.message); }
      } });
    } } }, h('h3', { text: p.title }), h('p', { class: 'muted small', text: `${p.length} days · ${p.summary}` })))),
    g.plan ? h('button', { class: 'btn ghost danger', type: 'button', on: { click: async () => {
      sh.close();
      try { await api.post(`groups/${g.id}`, { plan: null }); reload('reading'); } catch (e) { toast(e.message); }
    } } }, 'Stop reading a plan') : null);
}

function roleSheet(g, m, reload) {
  const sh = sheet(`${m.name}’s role`);
  const roles = [['leader', 'Leader', 'Runs the group: everything moderators can do, plus the group’s details, plan and roles.'],
    ['moderator', 'Moderator', 'Keeps the chat in order: deletes messages, removes members, resets the invite link.'],
    ['member', 'Member', 'Reads, chats and follows the plan.']];
  const choices = h('div', { class: 'stack' }, roles.map(([value, label, about]) => h('label', { class: 'check-row' },
    h('input', { type: 'radio', name: 'role', value, checked: m.role === value }),
    h('span', {}, h('b', { text: label }), h('br'), h('small', { class: 'muted', text: about })))));
  const title = h('input', { class: 'input', maxlength: 30, value: m.title || '', placeholder: 'e.g. Prayer lead, Host, Worship' });
  const err = h('p', { class: 'form-error', role: 'alert' });
  sh.body.append(h('form', { class: 'form', on: { submit: async (e) => {
    e.preventDefault();
    try {
      await api.post(`groups/${g.id}/role`, { user_id: m.id, role: choices.querySelector('input:checked').value, title: title.value });
      sh.close();
      toast('Role updated');
      reload('members');
    } catch (ex) { err.textContent = ex.message; }
  } } }, choices, h('label', { class: 'field' }, h('span', { text: 'Title (optional badge)' }), title), err,
  h('button', { class: 'btn primary', type: 'submit' }, 'Save')));
}

function membersTab(area, g, me, reload) {
  const can = g.can || {};
  const url = inviteUrl(g.invite);
  const rank = { leader: 3, moderator: 2, member: 1 };
  const actions = (m) => {
    if (m.id === me.id) return h('div', { class: 'row' }, can.roles ? h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => roleSheet(g, m, reload) } }, 'Title') : null);
    const out = [];
    if (can.roles) out.push(h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => roleSheet(g, m, reload) } }, 'Role'));
    if (can.moderate && rank[m.role] < rank[g.role]) {
      out.push(h('button', { class: 'btn ghost sm danger', type: 'button', on: { click: async () => {
        if (!(await confirmSheet(`Remove ${m.name}?`, 'They leave the group and lose access to its chat. Reset the invite link too if they shouldn’t come back.', { ok: 'Remove', danger: true }))) return;
        try { await api.post(`groups/${g.id}/remove`, { user_id: m.id }); toast(`${m.name} removed`); reload('members'); } catch (e) { toast(e.message); }
      } } }, 'Remove'));
    }
    return h('div', { class: 'row' }, ...out);
  };
  const share = navigator.share ? h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Share invite link', on: { click: () => {
    navigator.share({ title: g.name, text: `Join "${g.name}" on The Gift`, url }).catch(() => {});
  } } }, icon('share')) : null;
  area.append(h('div', { class: 'page stack' },
    h('section', { class: 'card' },
      h('div', { class: 'card-head' }, icon('link'), h('span', { class: 'label', text: 'Invite link' })),
      h('p', { class: 'muted small', text: 'Anyone with this link can join. Send it only to people you want in the group.' }),
      h('div', { class: 'invite-box' }, h('code', { text: url }),
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Copy invite link', on: { click: async () => {
          toast((await copyText(url)) ? 'Invite link copied' : "Couldn't copy");
        } } }, icon('copy')), share),
      can.moderate ? h('button', { class: 'btn ghost sm', type: 'button', on: { click: async () => {
        if (!(await confirmSheet('Reset the invite link?', 'The old link stops working. People already in the group stay.', { ok: 'Reset link' }))) return;
        try { await api.post(`groups/${g.id}/invite`); toast('New invite link ready'); reload('members'); } catch (e) { toast(e.message); }
      } } }, 'Reset link') : null),
    h('section', { class: 'card' },
      h('div', { class: 'card-head' }, icon('users'), h('span', { class: 'label', text: `${g.members.length} member${g.members.length === 1 ? '' : 's'}` })),
      h('div', { class: 'members' }, g.members.map((m) => h('div', { class: 'member' },
        avatar(m, 38),
        h('div', { class: 'member-text' }, h('a', { class: 'person-link', href: `#/u/${m.username}` }, h('b', { text: m.id === me.id ? `${m.name} (you)` : m.name })),
          h('div', { class: 'row wrap' }, h('span', { class: 'muted small', text: `@${m.username}` }), ...roleBadges(m))),
        actions(m))))),
    h('section', { class: 'card' },
      h('div', { class: 'card-head' }, icon('sliders'), h('span', { class: 'label', text: 'Group' })),
      g.about ? h('p', { class: 'muted', text: g.about }) : null,
      h('div', { class: 'row wrap' },
        can.edit ? h('button', { class: 'btn sm', type: 'button', on: { click: () => {
          const sh = sheet('Edit group');
          groupForm(sh, g, { submitLabel: 'Save', onSubmit: async (fields) => {
            const { plan, plan_start, ...rest } = fields; // the plan is changed from the Reading tab
            await api.post(`groups/${g.id}`, rest);
            reload('members');
          } });
        } } }, 'Edit details') : null,
        h('button', { class: 'btn ghost sm', type: 'button', on: { click: async () => {
          const last = g.members.length === 1;
          if (!(await confirmSheet('Leave this group?', last ? "You're the last member, so the group and its chat will be deleted." : 'You can rejoin with an invite link.', { ok: 'Leave', danger: true }))) return;
          try { await api.post(`groups/${g.id}/leave`); toast('You left the group'); go('#/community', { replace: true }); } catch (e) { toast(e.message); }
        } } }, icon('logout'), 'Leave group'),
        can.edit ? h('button', { class: 'btn ghost sm danger', type: 'button', on: { click: async () => {
          if (!(await confirmSheet(`Delete “${g.name}”?`, 'This deletes the group, its chat and its progress for everyone. It cannot be undone.', { ok: 'Delete group', danger: true }))) return;
          try { await api.post(`groups/${g.id}/delete`); toast('Group deleted'); go('#/community', { replace: true }); } catch (e) { toast(e.message); }
        } } }, icon('trash'), 'Delete group') : null))));
  return null;
}

export async function renderGroup(root, r) {
  const gid = Number(r.path[0]);
  const me = await api.currentUser();
  if (!me) { go('#/community', { replace: true }); return null; }
  root.append(loading());
  let g;
  try { g = await api.get(`groups/${gid}`); } catch (e) {
    root.replaceChildren(h('div', { class: 'page' }, errorBox(e), h('p', { class: 'center' }, h('a', { href: '#/community' }, 'Back to groups'))));
    return null;
  }
  const tab = r.params.get('tab') || 'chat';
  const reload = (t) => go(`#/groups/${gid}?tab=${t}`, { replace: true });
  const area = h('div');
  root.replaceChildren(
    h('div', { class: 'group-head' },
      h('a', { class: 'icon-btn', href: '#/community', 'aria-label': 'All groups' }, icon('back')),
      h('div', { class: 'gavatar', text: initials(g.name) }),
      h('div', {}, h('h2', { text: g.name }),
        h('div', { class: 'gmeta', text: [g.area, `${g.members.length} member${g.members.length === 1 ? '' : 's'}`].filter(Boolean).join(' · ') }))),
    h('div', { class: 'group-tabs' }, segmented([['chat', 'Chat'], ['reading', 'Reading'], ['members', 'Members']], tab,
      (v) => go(`#/groups/${gid}?tab=${v}`, { replace: true }))),
    area);
  if (tab === 'reading') return readingTab(area, g, me, reload);
  if (tab === 'members') return membersTab(area, g, me, reload);
  return chatTab(area, g, me);
}
