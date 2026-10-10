// Music: public-domain hymns, featured and approved artists, the artist
// studio (apply, upload), and the admin review queue.

import * as api from '../api.js';
import * as player from '../player.js';
import { readHash, refLabel } from '../bible.js';
import { h, icon, sheet, toast, loading, errorBox, confirmSheet, resizeImage, pickFile, initials } from '../ui.js';
import { go, segmented } from '../main.js';
import { authForms } from './community.js';
import { ago } from '../dates.js';

const LINK_LABELS = { spotify: 'Spotify', apple: 'Apple Music', youtube: 'YouTube', bandcamp: 'Bandcamp', soundcloud: 'SoundCloud', website: 'Website' };

function art(src, name, cls = 'cover') {
  return src ? h('img', { class: cls, src, alt: '', loading: 'lazy' })
    : h('div', { class: `${cls} cover-blank`, text: initials(name || '♪') });
}

function playButton(onPlay, label = 'Play') {
  return h('button', { class: 'play-btn', type: 'button', 'aria-label': label, on: { click: (e) => { e.preventDefault(); e.stopPropagation(); onPlay(); } } }, icon('play'));
}

const songTrack = (s) => ({ url: s.url, title: s.title, artist: s.artist, art: s.photo, songId: s.id });

function songRow(list, i, { showArtist = true } = {}) {
  const s = list[i];
  return h('div', { class: 'song-row' },
    playButton(() => player.play(list.map(songTrack), i), `Play ${s.title}`),
    h('div', { class: 'song-text' }, h('b', { text: s.title }),
      showArtist ? h('a', { class: 'muted small', href: `#/artist/${s.artist_id}`, text: s.artist }) : null),
    s.status && s.status !== 'approved' ? h('span', { class: `pill ${s.status === 'pending' ? 'nc' : 'unk'}`, text: s.status }) : h('span', { class: 'muted small', text: s.plays ? `${s.plays} plays` : '' }));
}

function hymnTrack(hy) { return { url: hy.audio.url, title: hy.title, artist: hy.audio.performer || hy.author, art: '/app/img/hymn.svg' }; }

function artistCard(a) {
  return h('a', { class: 'artist-card', href: `#/artist/${a.id}` }, art(a.photo, a.name),
    h('b', { text: a.name }), h('small', { class: 'muted', text: a.genre || 'Artist' }));
}

// -------------------------------------------------------------------- home

export async function render(root, r) {
  const tab = r.params.get('tab') || 'foryou';
  const page = h('div', { class: 'page' },
    h('header', { class: 'music-hero' }, h('img', { src: '/app/img/music.svg', alt: '' }),
      h('div', {}, h('p', { class: 'eyebrow', text: 'Music' }), h('h1', { text: 'Songs of faith' }),
        h('p', { class: 'sub', text: 'Classic hymns, and new music from Christian artists.' }))),
    segmented([['foryou', 'For you'], ['hymns', 'Hymns'], ['artists', 'Artists']], tab, (v) => go(`#/music?tab=${v}`, { replace: true })),
    loading());
  root.append(page);
  let m;
  try { m = await api.get('music'); } catch (e) { page.lastChild.replaceWith(errorBox(e, () => go(location.hash))); return null; }
  const hymnList = h('div', { class: 'list' }, m.hymns.map((hy) => h('a', { class: 'list-row', href: `#/hymn/${hy.id}` },
    h('img', { class: 'cover sm', src: '/app/img/hymn.svg', alt: '' }),
    h('div', { class: 'song-text' }, h('b', { text: hy.title }), h('small', { class: 'muted', text: [hy.author, hy.year].filter(Boolean).join(' · ') })),
    hy.audio ? icon('music') : null)));
  let content;
  if (tab === 'hymns') {
    content = m.hymns.length ? hymnList : h('div', { class: 'empty' }, h('h3', { text: 'Hymns are on their way' }));
  } else if (tab === 'artists') {
    content = m.artists.length ? h('div', { class: 'artist-grid' }, m.artists.map(artistCard))
      : h('div', { class: 'empty' }, h('h3', { text: 'No artists yet' }), h('p', { text: 'Be the first: apply from the artist studio.' }));
  } else {
    content = h('div', { class: 'stack' },
      m.featured.length ? h('section', {}, h('h2', { class: 'section-title', text: 'Featured artists' }),
        h('div', { class: 'artist-row' }, m.featured.map(artistCard))) : null,
      m.songs.length ? h('section', {}, h('h2', { class: 'section-title', text: 'New songs' }),
        h('div', { class: 'list' }, m.songs.map((_, i) => songRow(m.songs, i)))) : null,
      h('section', {}, h('div', { class: 'row' }, h('h2', { class: 'section-title', text: 'Hymns' }), h('span', { class: 'spacer' }),
        h('a', { class: 'btn ghost sm', href: '#/music?tab=hymns' }, 'All hymns')),
      m.hymns.length ? h('div', { class: 'list' }, [...hymnList.children].slice(0, 6)) : h('p', { class: 'muted', text: 'Hymns are on their way.' })),
      h('a', { class: 'card link cta-card', href: '#/studio' }, icon('mic'),
        h('div', {}, h('h3', { text: 'Are you a Christian artist?' }), h('p', { class: 'muted', text: 'Apply to share your music here. Every artist and song is reviewed before it goes live.' }))));
  }
  page.lastChild.replaceWith(content);
  return null;
}

