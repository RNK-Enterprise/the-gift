// Today: the daily devotional, today's plan reading, and ways back in.

import * as api from '../api.js';
import * as store from '../store.js';
import { bookName, readHash, refLabel } from '../bible.js';
import { dayNumber, fmtDate, monthDay, streak } from '../dates.js';
import { h, icon, loading, ring, toast } from '../ui.js';
import { segmented } from '../main.js';
import * as progress from '../progress.js';

export function segLabel([book, from, to]) {
  return from === to ? refLabel({ b: book, c: from }) : `${bookName(book)} ${from}–${to}`;
}

export function readingLinks(segs, t) {
  return h('ul', { class: 'reading-list' }, segs.map((s) =>
    h('li', {}, h('a', { href: readHash({ t, b: s[0], c: s[1] }) }, icon('book'), h('span', { text: segLabel(s) }),
      h('span', { class: 'spacer' }), icon('chevR')))));
}

function runs(block, t) {
  const out = [];
  for (const r of block) {
    if (r.br) out.push(h('br'));
    else if (r.ref) out.push(h('a', { href: readHash({ t, b: r.ref.b, c: r.ref.c, v: r.ref.v }), text: r.t }));
    else if (r.i) out.push(h('em', { text: r.t }));
    else out.push(r.t);
  }
  return out;
}

function devotionalCard(t) {
  const card = h('section', { class: 'card devo', 'aria-label': 'Daily devotional' }, loading());
  const hour = new Date().getHours();
  let slot = hour >= 15 || hour < 4 ? 'evening' : 'morning';

  api.devotional(monthDay()).then((entry) => {
    const content = h('div');
    const fill = () => {
      const sec = entry[slot] || entry.morning || entry.evening;
      const body = h('div', { class: 'devo-body clamped' }, sec.blocks.map((b) => (b.p
        ? h('p', {}, runs(b.p, t))
        : h('div', { class: 'poem' }, b.poem.map((line) => h('div', {}, runs(line, t)))))));
      const more = h('button', { class: 'btn ghost sm', type: 'button' }, 'Keep reading', icon('chevD'));
      more.addEventListener('click', () => { body.classList.remove('clamped'); more.remove(); });
      const journalParams = new URLSearchParams({ prompt: sec.title });
      if (sec.verse) {
        journalParams.set('b', sec.verse.ref.b);
        journalParams.set('c', sec.verse.ref.c);
        if (sec.verse.ref.v) journalParams.set('v', sec.verse.ref.v);
        journalParams.set('t', t);
      }
      content.replaceChildren(...[
        h('p', { class: 'devo-title', text: sec.title }),
        sec.verse ? h('blockquote', { class: 'devo-verse' }, sec.verse.text) : null,
        sec.verse ? h('a', { class: 'devo-ref', href: readHash({ t, ...sec.verse.ref }) }, sec.verse.label, ' →') : null,
        body,
        h('div', { class: 'row wrap devo-foot' }, more, h('span', { class: 'spacer' }),
          h('a', { class: 'btn sm', href: `#/journal/new?${journalParams}` }, icon('pen'), 'Reflect in journal')),
        h('p', { class: 'source', text: "C. H. Spurgeon, Morning and Evening (1865) · public domain" })].filter(Boolean));
    };
    card.replaceChildren(
      h('div', { class: 'card-head' }, icon(slot === 'evening' ? 'moon' : 'sun'), h('span', { class: 'label', text: 'Devotional' }),
        h('span', { class: 'spacer' }),
        segmented([['morning', 'Morning'], ['evening', 'Evening']], slot, (v) => {
          slot = v;
          card.querySelector('.card-head .i').replaceWith(icon(v === 'evening' ? 'moon' : 'sun'));
          fill();
        })),
      content);
    fill();
  }).catch((e) => {
    card.replaceChildren(h('div', { class: 'card-head' }, icon('sun'), h('span', { class: 'label', text: 'Devotional' })),
      h('p', { class: 'muted', text: e.status === 0 ? "Today's devotional isn't available offline yet." : e.message }));
  });
  return card;
}

