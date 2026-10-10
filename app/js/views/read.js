// The reader: one chapter at a time, optionally side by side with a second
// translation, plus search. Tap verses to highlight, bookmark, copy, journal
// or share them with a study group.

import * as api from '../api.js';
import * as store from '../store.js';
import {
  bookName, refLabel, versesLabel, readHash, parseRef, testament, languageName,
  LICENCE_CLASS, coverage, markMatches, queryTerms,
} from '../bible.js';
import { h, icon, sheet, toast, loading, errorBox, copyText, autoGrow } from '../ui.js';
import { go, openSettings } from '../main.js';
import * as progress from '../progress.js';

const COLORS = [['y', 'Yellow'], ['g', 'Green'], ['b', 'Blue'], ['p', 'Pink']];

function hashFor({ t, b, c, v, p }) {
  const params = new URLSearchParams({ t, b, c });
  if (v) params.set('v', v);
  if (p) params.set('p', p);
  return `#/read?${params}`;
}

async function usableTranslations() {
  const all = await api.translations();
  return all.filter((x) => x.ot + x.nt + x.other > 0);
}

async function translationMeta(id) {
  const all = await usableTranslations();
  return all.find((x) => x.id === id) || all.find((x) => x.id === 'KJV') || all[0];
}

// ------------------------------------------------------------------ pickers

export async function pickTranslation(currentId, { title = 'Translation', allowNone = false } = {}) {
  const all = await api.translations();
  return new Promise((resolve) => {
    let picked;
    const sh = sheet(title, { tall: true, onClose: () => resolve(picked) });
    const filter = h('input', { class: 'input', type: 'search', placeholder: 'Filter by name or language', 'aria-label': 'Filter translations' });
    const list = h('div', { class: 'tlist' });
    const usable = all.filter((x) => x.ot + x.nt + x.other > 0);
    const empty = all.filter((x) => x.ot + x.nt + x.other === 0);
    const groups = new Map();
    for (const t of usable) {
      const lang = languageName(t.lang);
      if (!groups.has(lang)) groups.set(lang, []);
      groups.get(lang).push(t);
    }
    const order = [...groups.keys()].sort((a, b) => (a === 'English' ? -1 : b === 'English' ? 1 : a.localeCompare(b)));
    const choose = (id) => { picked = id; sh.close(); };

    const draw = () => {
      const q = filter.value.trim().toLowerCase();
      const parts = [];
      if (allowNone && !q) {
        parts.push(h('button', { class: `titem${!currentId ? ' on' : ''}`, type: 'button', on: { click: () => choose('') } },
          h('span', { class: 'tid' }, '—'), h('span', { class: 'ttitle', text: 'No comparison' }),
          h('span', { class: 'tmeta', text: 'Read one translation' })));
      }
      for (const lang of order) {
        const items = groups.get(lang).filter((t) => !q || t.id.toLowerCase().includes(q)
          || t.title.toLowerCase().includes(q) || lang.toLowerCase().includes(q));
        if (!items.length) continue;
        parts.push(h('div', { class: 'tgroup' }, h('h4', { text: lang }), items.map((t) =>
          h('button', { class: `titem${t.id === currentId ? ' on' : ''}`, type: 'button', on: { click: () => choose(t.id) } },
            h('span', { class: 'tid', text: t.id }),
            h('span', { class: 'ttitle', text: t.title }),
            h('span', { class: 'tmeta' },
              t.class ? h('span', { class: `pill ${LICENCE_CLASS[t.class] || ''}`, text: t.class }) : null,
              coverage(t))))));
      }
      if (!parts.length) parts.push(h('p', { class: 'muted', text: 'No translation matches that.' }));
      if (!q && empty.length) {
        parts.push(h('p', { class: 'muted small', text: `Not readable here: ${empty.map((t) => t.id).join(', ')} — the source file has no verse text.` }));
      }
      list.replaceChildren(...parts);
    };
    filter.addEventListener('input', draw);
    sh.body.append(filter, list);
    draw();
    requestAnimationFrame(() => list.querySelector('.titem.on')?.scrollIntoView({ block: 'center' }));
  });
}