// ------------------------------------------------------------------ artist

export async function renderArtist(root, r) {
  const page = h('div', { class: 'page' }, loading());
  root.append(page);
  let a;
  try { a = await api.get(`artists/${r.path[0]}`); } catch (e) { page.replaceChildren(errorBox(e)); return null; }
  const links = Object.entries(a.links || {});
  page.replaceChildren(...[
    h('a', { class: 'btn ghost sm', href: '#/music' }, icon('chevL'), 'Music'),
    h('header', { class: 'artist-head' }, art(a.photo, a.name, 'cover lg'),
      h('div', {}, h('p', { class: 'eyebrow', text: a.featured ? 'Featured artist' : 'Artist' }), h('h1', { text: a.name }),
        a.genre ? h('p', { class: 'muted', text: a.genre }) : null,
        a.status && a.status !== 'approved' ? h('span', { class: 'pill nc', text: `Application ${a.status}` }) : null)),
    a.songs.length ? h('div', { class: 'row wrap' }, h('button', { class: 'btn primary', type: 'button', on: { click: () => {
      const live = a.songs.filter((s) => !s.status || s.status === 'approved');
      if (live.length) player.play(live.map(songTrack));
    } } }, icon('play'), 'Play all')) : null,
    links.length ? h('div', { class: 'row wrap' }, links.map(([k, url]) => h('a', { class: 'btn sm', href: url, target: '_blank', rel: 'noopener noreferrer' }, icon(k === 'website' ? 'globe' : 'music'), LINK_LABELS[k] || k))) : null,
    a.bio ? h('p', { class: 'profile-bio', text: a.bio }) : null,
    h('h2', { class: 'section-title', text: 'Songs' }),
    a.songs.length ? h('div', { class: 'list' }, a.songs.map((_, i) => songRow(a.songs.map((s) => ({ ...s, artist: a.name, photo: a.photo })), i, { showArtist: false })))
      : h('p', { class: 'muted', text: 'No songs yet.' }),
  ].filter(Boolean));
  return null;
}

// ------------------------------------------------------------------- hymn

export async function renderHymn(root, r) {
  const page = h('div', { class: 'page' }, loading());
  root.append(page);
  let hy;
  try { hy = await api.get(`hymns/${r.path[0]}`); } catch (e) { page.replaceChildren(errorBox(e)); return null; }
  const t = 'KJV';
  page.replaceChildren(...[
    h('a', { class: 'btn ghost sm', href: '#/music?tab=hymns' }, icon('chevL'), 'Hymns'),
    h('header', { class: 'artist-head' }, h('img', { class: 'cover lg', src: '/app/img/hymn.svg', alt: '' }),
      h('div', {}, h('p', { class: 'eyebrow', text: 'Hymn' }), h('h1', { text: hy.title }),
        h('p', { class: 'muted', text: [hy.author, hy.year, hy.tune ? `Tune: ${hy.tune}` : null].filter(Boolean).join(' · ') }))),
    hy.audio ? h('div', { class: 'row wrap' }, h('button', { class: 'btn primary', type: 'button', on: { click: () => player.play([hymnTrack(hy)]) } }, icon('play'), 'Listen')) : null,
    hy.scripture && hy.scripture.length ? h('div', { class: 'row wrap' }, hy.scripture.map((s) => h('a', { class: 'pill pd', href: readHash({ t, ...s }), text: refLabel(s) }))) : null,
    h('div', { class: 'lyrics' }, (hy.verses || []).map((stanza, i) => h('div', { class: 'stanza' },
      h('span', { class: 'stanza-n', text: String(i + 1) }),
      h('div', {}, stanza.map((line) => h('div', { text: line })))),
      hy.chorus ? h('div', { class: 'stanza chorus' }, h('span', { class: 'stanza-n', text: 'Refrain' }),
        h('div', {}, hy.chorus.map((line) => h('div', { text: line })))) : null)),
    h('p', { class: 'source', text: [hy.text_credit, hy.audio ? `Recording: ${hy.audio.performer} · ${hy.audio.licence}` : null].filter(Boolean).join(' · ') }),
    hy.audio && hy.audio.source ? h('p', { class: 'source' }, h('a', { href: hy.audio.source, target: '_blank', rel: 'noopener noreferrer' }, 'About this recording')) : null,
  ].filter(Boolean));
  return null;
}

