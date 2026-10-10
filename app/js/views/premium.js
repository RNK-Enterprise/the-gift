// Plans: Free, Plus, Premium, and Church (contact us). Buying goes through
// Google Play inside the Android app and Stripe on the web; the server
// checks every purchase with the provider before anything unlocks.

import * as api from '../api.js';
import * as store from '../store.js';
import * as sync from '../sync.js';
import { h, icon, toast, loading, errorBox, sheet, confirmSheet } from '../ui.js';
import { go, segmented } from '../main.js';
import { authForms } from './community.js';
import { ago } from '../dates.js';

const PLANS = [
  { id: 'free', name: 'Free', price: { month: 'Free', year: 'Free' },
    features: ['139 Bible translations (116 in the Play app)', 'Daily devotional and reading plans', 'Private journal on this device',
      'Join study groups and chat', 'Lead 2 groups of up to 30', 'Matthew Henry (Concise) and cross-references', 'Hymns and artists'] },
  { id: 'plus', name: 'Plus', price: { month: '$1.99 / month', year: '$19.99 / year' },
    features: ['Everything in Free', 'Sync & backup across your devices', 'Journal encrypted before it leaves your device', 'Offline Bibles'] },
  { id: 'premium', name: 'Premium', price: { month: '$4.99 / month', year: '$49.99 / year' }, best: true,
    features: ['Everything in Plus', 'All 12 commentaries and cross-references', 'Bible dictionaries & Strong’s', 'Lead 20 groups of up to 150', 'Artist pro: 100 songs and listening stats'] },
];
const PLAY_PRODUCTS = { plus: { month: 'plus_monthly', year: 'plus_yearly' }, premium: { month: 'premium_monthly', year: 'premium_yearly' } };

async function playService() {
  if (!('getDigitalGoodsService' in window)) return null;
  try { return await window.getDigitalGoodsService('https://play.google.com/billing'); } catch { return null; }
}

async function buyOnPlay(product) {
  const req = new PaymentRequest([{ supportedMethods: 'https://play.google.com/billing', data: { sku: product } }],
    { total: { label: 'Total', amount: { currency: 'USD', value: '0' } } });
  const res = await req.show();
  try {
    await api.post('billing/play/verify', { product, token: res.details.purchaseToken });
    await res.complete('success');
    return true;
  } catch (e) {
    await res.complete('fail');
    throw e;
  }
}

function planCard(p, current, period, onBuy) {
  const isCurrent = current === p.id;
  return h('article', { class: `card plan-tier${p.best ? ' best' : ''}${isCurrent ? ' current' : ''}`, dataset: { plan: p.id } },
    p.best ? h('span', { class: 'pill pd tier-flag', text: 'Most loved' }) : null,
    h('h3', { text: p.name }),
    h('p', { class: 'tier-price', text: p.price[period] }),
    h('ul', { class: 'feature-list' }, p.features.map((f) => h('li', {}, icon('check'), h('span', { text: f })))),
    isCurrent ? h('span', { class: 'btn block', text: 'Your plan' })
      : p.id === 'free' ? null
        : h('button', { class: `btn block ${p.best ? 'primary' : ''}`, type: 'button', on: { click: () => onBuy(p.id) } }, `Get ${p.name}`));
}

function churchForm() {
  const f = (name, label, attrs = {}) => {
    const input = h(attrs.textarea ? 'textarea' : 'input', { class: attrs.textarea ? 'textarea' : 'input', name, ...attrs, textarea: null });
    return [input, h('label', { class: 'field' }, h('span', { text: label }), input)];
  };
  const [name, nameF] = f('name', 'Your name', { required: true, maxlength: 80 });
  const [church, churchF] = f('church', 'Church or ministry', { required: true, maxlength: 120 });
  const [role, roleF] = f('role', 'Your role', { maxlength: 60, placeholder: 'e.g. Pastor, small-groups lead' });
  const [size, sizeF] = f('size', 'Roughly how many people', { maxlength: 40, placeholder: 'e.g. 250' });
  const [email, emailF] = f('email', 'Email', { required: true, type: 'email', maxlength: 120 });
  const [phone, phoneF] = f('phone', 'Phone (optional)', { type: 'tel', maxlength: 40 });
  const [message, messageF] = f('message', 'What would help your congregation?', { textarea: true, rows: 3, maxlength: 2000 });
  const err = h('p', { class: 'form-error', role: 'alert' });
  const form = h('form', { class: 'form', on: { submit: async (e) => {
    e.preventDefault();
    err.textContent = '';
    try {
      await api.post('contact/church', { name: name.value, church: church.value, role: role.value, size: size.value,
        email: email.value, phone: phone.value, message: message.value });
      form.replaceChildren(h('div', { class: 'empty' }, h('h3', { text: 'Thank you!' }), h('p', { text: 'We’ll be in touch about a plan for your church.' })));
    } catch (ex) { err.textContent = ex.message; }
  } } }, nameF, churchF, h('div', { class: 'split' }, roleF, sizeF), emailF, phoneF, messageF,
  h('p', { class: 'muted small', text: 'We use these details only to reply about a church plan.' }),
  err, h('button', { class: 'btn primary', type: 'submit' }, 'Contact us'));
  return form;
}