function pickPassage(bk, current) {
  return new Promise((resolve) => {
    let picked;
    const sh = sheet('Go to', { tall: true, onClose: () => resolve(picked) });
    const filter = h('input', { class: 'input', type: 'search', placeholder: 'Find a book', 'aria-label': 'Find a book' });
    const area = h('div');

    const chapters = (book) => {
      sh.setTitle(bookName(book.name));
      area.replaceChildren(
        h('button', { class: 'btn ghost sm', type: 'button', on: { click: () => { sh.setTitle('Go to'); books(); } } }, icon('chevL'), 'All books'),
        h('div', { class: 'chapters' }, book.chapters.map((c) => h('button', {
          class: `chn${book.name === current.b && c === current.c ? ' on' : ''}`, type: 'button', text: String(c),
          on: { click: () => { picked = { b: book.name, c }; sh.close(); } },
        }))));
      filter.hidden = true;
    };
    const books = () => {
      filter.hidden = false;
      const q = filter.value.trim().toLowerCase();
      const sections = [['ot', 'Old Testament'], ['nt', 'New Testament'], ['other', 'More books']];
      const parts = [];
      for (const [key, label] of sections) {
        const items = bk.books.filter((x) => testament(x.name) === key
          && (!q || bookName(x.name).toLowerCase().includes(q) || x.name.toLowerCase().includes(q)));
        if (!items.length) continue;
        parts.push(h('div', { class: 'sheet-section' }, h('h4', { text: label }),
          h('div', { class: 'books' }, items.map((x) => h('button', {
            class: `book${x.name === current.b ? ' on' : ''}`, type: 'button', text: bookName(x.name),
            on: { click: () => (x.chapters.length === 1 ? (picked = { b: x.name, c: x.chapters[0] }, sh.close()) : chapters(x)) },
          })))));
      }
      area.replaceChildren(...(parts.length ? parts : [h('p', { class: 'muted', text: 'No book matches that.' })]));
    };
    filter.addEventListener('input', books);
    filter.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); area.querySelector('.book')?.click(); }
    });
    sh.body.append(filter, area);
    books();
  });
}

// ----------------------------------------------------------------- study

function noteRuns(runs, t, close) {
  return runs.map((r) => {
    if (r.br) return h('br');
    if (r.ref) {
      return h('a', { href: readHash({ t, b: r.ref.b, c: r.ref.c, v: r.ref.v }), text: r.t, on: { click: close } });
    }
    const tag = r.s ? 'sup' : r.b ? 'strong' : r.i ? 'em' : null;
    return tag ? h(tag, { text: r.t }) : r.t;
  });
}

