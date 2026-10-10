// The journal: private notes, prayers and reflections, kept only on this
// device. Entries can carry the verse they're about. Bookmarks and
// highlights live here too. Export/import moves them between devices.

import * as api from '../api.js';
import * as store from '../store.js';
import { refLabel, readHash, bookName } from '../bible.js';
import { ago } from '../dates.js';
import { h, icon, toast, confirmSheet, autoGrow } from '../ui.js';
import { go, segmented } from '../main.js';

function privateNote() {
  return h('p', { class: 'private-note' }, icon('lock'), 'Private: stored only on this device, never sent anywhere.');
}

function download(name, data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  const a = h('a', { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function exportAll() {
  download(`the-gift-journal-${new Date().toISOString().slice(0, 10)}.json`, {
    app: 'the-gift', version: 1, exported: new Date().toISOString(),
    journal: store.journal(), bookmarks: store.bookmarks(), highlights: store.highlights(),
  });
  toast('Exported');
}

function importAll() {
  const input = h('input', { type: 'file', accept: '.json,application/json' });
  input.addEventListener('change', async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      const n = store.importJournal(Array.isArray(data.journal) ? data.journal : []);
      if (Array.isArray(data.bookmarks)) {
        const have = store.bookmarks();
        const key = (x) => `${x.b}|${x.c}|${x.v}`;
        const seen = new Set(have.map(key));
        store.save('bookmarks', [...have, ...data.bookmarks.filter((x) => x && x.b && !seen.has(key(x)))]);
      }
      if (data.highlights && typeof data.highlights === 'object') {
        store.save('highlights', { ...data.highlights, ...store.highlights() });
      }
      toast(`Imported ${n} entr${n === 1 ? 'y' : 'ies'}`);
      go('#/journal', { replace: true });
    } catch {
      toast("That file isn't a journal export");
    }
  });
  input.click();
}

function entryCard(e) {
  const d = new Date(e.created);
  return h('a', { class: 'card link jentry', href: `#/journal/${e.id}` },
    h('div', { class: 'jdate' }, h('b', { text: String(d.getDate()) }),
      h('small', { text: d.toLocaleDateString(undefined, { weekday: 'short' }) })),
    h('div', {},
      h('div', { class: 'jtitle', text: e.title || (e.body.split('\n')[0] || 'Untitled').slice(0, 80) }),
      e.body ? h('p', { class: 'jex', text: e.title ? e.body : e.body.split('\n').slice(1).join(' ') }) : null,
      e.ref ? h('span', { class: 'pill jref', text: refLabel(e.ref) }) : null));
}

function renderEntries(area, filter) {
  const q = filter.trim().toLowerCase();
  const all = store.journal().filter((e) => !q || `${e.title} ${e.body} ${e.ref ? refLabel(e.ref) : ''}`.toLowerCase().includes(q));
  if (!all.length) {
    area.replaceChildren(h('div', { class: 'empty' },
      h('h3', { text: q ? 'Nothing matches' : 'Your journal is empty' }),
      h('p', { text: q ? 'Try another word.' : 'Write a prayer, a question, or what a passage stirred in you. Tap a verse while reading to write about it.' }),
      q ? null : h('a', { class: 'btn primary', href: '#/journal/new' }, icon('plus'), 'New entry')));
    return;
  }
  const parts = [];
  let month = '';
  for (const e of all) {
    const m = new Date(e.created).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
    if (m !== month) { month = m; parts.push(h('h3', { class: 'jmonth', text: m })); }
    parts.push(entryCard(e));
  }
  area.replaceChildren(h('div', { class: 'jlist' }, parts));
}

function renderBookmarks(area) {
  const list = store.bookmarks();
  if (!list.length) {
    area.replaceChildren(h('div', { class: 'empty' }, h('h3', { text: 'No bookmarks yet' }),
      h('p', { text: 'Tap a verse while reading, then the bookmark button.' })));
    return;
  }
  area.replaceChildren(h('div', { class: 'jlist' }, list.map((x) => h('a', { class: 'card link', href: readHash(x) },
    h('div', { class: 'row' }, icon('bookmark'), h('b', { text: refLabel(x) }), h('span', { class: 'spacer' }),
      h('span', { class: 'muted small', text: `${x.t || ''} · ${ago(x.at)}` }))))));
}

function renderHighlights(area) {
  const all = Object.entries(store.highlights());
  if (!all.length) {
    area.replaceChildren(h('div', { class: 'empty' }, h('h3', { text: 'No highlights yet' }),
      h('p', { text: 'Tap a verse while reading and pick a colour.' })));
    return;
  }
  const byChapter = new Map();
  for (const [key, color] of all) {
    const [b, c, v] = key.split('|');
    const k = `${b}|${c}`;
    if (!byChapter.has(k)) byChapter.set(k, []);
    byChapter.get(k).push([Number(v), color]);
  }
  const t = (store.load('last', null) || {}).t || store.settings().translation;
  area.replaceChildren(h('div', { class: 'jlist' }, [...byChapter.entries()].map(([k, verses]) => {
    const [b, c] = k.split('|');
    verses.sort((x, y) => x[0] - y[0]);
    return h('a', { class: 'card link', href: readHash({ t, b, c: Number(c), v: verses[0][0] }) },
      h('div', { class: 'row wrap' }, h('b', { text: refLabel({ b, c: Number(c) }) }), h('span', { class: 'spacer' }),
        h('span', { class: 'swatches' }, verses.slice(0, 12).map(([v, color]) => h('span', { class: 'pill', title: `Verse ${v}` },
          h('span', { class: `hdot ${color}` }), String(v))))));
  })));
}

async function renderList(root, r) {
  const tab = r.params.get('tab') || 'entries';
  const filter = h('input', { class: 'input', type: 'search', placeholder: 'Search your journal', 'aria-label': 'Search your journal' });
  const area = h('div');
  const tools = h('div', { class: 'jtools' },
    segmented([['entries', 'Entries'], ['bookmarks', 'Bookmarks'], ['highlights', 'Highlights']], tab,
      (v) => go(`#/journal?tab=${v}`, { replace: true })),
    h('span', { class: 'spacer' }),
    h('button', { class: 'icon-btn', type: 'button', title: 'Export a backup', 'aria-label': 'Export a backup', on: { click: exportAll } }, icon('download')),
    h('button', { class: 'icon-btn', type: 'button', title: 'Import a backup', 'aria-label': 'Import a backup', on: { click: importAll } }, icon('upload')));
  root.append(h('div', { class: 'page' },
    h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Journal' }),
      h('div', { class: 'row wrap' }, h('h1', { text: 'Your journal' }), h('span', { class: 'spacer' }),
        h('a', { class: 'btn primary', href: '#/journal/new' }, icon('plus'), 'New entry')),
      privateNote()),
    tools,
    tab === 'entries' ? h('div', { class: 'jtools' }, filter) : null,
    area));
  if (tab === 'bookmarks') renderBookmarks(area);
  else if (tab === 'highlights') renderHighlights(area);
  else {
    renderEntries(area, '');
    filter.addEventListener('input', () => renderEntries(area, filter.value));
  }
}