// ---------------------------------------------------------- offline Bibles

const OFFLINE = 'gift-offline';

async function downloadTranslation(t, onProgress) {
  const data = await api.get('download', { t });
  const cache = await caches.open(OFFLINE);
  const json = (obj) => new Response(JSON.stringify(obj), { headers: { 'Content-Type': 'application/json' } });
  const books = [];
  let i = 0;
  for (const ch of data.chapters) {
    await cache.put(`/api/chapter?${new URLSearchParams({ t, b: ch.book, c: ch.chapter })}`, json(ch));
    const last = books[books.length - 1];
    if (last && last.name === ch.book) last.chapters.push(ch.chapter); else books.push({ name: ch.book, chapters: [ch.chapter] });
    i += 1;
    if (i % 100 === 0) onProgress(i / data.chapters.length);
  }
  const meta = (await api.translations()).find((x) => x.id === t) || { id: t, title: data.title };
  await cache.put(`/api/books?${new URLSearchParams({ t })}`, json({ ...meta, books }));
  const list = store.load('offline', []).filter((x) => x.t !== t);
  list.push({ t, title: data.title, at: Date.now(), chapters: data.chapters.length });
  store.save('offline', list);
}

async function removeTranslation(t) {
  const cache = await caches.open(OFFLINE);
  for (const req of await cache.keys()) {
    if (new URL(req.url).searchParams.get('t') === t) await cache.delete(req);
  }
  store.save('offline', store.load('offline', []).filter((x) => x.t !== t));
}