// Commentaries and cross-references for one verse, with a verse stepper.
export async function openStudy({ t, b, c, v, verses }) {
  let all;
  try { all = await api.commentaries(); } catch (e) { toast(e.message); return; }
  const premium = api.tierRank((await api.plan()).tier) >= 2; // the server checks again; this just saves a trip
  const side = testament(b) === 'nt' ? 'nt' : 'ot';
  const mods = all.filter((m) => m[side]);
  if (!mods.length) { toast('No study notes for this book'); return; }
  const DICT = { id: 'dictionary', name: 'Dictionary', premium: true };
  const saved = store.settings().commentary;
  let current = mods.find((m) => m.id === saved && (premium || !m.premium)) || mods.find((m) => !m.premium) || mods[0];
  let verse = v;
  const sh = sheet('Study', { tall: true });
  const chips = h('div', { class: 'chips', role: 'tablist' });
  const stepLabel = h('span', { class: 'step-label' });
  const prev = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Previous verse' }, icon('chevL'));
  const next = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Next verse' }, icon('chevR'));
  const body = h('div', { class: 'note' });
  const upsell = (what) => h('div', { class: 'empty' }, icon('crown'), h('h3', { text: `${what} is part of Premium` }),
    h('p', { text: 'Premium opens all 12 commentaries, the cross-references and the Bible dictionaries.' }),
    h('a', { class: 'btn primary', href: '#/premium', on: { click: () => sh.close() } }, 'See plans'));
  const drawDictionary = (word = '') => {
    const input = h('input', { class: 'input', type: 'search', value: word, placeholder: 'A word, a name, or G26 / H430', 'aria-label': 'Look up' });
    const out = h('div', { class: 'stack' });
    const lookUp = async (q) => {
      if (!q.trim()) return;
      out.replaceChildren(loading());
      try {
        const res = await api.dictionary(q.trim());
        out.replaceChildren(...(res.entries.length ? res.entries.map((e) => h('article', { class: 'stack' },
          h('p', { class: 'note-meta' }, h('b', { text: e.name }), ` · ${e.key}`),
          ...e.blocks.map((bl) => (bl.h ? h('h4', { text: bl.h }) : h('p', {}, noteRuns(bl.p, t, sh.close))))))
          : [h('p', { class: 'muted', text: `Nothing called “${q}”.` })]),
          res.suggest.length ? h('div', { class: 'chips wrap' }, res.suggest.map((w) => h('button', { class: 'chip', type: 'button', text: w, on: { click: () => { input.value = w; lookUp(w); } } }))) : null);
      } catch (e) {
        out.replaceChildren(e.status === 402 ? upsell('The dictionary') : h('p', { class: 'muted', text: e.message }));
      }
    };
    body.replaceChildren(h('form', { class: 'row', on: { submit: (e) => { e.preventDefault(); lookUp(input.value); } } },
      input, h('button', { class: 'btn', type: 'submit' }, icon('search'))), out);
    if (word) lookUp(word);
  };
  const draw = async () => {
    sh.setTitle(refLabel({ b, c, v: verse }));
    stepLabel.textContent = `Verse ${verse}`;
    prev.disabled = verse <= verses[0];
    next.disabled = verse >= verses[verses.length - 1];
    if (current === DICT) {
      for (const el of chips.children) el.classList.toggle('on', el.dataset.id === 'dictionary');
      if (premium) drawDictionary(); else body.replaceChildren(upsell('The dictionary'));
      return;
    }
    if (current.premium && !premium) {
      for (const el of chips.children) el.classList.toggle('on', el.dataset.id === current.id);
      body.replaceChildren(upsell(current.name));
      return;
    }
    for (const el of chips.children) el.classList.toggle('on', el.dataset.id === current.id);
    body.replaceChildren(loading());
    try {
      const n = await api.commentary(current.id, b, c, verse);
      const range = n.from === n.to ? `${c}:${n.from}` : `${c}:${n.from}–${n.to}`;
      body.replaceChildren(...[
        h('p', { class: 'note-meta' }, h('b', { text: n.name }), ` · on ${refLabel({ b, c })}${range.slice(String(c).length)}`),
        n.nearest ? h('p', { class: 'muted small', text: `There's no note on verse ${verse} itself, so this is the nearest one before it.` }) : null,
        ...n.blocks.map((bl) => (bl.h ? h('h4', { text: bl.h }) : h('p', {}, noteRuns(bl.p, t, sh.close)))),
        current.free ? null : h('p', { class: 'muted small', text: `${current.licence}.` }),
      ].filter(Boolean));
    } catch (e) {
      body.replaceChildren(e.status === 402 ? upsell(current.name)
        : h('p', { class: 'muted', text: e.status === 404 ? `${current.name} has no note on this verse.` : e.message }));
    }
    body.scrollTop = 0;
    sh.body.scrollTop = 0;
  };
  for (const m of [...mods, DICT]) {
    chips.append(h('button', { class: 'chip', type: 'button', role: 'tab', dataset: { id: m.id },
      on: { click: () => { current = m; if (m !== DICT) store.setSetting('commentary', m.id); draw(); } } },
    m.premium ? icon('lock') : null, m.name));
  }
  const step = (d) => {
    const i = verses.indexOf(verse) + d;
    if (i >= 0 && i < verses.length) { verse = verses[i]; draw(); }
  };
  prev.addEventListener('click', () => step(-1));
  next.addEventListener('click', () => step(1));
  sh.body.append(chips, h('div', { class: 'stepper' }, prev, stepLabel, next), body);
  draw();
  requestAnimationFrame(() => chips.querySelector('.on')?.scrollIntoView({ inline: 'center', block: 'nearest' }));
}

