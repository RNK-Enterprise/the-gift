// Small DOM toolkit: build elements without innerHTML (so nothing from the
// network is ever parsed as markup), icons, sheets and toasts.

const PROPS = new Set(['value', 'checked', 'disabled', 'hidden', 'selected', 'type', 'min', 'max', 'step']);

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'on') for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (PROPS.has(k)) el[k] = v;
      else el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  append(el, kids);
  return el;
}

function append(el, kids) {
  for (const kid of kids) {
    if (kid == null || kid === false) continue;
    if (Array.isArray(kid)) append(el, kid);
    else el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

// 24×24 stroke icons, drawn for this app
const ICONS = {
  sun: 'M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6zM12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4',
  moon: 'M20 14.6A8.2 8.2 0 1 1 9.4 4a6.6 6.6 0 0 0 10.6 10.6z',
  book: 'M12 6.6c-1.9-1.5-4.6-1.9-7.2-1.7v12.4c2.6-.2 5.3.2 7.2 1.7 1.9-1.5 4.6-1.9 7.2-1.7V4.9c-2.6-.2-5.3.2-7.2 1.7zM12 6.6V19',
  calendar: 'M4 6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v12a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM4 10h16M8.5 3v4M15.5 3v4',
  pen: 'M4 20h4.2L19 9.2a2.9 2.9 0 0 0-4.2-4.2L4 15.8zM13.4 6.4l4.2 4.2',
  users: 'M9 11.5a3.6 3.6 0 1 0 0-7.2 3.6 3.6 0 0 0 0 7.2zM2.8 20a6.2 6.2 0 0 1 12.4 0M16 4.6a3.6 3.6 0 0 1 0 6.8M18 14.2a6.2 6.2 0 0 1 3.2 5.8',
  pin: 'M12 21s-6.8-6-6.8-11.3a6.8 6.8 0 0 1 13.6 0C18.8 15 12 21 12 21zM12 12.2a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
  search: 'M10.8 18a7.2 7.2 0 1 0 0-14.4 7.2 7.2 0 0 0 0 14.4zM20.5 20.5l-4.6-4.6',
  sliders: 'M4 7h8.5M16.5 7H20M4 17h3.5M11.5 17H20M14.5 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM9.5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  chevL: 'M15 18l-6-6 6-6',
  chevR: 'M9 6l6 6-6 6',
  chevD: 'M6 9.5l6 6 6-6',
  back: 'M19 12H5.5M11.5 18l-6-6 6-6',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  copy: 'M9 9.5A1.5 1.5 0 0 1 10.5 8h8A1.5 1.5 0 0 1 20 9.5v9a1.5 1.5 0 0 1-1.5 1.5h-8A1.5 1.5 0 0 1 9 18.5zM15.5 8V5.5A1.5 1.5 0 0 0 14 4H5.5A1.5 1.5 0 0 0 4 5.5V14a1.5 1.5 0 0 0 1.5 1.5H9',
  link: 'M10 14a4.4 4.4 0 0 0 6.3 0l3-3a4.4 4.4 0 0 0-6.3-6.3l-.9.9M14 10a4.4 4.4 0 0 0-6.3 0l-3 3a4.4 4.4 0 0 0 6.3 6.3l.9-.9',
  bookmark: 'M6.5 3.5h11v17L12 16.4l-5.5 4.1z',
  send: 'M20.5 3.5 10.6 13.4M20.5 3.5 14.2 20.5l-3.6-7.1-7.1-3.6z',
  plus: 'M12 5v14M5 12h14',
  columns: 'M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM12 4v16',
  type: 'M3.5 18 8 6l4.5 12M5.2 13.8h5.6M14.5 18l3-7 3 7M15.4 16h4.2',
  download: 'M12 3.5v11.5M7 10.5l5 5 5-5M4.5 20.5h15',
  upload: 'M12 20.5V9M7 13.5l5-5 5 5M4.5 3.5h15',
  trash: 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5',
  logout: 'M14.5 4H18a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3.5M10 16.5 5.5 12 10 7.5M5.5 12h10',
  flame: 'M12 21.5c3.9 0 6.8-2.6 6.8-6.5 0-4.2-3.4-6.4-4.8-10.7-1.5 2.2-1.9 3.9-1.9 5.8-1.2-.9-1.9-2.3-2.1-3.8C7.2 8.2 5.2 10.9 5.2 15c0 3.9 2.9 6.5 6.8 6.5z',
  locate: 'M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM12 2v3M12 19v3M2 12h3M19 12h3',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.4 2.5 3.6 5.5 3.6 9s-1.2 6.5-3.6 9c-2.4-2.5-3.6-5.5-3.6-9S9.6 5.5 12 3z',
  phone: 'M5.5 3.8h3.6l1.8 4.6-2.3 1.4a10.6 10.6 0 0 0 5.6 5.6l1.4-2.3 4.6 1.8v3.6a1.9 1.9 0 0 1-2 1.9A16 16 0 0 1 3.6 5.8a1.9 1.9 0 0 1 1.9-2z',
  route: 'M3.5 11 20.5 3.5 13 20.5l-1.9-7.6z',
  install: 'M12 3.5v10M8 9.5l4 4 4-4M4.5 15.5v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3',
  lock: 'M6 11h12a1 1 0 0 1 1 1v7.5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V12a1 1 0 0 1 1-1zM8.5 11V7.8a3.5 3.5 0 0 1 7 0V11',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  share: 'M12 15V3.5M7.5 8 12 3.5 16.5 8M5 12.5v6A2 2 0 0 0 7 20.5h10a2 2 0 0 0 2-2v-6',
  quote: 'M5 17c2.4-1.2 3.6-3 3.6-5.6V7H4.5v4.6h4M14.5 17c2.4-1.2 3.6-3 3.6-5.6V7h-4.1v4.6h4',
  chat: 'M20 11.6c0 4.1-3.6 7.4-8 7.4-1.2 0-2.3-.2-3.3-.6L4 19.8l1.3-3.7A7 7 0 0 1 4 11.6C4 7.5 7.6 4.2 12 4.2s8 3.3 8 7.4z',
  music: 'M9 18.5V6l11-2.5v12M9 18.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM20 15.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM9 10l11-2.5',
  play: 'M7 4.8v14.4a.8.8 0 0 0 1.2.7l11.3-7.2a.8.8 0 0 0 0-1.4L8.2 4.1A.8.8 0 0 0 7 4.8z',
  pause: 'M7 4.5h3v15H7zM14 4.5h3v15h-3z',
  skipBack: 'M18 5.5v13L8.5 12zM6 5.5v13',
  skipFwd: 'M6 5.5v13l9.5-6.5zM18 5.5v13',
  user: 'M12 12.2a4.2 4.2 0 1 0 0-8.4 4.2 4.2 0 0 0 0 8.4zM4.5 20.5a7.5 7.5 0 0 1 15 0',
  heart: 'M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z',
  crown: 'M3.5 8l4.3 3.6L12 5l4.2 6.6L20.5 8 19 18H5zM5 21h14',
  award: 'M12 14.5a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11zM8.6 13.4 7.5 21l4.5-2.6 4.5 2.6-1.1-7.6',
  shield: 'M12 3l7.5 3v5.6c0 4.4-3.1 8.2-7.5 9.4-4.4-1.2-7.5-5-7.5-9.4V6zM8.8 12l2.2 2.2 4.3-4.4',
  device: 'M8 3h8a1.5 1.5 0 0 1 1.5 1.5v15A1.5 1.5 0 0 1 16 21H8a1.5 1.5 0 0 1-1.5-1.5v-15A1.5 1.5 0 0 1 8 3zM11 18h2',
  camera: 'M4 8.5A1.5 1.5 0 0 1 5.5 7h2.3l1.5-2.2h5.4L16.2 7h2.3A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5zM12 16.2a3.4 3.4 0 1 0 0-6.8 3.4 3.4 0 0 0 0 6.8z',
  mic: 'M12 3.5a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0v-5a3 3 0 0 1 3-3zM6 11a6 6 0 0 0 12 0M12 17v3.5',
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 13.5l1.6 1.2-2 3.4-1.9-.8a7.6 7.6 0 0 1-2.1 1.2l-.3 2h-4l-.3-2a7.6 7.6 0 0 1-2.1-1.2l-1.9.8-2-3.4 1.6-1.2a7.4 7.4 0 0 1 0-2.4L4.4 9.9l2-3.4 1.9.8a7.6 7.6 0 0 1 2.1-1.2l.3-2h4l.3 2a7.6 7.6 0 0 1 2.1 1.2l1.9-.8 2 3.4-1.6 1.2a7.4 7.4 0 0 1 0 2.4z',
  study: 'M4 5.5h5.5A2.5 2.5 0 0 1 12 8v11.5a1.6 1.6 0 0 0-1.6-1.6H4zM20 5.5h-5.5A2.5 2.5 0 0 0 12 8v11.5a1.6 1.6 0 0 1 1.6-1.6H20z',
  sparkle: 'M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9-1.9 5.1-1.9-5.1L5 10.5l5.1-1.9zM18.5 16l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z',
};

export function icon(name, cls = 'i') {
  const span = document.createElement('span');
  span.className = cls;
  span.setAttribute('aria-hidden', 'true');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', name === 'more' ? '3' : '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICONS[name] || '');
  svg.append(path);
  span.append(svg);
  return span;
}

export function fillIcons(root = document) {
  for (const el of root.querySelectorAll('[data-icon]')) {
    el.replaceWith(icon(el.dataset.icon, el.className || 'i'));
  }
}

export function ring(fraction, label) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 64 64');
  svg.setAttribute('class', 'ring');
  const r = 27, c = 2 * Math.PI * r;
  const track = document.createElementNS(ns, 'circle');
  for (const [k, v] of Object.entries({ cx: 32, cy: 32, r, class: 'track' })) track.setAttribute(k, v);
  const bar = document.createElementNS(ns, 'circle');
  for (const [k, v] of Object.entries({ cx: 32, cy: 32, r, class: 'bar', transform: 'rotate(-90 32 32)',
    'stroke-dasharray': c, 'stroke-dashoffset': c * (1 - Math.max(0, Math.min(1, fraction))) })) bar.setAttribute(k, v);
  const text = document.createElementNS(ns, 'text');
  for (const [k, v] of Object.entries({ x: 32, y: 37, 'text-anchor': 'middle' })) text.setAttribute(k, v);
  text.textContent = label;
  svg.append(track, bar, text);
  return svg;
}