function offlineSection(rank) {
  const box = h('section', { class: 'card stack' }, h('div', { class: 'card-head' }, icon('download'), h('span', { class: 'label', text: 'Offline Bibles' })));
  if (!('caches' in window) || !window.isSecureContext) {
    box.append(h('p', { class: 'muted', text: 'Offline reading needs the installed app or a secure (https) connection.' }));
    return box;
  }
  if (rank < 1) {
    box.append(h('p', { class: 'muted', text: 'Download whole translations and read with no connection. Part of Plus and Premium.' }));
    return box;
  }
  const t = (store.load('last', null) || {}).t || store.settings().translation;
  const list = h('div', { class: 'list' });
  const draw = () => {
    const items = store.load('offline', []);
    list.replaceChildren(...(items.length ? items.map((x) => h('div', { class: 'song-row' }, icon('book'),
      h('div', { class: 'song-text' }, h('b', { text: `${x.t} · ${x.title}` }), h('small', { class: 'muted', text: `${x.chapters} chapters · saved ${ago(x.at)}` })),
      h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Remove ${x.t}`, on: { click: async () => { await removeTranslation(x.t); draw(); } } }, icon('trash'))))
      : [h('p', { class: 'muted small', style: null, text: 'Nothing downloaded yet.' })]));
  };
  const btn = h('button', { class: 'btn primary', type: 'button' }, icon('download'), `Download ${t}`);
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      await downloadTranslation(t, (f) => { btn.textContent = `Saving… ${Math.round(f * 100)}%`; });
      toast(`${t} is ready offline`);
      draw();
    } catch (e) { toast(e.message); } finally { btn.disabled = false; btn.replaceChildren(icon('download'), `Download ${t}`); }
  });
  draw();
  box.append(h('p', { class: 'muted small', text: 'Choose a translation in the Bible tab, then download it here.' }), btn, list);
  return box;
}

function syncSection(rank, user) {
  const box = h('section', { class: 'card stack' }, h('div', { class: 'card-head' }, icon('shield'), h('span', { class: 'label', text: 'Sync & backup' })));
  if (rank < 1) {
    box.append(h('p', { class: 'muted', text: 'Your journal, highlights, bookmarks and plan on every device you sign in to. Journal entries are encrypted on your device first. Part of Plus and Premium.' }));
    return box;
  }
  const line = h('p', { class: 'muted' });
  const unlock = h('div');
  const draw = async () => {
    const st = sync.status();
    line.textContent = st.last ? `Last synced ${ago(st.last)}${st.pending ? ` · ${st.pending} waiting` : ''}` : 'Not synced yet';
    unlock.replaceChildren();
    if (!(await sync.hasKey()) || st.locked) {
      const pw = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', placeholder: 'Your password' });
      unlock.append(h('p', { class: 'small', text: 'Enter your password to unlock your encrypted journal on this device.' }),
        h('form', { class: 'row', on: { submit: async (e) => {
          e.preventDefault();
          try {
            await api.post('me/verify', { password: pw.value });
            await sync.rememberKey(user.username, pw.value);
            await sync.syncNow();
            toast('Journal unlocked');
            draw();
          } catch (ex) { toast(ex.message); }
        } } }, pw, h('button', { class: 'btn', type: 'submit' }, 'Unlock')));
    }
  };
  draw();
  box.append(line, unlock, h('button', { class: 'btn sm', type: 'button', on: { click: async () => { await sync.syncNow(); draw(); } } }, 'Sync now'));
  return box;
}

export async function render(root, r) {
  let period = 'year';
  const page = h('div', { class: 'page' },
    h('header', { class: 'page-head center' }, h('img', { class: 'premium-logo', src: '/app/img/logo.jpg', alt: '' }),
      h('p', { class: 'eyebrow', text: 'Plans' }), h('h1', { text: 'Grow deeper' }),
      h('p', { class: 'sub', style: null, text: 'Reading the Bible, the devotional, plans and groups are free, always. Plus and Premium add tools for going further, and keep this work going.' })),
    loading());
  root.append(page);
  const user = await api.currentUser();
  const status = user ? await api.plan(true) : { tier: 'free' };
  const rank = api.tierRank(status.tier);
  if (r.params.get('paid')) toast('Thank you! Your plan is being confirmed.');
  const play = api.channel === 'play' ? await playService() : null;

  const buy = async (planId) => {
    if (!user) { toast('Sign in first'); go('#/me'); return; }
    try {
      if (api.channel === 'play') {
        if (!play) { toast('Google Play billing isn’t available on this device.'); return; }
        if (await buyOnPlay(PLAY_PRODUCTS[planId][period])) { toast('Welcome to ' + planId[0].toUpperCase() + planId.slice(1)); go('#/premium', { replace: true }); }
      } else {
        const { url } = await api.post('billing/stripe/checkout', { plan: planId, period });
        location.href = url;
      }
    } catch (e) { toast(e.message); }
  };

  const cards = h('div', { class: 'plan-tiers' });
  const drawCards = () => cards.replaceChildren(...PLANS.map((p) => planCard(p, status.tier, period, buy)));
  drawCards();
  if (play) { // real, localized prices from Google Play
    try {
      const details = await play.getDetails(Object.values(PLAY_PRODUCTS).flatMap((x) => Object.values(x)));
      for (const d of details) {
        for (const p of PLANS) for (const per of ['month', 'year']) {
          if (PLAY_PRODUCTS[p.id] && PLAY_PRODUCTS[p.id][per] === d.itemId) {
            p.price[per] = `${new Intl.NumberFormat(undefined, { style: 'currency', currency: d.price.currency }).format(Number(d.price.value))} / ${per}`;
          }
        }
      }
      drawCards();
    } catch { /* keep the listed prices */ }
  }

  const manage = user && rank > 0 ? h('section', { class: 'card' },
    h('div', { class: 'card-head' }, icon('crown'), h('span', { class: 'label', text: 'Your plan' })),
    h('h2', { text: status.tier === 'premium' ? 'Premium' : 'Plus' }),
    ...status.subscriptions.filter((s) => s.period_end * 1000 > Date.now()).slice(0, 1).map((s) => h('p', { class: 'muted',
      text: `${s.status === 'canceling' ? 'Ends' : 'Renews'} ${new Date(s.period_end * 1000).toLocaleDateString()} · ${s.provider === 'play' ? 'Google Play' : s.provider === 'stripe' ? 'card' : 'gift'}` })),
    status.subscriptions.some((s) => s.provider === 'stripe') && api.channel !== 'play'
      ? h('button', { class: 'btn sm', type: 'button', on: { click: async () => {
        try { location.href = (await api.post('billing/stripe/portal')).url; } catch (e) { toast(e.message); }
      } } }, 'Manage billing')
      : status.subscriptions.some((s) => s.provider === 'play')
        ? h('a', { class: 'btn sm', href: 'https://play.google.com/store/account/subscriptions', target: '_blank', rel: 'noopener' }, 'Manage on Google Play') : null) : null;

  page.lastChild.replaceWith(h('div', { class: 'stack' },
    manage,
    h('div', { class: 'center' }, segmented([['month', 'Monthly'], ['year', 'Yearly · save ~16%']], period, (v) => { period = v; drawCards(); })),
    cards,
    !user ? h('p', { class: 'muted center small', text: 'Sign in (from Me) before choosing a plan.' }) : null,
    user ? syncSection(rank, user) : null,
    user ? offlineSection(rank) : null,
    h('section', { class: 'card stack church' },
      h('div', { class: 'card-head' }, icon('users'), h('span', { class: 'label', text: 'For churches' })),
      h('h2', { text: 'A plan for your congregation' }),
      h('p', { class: 'muted', text: 'Premium for everyone in your church, groups set up for your small groups and ministries, and someone to help you get started. Tell us about your church and we’ll put a plan together.' }),
      churchForm()),
    h('p', { class: 'muted small center', text: api.channel === 'play' ? 'Subscriptions are billed by Google Play and renew until cancelled.' : 'Card payments by Stripe. Subscriptions renew until cancelled; cancel any time.' }),
    h('p', { class: 'center small' }, h('a', { href: '/app/legal/terms.html' }, 'Terms'), ' · ', h('a', { href: '/app/legal/privacy.html' }, 'Privacy'))));
  return null;
}