// --------------------------------------------------------------- sharing

async function shareToGroup(ref, label) {
  const user = await api.currentUser();
  if (!user) {
    toast('Sign in to share with a study group');
    go('#/community');
    return;
  }
  let groups;
  try { ({ groups } = await api.get('groups')); } catch (e) { toast(e.message); return; }
  if (!groups.length) {
    toast('Join or start a study group first');
    go('#/community');
    return;
  }
  const sh = sheet(`Share ${label}`);
  const note = h('textarea', { class: 'textarea', rows: 2, placeholder: 'Add a thought (optional)', maxlength: 2000 });
  autoGrow(note);
  sh.body.append(note, h('div', { class: 'stack' }, groups.map((g) =>
    h('button', { class: 'btn block', type: 'button', on: { click: async () => {
      try {
        await api.post(`groups/${g.id}/messages`, { body: note.value, ref });
        sh.close();
        toast(`Shared with ${g.name}`);
      } catch (e) { toast(e.message); }
    } } }, icon('send'), g.name))));
}

// ---------------------------------------------------------------- reader

export async function render(root, r) {
  const s = store.settings();
  const last = store.load('last', null);
  root.append(loading());

  let meta, bk;
  try {
    meta = await translationMeta(r.params.get('t') || (last && last.t) || s.translation);
    bk = await api.books(meta.id);
  } catch (e) {
    root.replaceChildren(h('div', { class: 'page' }, errorBox(e, () => go(location.hash))));
    return null;
  }
  const t = meta.id;
  const bookOf = (name) => bk.books.find((x) => x.name === name);
  let b = r.params.get('b') || (last && last.t === t ? last.b : null) || (last && last.b);
  let missing = null;
  if (b && !bookOf(b)) { missing = b; b = null; }
  if (!b) b = (bookOf('Genesis') || bookOf('Matthew') || bk.books[0]).name;
  const chapters = bookOf(b).chapters;
  let c = Number(r.params.get('c')) || (last && last.b === b ? last.c : 0) || chapters[0];
  if (!chapters.includes(c)) c = chapters.find((x) => x >= c) || chapters[chapters.length - 1];
  const v = Number(r.params.get('v')) || null;
  const p = r.params.get('p') || '';

  const canonical = hashFor({ t, b, c, v, p });
  if (location.hash !== canonical) history.replaceState(null, '', canonical);
  store.save('last', { t, b, c });

  const selected = new Set();
  let vbar = null;

  // -- top bar
  const passageBtn = h('button', { class: 'passage-btn', type: 'button', 'aria-label': 'Choose book and chapter' },
    refLabel({ b, c }), icon('chevD'));
  const transBtn = h('button', { class: 'trans-btn', type: 'button', 'aria-label': 'Choose translation' }, t, icon('chevD'));
  const compareBtn = h('button', { class: `icon-btn${p ? ' on' : ''}`, type: 'button', title: 'Compare translations', 'aria-label': 'Compare translations' }, icon('columns'));
  const searchBtn = h('a', { class: 'icon-btn', href: `#/search?t=${encodeURIComponent(t)}`, title: 'Search', 'aria-label': 'Search' }, icon('search'));
  const studyBtn = h('button', { class: 'icon-btn', type: 'button', title: 'Study notes', 'aria-label': 'Study notes' }, icon('study'));
  const typeBtn = h('button', { class: 'icon-btn', type: 'button', title: 'Text settings', 'aria-label': 'Text settings', on: { click: openSettings } }, icon('type'));
  const bar = h('div', { class: 'rbar' }, passageBtn, transBtn, h('span', { class: 'spacer' }), studyBtn, compareBtn, searchBtn, typeBtn);

  passageBtn.addEventListener('click', async () => {
    const to = await pickPassage(bk, { b, c });
    if (to) go(hashFor({ t, b: to.b, c: to.c, p }));
  });
  transBtn.addEventListener('click', async () => {
    const id = await pickTranslation(t);
    if (id && id !== t) { store.setSetting('translation', id); go(hashFor({ t: id, b, c, v, p: p === id ? '' : p })); }
  });
  compareBtn.addEventListener('click', async () => {
    const id = await pickTranslation(p, { title: 'Compare with', allowNone: true });
    if (id !== undefined) go(hashFor({ t, b, c, v, p: id === t ? '' : id }));
  });

  let data, par = null, parMeta = null;
  try {
    data = await api.chapter(t, b, c);
    if (p) {
      parMeta = await translationMeta(p);
      if (parMeta && parMeta.id === p) par = await api.chapter(p, b, c).catch(() => null);
      else parMeta = null;
    }
  } catch (e) {
    root.replaceChildren(bar, h('div', { class: 'page' }, errorBox(e, () => go(location.hash))));
    return null;
  }

  const verseNums = data.verses.map(([n]) => n);
  studyBtn.addEventListener('click', () => openStudy({ t, b, c, v: v && verseNums.includes(v) ? v : verseNums[0], verses: verseNums }));

  // -- the text
  const hl = store.highlights();
  const verseSpan = (n, text) => {
    const span = h('span', { class: 'v', dataset: { v: n } }, h('sup', { class: 'vn', text: String(n) }), text);
    const color = hl[`${b}|${c}|${n}`];
    if (color) span.classList.add(`hl-${color}`);
    if (store.isBookmarked(b, c, n)) span.append(h('span', { class: 'bm', 'aria-label': 'bookmarked', text: '◆' }));
    return span;
  };
  const textLang = { lang: meta.lang || null, dir: meta.dir || 'ltr' };
  const title = h('h1', { class: 'ch-title', lang: 'en', dir: 'ltr' },
    h('span', { class: 'ch-book', text: bookName(b) }), h('span', { class: 'num', text: String(c) }),
    h('span', { class: 'tname', text: meta.title }));

  let textEl;
  if (p && parMeta) {
    textEl = h('div', { class: 'compare' }, title);
    if (!par) {
      textEl.append(h('p', { class: 'muted center', text: `${parMeta.id} doesn't include ${refLabel({ b, c })}.` }));
    }
    const colHead = (m) => h('span', { title: m.title }, h('b', { text: m.id }), ` ${m.title}`);
    textEl.append(h('div', { class: 'c-head' }, h('span'), colHead(meta), par ? colHead(parMeta) : h('span')));
    const mine = new Map(data.verses);
    const theirs = new Map(par ? par.verses : []);
    const nums = [...new Set([...mine.keys(), ...theirs.keys()])].sort((x, y) => x - y);
    for (const n of nums) {
      const a = mine.has(n) ? verseSpan(n, mine.get(n)) : h('span', { class: 'c-missing', text: '—' });
      a.querySelector?.('.vn')?.remove();
      textEl.append(h('div', { class: 'c-row' }, h('span', { class: 'c-n', text: String(n) }),
        h('div', { class: 'c-a', ...textLang }, a),
        par ? h('div', { class: 'c-b', lang: parMeta.lang || null, dir: parMeta.dir || 'ltr', 'data-t': parMeta.id },
          theirs.has(n) ? theirs.get(n) : h('span', { class: 'c-missing', text: '—' })) : h('div')));
    }
  } else {
    const flow = h('div', { class: s.layout === 'lines' ? 'lines' : 'flow' });
    data.verses.forEach(([n, text], i) => {
      flow.append(verseSpan(n, text));
      if (s.layout !== 'lines' && i < data.verses.length - 1) flow.append(' ');
    });
    textEl = h('article', { class: 'scripture', ...textLang }, title, flow);
  }

  // -- verse selection
  const refreshMarks = () => {
    const hls = store.highlights();
    for (const el of textEl.querySelectorAll('.v')) {
      const n = Number(el.dataset.v);
      el.classList.toggle('sel', selected.has(n));
      for (const [k] of COLORS) el.classList.toggle(`hl-${k}`, hls[`${b}|${c}|${n}`] === k);
      const bm = el.querySelector('.bm');
      const isBm = store.isBookmarked(b, c, n);
      if (isBm && !bm) el.append(h('span', { class: 'bm', 'aria-label': 'bookmarked', text: '◆' }));
      if (!isBm && bm) bm.remove();
    }
  };
  const selectedText = () => {
    const byNum = new Map(data.verses);
    return [...selected].sort((x, y) => x - y).map((n) => byNum.get(n)).join(' ');
  };
  const closeBar = () => { selected.clear(); refreshMarks(); if (vbar) { vbar.remove(); vbar = null; } };
  const showBar = () => {
    if (vbar) vbar.remove();
    if (!selected.size) { vbar = null; return; }
    const nums = [...selected].sort((x, y) => x - y);
    const label = versesLabel(b, c, nums);
    const hls = store.highlights();
    const current = nums.every((n) => hls[`${b}|${c}|${n}`] === hls[`${b}|${c}|${nums[0]}`]) ? hls[`${b}|${c}|${nums[0]}`] : null;
    const swatches = h('div', { class: 'swatches' },
      COLORS.map(([k, name]) => h('button', { class: `swatch ${k}${current === k ? ' on' : ''}`, type: 'button',
        title: name, 'aria-label': `Highlight ${name.toLowerCase()}`,
        on: { click: () => { store.setHighlight(b, c, nums, current === k ? null : k); closeBar(); } } })),
      current ? h('button', { class: 'swatch none', type: 'button', title: 'Remove highlight', 'aria-label': 'Remove highlight',
        on: { click: () => { store.setHighlight(b, c, nums, null); closeBar(); } } }, icon('x')) : null);
    const first = nums[0], lastN = nums[nums.length - 1];
    vbar = h('div', { class: 'vbar', role: 'toolbar', 'aria-label': `Actions for ${label}` },
      h('span', { class: 'vbar-ref', text: label }),
      swatches,
      h('div', { class: 'vbar-actions' },
      h('button', { class: 'icon-btn', type: 'button', title: 'Study notes', 'aria-label': 'Study notes', on: { click: () => {
        openStudy({ t, b, c, v: first, verses: verseNums });
        closeBar();
      } } }, icon('study')),
      h('button', { class: 'icon-btn', type: 'button', title: 'Bookmark', 'aria-label': 'Bookmark', on: { click: () => {
        const added = store.toggleBookmark(b, c, first, t);
        toast(added ? 'Bookmarked' : 'Bookmark removed');
        closeBar();
      } } }, icon('bookmark')),
      h('button', { class: 'icon-btn', type: 'button', title: 'Copy', 'aria-label': 'Copy', on: { click: async () => {
        const ok = await copyText(`${selectedText()}\n— ${label} (${t})`);
        toast(ok ? 'Copied' : "Couldn't copy");
        closeBar();
      } } }, icon('copy')),
      h('a', { class: 'icon-btn', title: 'Write about this', 'aria-label': 'Write about this in your journal',
        href: `#/journal/new?${new URLSearchParams({ t, b, c, v: first, v2: lastN })}` }, icon('pen')),
      h('button', { class: 'icon-btn', type: 'button', title: 'Share with a group', 'aria-label': 'Share with a study group', on: { click: () => {
        if (lastN - first > 9) { toast('Share up to 10 verses at a time'); return; }
        shareToGroup({ t, b, c, v: first, v2: lastN }, refLabel({ b, c, v: first, v2: lastN }));
      } } }, icon('share')),
      h('button', { class: 'icon-btn', type: 'button', title: 'Close', 'aria-label': 'Clear selection', on: { click: closeBar } }, icon('x'))));
    document.body.append(vbar);
  };
  textEl.addEventListener('click', (e) => {
    const el = e.target.closest('.v');
    if (!el || e.target.closest('a')) return;
    if (window.getSelection && String(window.getSelection()).length > 2) return; // they're selecting text to copy
    const n = Number(el.dataset.v);
    if (selected.has(n)) selected.delete(n); else selected.add(n);
    refreshMarks();
    showBar();
  });

  // -- chapter navigation
  const navLink = (to, dir) => (to ? h('a', { class: dir, href: hashFor({ t, b: to[0], c: to[1], p }) },
    h('small', { text: dir === 'prev' ? 'Previous' : 'Next' }), h('b', { text: `${bookName(to[0])} ${to[1]}` })) : h('span', { class: 'gap' }));
  const nav = h('nav', { class: 'ch-nav', 'aria-label': 'Chapters' }, navLink(data.prev, 'prev'), navLink(data.next, 'next'));
  const arrows = p && parMeta ? [] : [ // compare view is full width: the bottom nav does it
    data.prev ? h('a', { class: 'side-arrow prev', href: hashFor({ t, b: data.prev[0], c: data.prev[1], p }), 'aria-label': 'Previous chapter' }, icon('chevL')) : null,
    data.next ? h('a', { class: 'side-arrow next', href: hashFor({ t, b: data.next[0], c: data.next[1], p }), 'aria-label': 'Next chapter' }, icon('chevR')) : null,
  ].filter(Boolean);

  // Bible progress: one tap at the end of the chapter (66-book canon only)
  const canon = testament(b) !== 'other';
  let markBtn = null;
  if (canon) {
    const drawMark = (on) => markBtn.replaceChildren(icon('check'), on ? 'Read ✓' : 'Mark as read');
    markBtn = h('button', { class: `btn ${progress.isRead(b, c) ? '' : 'primary'}`, type: 'button' });
    drawMark(progress.isRead(b, c));
    markBtn.addEventListener('click', async () => {
      const on = !progress.isRead(b, c);
      markBtn.classList.toggle('primary', !on);
      drawMark(on);
      await progress.mark([[b, c]], on);
      if (on) toast(`${refLabel({ b, c })} marked as read`);
    });
  }
  const foot = h('p', { class: 'licence-foot' },
    `${meta.title}${meta.licence ? ` · ${meta.licence}` : ''}${meta.class ? ` (${meta.class.toLowerCase()})` : ''}. `,
    h('a', { href: '/Bibles/README.md' }, 'Licence details'), ' · ',
    h('a', { href: `/Bibles/formats/text/${encodeURIComponent(t)}.txt` }, 'Download this translation'));

  root.replaceChildren(...[bar,
    missing ? h('p', { class: 'muted center small', text: `${t} doesn't include ${bookName(missing)}.` }) : null,
    textEl, markBtn ? h('div', { class: 'mark-read' }, markBtn) : null, nav, foot, ...arrows].filter(Boolean));

  if (v) {
    const target = textEl.querySelector(`.v[data-v="${v}"]`);
    if (target) {
      requestAnimationFrame(() => {
        target.scrollIntoView({ block: 'center' });
        target.classList.add('flash');
      });
    }
  }

  // warm the next chapter so turning the page is instant
  if (data.next) setTimeout(() => api.chapter(t, data.next[0], data.next[1]).catch(() => {}), 600);

  const keys = (e) => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName || '') || document.querySelector('dialog[open]')) return;
    if (e.key === 'ArrowLeft' && data.prev) go(hashFor({ t, b: data.prev[0], c: data.prev[1], p }));
    else if (e.key === 'ArrowRight' && data.next) go(hashFor({ t, b: data.next[0], c: data.next[1], p }));
    else if (e.key === 'Escape') closeBar();
  };
  document.addEventListener('keydown', keys);
  return () => {
    document.removeEventListener('keydown', keys);
    if (vbar) vbar.remove();
  };
}