// ----------------------------------------------------------------- studio

function linkFields(links) {
  links = links || {};
  const inputs = {};
  const box = h('div', { class: 'stack' }, Object.entries(LINK_LABELS).map(([k, label]) => {
    inputs[k] = h('input', { class: 'input', type: 'url', value: links[k] || '', placeholder: k === 'website' ? 'https://…' : `Your ${label} page` });
    return h('label', { class: 'field' }, h('span', { text: label }), inputs[k]);
  }));
  return { box, values: () => Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value.trim()]).filter(([, v]) => v)) };
}

function artistForm(a, onDone) {
  let photo = a ? (a.photo ? a.photo.split('/').pop() : null) : null;
  const pic = h('div', {}, art(a && a.photo, a && a.name, 'cover lg'));
  const name = h('input', { class: 'input', required: true, maxlength: 60, value: (a && a.name) || '' });
  const genre = h('input', { class: 'input', maxlength: 40, value: (a && a.genre) || '', placeholder: 'e.g. Worship, Gospel, Hymns, Rap' });
  const bio = h('textarea', { class: 'textarea', rows: 5, maxlength: 1500, placeholder: 'Your story, your ministry, what your music is about' });
  bio.value = (a && a.bio) || '';
  const links = linkFields(a && a.links);
  const err = h('p', { class: 'form-error', role: 'alert' });
  const choose = h('button', { class: 'btn sm', type: 'button' }, icon('camera'), 'Artist photo');
  choose.addEventListener('click', async () => {
    const file = await pickFile('image/*');
    if (!file) return;
    choose.disabled = true;
    try {
      const res = await api.upload(await resizeImage(file, 800));
      photo = res.id;
      pic.replaceChildren(art(res.url, name.value, 'cover lg'));
    } catch (e) { toast(e.message); } finally { choose.disabled = false; }
  });
  return h('form', { class: 'form', on: { submit: async (e) => {
    e.preventDefault();
    err.textContent = '';
    try {
      await api.post('studio', { name: name.value, genre: genre.value, bio: bio.value, links: links.values(), photo });
      toast(a ? 'Saved' : 'Application sent. We’ll review it soon.');
      onDone();
    } catch (ex) { err.textContent = ex.message; }
  } } },
  h('div', { class: 'row' }, pic, choose),
  h('label', { class: 'field' }, h('span', { text: 'Artist name' }), name),
  h('label', { class: 'field' }, h('span', { text: 'Style' }), genre),
  h('label', { class: 'field' }, h('span', { text: 'About' }), bio),
  h('details', { class: 'more' }, h('summary', { text: 'Links to your music elsewhere' }), links.box),
  err, h('button', { class: 'btn primary', type: 'submit' }, a ? 'Save' : 'Send application'));
}