export function planCard(t, { compact = false } = {}) {
  const p = store.plan();
  if (!p) {
    return h('a', { class: 'card link', href: '#/plans' },
      h('div', { class: 'card-head' }, icon('calendar'), h('span', { class: 'label', text: 'Reading plan' })),
      h('h2', { text: 'Read the whole Bible this year' }),
      h('p', { class: 'muted', text: 'Or the Gospels in 30 days, or Psalms in a month. Pick a plan and The Gift keeps your place.' }),
      h('span', { class: 'btn primary sm' }, 'Choose a plan'));
  }
  const card = h('section', { class: 'card', 'aria-label': 'Reading plan' }, loading());
  api.planDetail(p.id).then((plan) => {
    const n = dayNumber(p.start);
    const doneCount = p.done.length;
    const head = h('div', { class: 'card-head' }, icon('calendar'), h('span', { class: 'label', text: "Today's reading" }),
      h('span', { class: 'spacer' }), h('a', { class: 'btn ghost sm', href: `#/plans/${plan.id}` }, 'Plan'));
    if (n < 1) {
      card.replaceChildren(head, h('h2', { text: plan.title }),
        h('p', { class: 'muted', text: `Starts ${fmtDate(p.start, { weekday: 'long', day: 'numeric', month: 'long' })}.` }));
      return;
    }
    if (n > plan.length) {
      card.replaceChildren(head, h('h2', { text: `${plan.title} — finished` }),
        h('p', { class: 'muted', text: `You marked ${doneCount} of ${plan.length} days as read.` }),
        h('a', { class: 'btn sm', href: '#/plans' }, 'Choose another plan'));
      return;
    }
    const isDone = p.done.includes(n);
    const behind = Array.from({ length: n - 1 }, (_, i) => i + 1).filter((d) => !p.done.includes(d)).length;
    const st = streak(p.done, n);
    const mark = h('button', { class: `btn ${isDone ? '' : 'primary'} sm`, type: 'button' },
      icon('check'), isDone ? 'Read today' : 'Mark as read');
    mark.addEventListener('click', () => {
      store.setDayDone(n, !isDone);
      if (!isDone) { // the day's chapters count toward Bible progress too
        const chapters = [];
        for (const [book, from, to] of plan.days[n - 1]) for (let c = from; c <= to; c += 1) chapters.push([book, c]);
        progress.mark(chapters, true);
      }
      if (!isDone) toast(n === plan.length ? 'Plan complete. Well done!' : `Day ${n} done`);
      card.replaceWith(planCard(t, { compact }));
    });
    card.replaceChildren(head,
      h('div', { class: 'plan-top' }, ring(doneCount / plan.length, `${Math.round((doneCount / plan.length) * 100)}%`),
        h('div', {}, h('h2', { text: plan.title }),
          h('div', { class: 'row wrap' }, h('span', { class: 'muted', text: `Day ${n} of ${plan.length}` }),
            st > 1 ? h('span', { class: 'streak' }, icon('flame'), `${st}-day streak`) : null))),
      readingLinks(plan.days[n - 1], t),
      h('div', { class: 'row wrap devo-foot' },
        behind ? h('a', { class: 'muted small', href: `#/plans/${plan.id}` }, `${behind} earlier day${behind > 1 ? 's' : ''} to catch up`) : null,
        h('span', { class: 'spacer' }), mark));
  }).catch((e) => card.replaceChildren(h('p', { class: 'muted', text: e.message })));
  return card;
}

function countLine() {
  const p = h('p', { class: 'muted', text: 'Free translations in dozens of languages.' });
  api.translations().then((all) => {
    const usable = all.filter((t) => t.ot + t.nt + t.other > 0);
    const langs = new Set(usable.map((t) => t.lang)).size;
    p.textContent = `${usable.length} translations in ${langs} languages, free to read.`;
  }).catch(() => {});
  return p;
}

export async function render(root) {
  const s = store.settings();
  const last = store.load('last', null);
  const t = (last && last.t) || s.translation;
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 4 ? 'Good evening' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const user = await api.currentUser();

  const quick = h('div', { class: 'quick' },
    h('a', { class: 'card link', href: '#/community' }, icon('users'),
      h('h3', { text: 'Study together' }), h('p', { text: user ? 'Your groups and chat' : 'Start a private group' })),
    h('a', { class: 'card link', href: '#/churches' }, icon('pin'),
      h('h3', { text: 'Find a church' }), h('p', { text: 'Churches near you' })),
    h('a', { class: 'card link', href: `#/search?t=${encodeURIComponent(t)}` }, icon('search'),
      h('h3', { text: 'Search' }), h('p', { text: 'Words or a reference' })),
    h('a', { class: 'card link', href: '#/journal/new' }, icon('pen'),
      h('h3', { text: 'Write' }), h('p', { text: 'A private journal entry' })));

  const cont = last ? h('a', { class: 'card link', href: readHash(last) },
    h('div', { class: 'card-head' }, icon('book'), h('span', { class: 'label', text: 'Continue reading' })),
    h('h2', { text: refLabel({ b: last.b, c: last.c }) }),
    h('p', { class: 'muted', text: last.t })) : h('a', { class: 'card link', href: '#/read' },
    h('div', { class: 'card-head' }, icon('book'), h('span', { class: 'label', text: 'Start reading' })),
    h('h2', { text: 'In the beginning' }),
    countLine());

  root.append(h('div', { class: 'page wide' },
    h('header', { class: 'hero' }, h('img', { class: 'hero-dawn', src: '/app/img/dawn.svg', alt: '' }),
      h('p', { class: 'date', text: now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' }) }),
      h('h1', { text: user ? `${greeting}, ${user.name.split(' ')[0]}` : greeting })),
    h('div', { class: 'today-grid' },
      devotionalCard(t),
      h('div', { class: 'col stack' }, planCard(t), cont, quick))));
}