export function progressBar(fraction) {
  const fill = h('span');
  fill.style.width = `${Math.round(Math.max(0, Math.min(1, fraction)) * 100)}%`;
  return h('div', { class: 'progress', role: 'progressbar', 'aria-valuenow': Math.round(fraction * 100),
    'aria-valuemin': 0, 'aria-valuemax': 100 }, fill);
}

export function toast(message) {
  const box = document.querySelector('.toasts');
  if (!box) return;
  const t = h('div', { class: 'toast', text: message });
  box.append(t);
  setTimeout(() => t.remove(), 2600);
}

// A modal sheet (bottom sheet on phones, centred card on desktop).
export function sheet(title, { tall = false, onClose } = {}) {
  // focus lands on the body, not the close button: no stray focus ring on open
  const body = h('div', { class: 'sheet-body', tabindex: '-1', autofocus: true });
  const closeBtn = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close' }, icon('x'));
  const head = h('div', { class: 'sheet-head' }, h('h3', { text: title }), closeBtn);
  const dlg = h('dialog', { class: `sheet${tall ? ' tall' : ''}`, 'aria-label': title }, head, body);
  const close = () => { if (dlg.open) dlg.close(); };
  closeBtn.addEventListener('click', close);
  dlg.addEventListener('click', (e) => { if (e.target === dlg) close(); });
  dlg.addEventListener('close', () => { dlg.remove(); onClose && onClose(); });
  document.body.append(dlg);
  dlg.showModal();
  return { dlg, body, head, close, setTitle: (t) => { head.querySelector('h3').textContent = t; } };
}