function songForm(onDone) {
  let media = null;
  const title = h('input', { class: 'input', required: true, maxlength: 100 });
  const lyrics = h('textarea', { class: 'textarea', rows: 4, maxlength: 5000, placeholder: 'Lyrics (optional)' });
  const rights = h('input', { type: 'checkbox' });
  const fileLabel = h('span', { class: 'muted small', text: 'MP3, M4A, Ogg, WAV or FLAC · up to 40 MB' });
  const err = h('p', { class: 'form-error', role: 'alert' });
  const choose = h('button', { class: 'btn', type: 'button' }, icon('upload'), 'Choose audio file');
  choose.addEventListener('click', async () => {
    const file = await pickFile('audio/*');
    if (!file) return;
    choose.disabled = true;
    fileLabel.textContent = `Uploading ${file.name}…`;
    try {
      const res = await api.upload(file);
      media = res.id;
      fileLabel.textContent = `${file.name} ✓`;
      if (!title.value) title.value = file.name.replace(/\.[^.]+$/, '');
    } catch (e) { fileLabel.textContent = e.message; } finally { choose.disabled = false; }
  });
  return h('form', { class: 'form', on: { submit: async (e) => {
    e.preventDefault();
    err.textContent = '';
    if (!media) { err.textContent = 'Choose the audio file first.'; return; }
    try {
      await api.post('studio/songs', { title: title.value, media, lyrics: lyrics.value, rights: rights.checked });
      toast('Song sent for review');
      onDone();
    } catch (ex) { err.textContent = ex.message; }
  } } },
  h('div', { class: 'row wrap' }, choose, fileLabel),
  h('label', { class: 'field' }, h('span', { text: 'Song title' }), title),
  lyrics,
  h('label', { class: 'check-row' }, rights, h('span', { text: 'I own this recording, or have permission to share it, and it contains nothing I don’t have the rights to.' })),
  err, h('button', { class: 'btn primary', type: 'submit' }, 'Send for review'));
}

export async function renderStudio(root) {
  const page = h('div', { class: 'page' }, h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Artist studio' }), h('h1', { text: 'Share your music' })), loading());
  root.append(page);
  const user = await api.currentUser();
  if (!user) { page.lastChild.replaceWith(h('div', { class: 'auth' }, h('p', { class: 'muted', text: 'Sign in to apply as an artist.' }), authForms(() => go('#/studio', { replace: true }), { intro: false }))); return null; }
  let s;
  try { s = await api.get('studio'); } catch (e) { page.lastChild.replaceWith(errorBox(e)); return null; }
  const reload = () => go('#/studio', { replace: true });
  const a = s.artist;
  let body;
  if (!a) {
    body = h('div', { class: 'stack' },
      h('p', { class: 'muted', text: 'Tell us about your music. Once your application is approved you can upload songs, and each song is reviewed before it plays in the app.' }),
      artistForm(null, reload));
  } else if (a.status !== 'approved') {
    body = h('div', { class: 'stack' },
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, icon('mic'), h('span', { class: 'label', text: a.status === 'pending' ? 'Waiting for review' : 'Not approved' })),
        h('p', { text: a.status === 'pending' ? 'Thanks! Your application is in the queue.' : (a.note || 'Your application wasn’t approved. You can edit it and send it again.') })),
      artistForm(a, reload));
  } else {
    body = h('div', { class: 'stack' },
      h('a', { class: 'card link artist-head', href: `#/artist/${a.id}` }, art(a.photo, a.name, 'cover'), h('div', {}, h('b', { text: a.name }), h('p', { class: 'muted small', text: 'Your public artist page' }))),
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, icon('upload'), h('span', { class: 'label', text: 'Add a song' })), songForm(reload)),
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, icon('music'), h('span', { class: 'label', text: `Your songs · ${a.songs.length}` })),
        a.songs.length ? h('div', { class: 'list' }, a.songs.map((song, i) => h('div', { class: 'song-row' },
          playButton(() => player.play([songTrack({ ...song, artist: a.name, photo: a.photo })])),
          h('div', { class: 'song-text' }, h('b', { text: song.title }),
            h('small', { class: 'muted', text: song.status === 'approved' ? `${song.plays} plays` : song.status === 'rejected' ? (song.note || 'Not approved') : 'Waiting for review' })),
          h('span', { class: `pill ${song.status === 'approved' ? 'pd' : song.status === 'pending' ? 'nc' : 'unk'}`, text: song.status }),
          h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Delete song', on: { click: async () => {
            if (await confirmSheet(`Delete “${song.title}”?`, 'It will be removed from the app.', { ok: 'Delete', danger: true })) {
              try { await api.post(`songs/${song.id}/delete`); reload(); } catch (e) { toast(e.message); }
            }
          } } }, icon('trash')))))
          : h('p', { class: 'muted', text: 'No songs yet.' })),
      h('details', { class: 'more card' }, h('summary', { text: 'Edit artist profile' }), artistForm(a, reload)));
  }
  page.lastChild.replaceWith(body);
  return null;
}

// ------------------------------------------------------------------ admin

