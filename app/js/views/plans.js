// Reading plans: pick one, see every day, tick days off. Progress is
// personal and stays on this device (a study group can follow a plan
// together; see community.js).

import * as api from '../api.js';
import * as store from '../store.js';
import { readHash } from '../bible.js';
import { dayNumber, todayISO, addDays, fmtDate, streak } from '../dates.js';
import { h, icon, sheet, toast, loading, errorBox, progressBar, confirmSheet } from '../ui.js';
import { go } from '../main.js';
import { segLabel } from './today.js';

function perDay(p) {
  return (p.chapters / p.length).toFixed(1).replace(/\.0$/, '');
}

export function startPlanSheet(p, { onStart } = {}) {
  const sh = sheet(`Start “${p.title}”`);
  const date = h('input', { class: 'input', type: 'date', value: todayISO(), required: true });
  sh.body.append(
    h('p', { class: 'muted', text: `${p.length} days, about ${perDay(p)} chapters a day. You can tick days off in any order and catch up whenever you like.` }),
    h('form', { class: 'form', on: { submit: (e) => {
      e.preventDefault();
      if (!date.value) return;
      if (onStart) onStart(date.value);
      else {
        store.startPlan(p.id, date.value);
        toast('Plan started');
        go('#/today');
      }
      sh.close();
    } } },
    h('label', { class: 'field' }, h('span', { text: 'Start date' }), date),
    h('button', { class: 'btn primary', type: 'submit' }, icon('calendar'), 'Start plan')));
}

async function renderList(root) {
  const page = h('div', { class: 'page wide' },
    h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Reading plans' }),
      h('h1', { text: 'Read with a rhythm' }),
      h('p', { class: 'sub', text: 'Each day is about the same amount of reading. Your progress stays on this device; to read a plan with others, start a study group.' })),
    loading());
  root.append(page);
  let plans;
  try { plans = await api.plans(); } catch (e) { page.lastChild.replaceWith(errorBox(e, () => go(location.hash))); return; }
  const mine = store.plan();
  const active = mine && plans.find((p) => p.id === mine.id);
  const parts = [];
  if (active) {
    const n = dayNumber(mine.start);
    const done = mine.done.length;
    parts.push(h('section', { class: 'card active-plan' },
      h('div', { class: 'card-head' }, icon('calendar'), h('span', { class: 'label', text: 'Your plan' })),
      h('h2', { text: active.title }),
      h('p', { class: 'muted', text: n < 1 ? `Starts ${fmtDate(mine.start)}`
        : n > active.length ? 'Finished' : `Day ${n} of ${active.length} · ${done} day${done === 1 ? '' : 's'} read` }),
      progressBar(done / active.length),
      h('div', { class: 'row wrap' },
        h('a', { class: 'btn primary sm', href: `#/plans/${active.id}` }, 'Open plan'),
        h('span', { class: 'spacer' }),
        h('button', { class: 'btn ghost sm', type: 'button', on: { click: async () => {
          if (await confirmSheet('Stop this plan?', 'Your ticked-off days for this plan will be cleared.', { ok: 'Stop plan', danger: true })) {
            store.stopPlan();
            go('#/plans', { replace: true });
          }
        } } }, 'Stop plan'))));
  }
  parts.push(h('div', { class: 'plans-grid' }, plans.map((p) => h('article', { class: `card plan-card${active && active.id === p.id ? ' active' : ''}` },
    h('h3', { text: p.title }),
    h('div', { class: 'meta' }, h('span', { class: 'pill', text: `${p.length} days` }), h('span', { class: 'pill', text: `~${perDay(p)} chapters a day` })),
    h('p', { text: p.summary }),
    h('div', { class: 'row' },
      h('a', { class: 'btn ghost sm', href: `#/plans/${p.id}` }, 'Preview'),
      h('span', { class: 'spacer' }),
      active && active.id === p.id ? h('span', { class: 'pill pd', text: 'Following' })
        : h('button', { class: 'btn sm', type: 'button', on: { click: async () => {
          if (active && !(await confirmSheet('Switch plans?', `You're following “${active.title}”. Switching clears its progress.`, { ok: 'Switch' }))) return;
          startPlanSheet(p);
        } } }, 'Start'))))));
  page.lastChild.replaceWith(...parts);
}

async function renderPlan(root, id) {
  const page = h('div', { class: 'page' }, loading());
  root.append(page);
  let p;
  try { p = await api.planDetail(id); } catch (e) { page.replaceChildren(errorBox(e, () => go(location.hash))); return; }
  const s = store.settings();
  const t = (store.load('last', null) || {}).t || s.translation;
  const mine = store.plan();
  const following = mine && mine.id === p.id;
  const n = following ? dayNumber(mine.start) : 0;
  const done = new Set(following ? mine.done : []);

  const head = h('header', { class: 'page-head' },
    h('a', { class: 'btn ghost sm', href: '#/plans' }, icon('chevL'), 'All plans'),
    h('h1', { text: p.title }),
    h('p', { class: 'sub', text: p.summary }));
  if (following) {
    const st = streak(mine.done, n);
    head.append(h('div', { class: 'row wrap', }, h('span', { class: 'muted', text: `${done.size} of ${p.length} days read` }),
      st > 1 ? h('span', { class: 'streak' }, icon('flame'), `${st}-day streak`) : null));
    head.append(progressBar(done.size / p.length));
  } else {
    head.append(h('button', { class: 'btn primary', type: 'button', on: { click: () => startPlanSheet(p) } }, icon('calendar'), 'Start this plan'));
  }

  const list = h('div', { class: 'days' });
  p.days.forEach((segs, i) => {
    const day = i + 1;
    const date = following ? addDays(mine.start, i) : null;
    const isDone = done.has(day);
    const check = following ? h('button', { class: `check${isDone ? ' on' : ''}`, type: 'button',
      'aria-pressed': String(isDone), 'aria-label': `Day ${day} read` }, icon('check')) : h('span');
    if (following) {
      check.addEventListener('click', () => {
        const on = !check.classList.contains('on');
        store.setDayDone(day, on);
        check.classList.toggle('on', on);
        check.setAttribute('aria-pressed', String(on));
        row.classList.toggle('done', on);
      });
    }
    const row = h('div', { class: `day${day === n ? ' today' : ''}${isDone ? ' done' : ''}`, id: `day-${day}` },
      h('div', { class: 'day-n' }, String(day), date ? h('small', { text: fmtDate(date, { day: 'numeric', month: 'short' }) }) : null),
      h('div', { class: 'day-segs' }, segs.map((sg) => h('a', { href: readHash({ t, b: sg[0], c: sg[1] }), text: segLabel(sg) }))),
      check);
    list.append(row);
  });
  page.replaceChildren(head, list);
  if (following && n >= 1 && n <= p.length) {
    requestAnimationFrame(() => document.getElementById(`day-${n}`)?.scrollIntoView({ block: 'center' }));
  }
}

export async function render(root, r) {
  if (r.path[0]) await renderPlan(root, r.path[0]);
  else await renderList(root);
  return null;
}