export function confirmSheet(title, message, { ok = 'OK', danger = false } = {}) {
  return new Promise((resolve) => {
    let answer = false;
    const s = sheet(title, { onClose: () => resolve(answer) });
    s.body.append(
      h('p', { class: 'muted', text: message }),
      h('div', { class: 'row' },
        h('span', { class: 'spacer' }),
        h('button', { class: 'btn ghost', type: 'button', on: { click: s.close } }, 'Cancel'),
        h('button', { class: `btn ${danger ? 'danger' : 'primary'}`, type: 'button',
          on: { click: () => { answer = true; s.close(); } } }, ok)));
  });
}

export function loading() {
  return h('div', { class: 'loading' }, h('div', { class: 'spinner', 'aria-label': 'Loading' }));
}

export function errorBox(err, retry) {
  return h('div', { class: 'empty' },
    h('h3', { text: 'Something went wrong' }),
    h('p', { text: (err && err.message) || 'Please try again.' }),
    retry ? h('button', { class: 'btn', type: 'button', on: { click: retry } }, 'Try again') : null);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // http:// on the LAN has no async clipboard: fall back to a selection copy
    const ta = h('textarea', { class: 'input' });
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    ta.remove();
    return ok;
  }
}

export function initials(name) {
  const parts = String(name || '?').trim().split(/\s+/).filter(Boolean);
  return ((parts[0] || '?')[0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

// A round picture, or initials on a colour picked from the name.
export function avatar(person, size = 40) {
  const el = person && person.avatar
    ? h('img', { class: 'av', src: person.avatar, alt: '', width: size, height: size, loading: 'lazy' })
    : h('span', { class: 'av av-i', text: initials(person ? person.name : '?'), 'aria-hidden': 'true' });
  if (!(person && person.avatar)) {
    let hash = 0;
    for (const ch of String(person ? person.username || person.name : '')) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    el.dataset.hue = String(hash % 6);
  }
  el.style.width = `${size}px`;
  el.style.height = `${size}px`;
  el.style.fontSize = `${Math.round(size * 0.38)}px`;
  return el;
}

// Shrink a picture in the browser before uploading (and strip its metadata,
// location included): a square-ish JPEG no bigger than `max` pixels.
export async function resizeImage(file, max = 512) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("That picture couldn't be read."));
      i.src = url;
    });
    const scale = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.86));
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function pickFile(accept) {
  return new Promise((resolve) => {
    const input = h('input', { type: 'file', accept });
    input.addEventListener('change', () => resolve(input.files && input.files[0]));
    input.click();
  });
}

export function autoGrow(ta) {
  const fit = () => { ta.style.height = 'auto'; ta.style.height = `${ta.scrollHeight + 2}px`; };
  ta.addEventListener('input', fit);
  requestAnimationFrame(fit);
  return fit;
}