export async function renderAdmin(root) {
  const page = h('div', { class: 'page' }, h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Admin' }), h('h1', { text: 'Review' })), loading());
  root.append(page);
  const user = await api.currentUser();
  if (!user || !user.is_admin) { page.lastChild.replaceWith(h('div', { class: 'empty' }, h('h3', { text: 'Admins only' }))); return null; }
  let q, audit;
  try {
    q = await api.verified(() => api.get('admin'));
    audit = await api.verified(() => api.get('admin/audit'));
  } catch (e) { page.lastChild.replaceWith(errorBox(e, () => go(location.hash))); return null; }
  const reload = () => go('#/admin', { replace: true });
  const review = async (kind, id, action) => {
    let note = '';
    if (action === 'reject') {
      note = window.prompt('A short note for them (optional):', '') || '';
    } else if (action === 'remove' && !(await confirmSheet('Remove for good?', 'This deletes it and its files.', { ok: 'Remove', danger: true }))) return;
    try { await api.verified(() => api.post(`admin/${kind}/${id}`, { action, note })); toast('Done'); reload(); } catch (e) { toast(e.message); }
  };
  page.lastChild.replaceWith(h('div', { class: 'stack' },
    h('div', { class: 'stats' }, h('div', { class: 'stat' }, h('b', { text: String(q.stats.users) }), h('small', { text: 'accounts' })),
      h('div', { class: 'stat' }, h('b', { text: String(q.stats.groups) }), h('small', { text: 'groups' })),
      h('div', { class: 'stat' }, h('b', { text: String(q.stats.songs) }), h('small', { text: 'songs live' }))),
    h('h2', { class: 'section-title', text: `Artist applications · ${q.artists.length}` }),
    q.artists.length ? q.artists.map((a) => h('section', { class: 'card stack' },
      h('div', { class: 'artist-head' }, art(a.photo, a.name, 'cover'), h('div', {}, h('b', { text: a.name }), h('p', { class: 'muted small', text: `@${a.username} · ${a.genre || 'no style given'} · ${ago(a.created * 1000)}` }))),
      a.bio ? h('p', { text: a.bio }) : null,
      Object.keys(a.links).length ? h('div', { class: 'row wrap' }, Object.entries(a.links).map(([k, url]) => h('a', { class: 'pill', href: url, target: '_blank', rel: 'noopener noreferrer', text: LINK_LABELS[k] || k }))) : null,
      h('div', { class: 'row wrap' }, h('button', { class: 'btn primary sm', type: 'button', on: { click: () => review('artists', a.id, 'approve') } }, 'Approve'),
        h('button', { class: 'btn sm', type: 'button', on: { click: () => review('artists', a.id, 'reject') } }, 'Reject'))))
      : h('p', { class: 'muted', text: 'Nothing waiting.' }),
    h('h2', { class: 'section-title', text: `Songs to review · ${q.songs.length}` }),
    q.songs.length ? h('div', { class: 'list' }, q.songs.map((s) => h('div', { class: 'song-row' },
      playButton(() => player.play([songTrack(s)])),
      h('div', { class: 'song-text' }, h('b', { text: s.title }), h('small', { class: 'muted', text: s.artist })),
      h('button', { class: 'btn primary sm', type: 'button', on: { click: () => review('songs', s.id, 'approve') } }, 'Approve'),
      h('button', { class: 'btn sm', type: 'button', on: { click: () => review('songs', s.id, 'reject') } }, 'Reject'))))
      : h('p', { class: 'muted', text: 'Nothing waiting.' }),
    h('h2', { class: 'section-title', text: 'Artists' }),
    h('div', { class: 'list' }, q.approved.map((a) => h('div', { class: 'song-row' }, art(a.photo, a.name, 'cover sm'),
      h('div', { class: 'song-text' }, h('a', { href: `#/artist/${a.id}`, text: a.name })),
      h('button', { class: `btn sm${a.featured ? ' primary' : ''}`, type: 'button', on: { click: () => review('artists', a.id, a.featured ? 'unfeature' : 'feature') } }, a.featured ? 'Featured' : 'Feature'),
      h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Remove artist', on: { click: () => review('artists', a.id, 'remove') } }, icon('trash'))))),
    h('details', { class: 'more card' }, h('summary', { text: `Audit log · last ${audit.events.length} events` }),
      h('div', { class: 'audit' }, audit.events.map((ev) => h('div', { class: 'audit-row' },
        h('span', { class: 'muted small', text: new Date(ev.at * 1000).toLocaleString() }),
        h('b', { text: ev.action }), h('span', { class: 'small', text: [ev.username && `@${ev.username}`, ev.ip, ev.detail].filter(Boolean).join(' · ') })))))));
  return null;
}