// ---------------------------------------------------------------- search

export async function renderSearch(root, r) {
  const s = store.settings();
  const last = store.load('last', null);
  const q = (r.params.get('q') || '').trim();
  const scope = r.params.get('b') || '';
  let meta;
  try { meta = await translationMeta(r.params.get('t') || (last && last.t) || s.translation); } catch (e) {
    root.append(h('div', { class: 'page' }, errorBox(e, () => go(location.hash))));
    return null;
  }
  const t = meta.id;
  const bk = await api.books(t).catch(() => ({ books: [] }));
  const names = bk.books.map((x) => x.name);
  const chaptersOf = (name) => (bk.books.find((x) => x.name === name) || {}).chapters;

  const input = h('input', { class: 'input', type: 'search', value: q, placeholder: 'Search words, or John 3:16',
    'aria-label': 'Search the Bible', autocomplete: 'off', enterkeyhint: 'search' });
  const transBtn = h('button', { class: 'trans-btn', type: 'button', 'aria-label': 'Choose translation' }, t, icon('chevD'));
  const results = h('div');
  const page = h('div', { class: 'page' },
    h('div', { class: 'search-top' },
      h('a', { class: 'icon-btn', href: last ? readHash(last) : '#/read', 'aria-label': 'Back to reading' }, icon('back')),
      h('form', { role: 'search', on: { submit: (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        const ref = parseRef(text, names, chaptersOf);
        if (ref) go(readHash({ t, ...ref }));
        else go(`#/search?${new URLSearchParams({ t, q: text, ...(scope ? { b: scope } : {}) })}`);
      } } }, input, h('button', { class: 'btn primary', type: 'submit', 'aria-label': 'Search' }, icon('search'))),
      transBtn),
    results);
  root.append(page);
  transBtn.addEventListener('click', async () => {
    const id = await pickTranslation(t);
    if (id) go(`#/search?${new URLSearchParams({ t: id, ...(q ? { q } : {}) })}`);
  });
  if (!q) {
    input.focus();
    results.append(h('div', { class: 'empty' },
      h('h3', { text: 'Search the Bible' }),
      h('p', { text: 'Find words in any language: accents and vowel points don’t matter. Put a phrase in "quotes". Or jump straight to a passage: John 3:16, Ps 23, 1 Cor 13.' })));
    return null;
  }

  results.append(loading());
  let data;
  try {
    data = await api.get('search', { t, q, ...(scope ? { b: scope } : {}) });
  } catch (e) {
    results.replaceChildren(errorBox(e, () => go(location.hash)));
    return null;
  }
  const terms = queryTerms(q);
  const scopeBook = scope || (last && last.t === t ? last.b : null);
  const scopeSeg = scopeBook ? h('div', { class: 'seg' },
    h('button', { type: 'button', class: scope ? '' : 'on', text: 'All books',
      on: { click: () => go(`#/search?${new URLSearchParams({ t, q })}`) } }),
    h('button', { type: 'button', class: scope ? 'on' : '', text: bookName(scopeBook),
      on: { click: () => go(`#/search?${new URLSearchParams({ t, q, b: scopeBook })}`) } })) : null;
  const count = data.total === 1 ? '1 verse' : `${data.total.toLocaleString()} verses`;
  results.replaceChildren(
    h('div', { class: 'search-meta' }, h('span', { text: data.total > data.hits.length ? `${count} · showing the first ${data.hits.length}` : count }),
      h('span', { class: 'spacer' }), scopeSeg),
    data.hits.length ? h('div', { class: 'hits', lang: meta.lang || null, dir: meta.dir }, data.hits.map(([b, c, v, text]) =>
      h('a', { class: 'hit', href: readHash({ t, b, c, v }) },
        h('div', { class: 'hit-ref', lang: 'en', dir: 'ltr', text: refLabel({ b, c, v }) }),
        h('div', { class: 'hit-text' }, markMatches(text, terms).map(([part, on]) => (on ? h('mark', { text: part }) : part))))))
      : h('div', { class: 'empty' }, h('h3', { text: 'No verses found' }),
        h('p', { text: `Nothing in ${t} matches “${q}”. Try fewer words, or another translation.` })));
  return null;
}

