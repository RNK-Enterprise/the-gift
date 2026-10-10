// One audio player for the whole app: it keeps playing while you move
// between screens. A queue of tracks, a mini player above the tab bar, and
// lock-screen / headphone controls through the Media Session API.

import * as api from './api.js';
import { h, icon } from './ui.js';

const audio = new Audio();
audio.preload = 'metadata';
let queue = [];
let index = -1;
let counted = false;
let bar = null;
const listeners = new Set();

export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function changed() { for (const fn of listeners) fn(current()); render(); }

export function current() {
  return index >= 0 ? { ...queue[index], playing: !audio.paused, index, length: queue.length } : null;
}

// tracks: [{url, title, artist, art, songId}]
export function play(tracks, start = 0) {
  queue = tracks.filter((t) => t && t.url);
  if (!queue.length) return;
  load(Math.max(0, Math.min(start, queue.length - 1)));
}

function load(i) {
  index = i;
  counted = false;
  const t = queue[i];
  audio.src = t.url;
  audio.play().catch(() => {});
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: t.title, artist: t.artist || '', album: 'The Gift',
      artwork: t.art ? [{ src: t.art, sizes: '512x512' }] : [{ src: '/app/icons/icon-512.png', sizes: '512x512', type: 'image/png' }],
    });
  }
  changed();
}

export function toggle() { if (index < 0) return; if (audio.paused) audio.play().catch(() => {}); else audio.pause(); }
export function next() { if (index < queue.length - 1) load(index + 1); }
export function prev() { if (audio.currentTime > 4 || index === 0) audio.currentTime = 0; else load(index - 1); }
export function stop() { audio.pause(); audio.removeAttribute('src'); audio.load(); queue = []; index = -1; changed(); }
export function isCurrent(url) { return index >= 0 && queue[index].url === url; }

audio.addEventListener('play', changed);
audio.addEventListener('pause', changed);
audio.addEventListener('ended', () => { if (index < queue.length - 1) load(index + 1); else changed(); });
audio.addEventListener('timeupdate', () => {
  if (bar) {
    const fill = bar.querySelector('.pl-progress > span');
    if (fill && audio.duration) fill.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
  }
  const t = queue[index];
  if (t && t.songId && !counted && audio.currentTime > 30) {
    counted = true; // a play counts after 30 seconds of listening
    api.post(`songs/${t.songId}/play`).catch(() => {});
  }
});

if ('mediaSession' in navigator) {
  navigator.mediaSession.setActionHandler('play', toggle);
  navigator.mediaSession.setActionHandler('pause', toggle);
  navigator.mediaSession.setActionHandler('previoustrack', prev);
  navigator.mediaSession.setActionHandler('nexttrack', next);
}

function render() {
  const t = index >= 0 ? queue[index] : null;
  document.body.classList.toggle('has-player', Boolean(t));
  if (!t) { if (bar) { bar.remove(); bar = null; } return; }
  if (!bar) {
    bar = h('div', { class: 'player', role: 'region', 'aria-label': 'Now playing' });
    document.body.append(bar);
  }
  const progress = h('div', { class: 'pl-progress', title: 'Seek' }, h('span'));
  progress.addEventListener('click', (e) => {
    const r = progress.getBoundingClientRect();
    if (audio.duration) audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
  });
  bar.replaceChildren(
    progress,
    t.art ? h('img', { class: 'pl-art', src: t.art, alt: '' }) : h('div', { class: 'pl-art pl-art-blank' }, icon('music')),
    h('div', { class: 'pl-text' }, h('div', { class: 'pl-title', text: t.title }), h('div', { class: 'pl-artist', text: t.artist || '' })),
    h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Previous', on: { click: prev } }, icon('skipBack')),
    h('button', { class: 'icon-btn pl-play', type: 'button', 'aria-label': audio.paused ? 'Play' : 'Pause', on: { click: toggle } },
      icon(audio.paused ? 'play' : 'pause')),
    h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Next', disabled: index >= queue.length - 1, on: { click: next } }, icon('skipFwd')),
    h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close player', on: { click: stop } }, icon('x')));
}