async function renderEditor(root, r) {
  const id = r.path[0] === 'new' ? null : r.path[0];
  let entry = id ? store.journalEntry(id) : null;
  if (id && !entry) {
    root.append(h('div', { class: 'page' }, h('div', { class: 'empty' }, h('h3', { text: 'Entry not found' }),
      h('p', { text: 'It may have been deleted, or written on another device.' }),
      h('a', { class: 'btn', href: '#/journal' }, 'Back to journal'))));
    return null;
  }
  if (!entry) {
    const pr = r.params;
    const ref = pr.get('b') && pr.get('c') ? { t: pr.get('t') || store.settings().translation, b: pr.get('b'),
      c: Number(pr.get('c')), v: Number(pr.get('v')) || null, v2: Number(pr.get('v2')) || null } : null;
    entry = { id: store.newId(), title: '', body: '', ref, prompt: pr.get('prompt') || '', quote: '' };
  }

  const title = h('input', { class: 'ed-title', value: entry.title, placeholder: 'Title', maxlength: 120, 'aria-label': 'Title' });
  const body = h('textarea', { class: 'ed-body', placeholder: 'Write freely…', 'aria-label': 'Entry' });
  body.value = entry.body;
  const saved = h('span', { class: 'saved', text: entry.updated ? `Saved ${ago(entry.updated)}` : '' });
  const quote = h('div', { class: 'ed-quote', hidden: !entry.quote, text: entry.quote || '' });

  let timer = null;
  let stored = Boolean(id);
  const persist = () => {
    clearTimeout(timer);
    timer = null;
    entry.title = title.value.trim();
    entry.body = body.value;
    if (!stored && !entry.title && !entry.body.trim()) return;
    entry = store.saveEntry(entry);
    if (!stored) { stored = true; history.replaceState(null, '', `#/journal/${entry.id}`); }
    saved.textContent = 'Saved';
  };
  const later = () => { saved.textContent = 'Editing…'; clearTimeout(timer); timer = setTimeout(persist, 500); };
  title.addEventListener('input', later);
  body.addEventListener('input', later);

  if (entry.ref && !entry.quote && entry.ref.v) {
    api.chapter(entry.ref.t, entry.ref.b, entry.ref.c).then((ch) => {
      const last = entry.ref.v2 || entry.ref.v;
      entry.quote = ch.verses.filter(([n]) => n >= entry.ref.v && n <= last).map(([, x]) => x).join(' ');
      quote.textContent = entry.quote;
      quote.hidden = !entry.quote;
      if (stored) store.saveEntry(entry);
    }).catch(() => {});
  }

  const created = new Date(entry.created || Date.now());
  root.append(h('div', { class: 'page' },
    h('div', { class: 'row', }, h('a', { class: 'btn ghost sm', href: '#/journal', on: { click: persist } }, icon('chevL'), 'Journal'),
      h('span', { class: 'spacer' }), saved,
      h('button', { class: 'icon-btn', type: 'button', title: 'Delete entry', 'aria-label': 'Delete entry', on: { click: async () => {
        if (!stored) { go('#/journal'); return; }
        if (await confirmSheet('Delete this entry?', 'It will be gone from this device.', { ok: 'Delete', danger: true })) {
          clearTimeout(timer);
          store.deleteEntry(entry.id);
          toast('Entry deleted');
          go('#/journal', { replace: true });
        }
      } } }, icon('trash'))),
    h('div', { class: 'editor' },
      h('div', { class: 'ed-meta' }, h('span', { text: created.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) }),
        entry.ref ? h('a', { class: 'pill pd', href: readHash(entry.ref), text: `${refLabel(entry.ref)} · ${entry.ref.t}` }) : null),
      title,
      entry.prompt ? h('div', { class: 'ed-prompt' }, `Reflecting on: ${entry.prompt}`) : null,
      quote,
      body,
      privateNote())));
  const fit = autoGrow(body);
  if (!id) (entry.ref || entry.prompt ? body : title).focus();
  fit();
  return () => { if (timer) persist(); };
}

export async function render(root, r) {
  if (r.path[0]) return renderEditor(root, r);
  await renderList(root, r);
  return null;
}

